# ClaimCheck Examples & Evaluation Benchmark Scenarios

This directory contains representative evaluation scenarios demonstrating the end-to-end capabilities of **PR_checker (ClaimCheck)** across all official problem statement labels:

| Directory | Evaluation Scenario | Input File | Output File | Official Label | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`01_confirmed_bug`** | Genuine bug report with reproduction code | `input_issue.md` | `actual_output.md` | `confirmed` | **90.0%** |
| **`02_cannot_reproduce`** | Non-reproducible / false positive report | `input_issue.md` | `actual_output.md` | `cannot reproduce` | **85.0%** |
| **`03_invalid_fabricated`** | AI-hallucinated symbol or non-existent file | `input_issue.md` | `actual_output.md` | `invalid` | **95.0%** |
| **`04_uncertain_external_dependency`** | Network or cloud-dependent issue | `input_issue.md` | `actual_output.md` | `uncertain` | **35.0%** |
| **`05_pull_request_regression_check`** | PR patch introducing security risks & deleting tests | `input_patch.diff` | `actual_output.json` | `REVIEW_REQUIRED` | **Regression Risk** |

---

## How to Re-Run All Examples
To execute the triage pipeline across these scenarios locally:

```bash
# 1. Confirmed Bug
python -m src.cli triage --file examples/01_confirmed_bug/input_issue.md --repo examples/01_confirmed_bug

# 2. Cannot Reproduce
python -m src.cli triage --file examples/02_cannot_reproduce/input_issue.md --repo examples/02_cannot_reproduce

# 3. Invalid Fabricated
python -m src.cli triage --file examples/03_invalid_fabricated/input_issue.md --repo examples/03_invalid_fabricated

# 4. Uncertain External Dependency
python -m src.cli triage --file examples/04_uncertain_external_dependency/input_issue.md --repo examples/04_uncertain_external_dependency

# 5. PR Regression Check
python -m src.cli check-pr --patch examples/05_pull_request_regression_check/input_patch.diff
```
