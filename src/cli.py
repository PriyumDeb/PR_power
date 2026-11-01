import argparse
import json
import sys
from pathlib import Path
from src.evaluator import EvidenceEvaluator
from src.pr_diff import PRDiffVerifier


def format_markdown_dossier(evidence) -> str:
    """Formats verification evidence into a GitHub-compatible markdown comment."""
    status_emoji = {
        "confirmed": "🔴 [CONFIRMED BUG]",
        "cannot reproduce": "🟢 [CANNOT REPRODUCE]",
        "invalid": "⚪ [INVALID / FABRICATED]",
        "uncertain": "🟡 [UNCERTAIN / EXTERNAL DEPS]"
    }.get(evidence.label.value, "❓ [TRIAGE RESULT]")

    report = [
        f"### {status_emoji} - ClaimCheck Triage Report",
        f"**Official Triage Label**: `{evidence.label.value}`  ",
        f"**Confidence Score**: `{evidence.confidence_score * 100:.1f}%`  ",
        "",
        "#### Summary of Evidence",
        f"> {evidence.summary}",
        ""
    ]

    if evidence.target_file:
        gh_url = f"https://github.com/PriyumDeb/PR_power/blob/main/{evidence.target_file}"
        report.append(f"**Repository File**: [`{evidence.target_file}`]({gh_url})\n")

    if evidence.caught_exception:
        report.append(f"**Observed Exception**: `{evidence.caught_exception}`")

    if evidence.stderr:
        report.append("<details><summary><b>Execution Trace / Stderr</b></summary>\n")
        report.append(f"```text\n{evidence.stderr.strip()}\n```\n</details>\n")

    if evidence.reasons_for_uncertainty:
        report.append("#### Reasons for Uncertainty")
        for r in evidence.reasons_for_uncertainty:
            report.append(f"- {r}")
        report.append("")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="PR_checker: Evidence-Based Issue and PR Triage")
    subparsers = parser.add_subparsers(dest="command")

    # Command: triage
    triage_parser = subparsers.add_parser("triage", help="Triage an incoming issue or PR claim")
    triage_parser.add_argument("--repo", default=".", help="Path to repository root")
    triage_parser.add_argument("--text", help="Raw issue/PR text to evaluate")
    triage_parser.add_argument("--file", help="Path to file containing issue/PR text")
    triage_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")

    # Command: check-pr
    pr_parser = subparsers.add_parser("check-pr", help="Evaluate a PR patch for regressions")
    pr_parser.add_argument("--repo", default=".", help="Path to repository root")
    pr_parser.add_argument("--patch", required=True, help="Path to patch/diff file")
    pr_parser.add_argument("--run-tests", action="store_true", help="Run repository pytest suite")

    args = parser.parse_args()

    if args.command == "triage":
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
        elif args.text:
            text = args.text
        else:
            print("Error: Must provide either --text or --file.", file=sys.stderr)
            sys.exit(1)

        evaluator = EvidenceEvaluator(repo_path=args.repo)
        evidence = evaluator.evaluate_text(text)

        if args.format == "json":
            print(evidence.model_dump_json(indent=2))
        else:
            print(format_markdown_dossier(evidence))

    elif args.command == "check-pr":
        patch_text = Path(args.patch).read_text(encoding="utf-8")
        verifier = PRDiffVerifier(repo_path=args.repo)
        result = verifier.evaluate_pr_patch(patch_text, run_tests=args.run_tests)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
