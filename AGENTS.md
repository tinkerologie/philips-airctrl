# AI Agent Instructions for Philips AirCtrl Python Library

> Single source of truth for all AI coding assistants working on this repository.

## Project Identity

| Key | Value |
| --- | --- |
| **Name** | Philips AirCtrl Python Library |
| **Repository** | `github.com/tinkerologie/philips-airctrl` |
| **Default Branch** | `main` |
| **Description** | Python client library for communicating with Philips air purifiers over CoAP and HTTP. |

Async Python library and CLI for controlling Philips air purifiers. Provides network discovery,
device data extraction, and an interactive Home Assistant setup wizard.

## Mandatory Development Workflow for AI Agents

All AI coding assistants (Claude Code, Gemini, GitHub Copilot, Cursor, Roo, Devin, etc.) MUST strictly adhere to the following workflow when working on this repository:

1. Issue-First Requirement: Never start writing code or creating pull requests without an existing GitHub Issue.
2. Issue Template: Issues must be created using the official Issue Forms (`01-bug-report.yml` for bugs or `02-enhancement-request.yml` for enhancements).
3. CodeRabbit AI Plan: Every issue must have a generated Coding Plan from CodeRabbit AI (`@coderabbitai plan`). AI agents must read and implement strictly according to the approved plan.
4. Branch Discipline: Always create and work on a dedicated branch (`feat/<issue-id>-<description>` or `fix/<issue-id>-<description>`). NEVER commit directly to `main`.
5. Documentation & Changelog: Update `CHANGELOG.md` under `## [Unreleased]` for any user-facing or architectural changes.
6. Local Verification: Run all test, lint, format, and typecheck commands locally before committing. All tests must pass with zero errors and zero warnings.
7. PR Template Completion: Always use `.github/PULL_REQUEST_TEMPLATE.md`. Complete all fields, link the issue using `Closes #<id>` or `Fixes #<id>` when the PR fully resolves it, or `Part of #<id>` for partial work (only maintainers with write access may write `None`, for housekeeping), and check all Pre-Submission Governance boxes with real terminal output.
8. Draft PR First: ALWAYS open pull requests as DRAFT (`gh pr create --draft`).
9. CI Verification: Wait for CI workflows to run on the draft PR and verify that all status checks pass.
10. Ready for Review: Only mark the PR as ready for review (`gh pr ready`) once all checks pass and all due diligence is verified.
11. Review Clearance: Review and resolve all CodeRabbit AI and GitHub Copilot comments. Ensure Codecov reports show zero errors, zero warnings, and no coverage drop.


## Executable Verification Commands

- `pytest` — Run test suite
- `pytest --cov=src` — Run tests with coverage
- `ruff check .` — Run ruff linter
- `ruff format --check .` — Check code formatting
- `mypy src` — Static type checking
- `pre-commit run --all-files` — Run all configured pre-commit hooks

Dependencies are managed with `uv`; run the tools above through `uv run` (for example
`uv run pytest`). Coverage must stay at 100% (`fail_under = 100`).

```bash
uv sync --extra dev                                         # Install all dependencies including dev
uv run pytest tests/test_cli.py                             # Run a single test file
uv run pytest tests/test_cli.py::TestParseArgs::test_status # Run a single test
uv run pytest -k "test_discover"                            # Run tests matching a pattern
uv run pytest -m "not slow"                                 # Skip slow tests
uv run ruff check --fix src/ tests/                         # Lint with auto-fix
uv run ruff format src/ tests/                              # Format
uv run bandit -c pyproject.toml -r src/                     # Security scan
```

## Architecture

```text
src/philips_airctrl/
├── __main__.py          # CLI entry point → calls cli.main()
├── cli.py               # Argument parsing and command dispatch (argparse)
├── coap/
│   ├── client.py        # Async CoAP client (Client class) — device communication
│   └── encryption.py    # AES-CBC encryption/decryption for CoAP payloads
├── discovery.py         # Network scanning for Philips devices (DeviceDiscovery)
├── device_info.py       # Device capability analysis and reporting (DeviceInfoExtractor)
├── models.py            # All Pydantic v2 data models (DeviceInfo, DeviceReport, HAConfig, etc.)
├── setup_wizard.py      # Interactive CLI wizard using click (SetupWizard)
└── _version.py          # Single source of truth for package version
```

