import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Unicode Bidirectional Override characters used in Trojan Source attacks (CVE-2021-42574)
BIDI_CHARS = [
    "\u202A",  # Left-to-Right Embedding (LRE)
    "\u202B",  # Right-to-Left Embedding (RLE)
    "\u202C",  # Pop Directional Formatting (PDF)
    "\u202D",  # Left-to-Right Override (LRO)
    "\u202E",  # Right-to-Left Override (RLO)
    "\u2066",  # Left-to-Right Isolate (LRI)
    "\u2067",  # Right-to-Left Isolate (RLI)
    "\u2068",  # First Strong Isolate (FSI)
    "\u2069",  # Pop Directional Isolate (PDI)
]


class PRDiffVerifier:
    """Performs differential regression verification and security scanning on PR patches."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

    def run_repo_tests(self) -> Tuple[bool, str]:
        """Runs the repository test suite via pytest and returns (passed, output)."""
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=15
            )
            return (res.returncode == 0, res.stdout + res.stderr)
        except Exception as e:
            return (False, f"Test execution failed: {str(e)}")

    def evaluate_pr_patch(self, patch_content: str, run_tests: bool = False) -> Dict[str, object]:
        """
        Evaluates a PR patch for security, supply-chain risks, and test regression:
        1. Guards against Diff-Bombs (> 10,000 lines).
        2. Detects Trojan Source (BiDi Unicode injection, CVE-2021-42574).
        3. Scans for removed test assertions and newly introduced dangerous primitives.
        4. Optionally runs repository test suite to catch regressions.
        """
        # Guard 1: Diff size limit
        lines = patch_content.splitlines()
        if len(lines) > 10000:
            return {
                "regression_risk": True,
                "status": "REJECTED",
                "summary": "Diff Bomb rejected: Patch exceeds maximum allowed limit (10,000 lines).",
                "total_lines": len(lines)
            }

        # Guard 2: Trojan Source (Invisible Unicode BiDi characters)
        bidi_detected = any(any(ch in line for ch in BIDI_CHARS) for line in lines)

        added_lines = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
        removed_lines = [l for l in lines if l.startswith("-") and not l.startswith("---")]

        # Check if tests or assertions were deleted
        deleted_tests = [
            l for l in removed_lines
            if "def test_" in l or "assert " in l or "self.assert" in l
        ]

        # Check for dangerous system calls / backdoors introduced in added lines
        # Distinguish dangerous shell injection (shell=True, os.system) from legitimate subprocess use
        risky_calls = []
        dangerous_patterns = [
            "os.system", "os.popen", "eval(", "exec(", "shutil.rmtree",
            "pickle.loads", "ctypes.", "__import__"
        ]
        for l in added_lines:
            for pat in dangerous_patterns:
                if pat in l:
                    risky_calls.append(pat)
            if "subprocess." in l and "shell=True" in l:
                risky_calls.append("subprocess(shell=True)")

        has_regression_risk = len(deleted_tests) > 0 or len(risky_calls) > 0 or bidi_detected

        warnings: List[str] = []
        if bidi_detected:
            warnings.append("CRITICAL: Trojan Source invisible Unicode characters detected (CVE-2021-42574).")
        if deleted_tests:
            warnings.append(f"PR deletes {len(deleted_tests)} test assertions.")
        if risky_calls:
            warnings.append(f"PR introduces {len(set(risky_calls))} sensitive primitives ({', '.join(set(risky_calls))}).")

        test_result = None
        if run_tests and (self.repo_path / "tests").exists():
            tests_passed, test_out = self.run_repo_tests()
            test_result = {
                "passed": tests_passed,
                "summary": "Repository test suite passed." if tests_passed else "Repository test suite failed."
            }
            if not tests_passed:
                has_regression_risk = True
                warnings.append("Repository test suite failed.")

        res: Dict[str, object] = {
            "total_added": len(added_lines),
            "total_removed": len(removed_lines),
            "deleted_test_assertions": len(deleted_tests),
            "risky_patterns_introduced": list(set(risky_calls)),
            "trojan_source_bidi_detected": bidi_detected,
            "regression_risk": has_regression_risk,
            "status": "PASS" if not has_regression_risk else "REVIEW_REQUIRED",
            "summary": "No regressions, deleted assertions, or security hazards detected." if not has_regression_risk
                       else "Caution: " + " ".join(warnings)
        }
        if test_result:
            res["test_suite"] = test_result

        return res
