import tempfile
from pathlib import Path
from src.evaluator import EvidenceEvaluator
from src.models import TriageLabel


def test_end_to_end_messy_issue_with_http_links():
    """Verifies that normal issues containing http:// links and 'API' do not trigger false uncertain."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calculator.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        messy_markdown = """
        ### Bug in `calculator.divide`: ZeroDivisionError observed!
        Referencing issue at http://github.com/myorg/myrepo/issues/42.
        The public REST API documentation at https://api.myrepo.org says division should handle zero.
        
        Reproduction code:
        ```python
        from calculator import divide
        divide(100, 0)
        ```
        """

        evidence = evaluator.evaluate_text(messy_markdown)
        # Should NOT be uncertain due to 'http' or 'api'
        assert evidence.label == TriageLabel.CONFIRMED
        assert evidence.caught_exception == "ZeroDivisionError"
        assert evidence.confidence_score >= 0.90


def test_end_to_end_messy_incomplete_snippet_syntax_error():
    """Verifies that broken user code with SyntaxError on an existing function returns UNCERTAIN, not confirmed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "calculator.py").write_text("def divide(a, b): return a / b\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        broken_markdown = """
        ### Crash in `calculator.divide`
        I tried running an incomplete snippet:
        ```python
        from calculator import divide
        divide(
        ```
        """
        evidence = evaluator.evaluate_text(broken_markdown)
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.symbol_exists is True


def test_end_to_end_messy_dotted_symbol_and_constant():
    """Verifies that dotted symbols and constants work end-to-end through raw markdown."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "config.py").write_text("DEFAULT_TIMEOUT: int = 30\n", encoding="utf-8")

        evaluator = EvidenceEvaluator(repo_path=tmp_path)
        text = "Check the constant `DEFAULT_TIMEOUT` in `config.py`."

        evidence = evaluator.evaluate_text(text)
        # Symbol exists, but no snippet was provided -> UNCERTAIN with symbol_exists=True
        assert evidence.label == TriageLabel.UNCERTAIN
        assert evidence.symbol_exists is True
        assert "snippet" in evidence.summary.lower()
