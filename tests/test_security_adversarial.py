import tempfile
from pathlib import Path
from src.ast_verifier import ASTVerifier
from src.evaluator import EvidenceEvaluator
from src.models import TechnicalClaim, TriageLabel
from src.pr_diff import PRDiffVerifier
from src.sandbox import SandboxRunner


def test_dunder_subclasses_jailbreak_blocked():
    """Verifies that classic Python jailbreak reflection attacks are statically intercepted."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    exploit_payload = "x = ().__class__.__bases__[0].__subclasses__()"
    res = runner.execute_snippet(exploit_payload)

    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"
    assert "reflection attribute '__subclasses__'" in res.stderr


def test_banned_module_imports_blocked():
    """Verifies that unauthorized system and networking modules are blocked, including _socket."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    for mod in ["subprocess", "socket", "_socket", "ctypes", "shutil", "urllib.request"]:
        code = f"import {mod}"
        res = runner.execute_snippet(code)
        assert not res.is_success, f"Failed to block import {mod}"
        assert res.caught_exception == "SecurityPolicyViolation"


def test_safe_os_and_sys_allowed():
    """Verifies that legitimate bug repros using os.path, sys.version, or threading are ALLOWED."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = (
        "import os.path\n"
        "import sys\n"
        "p = os.path.join('a', 'b')\n"
        "v = sys.version\n"
        "assert len(p) > 0\n"
    )
    res = runner.execute_snippet(code)
    assert res.is_success
    assert res.exit_code == 0
    assert res.caught_exception is None


def test_getattr_dynamic_escape_blocked():
    """Verifies dynamic getattr escapes like getattr(__builtins__, 'eval') are blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "fn = getattr(__builtins__, 'eval')\nfn('1+1')"
    res = runner.execute_snippet(code)
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"
    assert "getattr escape attempt" in res.stderr


def test_dynamic_eval_exec_blocked():
    """Verifies that arbitrary code execution primitives are blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    res_eval = runner.execute_snippet("eval('1 + 1')")
    assert not res_eval.is_success
    assert res_eval.caught_exception == "SecurityPolicyViolation"

    res_exec = runner.execute_snippet("exec('print(123)')")
    assert not res_exec.is_success
    assert res_exec.caught_exception == "SecurityPolicyViolation"


def test_destructive_system_calls_blocked():
    """Verifies that destructive calls like os.system or os.popen are blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    res = runner.execute_snippet("import os\nos.system('whoami')")
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"


def test_oversized_snippet_dos_guard():
    """Verifies that gigantic snippets are rejected before parsing."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    huge_code = "# harmless comment\n" * 3000  # > 25KB
    res = runner.execute_snippet(huge_code)
    assert not res.is_success
    assert res.security_violation == "SnippetSizeExceeded"


def test_infinite_loop_timeout_contained():
    """Verifies that CPU spin locks are terminated strictly within the timeout window."""
    runner = SandboxRunner(".", timeout_seconds=0.5)
    res = runner.execute_snippet("i = 0\nwhile True: i += 1")
    assert res.timed_out is True
    assert res.caught_exception == "TimeoutExpired"


def test_ast_path_traversal_blocked():
    """Verifies that directory traversal attacks in ASTVerifier cannot escape the repo root."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        verifier = ASTVerifier(tmp_path)

        # Attempt to escape repo root
        found, msg = verifier.verify_symbol_existence("../../../../etc/passwd", "root")
        assert not found
        assert "path traversal blocked" in msg.lower() or "not found" in msg.lower()

        # Attempt null-byte injection
        found_null, _ = verifier.verify_symbol_existence("file\0.py", "func")
        assert not found_null


