from src.extractor import ClaimExtractor


def test_extractor_skips_exception_names_as_symbols():
    extractor = ClaimExtractor()
    issue_text = """
    ### Bug Report: ZeroDivisionError in `calculator.divide`
    Calling `divide` with 0 causes `ZeroDivisionError`.
    ```python
    from calculator import divide
    divide(10, 0)
    ```
    """
    claim = extractor._fallback_heuristic_extraction(issue_text)

    # Must NOT pick ZeroDivisionError as the symbol
    assert claim.target_symbol != "ZeroDivisionError"
    # Should pick calculator.divide or divide
    assert claim.target_symbol in {"calculator.divide", "divide"}
    assert claim.expected_error == "ZeroDivisionError"
    assert claim.target_file in {"calculator.py", "calculator"}


def test_extractor_does_not_flag_generic_api_as_external_infra():
    extractor = ClaimExtractor()
    issue_text = """
    ### Restructure public API in `client.py`
    The http client method `fetch_record` needs refactoring.
    """
    claim = extractor._fallback_heuristic_extraction(issue_text)

    # "api" and "http" must NOT trigger external cloud dependencies
    assert "api" not in claim.external_dependencies
    assert "http" not in claim.external_dependencies
    assert len(claim.external_dependencies) == 0


def test_extractor_flags_real_cloud_infra():
    extractor = ClaimExtractor()
    issue_text = """
    ### S3 upload failure
    Cannot connect to AWS S3 bucket in `storage.py`.
    """
    claim = extractor._fallback_heuristic_extraction(issue_text)
    assert any(dep in ["aws", "s3"] for dep in claim.external_dependencies)


def test_extractor_handles_constants():
    extractor = ClaimExtractor()
    issue_text = """
    ### Issue with `DEFAULT_TIMEOUT` in `config.py`
    The default value is too low.
    """
    claim = extractor._fallback_heuristic_extraction(issue_text)
    assert claim.target_symbol == "DEFAULT_TIMEOUT"
    assert claim.target_file == "config.py"
