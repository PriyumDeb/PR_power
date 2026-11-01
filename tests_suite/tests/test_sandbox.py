from src.sandbox import SandboxRunner


def test_sandbox_catches_zero_division():
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "x = 10 / 0"
    res = runner.execute_snippet(code)

    assert res.is_success is False
    assert res.exit_code != 0
    assert res.caught_exception == "ZeroDivisionError"
    assert "ZeroDivisionError" in res.stderr


def test_sandbox_success_clean_exit():
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "x = 10 + 20\nassert x == 30"
    res = runner.execute_snippet(code)

    assert res.is_success is True
    assert res.exit_code == 0
    assert res.caught_exception is None


def test_sandbox_timeout_handling():
    runner = SandboxRunner(".", timeout_seconds=0.5)
    code = "import time\ntime.sleep(2.0)"
    res = runner.execute_snippet(code)

    assert res.timed_out is True
    assert res.caught_exception == "TimeoutExpired"


def test_sandbox_security_rejection():
    runner = SandboxRunner(".", timeout_seconds=2.0)
    code = "import os\nos.system('echo dangerous')"
    res = runner.execute_snippet(code)

    assert res.caught_exception == "SecurityPolicyViolation"