**Data flow:** CLI → Discovery/Client → Encryption → Device. Models are shared across all modules.

## Key Conventions

- **Python >=3.11** with src/ layout, built with hatchling
- **Pydantic v2** for all data models — use `model_validate()`, not `parse_obj()`
- **Async/await** throughout — tests use `asyncio_mode = "auto"` (no manual decorator needed)
- **Line length**: 100 characters (ruff)
- **Ruff rules**: E, W, F, I, N, UP, B, SIM, TCH, RUF, S (bandit security checks)
- **mypy strict**: `disallow_untyped_defs=true` — all functions need type annotations
- **Test style**: pytest class-based organization with `unittest.mock` (AsyncMock for async)
- **Version**: Edit `src/philips_airctrl/_version.py` — hatch reads it dynamically

## Boundaries and Safety Constraints

- Always: Write tests for any new or modified functionality, verify changes locally, and update CHANGELOG.md under `[Unreleased]`.
- Ask first: Major architectural changes, removing public APIs, or adding heavy external dependencies.
- Never: Commit secrets, credentials, API keys, or private certificates. Never commit directly to `main`.

## Issue and Pull Request Governance

These rules apply to every contributor, including AI coding agents. The full org-wide rules are in
[GOVERNANCE.md](https://github.com/tinkerologie/.github/blob/main/GOVERNANCE.md).

1. **Issue first.** Open an issue with the bug or enhancement template before opening a pull
   request. Keep the title prefix `[Bug]:` or `[Enhancement]:`, followed by a space and the title.
   Automation applies the `bug` or `enhancement` label when it can tell the type, and CodeRabbit
   then posts a Coding Plan on the issue. Implement from that plan. The labeler skips issues labeled
   `question`, `duplicate`, `invalid`, `wontfix`, or `no-type`, and never re-adds a type label that
   a maintainer removed.
2. **Link the issue.** In the PR's **Related Issues** section, write `Closes #<number>` (or `Fixes`
   or `Resolves`) when the PR completely resolves the issue; these keywords close it on merge. Use
   `Part of #<number>` or `Related to #<number>` for partial work. The linked issue must exist; an
   issue in another public repository (`owner/repo#123`) is fine. Only authors with write access or
   higher (maintainers) may write `None`, for housekeeping such as CI,
   documentation, or dependency updates; PR governance rejects `None` from everyone else.
3. **One change at a time.** Contributors without write access can have at most 2 open, non-draft
   pull requests here. GitHub enforces this limit, and draft pull requests do not count toward it.
   Do not open PRs that edit the same files as another open PR, such as `CHANGELOG.md`,
   translations, `README.md`, or generated bundles. Wait for the first to merge, rebase, then
   continue.
4. **Act on the Tinkerologie-Bot report.** When PR governance fails, Tinkerologie-Bot posts one comment
   listing every problem as a numbered item. Fix each item by editing the PR description or pushing
   the missing change; the check re-runs and the comment updates to passed.
5. **Rebase before review.** Rebase on `main` before marking a PR ready for review.
6. **Resolve conflicts first.** When a PR gets the `conflicts` label, rebase on `main`,
   resolve the conflicts (keep every `CHANGELOG.md` entry under `[Unreleased]`), re-run the tests,
   and force-push before doing any other work.
7. **Stale items.** Issues and PRs with no activity for 14 days are labeled `stale` and closed 30
   days later unless there is new activity. These labels are exempt:
   - Issues: `pinned`, `security`, `confirmed`, `work-in-progress`, `priority: critical`, `priority: high`.
   - Pull requests: `pinned`, `security`, `work-in-progress`.
