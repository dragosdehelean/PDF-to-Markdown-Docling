## 0) Project Overview

This repo is a **Python CLI** that converts **financial report PDFs** into **clean Markdown** suitable for RAG ingestion, using Docling’s layout pipeline and optional OCR.
It also includes **quality gates** (Markdown quality scoring + PDF↔MD fidelity audit) and **spacing/table repair utilities** to improve extraction for real-world financial PDFs.

## 1) Core Commands (copy/paste)
- Install deps: `uv sync`
- Dev: `uv run python main.py --help`
- Typecheck: `uv run python -m compileall .`
- Lint (fix): `N/A (not configured yet)`
- Tests (all): `N/A (no test suite yet)`
- E2E (all): `uv run python tools\audit_pdf_vs_md.py "<input.pdf>" "<output.md>"`
- Build (if required): `N/A (CLI script)`

## 2) Repo Map (where things go)
- Source: `main.py`, `conversion_utils.py`, `audit_utils.py`, `spacing_fix.py`, `pymupdf_spacing_fix.py`, `table_fixes.py`, `quality.py`, `export_utils.py`
- Tests: `tests/` (create when adding a formal suite; currently not present)
- Docs: `README.md`, this `AGENTS.md`, sample output `long_report.md`
- Config: `pyproject.toml`, `.python-version`

## 3) Tech Stack

- **Runtime:** Python 3.12 (see `.python-version`)
- **Package mgmt:** `uv` (lock + env via `uv sync`)
- **PDF→Doc/MD:** Docling `>=2.66.0`
- **PDF text & glyph reconstruction:** PyMuPDF `>=1.26.7`
- **GPU acceleration:** `torch==2.9.1+cu128`, `torchvision==0.24.1+cu128` (PyTorch cu128 index pinned in `pyproject.toml`)
- **OCR (optional):** CLI supports `tesseract` (default) + `rapidocr` / `easyocr` options (external deps/tools required)
- **Quality gates (local scripts):** `tools/quality_report.py`, `tools/audit_pdf_vs_md.py`

## 3) Strict Boundaries (must follow)

### ✅ Always
- Keep diffs small & scoped to the task
- Update/extend tests when behavior changes (or add a minimal test when introducing new behavior)
- Run: typecheck (`compileall`) + relevant quality gates before “done”
- Keep documentation **and** comments up to date (README, docstrings, inline comments, and help text)

### ⚠️ Ask first
- Add/remove dependencies, update lockfile for new deps
- Changing CUDA / PyTorch pinning or indexes
- CI/CD changes
- Large refactors across modules

### 🚫 NEVER
- Commit secrets / tokens / credentials
- Commit generated artifacts: `.venv/`, `__pycache__/`, `*.pt`, extracted images unless explicitly required
- Delete checks/quality gates just to make a run “green”
- Push directly on `main`

## 5) Testing Rules — REQUIRED

### Fundamental Principle
**Every behavior change MUST be verifiable.** Prefer automated tests; when a full suite is not present, use the provided quality gates and add small tests as you introduce stable interfaces.

### Required Test Types

a. **Unit Tests** — for isolated pure functions (parsers, scoring, spacing predicates)
   - Location: `tests/unit/`
   - Convention: `test_*.py`

b. **Integration Tests** — for module interactions (Docling conversion options, spacing fix merges)
   - Location: `tests/integration/`
   - Verify: conversion outputs, table cell repair, audit metrics

c. **E2E Tests** — for full CLI workflows
   - Location: `tests/e2e/`
   - Verify: running `main.py` on representative PDFs produces Markdown that passes basic quality thresholds

### Testing Quality Rules
- Deterministic tests (no random, no time-dependent flakiness)
- Prefer golden/snapshot tests for small, stable fixtures; avoid committing large PDFs

## 6) README.md Maintenance — REQUIRED
Update `README.md` when changes affect:
- setup / prerequisites (Python, uv, CUDA, OCR tools)
- CLI options / defaults
- project structure
- new important dependencies

Also keep **inline documentation** up to date:
- Docstrings on non-trivial helpers (especially conversion + spacing repair)
- Inline comments where intent is not obvious (keep comments true as code evolves)
- `--help` text and option descriptions (argparse) must match actual behavior

## 7) Code Conventions

### Do
- Keep `main.py` focused on CLI parsing; put logic in `*_utils.py` or dedicated modules
- Prefer Docling configuration/controls **before** adding post-processing heuristics
- Log via `logging`; ensure `--quiet` meaningfully reduces noise
- Keep outputs stable and RAG-friendly (page breaks, clean headings, minimal noise)
- Add small, focused utilities under `tools/` rather than bloating the main flow

### Don't
- DO NOT add heavyweight post-processing without first exhausting Docling options
- DO NOT silently change defaults (OCR mode, image mode, backend selection) without updating docs + help text
- DO NOT introduce new dependencies without approval

## 10) If you’re stuck

If you're not sure how to proceed:
1. **Ask** a clarifying question
2. **Propose** a short plan before implementation
3. **DO NOT** make major speculative changes without confirmation

## 11) Supplementary agent docs

Read these **before** working in the relevant area:
- `README.md` — usage, CLI flags, and expected behavior
- `pyproject.toml` — pinned runtime deps (Docling / PyMuPDF / PyTorch cu128)
- `tools/quality_report.py` and `tools/audit_pdf_vs_md.py` — quality gate semantics

> If a supplementary doc conflicts with this file, **this AGENTS.md takes precedence**.

---

## Final rule (mandatory)
At the end of any task that changes code, run all relevant checks (at minimum: `uv run python -m compileall .` and the appropriate quality gates).  
If something fails, fix until everything is green.
