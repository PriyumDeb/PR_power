import tempfile
from pathlib import Path
from src.ast_verifier import ASTVerifier


def test_ast_verifier_finds_symbols():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        math_file = tmp_path / "math_utils.py"
        math_file.write_text(
            "DEFAULT_TAX: float = 0.1\n"
            "MAX_LIMIT = 1000\n\n"
            "def calculate_total(price, tax=0.1):\n"
            "    return price * (1 + tax)\n\n"
            "class Invoice:\n"
            "    def generate(self):\n"
            "        pass\n",
            encoding="utf-8"
        )

        verifier = ASTVerifier(tmp_path)

        # File exists
        assert verifier.file_exists("math_utils.py") is True
        assert verifier.file_exists("non_existent.py") is False

        # Functions & Methods
        found, _ = verifier.verify_symbol_existence("math_utils.py", "calculate_total")
        assert found is True

        found_class, _ = verifier.verify_symbol_existence("math_utils.py", "Invoice")
        assert found_class is True

        found_method, _ = verifier.verify_symbol_existence("math_utils.py", "Invoice.generate")
        assert found_method is True

        # Constants & Module-level assignments
        found_const, _ = verifier.verify_symbol_existence("math_utils.py", "DEFAULT_TAX")
        assert found_const is True

        found_limit, _ = verifier.verify_symbol_existence("math_utils.py", "MAX_LIMIT")
        assert found_limit is True

        # Dotted symbol matching: "math_utils.calculate_total"
        found_dotted, _ = verifier.verify_symbol_existence("math_utils.py", "math_utils.calculate_total")
        assert found_dotted is True

        # Non-existent symbol
        not_found, msg = verifier.verify_symbol_existence("math_utils.py", "ghost_function")
        assert not_found is False
        assert "not found" in msg.lower()


def test_ast_verifier_global_search():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "service.py").write_text("def run_job(): pass\n", encoding="utf-8")

        verifier = ASTVerifier(tmp_path)
        found, _ = verifier.verify_symbol_existence(None, "run_job")
        assert found is True

        not_found, _ = verifier.verify_symbol_existence(None, "non_existent_fn")
        assert not_found is False
