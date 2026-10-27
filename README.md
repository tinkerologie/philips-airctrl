# philips-airctrl

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Tests](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)

Async Python library and CLI for controlling Philips air purifiers over encrypted CoAP. Includes network discovery, device data extraction, and an interactive setup wizard for collecting device information to help expand Home Assistant integration support.

## Features

- **Device Discovery** -- Scan your local network to find Philips air purifiers automatically
- **Device Data Extraction** -- Read 70+ data points including sensors, controls, and capabilities
- **Interactive Setup Wizard** -- Guided collection of device info for sharing with integration developers
- **Multiple Export Formats** -- JSON and YAML output
- **Async/Await** -- Built on `aiocoap` with full async support
- **Encrypted CoAP** -- AES-CBC encrypted communication with the device
- **Real-time Monitoring** -- Observe device status changes as they happen

## Supported Devices

Tested with:

- Philips AC4220/12
- Other Philips air purifiers using the CoAP protocol

## Installation

### From Source

```bash
git clone https://github.com/tinkerologie/philips-airctrl.git
cd philips-airctrl
uv sync
```

### With pip

```bash
git clone https://github.com/tinkerologie/philips-airctrl.git
cd philips-airctrl
pip install .
```

### Development

```bash
uv sync --extra dev
uv run pre-commit install
```

## Quick Start

### Discover Devices

```bash
# Scan all local networks
philips-airctrl discover

# Scan a specific subnet
philips-airctrl discover -n 192.168.1.0/24

# Increase timeout for slow networks
philips-airctrl discover -t 10.0
```

Example output:

```text
Discovering Philips air purifiers on the network...

Scanning networks: 192.168.1.0/24

Found 1 device(s):

+----------------+-----------+---------+----------+-------------+
| IP Address     | Model     | Name    | Firmware | WiFi Signal |
+================+===========+=========+==========+=============+
| 192.168.1.100 | AC4220/12 | Bedroom | 0.2.1    | -52 dBm     |
+----------------+-----------+---------+----------+-------------+
```

### Control a Device

```bash
# Get current status
philips-airctrl status -H 192.168.1.100

# Get status as JSON
philips-airctrl status -H 192.168.1.100 --json

# Set device parameters
philips-airctrl set -H 192.168.1.100 power=true mode=auto

# Monitor status changes in real-time
philips-airctrl status-observe -H 192.168.1.100
```

### Extract Device Information

```bash
# JSON output (default)
philips-airctrl device-info -H 192.168.1.100

# YAML output
philips-airctrl device-info -H 192.168.1.100 -f yaml

# Save to file
philips-airctrl device-info -H 192.168.1.100 -o device_report.json
```

### Interactive Setup Wizard

The wizard walks you through discovery, analysis, and export:

```bash
philips-airctrl setup
```

This will:

1. Discover devices on your network
2. Analyse capabilities and extract technical specifications
3. Generate JSON, YAML, and summary reports in `~/philips_airpurifier_config/`

## Library Usage

```python
import asyncio

from philips_airctrl import CoAPClient


async def main():
    client = await CoAPClient.create(host="192.168.1.100")

    try:
        # Read current status
        status, max_age = await client.get_status()
        print(status)

        # Set controls
        await client.set_control_values(data={"power": True, "mode": "auto"})

        # Observe real-time updates. The Observe registration is renewed every
        # Max-Age seconds (or renew_interval=...) so the stream stays alive; a
        # renewal that fails raises NetworkError or TimeoutError.
        async for update in client.observe_status():
            print(update)
            break
    finally:
        await client.shutdown()


asyncio.run(main())
```

### Discovery API

```python
import asyncio

from philips_airctrl.discovery import DeviceDiscovery


async def main() -> None:
    discovery = DeviceDiscovery(timeout=5.0)
    devices = await discovery.discover_devices()

    for device in devices:
        print(f"{device.name} ({device.model}) at {device.ip}")


asyncio.run(main())
```

