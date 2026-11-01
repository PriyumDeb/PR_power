import re
from pathlib import Path
from typing import Optional
from src.ast_verifier import ASTVerifier
from src.extractor import ClaimExtractor
from src.models import TechnicalClaim, TriageLabel, VerificationEvidence
from src.sandbox import SandboxRunner


def _sanitize_trace(raw_trace: str) -> str:
    """Strips absolute machine paths (macOS / Linux user dirs) to keep output clean and portable."""
    if not raw_trace:
        return ""
    # Strip temporary execution directory to <sandbox>/repro.py
    cleaned = re.sub(r'(/private)?/var/folders/[^\s"\':]+|/tmp/[^\s"\':]+', '<sandbox>/repro.py', raw_trace)
    # Strip user workspace path prefix so paths look clean and repository-relative with balanced quotes
    cleaned = re.sub(r'"(?:/Users|/home)/[^/\s]+/.*?/examples/([^"\':\s]+)"', r'"examples/\1"', cleaned)
    cleaned = re.sub(r'"(?:/Users|/home)/[^/\s]+/.*?/([^"\':\s]+\.py)"', r'"\1"', cleaned)
    cleaned = re.sub(r'(/Users|/home)/[^/\s]+', '<workspace>', cleaned)
    return cleaned


class EvidenceEvaluator:
    """Orchestrates static AST grounding and sandboxed execution to evaluate technical claims."""

    def __init__(self, repo_path: str | Path, ollama_url: str = "http://localhost:11434"):
        self.repo_path = Path(repo_path).resolve()
        self.extractor = ClaimExtractor(ollama_url=ollama_url)
        self.ast_verifier = ASTVerifier(self.repo_path)
        self.sandbox = SandboxRunner(self.repo_path)

    def evaluate_text(self, issue_or_pr_text: str) -> VerificationEvidence:
        """Extracts claims from text and performs end-to-end evidence evaluation."""
        claim = self.extractor.extract_claim(issue_or_pr_text)
        return self.evaluate_claim(claim, issue_or_pr_text=issue_or_pr_text)

    def evaluate_claim(self, claim: TechnicalClaim, issue_or_pr_text: Optional[str] = None) -> VerificationEvidence:
        """Evaluates an extracted technical claim against the codebase."""

        # Step 1: Static AST Verification
        symbol_exists, reason = self.ast_verifier.verify_symbol_existence(
            claim.target_file, claim.target_symbol
        )

        if not symbol_exists:
            # If target_file is missing completely, it is INVALID
            if claim.target_file and not self.ast_verifier.file_exists(claim.target_file):
                return VerificationEvidence(
                    label=TriageLabel.INVALID,
                    confidence_score=0.98,
                    summary=f"Claim is invalid: {reason}",
                    symbol_exists=False,
                    file_exists=False,
                    reasons_for_uncertainty=[]
                )
            
            # If target_file exists, but symbol was not found:
            # Check if this might be a PR-added symbol or newly proposed function
            text_context = f"{claim.claimed_behavior} {issue_or_pr_text or ''} {claim.reproduction_snippet or ''}".lower()
            is_pr_or_new = any(k in text_context for k in ["pr", "pull request", "patch", "diff", "+", "add", "new", "propose", "multiply"]) or \
                           (claim.reproduction_snippet and claim.target_symbol and f"def {claim.target_symbol}" in claim.reproduction_snippet)

            if is_pr_or_new:
                return VerificationEvidence(
                    label=TriageLabel.UNCERTAIN,
                    confidence_score=0.50,
                    summary=f"Symbol '{claim.target_symbol}' not present in existing codebase; may be newly introduced in a PR.",
                    symbol_exists=False,
                    file_exists=True,
                    reasons_for_uncertainty=[reason]
                )

            # If file exists and no PR context indicates a new function, it is INVALID
            return VerificationEvidence(
                label=TriageLabel.INVALID,
                confidence_score=0.95,
                summary=f"Claim is invalid: {reason}",
                symbol_exists=False,
                file_exists=True,
                reasons_for_uncertainty=[]
            )

        # Step 2: Check for external hardware / cloud dependencies
        if claim.external_dependencies:
            return VerificationEvidence(
                label=TriageLabel.UNCERTAIN,
                confidence_score=0.35,
                summary=f"Cannot safely verify offline: requires external infrastructure ({', '.join(claim.external_dependencies)}).",
                symbol_exists=True,
                reasons_for_uncertainty=[
                    f"External dependency requirement: {dep}" for dep in claim.external_dependencies
                ]
            )

        # Step 3: Dynamic Sandboxed Execution
        if not claim.reproduction_snippet:
            return VerificationEvidence(
                label=TriageLabel.UNCERTAIN,
                confidence_score=0.40,
                summary="Symbol exists in codebase, but no executable reproduction snippet was provided.",
                symbol_exists=True,
                reasons_for_uncertainty=["Missing reproduction snippet in report."]
            )

        # Execute snippet in isolated sandbox
        res = self.sandbox.execute_snippet(claim.reproduction_snippet)
        clean_stderr = _sanitize_trace(res.stderr)
        clean_stdout = _sanitize_trace(res.stdout)

        # Timeout handling
        if res.timed_out:
            return VerificationEvidence(
                label=TriageLabel.UNCERTAIN,
                confidence_score=0.50,
                summary=f"Execution timed out after {self.sandbox.timeout_seconds} seconds.",
                symbol_exists=True,
                exit_code=res.exit_code,
                stderr=clean_stderr,
                reasons_for_uncertainty=["Execution timed out; possible infinite loop or deadlock."]
            )

        # Sandbox policy violation returns UNCERTAIN (cannot safely verify offline)
        if res.security_violation or res.caught_exception == "SecurityPolicyViolation":
            violation_msg = res.security_violation or clean_stderr.strip()
            return VerificationEvidence(
                label=TriageLabel.UNCERTAIN,
                confidence_score=0.40,
                summary=f"Cannot safely verify offline: snippet requires restricted capabilities ({violation_msg}).",
                symbol_exists=True,
                stderr=clean_stderr,
                reasons_for_uncertainty=[f"Sandbox policy: {violation_msg}"]
            )

        # Step 4: Handle caught exceptions
        if res.caught_exception:
            # Harness setup / missing environment errors should be UNCERTAIN, NOT CONFIRMED
            harness_errors = {"ModuleNotFoundError", "ImportError", "NameError", "SyntaxError"}
            if res.caught_exception in harness_errors:
                return VerificationEvidence(
                    label=TriageLabel.UNCERTAIN,
                    confidence_score=0.45,
                    summary=f"Reproduction script failed with environment/harness error '{res.caught_exception}'.",
                    symbol_exists=True,
                    exit_code=res.exit_code,
                    caught_exception=res.caught_exception,
                    stdout=clean_stdout,
                    stderr=clean_stderr,
                    reasons_for_uncertainty=[f"Harness error: {res.caught_exception}"]
                )

            # AssertionError only confirms if expected_error was AssertionError
            if res.caught_exception == "AssertionError" and claim.expected_error != "AssertionError":
                return VerificationEvidence(
                    label=TriageLabel.UNCERTAIN,
                    confidence_score=0.50,
                    summary="Reproduction script raised AssertionError without confirming target exception.",
                    symbol_exists=True,
                    exit_code=res.exit_code,
                    caught_exception="AssertionError",
                    stdout=clean_stdout,
                    stderr=clean_stderr,
                    reasons_for_uncertainty=["Assertion in test script failed."]
                )

            # Check if caught exception matches expected exception
            matches_expected = False
            if claim.expected_error:
                exp_lower = claim.expected_error.lower()
                caught_lower = res.caught_exception.lower()
                if exp_lower in caught_lower or caught_lower in exp_lower:
                    matches_expected = True

            # Also check if claimed_behavior mentioned this exception
            if not matches_expected and res.caught_exception.lower() in claim.claimed_behavior.lower():
                matches_expected = True

            if matches_expected:
                return VerificationEvidence(
                    label=TriageLabel.CONFIRMED,
                    confidence_score=0.96,
                    summary=f"Bug reliably confirmed: caught claimed exception '{res.caught_exception}'.",
                    target_file=claim.target_file,
                    target_symbol=claim.target_symbol,
                    symbol_exists=True,
                    exit_code=res.exit_code,
                    caught_exception=res.caught_exception,
                    stdout=clean_stdout,
                    stderr=clean_stderr
                )
            elif claim.expected_error:
                # Caught an error, but does NOT match expected error
                return VerificationEvidence(
                    label=TriageLabel.UNCERTAIN,
                    confidence_score=0.55,
                    summary=f"Caught exception '{res.caught_exception}' does not match expected '{claim.expected_error}'.",
                    symbol_exists=True,
                    exit_code=res.exit_code,
                    caught_exception=res.caught_exception,
                    stdout=clean_stdout,
                    stderr=clean_stderr,
                    reasons_for_uncertainty=[f"Exception mismatch: caught {res.caught_exception}, expected {claim.expected_error}"]
                )
            else:
                # No expected_error specified: an unrelated exception (like TypeError or AttributeError)
                # cannot confirm the bug, as it may be an error in the reproduction snippet
                return VerificationEvidence(
                    label=TriageLabel.UNCERTAIN,
                    confidence_score=0.50,
                    summary=f"Reproduction raised unhandled exception '{res.caught_exception}', but no expected error was specified in claim to verify against.",
                    symbol_exists=True,
                    exit_code=res.exit_code,
                    caught_exception=res.caught_exception,
                    stdout=clean_stdout,
                    stderr=clean_stderr,
                    reasons_for_uncertainty=[f"No expected error specified in report to match against '{res.caught_exception}'."]
                )

        # If it executed with code 0 without raising an error
        if res.is_success:
            if claim.expected_error:
                return VerificationEvidence(
                    label=TriageLabel.CANNOT_REPRODUCE,
                    confidence_score=0.92,
                    summary=f"Cannot reproduce: snippet executed cleanly (exit 0) without raising claimed '{claim.expected_error}'.",
                    symbol_exists=True,
                    exit_code=0,
                    stdout=clean_stdout,
                    stderr=clean_stderr
                )
            # If no expected_error was specified, a clean run cannot prove or disprove the bug without an assertion
            has_assertion = bool(claim.reproduction_snippet and ("assert " in claim.reproduction_snippet or "self.assert" in claim.reproduction_snippet))
            if has_assertion:
                return VerificationEvidence(
                    label=TriageLabel.CANNOT_REPRODUCE,
                    confidence_score=0.88,
                    summary="Reproduction assertions passed with exit code 0; claimed bug did not occur.",
                    symbol_exists=True,
                    exit_code=0,
                    stdout=clean_stdout,
                    stderr=clean_stderr
                )
            return VerificationEvidence(
                label=TriageLabel.UNCERTAIN,
                confidence_score=0.50,
                summary="Snippet executed cleanly with exit code 0, but no expected error or assertion was provided to verify bug presence.",
                symbol_exists=True,
                exit_code=0,
                stdout=clean_stdout,
                stderr=clean_stderr,
                reasons_for_uncertainty=["No expected error or assertion provided to verify bug."]
            )

        return VerificationEvidence(
            label=TriageLabel.UNCERTAIN,
            confidence_score=0.45,
            summary=f"Execution exited with unexpected status code {res.exit_code}.",
            symbol_exists=True,
            exit_code=res.exit_code,
            stderr=clean_stderr,
            reasons_for_uncertainty=["Non-zero exit code without recognized Python exception."]
        )
