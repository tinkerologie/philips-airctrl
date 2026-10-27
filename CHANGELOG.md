# Changelog - philips-airctrl (Enhanced Home Assistant Fork)

All notable changes to this enhanced fork will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note**: This is an enhanced fork of the original aioairctrl package with significant additional features for Home Assistant integration. Version numbers start from 0.3.0 to distinguish from the original package.

## [Unreleased]

## [1.4.0] - 2026-10-28

### Fixed

- `observe_status()` no longer goes silent after a few minutes while the device stays reachable ([#34](https://github.com/tinkerologie/philips-airctrl/issues/34)). It now renews its Observe registration every Max-Age seconds of the latest registration response (RFC 7641 §3.3.1), on the same encryption session without a new sync. The replaced observation is cancelled once the new one has answered, and a renewal's first status is only yielded when it differs from the last one. A renewal that fails raises `NetworkError`, or `TimeoutError` after 10 seconds, so callers can reconnect. The observation is cancelled on every exit path (`break`, `aclose()`, cancellation, errors and the end of the stream).
- `get_status(observe=False)` and `observe_status()` no longer cancel an observation that aiocoap has already ended (after an error, or when the device answers without Observe). aiocoap rejects a second cancel with an `AssertionError`, which hid the original `NetworkError`.

### Added

- `observe_status(renew_interval=...)` keyword to override the renewal interval.
- Python 3.14 and 3.15 classifiers. CI runs the test suite on every supported Python from 3.11 to 3.15, with deprecation warnings treated as errors.

### Changed

- `get_status()` falls back to a Max-Age of 60 for a missing, non-integer or non-positive value, using the same rule as observation renewal.
- pytest-asyncio's fixture loop scope is set explicitly (`asyncio_default_fixture_loop_scope = "function"`), removing a deprecation warning.
- Package metadata uses a PEP 639 SPDX license expression (`license = "Apache-2.0"` with `license-files`) instead of the deprecated license table and `License ::` classifier; the build requires hatchling 1.27 or newer.
- On Python 3.15 and newer the minimum pydantic is 2.14.0, the first release with Python 3.15 wheels. Older Pythons keep the 2.11.0 floor, so Home Assistant 2026.10 (pydantic 2.13.5) is unaffected.

### Removed

- The Aikido security-scan agent instructions (`.github/instructions/aikido_rules.instructions.md`); the service is no longer used.

## [1.3.0] - 2026-10-19

### Added

- `py.typed` marker (PEP 561) and `Typing :: Typed` classifier, so type checkers use the library's annotations.
- `ClientNotInitialisedError` (a `RuntimeError`) in `philips_airctrl.coap.client`, raised with a clear message when a request is made before `Client.create()` / `async with Client(...)`; previously this surfaced as `AttributeError: 'NoneType' object has no attribute 'request'`.

### Changed

- Pydantic models (`philips_airctrl.models`) follow current Pydantic v2 practice: ports are validated to 1-65535 and `ConnectionInfo.max_age` to >= 0; `FieldDefinition.type` is `Literal["string", "integer", "boolean"]`; device status payloads and field values are typed as `pydantic.JsonValue` instead of `Any`. `DeviceInfoExtractor.get_device_info()` now builds the `DeviceReport` in one step instead of filling it after construction.
- Minimum Pydantic version raised from 2.0 to 2.11 (tested on 2.11.0, 2.12.2 and 2.14; Home Assistant 2026.4+ pins 2.12.2 or newer).
- `Client.create()` has an explicit signature, `create(host, port=5683, *, sync=True) -> Self`, instead of `*args, **kwargs`; existing calls are unaffected. `__aenter__` also returns `Self`.
- `mypy` now passes in full strict mode (`strict = true`): added `types-PyYAML`, `types-tabulate` and `types-netifaces` dev dependencies, enabled the `pydantic.mypy` plugin, ignored missing imports for the untyped `aiocoap`, and set `files = ["src"]` so a bare `uv run mypy` works. CI now runs `mypy` on every pull request.
- YAML exports use `yaml.safe_dump`. The CLI configures logging in `main()` instead of when `philips_airctrl.cli` is imported, and uses `logging.WARNING` instead of the deprecated `logging.WARN` alias.
- Pull requests get path labels and at most one type label, `bug` or `enhancement`, from the shared tinkerologie PR labeler. Dependabot pull requests whose largest update is a patch or minor version merge automatically once the checks and commit statuses on their head commit have finished without a failure (a Codecov check that is still pending is not waited for; a Codecov failure blocks); majors, and pull requests with open review threads, stay for review.
- Release workflows hardened (least-privilege job permissions, no expressions in shell scripts, no persisted checkout credentials, no dependency caches); scheduled workflows run on Australia/Brisbane time. New CI workflow runs lint and tests on every pull request. Relicensed from MIT to the Apache License 2.0; NOTICE retains the MIT notice for earlier releases.
- Workflow layout tidied after the release hardening (no behaviour change): blank-line layout restored in `release.yml`.
- Tinkerologie-Bot governance report updated to v1.4.3: an older run can no longer post a stale report after a newer run passed. Workflow formatting tidied.
- Repository standardised to the tinkerologie layout (STANDARDS.md in tinkerologie/.github): workflows renamed to the standard set (CI, Validate, Release, PR Governance, ...), every action pinned to a commit SHA, shared Dependabot, `.editorconfig`, `.gitattributes` and `CODEOWNERS` files, and organization-wide labels and community files.
- Tinkerologie-Bot's comment is now a readable "Pull request checklist": each problem is a numbered heading with plain-English guidance and its items listed underneath, and report updates for a pull request are serialised so an older run can never overwrite a newer one.
- Contribution governance: issues without a `bug` or `enhancement` label are labeled automatically when their type can be determined (issues labeled `question`, `duplicate`, `invalid`, `wontfix`, or `no-type` are skipped), so CodeRabbit can plan them. Pull requests that conflict with the default branch are labeled, and their authors are notified in a comment. Stale issues and pull requests are labeled after 14 days without activity and closed 30 days later. PR governance now re-validates a human-authored, non-draft PR when a bot such as CodeRabbit edits its description, instead of skipping the check and reporting a pass, only maintainers with write access may use `None` instead of linking an issue, and a link to an issue that does not exist now fails the check.
- Tinkerologie-Bot now posts one comment on pull requests that fail PR governance, listing every problem to fix, and updates it once they are fixed. PR governance runs from the default branch's workflow (`pull_request_target`), so a pull request cannot change its own check.
- Update repository URLs and documentation references to tinkerologie organization.

### Fixed

- Setup wizard no longer crashes when the selected device has no name (it falls back to the IP address for file names) or when the report has no Home Assistant config.
- CLI tests no longer leave an un-awaited `async_main` coroutine behind (`RuntimeWarning`).

## [1.2.0] - 2026-07-02

### Added

- **Plaintext `/sys/dev/info` support** (#7) - `CoAPClient` now exposes a
  `get_device_info()` method that reads the unencrypted `/sys/dev/info` CoAP
  resource without performing the sync handshake.  This is essential for
  push-only firmware variants (e.g. `AWS_Philips_AIR_Combo` used by CX7550/01)
  that never answer a direct `GET` of `/sys/dev/status`.
- **`sync=False` construction path** - `Client.create(..., sync=False)` (and the
  underlying `_init(sync=False)`) creates the aiocoap transport context without
  running the encrypted sync handshake, enabling identification of push-only
  devices without triggering the handshake.  The default `sync=True` preserves
  full backward compatibility for all existing callers.
- **`device-info-raw` CLI subcommand** - New CLI command
  `philips-airctrl device-info-raw -H <host>` reads the plaintext
  `/sys/dev/info` endpoint and prints the result as JSON.  Uses `sync=False`
  internally so it works on all firmware variants.
- **`INFO_PATH` constant** (`/sys/dev/info`) added alongside the existing path
  constants on the `Client` class.

## [1.1.0] - 2026-05-29

### Added

- **Observe-free one-shot status reads** (#6) - `Client.get_status()` now accepts
  an `observe: bool = True` parameter. When `observe=False`, the CoAP observation
  used to elicit a response is cancelled immediately after the first reply, so no
  lingering server-side subscription remains. This is intended for discovery
  probes, bounded polling, and single status checks on devices with a limited
  number of observer slots. The default (`observe=True`) preserves the previous
  behaviour for full backward compatibility.

### Changed

- Update repository URLs and documentation references to tinkerologie organization.

- One-shot callers (`discover`, `device-info`, and the `status` CLI command) now
  use `get_status(observe=False)` so they no longer leave observations registered
  on the device.

## [0.3.0] - 2025-01-27 - **Major Home Assistant Integration Release**

### Added - **Home Assistant Integration Features**

- **Automatic Device Discovery** - Network scanning for Philips air purifiers
- **Comprehensive Device Analysis** - Extract 70+ data points with capability detection
- **Interactive Setup Wizard** - User-friendly guided setup for non-technical users
- **Multiple Export Formats** - JSON and YAML output for easy integration
- **Home Assistant Configuration Generation** - Ready-to-use HA configs
- **Device Information Export** - Complete device analysis for integration development
- **Community Contribution Workflow** - Easy device info sharing for ha-philips-airpurifier project

### Added - **Development & Quality Improvements**

- Comprehensive test suite with 75%+ coverage
- Type hints throughout the codebase
- Modern pyproject.toml configuration
- Pre-commit hooks configuration
- GitHub Actions CI/CD pipeline
- Detailed README with usage examples
- Development documentation
- Code quality tools (Black, Flake8, MyPy)

### Changed - **Fork & Package Changes**

- **BREAKING**: Package renamed to `philips-airctrl` to distinguish from original
- **BREAKING**: No longer available on PyPI - must install from source
- **BREAKING**: CLI argument structure updated for new commands
- **BREAKING**: Migrated from setup.py to pyproject.toml
- Updated Python version requirement to 3.8+
- Enhanced CLI argument parsing for better testability
- Modernized code formatting with Black
- Updated project metadata and maintainer information

### Changed - **Technical Improvements**

- Improved error handling in client code
- Fixed encryption key overflow handling
- Enhanced async/await patterns throughout codebase

### Fixed

- Fixed bare except clause in client.py
- Fixed f-string without placeholders
- Fixed module imports organization
- Fixed encryption context key incrementation overflow
- Improved async/await patterns in tests

### Security

- Updated dependencies to latest versions
- Added security scanning configuration
- Improved error handling to prevent information leakage

### Development

- Added comprehensive test suite for all modules
- Set up automated testing with pytest
- Added code coverage reporting
- Implemented pre-commit hooks for code quality
- Added development environment setup documentation

## [0.2.5] - Previous Release

### Features

- Basic CoAP client functionality
- Encrypted communication with Philips air purifiers
- Command-line interface
- Status monitoring and control
- Device observation capabilities

### Known Issues

- Limited test coverage
- No type hints
- Basic error handling
- Manual dependency management

---

## Development Notes

### Version 0.2.6 Improvements Summary

This release represents a major modernization and quality improvement of the philips-airctrl library:

1. **Testing Infrastructure**: Added comprehensive test suite covering encryption, client functionality, and CLI operations with proper async mocking.

2. **Code Quality**: Implemented modern Python development practices including type hints, code formatting, and linting.

3. **Project Structure**: Migrated to modern pyproject.toml configuration and removed deprecated setup.py.

4. **Documentation**: Significantly enhanced README with detailed usage examples, API reference, and development guidelines.

5. **Development Workflow**: Added pre-commit hooks, CI/CD pipeline, and automated quality checks.

6. **Maintainability**: Improved error handling, fixed code quality issues, and added proper async patterns.

### Migration Guide from 0.2.5 to 0.2.6

The API remains backward compatible, but there are some development-related changes:

- **Python Version**: Now requires Python 3.8+ (was 3.6+)
- **Installation**: No changes to installation process
- **API**: All existing API calls remain the same
- **CLI**: All existing CLI commands work unchanged

For developers:
- Use `pip install -e ".[dev]"` for development dependencies
- Run tests with `pytest` instead of manual testing
- Use `black` for code formatting
- Use `pre-commit` for automated quality checks

### Future Roadmap

- Add support for more Philips air purifier models
- Implement device discovery functionality
- Add configuration file support
- Enhance error messages and user feedback
- Add integration with home automation systems
