import tempfile
from pathlib import Path
from src.evaluator import EvidenceEvaluator
from src.models import TechnicalClaim, TriageLabel


def test_evaluator_confirmed_bug():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="divide",
            claimed_behavior="Crashes with ZeroDivisionError when denominator is zero",
            reproduction_snippet="from calc import divide\ndivide(10, 0)",
            expected_error="ZeroDivisionError"
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.CONFIRMED
        assert evidence.caught_exception == "ZeroDivisionError"
        assert evidence.confidence_score >= 0.90


def test_evaluator_cannot_reproduce():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def safe_divide(a, b): return a / b if b != 0 else 0\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="safe_divide",
            claimed_behavior="Claims safe_divide crashes on zero",
            reproduction_snippet="from calc import safe_divide\nres = safe_divide(10, 0)\nassert res == 0",
            expected_error="ZeroDivisionError"
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.CANNOT_REPRODUCE
        assert evidence.confidence_score >= 0.85


def test_evaluator_invalid_symbol():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="hallucinated_function_name",
            claimed_behavior="Made up bug report",
            reproduction_snippet="import calc; calc.hallucinated_function_name()"
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.INVALID
        assert evidence.confidence_score >= 0.95


def test_evaluator_uncertain_external_deps():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "client.py").write_text("def fetch_data(): pass\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="client.py",
            target_symbol="fetch_data",
            claimed_behavior="AWS S3 bucket connection fails",
            external_dependencies=["aws", "s3"]
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.confidence_score < 0.50
        assert len(evidence.reasons_for_uncertainty) > 0


def test_evaluator_harness_error_returns_uncertain():
    """Harness/missing package errors like ModuleNotFoundError must NOT be marked confirmed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="divide",
            claimed_behavior="Crashes with missing module",
            reproduction_snippet="import non_existent_library_xyz\nnon_existent_library_xyz.run()",
            expected_error="ZeroDivisionError"
        )

        evidence = evaluator.evaluate_claim(claim)
        # Must be UNCERTAIN, NOT confirmed!
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.caught_exception == "ModuleNotFoundError"


def test_evaluator_exception_mismatch_returns_uncertain():
    """If reproduction raises a different exception than claimed, mark as UNCERTAIN."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a[0] / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="divide",
            claimed_behavior="Crashes with ZeroDivisionError",
            reproduction_snippet="from calc import divide\ndivide([], 0)",
            expected_error="ZeroDivisionError"
        )

        evidence = evaluator.evaluate_claim(claim)
        # Throws IndexError, which does not match ZeroDivisionError -> UNCERTAIN
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.caught_exception == "IndexError"


def test_evaluator_unspecified_expected_error_runtime_exception_returns_uncertain():
    """If no expected_error is specified, an unhandled TypeError/AttributeError returns UNCERTAIN, not confirmed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="divide",
            claimed_behavior="Calculation behaves strangely",
            reproduction_snippet="from calc import divide\ndivide('string', 5)",
            expected_error=None  # No expected error specified
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.caught_exception == "TypeError"


def test_evaluator_unspecified_expected_error_clean_run_returns_uncertain():
    """If no expected_error and no assertion, a clean exit code 0 returns UNCERTAIN, not cannot_reproduce."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="divide",
            claimed_behavior="Calculation issue without specifics",
            reproduction_snippet="from calc import divide\ndivide(10, 2)",
            expected_error=None  # No expected error, no assert statement
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.UNCERTAIN


def test_evaluator_pr_added_symbol_returns_uncertain():
    """If a symbol is newly added in a PR or unmerged patch, return UNCERTAIN, not invalid."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calc.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        claim = TechnicalClaim(
            target_file="calc.py",
            target_symbol="multiply",
            claimed_behavior="PR #42 adds multiply to calc.py, but encounters edge case",
            reproduction_snippet="from calc import multiply\nmultiply(2, 3)"
        )

        evidence = evaluator.evaluate_claim(claim)
        assert evidence.label == TriageLabel.UNCERTAIN
        assert "newly introduced in a PR" in evidence.summary
