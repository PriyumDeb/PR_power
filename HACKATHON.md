# Hackathon Project Registration

## Team Details
- **Team Name**: Observers
- **Team Members**:
  - Priyum Deb
  - Sejal Kundnani
  - Saksham Jha
  - Garvit Jain

## Selected Problem Statement
- **Problem**: Problem 02 - Evidence-Based Open Source Issue and Pull Request Triage
- **Category**: Artificial Intelligence | Developer Tools | Open Source Quality

## AI Models
- **Gemma 4** (via local Ollama)
- **Codestral** (via local Ollama)

## Why Gemma 4?
- **Multimodal Issue Parsing**: Contributors frequently attach screenshots of terminal stack traces, CLI logs, and UI errors instead of pasting code. Gemma 4 reads and extracts error traces directly from images attached to issues.
- **Atomic Claim Extraction**: Converts long, unstructured issue threads and maintainer comments into clean structured JSON (target files, functions, input payloads, and claimed exceptions).
- **128k Context Handling**: Ingests multi-comment issue discussions to capture the full context and consensus before we run any tests.
- **Low-Temperature Information Retrieval**: Runs as a strict extractor rather than a conversational bot, pulling exact claims without inventing hypothetical bugs.

## Why Codestral?
- **Specialized Code Architecture**: Trained specifically on code logic and fill-in-the-middle (FIM) patterns, making it far more reliable at synthesizing runnable Python reproduction snippets from partial bug descriptions.
- **Git Diff & Patch Understanding**: Natively understands unified diff syntax, allowing it to trace exactly which functions, arguments, or defaults changed in a Pull Request.
- **Minimal Test Synthesis**: Generates isolated 5-line micro-tests from extracted claims so our sandbox runner can execute and verify them deterministically.
- **Regression Pattern Detection**: Inspects PR diffs to flag dropped test assertions, altered method signatures, or suspicious side-effect calls before running the code.
