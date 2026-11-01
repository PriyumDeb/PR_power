import json
import re
import textwrap
from typing import List, Optional
import requests
from src.models import TechnicalClaim


class ClaimExtractor:
    """Extracts atomic technical claims from issues and PRs using local Gemma 4 or robust heuristic fallback."""

    def __init__(self, ollama_url: str = "http://localhost:11434", model_name: str = "gemma4:latest"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model_name = model_name

    def _call_ollama(self, prompt: str) -> Optional[dict]:
        """Calls the local Ollama API to run Gemma 4."""
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                    }
                },
                timeout=12
            )
            if resp.status_code == 200:
                raw_json = resp.json().get("response", "")
                return json.loads(raw_json)
        except Exception:
            return None
        return None

    def _fallback_heuristic_extraction(self, text: str) -> TechnicalClaim:
        """Deterministic heuristic fallback when Ollama is offline or in CI environment."""
        # 1. Extract python code blocks: ```python ... ```
        code_blocks = re.findall(r"```(?:python)?\s*\n([\s\S]*?)```", text)
        reproduction_code = textwrap.dedent(code_blocks[0]).strip() if code_blocks else None

        # 2. Extract explicit file references: e.g. calculator.py or src/utils.py
        file_match = re.search(r"\b([a-zA-Z0-9_\-/\\]+\.py)\b", text)
        target_file = file_match.group(1) if file_match else None

        # 3. Extract expected errors (e.g. ZeroDivisionError, TypeError, ValueError)
        error_match = re.search(r"\b([A-Z][a-zA-Z0-9]*(?:Error|Exception))\b", text)
        expected_error = error_match.group(1) if error_match else None

        # 4. Extract function/class/method symbols from backticks
        # Supports dotted paths: `calculator.divide`, `Invoice.generate`, `DEFAULT_TIMEOUT`
        backtick_matches = re.findall(r"`([a-zA-Z_][a-zA-Z0-9_\.]*)`", text)
        target_symbol = None

        for cand in backtick_matches:
            # Skip if it is an Exception / Error name
            if cand.endswith("Error") or cand.endswith("Exception"):
                continue
            # Skip generic markdown keywords or file names ending in .py
            if cand.endswith(".py") or cand in {"python", "bash", "true", "false", "none"}:
                continue
            target_symbol = cand
            break

        # If still no symbol found, search for 'def <name>' in snippets
        if not target_symbol and reproduction_code:
            def_match = re.search(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)", reproduction_code)
            if def_match:
                target_symbol = def_match.group(1)

        # If target_file is missing but target_symbol is dotted (e.g. calculator.divide)
        if not target_file and target_symbol and "." in target_symbol:
            possible_module = target_symbol.split(".")[0]
            target_file = f"{possible_module}.py"

        # 5. External Cloud Infrastructure dependencies ONLY (excluding generic terms like 'api' or 'http')
        external_deps: List[str] = []
        concrete_infra = [
            "aws", "s3", "postgresql", "postgres", "mysql", "redis",
            "mongodb", "dynamodb", "docker", "kubernetes", "stripe"
        ]
        for dep in concrete_infra:
            if re.search(r"\b" + dep + r"\b", text, re.IGNORECASE):
                external_deps.append(dep)

        return TechnicalClaim(
            target_file=target_file,
            target_symbol=target_symbol,
            claimed_behavior=text.strip().splitlines()[0] if text.strip() else "Unspecified behavior",
            reproduction_snippet=reproduction_code,
            expected_error=expected_error,
            external_dependencies=external_deps
        )

    def extract_claim(self, issue_or_pr_text: str) -> TechnicalClaim:
        """
        Extracts structured TechnicalClaim using local Gemma 4 model,
        falling back seamlessly to rule-based AST extraction if Ollama is not active.
        """
        prompt = f"""You are a precise open-source code triage engine.
Analyze the following bug report or pull request. Extract the atomic technical claims into JSON.

Required JSON format:
{{
  "target_file": "path/to/file.py or null",
  "target_symbol": "function_or_class_name or null (do NOT use Error types as symbols)",
  "claimed_behavior": "brief 1-sentence summary of the bug or claim",
  "reproduction_snippet": "executable Python code to reproduce the issue, or null",
  "expected_error": "Exception name like ZeroDivisionError or null",
  "external_dependencies": ["list", "of", "external", "services", "like", "aws", "database"]
}}

Text to analyze:
---
{issue_or_pr_text}
---
"""
        parsed = self._call_ollama(prompt)
        if parsed and isinstance(parsed, dict) and "claimed_behavior" in parsed:
            sym = parsed.get("target_symbol")
            # If model hallucinated an Error as symbol, clean it
            if sym and (sym.endswith("Error") or sym.endswith("Exception")):
                sym = None

            # If model didn't extract expected_error, search claimed_behavior and issue text
            exp_err = parsed.get("expected_error")
            if not exp_err or str(exp_err).lower() in {"null", "none", ""} or str(exp_err).lower().startswith("null") or str(exp_err).lower().startswith("none"):
                full_search = f"{parsed.get('claimed_behavior', '')} {issue_or_pr_text}"
                err_match = re.search(r"\b([A-Z][a-zA-Z0-9]*(?:Error|Exception))\b", full_search)
                if err_match:
                    exp_err = err_match.group(1)
                else:
                    exp_err = None

            repro = parsed.get("reproduction_snippet")
            if repro and isinstance(repro, str):
                repro = textwrap.dedent(repro).strip()
            return TechnicalClaim(
                target_file=parsed.get("target_file"),
                target_symbol=sym,
                claimed_behavior=parsed.get("claimed_behavior", "Extracted claim"),
                reproduction_snippet=repro,
                expected_error=exp_err,
                external_dependencies=parsed.get("external_dependencies", [])
            )

        return self._fallback_heuristic_extraction(issue_or_pr_text)