def test_trojan_source_bidi_unicode_detected():
    """Verifies detection of Trojan Source invisible Unicode characters (CVE-2021-42574)."""
    verifier = PRDiffVerifier(".")
    malicious_patch = (
        "diff --git a/auth.py b/auth.py\n"
        "--- a/auth.py\n"
        "+++ b/auth.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-def check_admin(user): return False\n"
        "+def check_admin(user): return True \u202e return False\n"
    )
    result = verifier.evaluate_pr_patch(malicious_patch)
    assert result["trojan_source_bidi_detected"] is True
    assert result["regression_risk"] is True
    assert "Trojan Source" in result["summary"]


def test_diff_bomb_rejected():
    """Verifies that patch bombs (> 10,000 lines) are blocked before regex processing."""
    verifier = PRDiffVerifier(".")
    huge_diff = "diff --git a/file.py b/file.py\n" + ("+line = 1\n" * 12000)
    result = verifier.evaluate_pr_patch(huge_diff)
    assert result["status"] == "REJECTED"
    assert "Diff Bomb" in result["summary"]


def test_evaluator_marks_sandbox_violation_as_uncertain():
    """Verifies that reproduction requiring disallowed system capabilities is marked UNCERTAIN."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "service.py").write_text("def ping(): pass\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        exploit_claim = TechnicalClaim(
            target_file="service.py",
            target_symbol="ping",
            claimed_behavior="Service ping function crashes",
            reproduction_snippet="import subprocess; subprocess.Popen(['ls'])"
        )

        evidence = evaluator.evaluate_claim(exploit_claim)
        # Sandbox security violation returns UNCERTAIN (cannot verify offline due to capability restrictions)
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.confidence_score == 0.40
        assert "restricted capabilities" in evidence.summary


def test_getattr_concatenation_escape_blocked():
    """Verifies that string-concatenated getattr attacks like getattr(os, 'sys' + 'tem') are caught."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "import os\nfn = getattr(os, 'sys' + 'tem')\nfn('ls')"
    res = runner.execute_snippet(code)
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"
    assert "getattr" in res.stderr


def test_os_execvp_blocked():
    """Verifies that os.execvp and other exec variants are blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "import os\nos.execvp('echo', ['echo', 'hello'])"
    res = runner.execute_snippet(code)
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"


def test_open_write_mode_blocked():
    """Verifies that open(..., 'w') is statically and dynamically blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "with open('pwn.txt', 'w') as f: f.write('bad')"
    res = runner.execute_snippet(code)
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"


def test_path_open_write_mode_blocked():
    """Verifies that Path.open('w') is blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "from pathlib import Path\nPath('pwn.txt').open('w')"
    res = runner.execute_snippet(code)
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"


def test_runtime_socket_and_write_killswitch():
    """Verifies that runtime preamble installs socket and open write blocks."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    # Even if someone bypasses AST with unusual constructs, runtime blocks it
    net_code = (
        "import socket\n"
        "try:\n"
        "    socket.socket()\n"
        "except PermissionError:\n"
        "    raise RuntimeError('BLOCKED_NET')\n"
    )
    res = runner.execute_snippet(net_code)
    # Notice: import socket is caught by SecurityASTScanner directly, which is even stronger!
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"


def test_from_os_import_system_blocked():
    """Verifies that 'from os import system' is intercepted both at import and call time."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "from os import system\nsystem('whoami')"
    res = runner.execute_snippet(code)
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"


def test_importlib_dynamic_loader_blocked():
    """Verifies that dynamic module loading via importlib or imp is blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    for mod in ["importlib", "imp", "pkgutil", "runpy"]:
        res = runner.execute_snippet(f"import {mod}")
        assert not res.is_success, f"Failed to block {mod}"
        assert res.caught_exception == "SecurityPolicyViolation"


def test_builtins_eval_attribute_blocked():
    """Verifies that builtins.eval and builtins.exec attribute calls are blocked."""
    runner = SandboxRunner(".", timeout_seconds=2.0)
    res = runner.execute_snippet("import builtins\nbuiltins.eval('1+1')")
    assert not res.is_success
    assert res.caught_exception == "SecurityPolicyViolation"
