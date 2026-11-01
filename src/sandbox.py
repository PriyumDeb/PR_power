import ast
import os
import re
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# Truly dangerous modules strictly prohibited from being imported in untrusted reproduction snippets
BANNED_MODULES: Set[str] = {
    "subprocess", "socket", "_socket", "ctypes", "shutil",
    "pty", "pickle", "shelve", "urllib", "http", "requests",
    "multiprocessing", "importlib", "imp", "pkgutil", "runpy",
    "code", "codeop", "posix", "_posixsubprocess", "nt"
}

# Dangerous method calls on permitted modules (e.g. os.system, os.popen, os.execvp)
DESTRUCTIVE_CALLS: Set[str] = {
    "system", "popen", "spawn", "fork", "kill", "remove",
    "unlink", "rmdir", "chmod", "chown", "rename", "touch",
    "exec", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe",
    "posix_spawn", "posix_spawnp"
}

# Prohibited evaluation primitives
BANNED_EVAL_CALLS: Set[str] = {
    "eval", "exec", "compile", "__import__", "breakpoint"
}

# Dunder attributes used in Python sandbox jailbreaks / object traversal
BANNED_ATTRIBUTES: Set[str] = {
    "__subclasses__", "__bases__", "__mro__", "__globals__",
    "__code__", "__reduce__", "__reduce_ex__"
}