### Device Info API

```python
import asyncio

from philips_airctrl.device_info import DeviceInfoExtractor


async def main() -> None:
    extractor = DeviceInfoExtractor("192.168.1.100")
    report = await extractor.get_device_info()

    print(extractor.export_json(report, pretty=True))
    print(extractor.export_yaml(report))


asyncio.run(main())
```

## CLI Reference

```text
philips-airctrl [-D] <command> [options]

Global options:
  -D, --debug              Enable debug logging

Commands:
  discover                 Find devices on the network
    -n, --network CIDR     Subnet to scan (e.g. 192.168.1.0/24)
    -t, --timeout SECONDS  Discovery timeout (default: 5.0)

  status -H HOST           Get device status
    -H, --host HOST        Device IP address (required)
    -P, --port PORT        CoAP port (default: 5683)
    -J, --json             Output as JSON

  status-observe -H HOST   Stream real-time status updates
    -H, --host HOST        Device IP address (required)
    -P, --port PORT        CoAP port (default: 5683)
    -J, --json             Output as JSON

  set -H HOST K=V [K=V ..] Set device parameters
    -H, --host HOST        Device IP address (required)
    -P, --port PORT        CoAP port (default: 5683)
    -I, --int              Encode values as integers

  device-info -H HOST      Extract comprehensive device data
    -H, --host HOST        Device IP address (required)
    -P, --port PORT        CoAP port (default: 5683)
    -f, --format FMT       json or yaml (default: json)
    -o, --output FILE      Write to file instead of stdout

  setup                    Interactive setup wizard
```

## Helping Expand Device Support

The device-info and setup commands produce technical reports that developers use to add support for new air purifier models in Home Assistant integrations.

**This tool does not generate ready-to-use Home Assistant configurations.** It extracts raw device data for integration developers.

To contribute:

1. Run `philips-airctrl setup` and follow the prompts
2. Open an issue in the relevant integration repo (e.g. [ha-philips-airpurifier](https://github.com/tinkerologie/ha-philips-airpurifier))
3. Attach the generated JSON file and include your device model number

## Project Structure

```text
philips-airctrl/
  src/philips_airctrl/       # Package source (src layout)
    _version.py              # Single source of truth for version
    cli.py                   # CLI entry point
    models.py                # Pydantic v2 data models
    discovery.py             # Network device discovery
    device_info.py           # Device data extraction
    setup_wizard.py          # Interactive setup wizard
    coap/                    # CoAP protocol layer
      client.py              # Async CoAP client
      encryption.py          # AES-CBC encryption
  tests/                     # Test suite (100% coverage)
  pyproject.toml             # Project metadata and tool config
```

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Security scan
uv run bandit -c pyproject.toml -r src/

# Run all pre-commit hooks
uv run pre-commit run --all-files
```

## Protocol Details

Communication uses CoAP (Constrained Application Protocol) over UDP port 5683 with:

- AES-CBC encryption with PKCS7 padding
- SHA-256 digest verification
- Custom key exchange/sync protocol

## Troubleshooting

**No devices found** -- Ensure the purifier is on the same network, powered on, and connected to WiFi. Try `-n 192.168.1.0/24` to specify a subnet, or increase the timeout with `-t 10.0`.

**Connection refused** -- Verify the IP, check that your firewall allows UDP on port 5683, and confirm the device is on the same network segment.

**Timeout errors** -- Check connectivity, increase timeouts, and verify the device is not in sleep mode.

**Debug mode** -- Add `-D` to any command for verbose protocol logging:

```bash
philips-airctrl -D status -H 192.168.1.100
```

## License

MIT -- see [LICENSE](LICENSE).

## Acknowledgments

- Original implementation by [betaboon](https://github.com/betaboon)
- CoAP protocol via [aiocoap](https://github.com/chrysn/aiocoap)
- Encryption via [pycryptodomex](https://github.com/Legrandin/pycryptodome)

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
