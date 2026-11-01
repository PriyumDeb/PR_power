from pathlib import Path
import json


def test_examples_directory_structure():
    """Validates that all mandatory example scenarios are present and non-empty."""
    examples_dir = Path("examples")
    assert examples_dir.exists() and examples_dir.is_dir()

    scenarios = [
        "01_confirmed_bug",
        "02_cannot_reproduce",
        "03_invalid_fabricated",
        "04_uncertain_external_dependency",
        "05_pull_request_regression_check"
    ]

    for scenario in scenarios:
        scen_path = examples_dir / scenario
        assert scen_path.exists() and scen_path.is_dir(), f"Missing scenario directory: {scenario}"

        # Must have an input and output
        files = list(scen_path.iterdir())
        assert len(files) >= 2, f"Scenario {scenario} must contain inputs and outputs"


def test_example_outputs_contain_expected_labels():
    """Validates that example outputs correspond to official problem statement labels."""
    ex1_md = Path("examples/01_confirmed_bug/actual_output.md").read_text()
    assert "`confirmed`" in ex1_md

    ex2_md = Path("examples/02_cannot_reproduce/actual_output.md").read_text()
    assert "`cannot reproduce`" in ex2_md

    ex3_md = Path("examples/03_invalid_fabricated/actual_output.md").read_text()
    assert "`invalid`" in ex3_md

    ex4_md = Path("examples/04_uncertain_external_dependency/actual_output.md").read_text()
    assert "`uncertain`" in ex4_md

    ex5_json = json.loads(Path("examples/05_pull_request_regression_check/actual_output.json").read_text())
    assert ex5_json["regression_risk"] is True