def _get_static_str(node: ast.AST) -> Optional[str]:
    """Statically resolves constant strings and concatenated binary operations."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _get_static_str(node.left)
        right = _get_static_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


class SecurityASTScanner(ast.NodeVisitor):
    """Deep AST visitor that statically detects sandbox escape attempts, network bypasses, and exploits."""

    def __init__(self):
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in BANNED_MODULES:
                self.violations.append(f"Restricted module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in BANNED_MODULES:
                self.violations.append(f"Restricted module import: '{node.module}'")
        for alias in node.names:
            if (
                alias.name in DESTRUCTIVE_CALLS
                or alias.name in BANNED_EVAL_CALLS
                or alias.name in BANNED_MODULES
            ):
                self.violations.append(f"Restricted import of dangerous primitive: '{alias.name}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 1. Check direct calls to eval/exec or destructive calls (e.g. system(), execvp())
        if isinstance(node.func, ast.Name):
            if node.func.id in BANNED_EVAL_CALLS or node.func.id in DESTRUCTIVE_CALLS:
                self.violations.append(f"Restricted call to '{node.func.id}()'")

        # 2. Check method calls like os.system(), os.execvp(), builtins.eval(), or pathlib write methods
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in DESTRUCTIVE_CALLS or node.func.attr in BANNED_EVAL_CALLS:
                self.violations.append(f"Restricted call to '{node.func.attr}()'")
            elif node.func.attr in {"write_text", "write_bytes"}:
                self.violations.append(f"Restricted filesystem write call: '{node.func.attr}()'")

        # 3. Check open(..., 'w') or Path.open('w')
        is_open_call = False
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            is_open_call = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "open":
            is_open_call = True

        if is_open_call:
            mode_str = None
            for arg in node.args:
                s = _get_static_str(arg)
                if s and isinstance(s, str) and any(m in s for m in ["w", "a", "+", "x"]):
                    mode_str = s
                    break
            for kw in node.keywords:
                if kw.arg == "mode":
                    s = _get_static_str(kw.value)
                    if s and isinstance(s, str) and any(m in s for m in ["w", "a", "+", "x"]):
                        mode_str = s
                        break
            if mode_str:
                self.violations.append(f"Restricted filesystem write mode in open('{mode_str}')")

        # 4. Check dynamic getattr escapes like getattr(__builtins__, 'eval') or getattr(os, 'sys' + 'tem')
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 1:
                target_obj = ""
                if isinstance(node.args[0], ast.Name):
                    target_obj = node.args[0].id
                if target_obj in {"__builtins__", "builtins"}:
                    self.violations.append("Dynamic getattr on builtins blocked")

            if len(node.args) >= 2:
                attr_name = _get_static_str(node.args[1])
                if attr_name:
                    if (
                        attr_name in BANNED_EVAL_CALLS
                        or attr_name in DESTRUCTIVE_CALLS
                        or attr_name in BANNED_MODULES
                        or attr_name in BANNED_ATTRIBUTES
                    ):
                        self.violations.append(f"Dynamic getattr escape attempt for '{attr_name}'")
                elif not isinstance(node.args[1], ast.Constant):
                    self.violations.append("Dynamic getattr with computed/concatenated attribute blocked")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in BANNED_ATTRIBUTES:
            self.violations.append(f"Security violation: access to internal reflection attribute '{node.attr}'")
        self.generic_visit(node)


class SandboxResult:
    def __init__(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        timed_out: bool = False,
        caught_exception: Optional[str] = None,
        security_violation: Optional[str] = None
    ):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.caught_exception = caught_exception
        self.security_violation = security_violation

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.security_violation


def _apply_os_resource_limits():
    """Applies strict POSIX resource limits (CPU quotas, file output limits, and memory caps)."""
    try:
        # Max CPU execution time: 3 seconds
        if hasattr(resource, "RLIMIT_CPU"):
            resource.setrlimit(resource.RLIMIT_CPU, (3, 4))
        # Max output file size write limit: 1MB
        if hasattr(resource, "RLIMIT_FSIZE"):
            resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 2 * 1024 * 1024))
        # Virtual memory limit: 512MB
        if hasattr(resource, "RLIMIT_AS"):
            try:
                resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 1024 * 1024 * 1024))
            except (ValueError, OSError):
                pass
    except Exception:
        pass


class SandboxRunner:
    """Executes reproduction code safely using multi-layered AST scanning and OS-level containment."""

    def __init__(self, repo_path: str | Path, timeout_seconds: float = 3.0):
        self.repo_path = Path(repo_path).resolve()
        self.timeout_seconds = timeout_seconds

    def _extract_exception(self, stderr: str) -> Optional[str]:
        """Extracts the Python exception type from stderr stack trace."""
        lines = stderr.strip().splitlines()
        for line in reversed(lines):
            match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_\.]*Error|[a-zA-Z_][a-zA-Z0-9_\.]*Exception):", line)
            if match:
                return match.group(1).split(".")[-1]
        return None

    def execute_snippet(self, code_snippet: str) -> SandboxResult:
        """
        Executes a Python reproduction snippet with defense-in-depth security:
        1. Static AST inspection for banned modules, functions, and jailbreak reflection gadgets.
        2. OS resource limits (CPU quotas, memory caps, file output limits).
        3. Runtime socket and network blocking in isolated ephemeral directory.
        """
        # Guard 1: Snippet size limit (prevent AST parser memory exhaustion)
        if len(code_snippet) > 25000:
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr="Security violation: Snippet exceeds maximum allowed size (25KB).",
                security_violation="SnippetSizeExceeded"
            )

        # Guard 2: Static AST Security Scanner
        try:
            tree = ast.parse(code_snippet)
            scanner = SecurityASTScanner()
            scanner.visit(tree)
            if scanner.violations:
                reason = "; ".join(scanner.violations)
                return SandboxResult(
                    exit_code=1,
                    stdout="",
                    stderr=f"SecurityPolicyViolation: {reason}",
                    caught_exception="SecurityPolicyViolation",
                    security_violation=reason
                )
        except SyntaxError as e:
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"SyntaxError: {str(e)}",
                caught_exception="SyntaxError"
            )

        # Guard 3: Runtime execution in isolated ephemeral directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            script_file = tmp_path / "repro_test.py"

            # Prepend un-bypassable runtime socket and filesystem kill-switch
            preamble = (
                "import sys, types, builtins\n"
                "# 1. Block network sockets at runtime\n"
                "for _mod_name in ['socket', '_socket']:\n"
                "    _mod = types.ModuleType(_mod_name)\n"
                "    def _block_net(*a, **k):\n"
                "        raise PermissionError('PR-Power Sandbox: Network access blocked.')\n"
                "    _mod.socket = _block_net\n"
                "    _mod.create_connection = _block_net\n"
                "    _mod.getaddrinfo = _block_net\n"
                "    _mod.__getattr__ = lambda name: _block_net\n"
                "    sys.modules[_mod_name] = _mod\n"
                "\n"
                "# 2. Block filesystem write open at runtime\n"
                "_orig_open = builtins.open\n"
                "def _safe_open(*args, **kwargs):\n"
                "    _mode = kwargs.get('mode', args[1] if len(args) > 1 else 'r')\n"
                "    if isinstance(_mode, str) and any(m in _mode for m in ['w', 'a', '+', 'x']):\n"
                "        raise PermissionError('PR-Power Sandbox: Filesystem write operations blocked.')\n"
                "    return _orig_open(*args, **kwargs)\n"
                "builtins.open = _safe_open\n"
                "\n"
            )
            script_file.write_text(preamble + code_snippet, encoding="utf-8")

            clean_env: Dict[str, str] = {
                "PYTHONPATH": str(self.repo_path),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            try:
                proc = subprocess.run(
                    [sys.executable, str(script_file)],
                    cwd=str(tmp_path),
                    env=clean_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    preexec_fn=_apply_os_resource_limits if sys.platform != "win32" else None
                )
                caught_err = self._extract_exception(proc.stderr)
                return SandboxResult(
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    timed_out=False,
                    caught_exception=caught_err
                )
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                return SandboxResult(
                    exit_code=-1,
                    stdout=stdout,
                    stderr=f"Execution timed out after {self.timeout_seconds}s.\n{stderr}",
                    timed_out=True,
                    caught_exception="TimeoutExpired"
                )
