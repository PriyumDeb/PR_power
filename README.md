# PR_checker (ClaimCheck)
### Evidence-Based Open Source Issue and Pull Request Triage Engine

> **Hacktoberfest 2026 | Hack Day Sonipat**  
> **Track**: Problem 02 — Evidence-Based Open Source Issue and Pull Request Triage  
> **Core AI Model**: `gemma4:latest` (8B parameters, offline via Ollama)

---

## 1. Problem Statement Overview
Open-source maintainers face an unprecedented wave of low-quality, AI-generated, or fabricated bug reports and pull requests. Traditional triage bots rely on basic LLM prompting, which hallucinates certainty without verifying technical claims.

**PR_checker** takes an evidence-first approach:
1. Deconstructs issues and PRs into **atomic technical claims** using local **Gemma 4**.
2. Statically grounds claims against the target repository's **Abstract Syntax Tree (AST)**.
3. Dynamically executes reproduction snippets inside a **sandboxed, resource-bounded runner**.
4. Emits evidence-backed assessments with the official evaluation labels:
   - `confirmed`: The bug is reliably reproduced in the sandbox with exact stack trace proof.
   - `cannot reproduce`: The code executes cleanly without reproducing the claimed error.
   - `invalid`: The claimed functions, files, or symbols do not exist in the codebase.
   - `uncertain`: The claims depend on external networks, private keys, or unsupported hardware.

---

## 2. Architecture & Pipeline

```
  Incoming Issue / Pull Request
               │
               ▼
┌──────────────────────────────┐
│  Atomic Claim Extraction     │ ➔ Gemma 4 (via Ollama) parses claims & snippets
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Static AST Verification     │ ➔ Verifies files, functions, and classes exist
└──────────────┬───────────────┘     [Fail ➔ INVALID]
               │ Pass
               ▼
┌──────────────────────────────┐
│  Sandboxed Micro-Runner      │ ➔ Executes reproduction with strict timeout & no net
└──────────────┬───────────────┘     [Pass / Fail / Timeout]
               │
               ▼
┌──────────────────────────────┐
│  Evidence Dossier Generator  │ ➔ Outputs markdown report with confidence score
└──────────────────────────────┘
```

---

## 3. Quickstart & Installation

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.ai) running locally with `gemma4`

### Installation
```bash
git clone https://github.com/PriyumDeb/PR_checker.git
cd PR_checker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running Tests
```bash
pytest -v tests/
```

---

## 4. License
This project is licensed under the [MIT License](LICENSE).
