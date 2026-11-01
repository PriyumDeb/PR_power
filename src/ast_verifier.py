import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class ASTVerifier:
    """Statically verifies claims against Python source code files and ASTs with path traversal protections."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()

    def _safe_resolve_path(self, relative_path: str) -> Optional[Path]:
        """
        Safely resolves a relative path within repo_root, strictly preventing
        directory traversal (e.g. '../../etc/passwd') and null-byte injection.
        """
        if not relative_path or "\0" in relative_path:
            return None

        try:
            target = (self.repo_root / relative_path).resolve()
            if target == self.repo_root or self.repo_root in target.parents:
                return target
            return None
        except Exception:
            return None

    def file_exists(self, relative_path: str) -> bool:
        """Checks if the referenced file exists safely in the repository."""
        target = self._safe_resolve_path(relative_path)
        return target is not None and target.exists()

    def get_symbols_in_file(self, relative_path: str) -> Tuple[Set[str], Dict[str, List[str]]]:
        """
        Parses a Python file and returns:
        - A set of all symbol names (functions, classes, methods, constants, module-level assignments).
        - A dict mapping function/method names to argument lists.
        """
        target = self._safe_resolve_path(relative_path)
        if target is None or not target.is_file() or target.suffix != ".py":
            return set(), {}

        # Guard: File size limit to prevent AST DoS (max 3MB)
        try:
            if target.stat().st_size > 3 * 1024 * 1024:
                return set(), {}
            content = target.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(target))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return set(), {}

        symbols: Set[str] = set()
        signatures: Dict[str, List[str]] = {}

        for node in ast.walk(tree):
            # 1. Functions & Async Functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.add(node.name)
                args = [arg.arg for arg in node.args.args]
                signatures[node.name] = args

            # 2. Classes & Methods
            elif isinstance(node, ast.ClassDef):
                symbols.add(node.name)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_name = f"{node.name}.{item.name}"
                        symbols.add(method_name)
                        symbols.add(item.name)
                        args = [arg.arg for arg in item.args.args]
                        signatures[method_name] = args

            # 3. Module-level Constants & Variable Assignments (e.g. DEFAULT_TIMEOUT = 30)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        symbols.add(tgt.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    symbols.add(node.target.id)

        return symbols, signatures

    def verify_symbol_existence(
        self, relative_path: Optional[str], symbol_name: Optional[str]
    ) -> Tuple[bool, str]:
        """
        Validates whether the claimed symbol exists in the given file or codebase.
        Supports dotted names (e.g. calculator.divide -> matches divide in calculator.py).
        """
        if not symbol_name and not relative_path:
            return True, "No specific file or symbol claimed."

        # If a dotted symbol is provided without file (e.g. calculator.divide)
        if symbol_name and "." in symbol_name and not relative_path:
            parts = symbol_name.split(".")
            candidate_file = f"{parts[0]}.py"
            if self.file_exists(candidate_file):
                relative_path = candidate_file

        # Candidate names for matching (e.g. for "calculator.divide", match both "calculator.divide" and "divide")
        candidate_names = {symbol_name} if symbol_name else set()
        if symbol_name and "." in symbol_name:
            candidate_names.add(symbol_name.split(".")[-1])

        if relative_path:
            target = self._safe_resolve_path(relative_path)
            if target is None:
                return False, f"Invalid or unsafe file path '{relative_path}' (path traversal blocked)."

            if not target.exists():
                return False, f"Referenced file '{relative_path}' does not exist in repository."

            if symbol_name:
                symbols, _ = self.get_symbols_in_file(relative_path)
                # Match full symbol or trailing name
                matched = any(c in symbols for c in candidate_names)
                if not matched:
                    return False, f"Symbol '{symbol_name}' not found in '{relative_path}'."
                return True, f"Found symbol '{symbol_name}' in '{relative_path}'."
            return True, f"File '{relative_path}' verified in repository."

        # Global search across repository
        if symbol_name:
            for py_file in self.repo_root.rglob("*.py"):
                if ".git" in py_file.parts or "venv" in py_file.parts or ".venv" in py_file.parts:
                    continue
                try:
                    rel_path = str(py_file.relative_to(self.repo_root))
                    symbols, _ = self.get_symbols_in_file(rel_path)
                    if any(c in symbols for c in candidate_names):
                        return True, f"Found symbol '{symbol_name}' in '{rel_path}'."
                except Exception:
                    continue
            return False, f"Symbol '{symbol_name}' was not found anywhere in the repository."

        return True, "Verification successful."
