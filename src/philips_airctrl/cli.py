"""Command-line interface for philips-airctrl."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import sys

from tabulate import tabulate

from philips_airctrl import CoAPClient
from philips_airctrl.device_info import DeviceInfoExtractor
from philips_airctrl.discovery import DeviceDiscovery
from philips_airctrl.setup_wizard import SetupWizard

logger = logging.getLogger(__package__)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="sub-command help",
    )

    parser.add_argument(
        "-D",
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable debug output",
    )
    parser_status = subparsers.add_parser(
        "status",
        help="get status of device",
    )
    parser_status.add_argument(
        "-H",
        "--host",
        dest="host",
        type=str,
        required=True,
        help="Address of CoAP device",
    )
    parser_status.add_argument(
        "-P",
        "--port",
        dest="port",
        type=int,
        default=5683,
        help="Port of CoAP device (default: %(default)s)",
    )
    parser_status.add_argument(
        "-J",
        "--json",
        dest="json",
        action="store_true",
        help="Output status as JSON",
    )
    parser_status_observe = subparsers.add_parser(
        "status-observe",
        help="Observe status of device",
    )
    parser_status_observe.add_argument(
        "-H",
        "--host",
        dest="host",
        type=str,
        required=True,
        help="Address of CoAP device",
    )
    parser_status_observe.add_argument(
        "-P",
        "--port",
        dest="port",
        type=int,
        default=5683,
        help="Port of CoAP device (default: %(default)s)",
    )
    parser_status_observe.add_argument(
        "-J",
        "--json",
        dest="json",
        action="store_true",
        help="Output status as JSON",
    )
    parser_set = subparsers.add_parser(
        "set",
        help="Set value of device",
    )
    parser_set.add_argument(
        "-H",
        "--host",
        dest="host",
        type=str,
        required=True,
        help="Address of CoAP device",
    )
    parser_set.add_argument(
        "-P",
        "--port",
        dest="port",
        type=int,
        default=5683,
        help="Port of CoAP device (default: %(default)s)",
    )
    parser_set.add_argument(
        "values",
        metavar="K=V",
        type=str,
        nargs="+",
        help="Key-Value pairs to set",
    )
    parser_set.add_argument(
        "-I",
        "--int",
        dest="value_as_int",
        action="store_true",
        help="Encode value as integer",
    )

    # Discovery command
    parser_discover = subparsers.add_parser(
        "discover",
        help="Discover Philips air purifiers on the network",
    )
    parser_discover.add_argument(
        "-n",
        "--network",
        dest="network",
        type=str,
        help="Specific network to scan (e.g., 192.168.1.0/24)",
    )
    parser_discover.add_argument(
        "-t",
        "--timeout",
        dest="timeout",
        type=float,
        default=5.0,
        help="Timeout for device discovery (default: %(default)s)",
    )

    # Device info command
    parser_device_info = subparsers.add_parser(
        "device-info",
        help="Get comprehensive device information",
    )
    parser_device_info.add_argument(
        "-H",
        "--host",
        dest="host",
        type=str,
        required=True,
        help="Address of CoAP device",
    )
    parser_device_info.add_argument(
        "-P",
        "--port",
        dest="port",
        type=int,
        default=5683,
        help="Port of CoAP device (default: %(default)s)",
    )
    parser_device_info.add_argument(
        "-f",
        "--format",
        dest="format",
        choices=["json", "yaml"],
        default="json",
        help="Output format (default: %(default)s)",
    )
    parser_device_info.add_argument(
        "-o",
        "--output",
        dest="output",
        type=str,
        help="Output file (default: stdout)",
    )

    # Setup wizard command
    subparsers.add_parser(
        "setup",
        help="Interactive setup wizard for Home Assistant integration",
    )

    # Device info raw command (plaintext /sys/dev/info, no encryption)
    parser_device_info_raw = subparsers.add_parser(
        "device-info-raw",
        help="Read plaintext /sys/dev/info resource (no encryption, suits push-only firmware)",
    )
    parser_device_info_raw.add_argument(
        "-H",
        "--host",
        dest="host",
        type=str,
        required=True,
        help="Address of CoAP device",
    )
    parser_device_info_raw.add_argument(
        "-P",
        "--port",
        dest="port",
        type=int,
        default=5683,
        help="Port of CoAP device (default: %(default)s)",
    )

    return parser.parse_args(args)


async def handle_discover_command(args: argparse.Namespace) -> None:
    """Handle the discover command."""
    print("Discovering Philips air purifiers on the network...")
    print()

    discovery = DeviceDiscovery(timeout=args.timeout)

    if args.network:
        devices = await discovery.discover_single_network(args.network)
        print(f"Scanning network: {args.network}")
    else:
        devices = await discovery.discover_devices()
        networks = discovery.get_network_ranges()
        print(f"Scanning networks: {', '.join(networks)}")

    print()

    if not devices:
        print("No devices found.")
        print()
        print("Troubleshooting tips:")
        print("  Ensure your air purifier is connected to the same network")
        print("  Check that the device is powered on")
        print("  Verify your firewall allows UDP traffic on port 5683")
        print("  Try specifying a specific network with -n option")
        return

    print(f"Found {len(devices)} device(s):")
    print()

    headers = ["IP Address", "Model", "Name", "Firmware", "WiFi Signal"]
    rows = []

    for device in devices:
        signal = f"{device.status.get('rssi', 'N/A')} dBm" if device.status else "N/A"
        rows.append(
            [
                device.ip,
                device.model or "Unknown",
                device.name or "Unknown",
                device.firmware_version or "Unknown",
                signal,
            ]
        )

    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print()
    print("Use 'philips-airctrl device-info -H <IP>' to extract technical device data")
    print("Use 'philips-airctrl setup' to collect device info for developers")


async def handle_device_info_command(args: argparse.Namespace) -> None:
    """Handle the device-info command."""
    print(f"Gathering device information from {args.host}...")

    extractor = DeviceInfoExtractor(args.host, args.port)
    device_info = await extractor.get_device_info()

    if args.format == "json":
        output = extractor.export_json(device_info, pretty=True)
    else:
        output = extractor.export_yaml(device_info)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Device information saved to: {args.output}")
    else:
        print(output)


async def handle_setup_command() -> None:
    """Handle the setup command."""
    wizard = SetupWizard()
    await wizard.run()


async def handle_device_info_raw_command(args: argparse.Namespace) -> None:
    """Handle the device-info-raw command.

    Reads the plaintext ``/sys/dev/info`` resource from the device without
    performing the encrypted sync handshake.  This is safe to use on push-only
    firmware variants that never answer a direct read of ``/sys/dev/status``.
    """
    client = await CoAPClient.create(host=args.host, port=args.port, sync=False)
    try:
        info = await client.get_device_info()
        print(json.dumps(info, indent=2))
    finally:
        await client.shutdown()


async def async_main() -> None:
    args = parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("coap").setLevel(logging.DEBUG)
        logging.getLogger("philips_airpurifier").setLevel(logging.DEBUG)

    if args.command == "discover":
        await handle_discover_command(args)
        return
    if args.command == "setup":
        await handle_setup_command()
        return
    if args.command == "device-info-raw":
        await handle_device_info_raw_command(args)
        return

    if not hasattr(args, "host") or not args.host:
        print("Error: Host is required for this command")
        return

    client = None
    try:
        client = await CoAPClient.create(host=args.host, port=args.port)
        if args.command == "status":
            status, max_age = await client.get_status(observe=False)
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(status)
                print(f"max_age = {max_age}")
        elif args.command == "status-observe":
            async for status in client.observe_status():
                if args.json:
                    print(json.dumps(status, indent=2))
                else:
                    print(status)
                sys.stdout.flush()
        elif args.command == "set":
            data: dict[str, str | int | bool] = {}
            failed = False
            for e in args.values:
                k, v = e.split("=")
                if v == "true":
                    data[k] = True
                elif v == "false":
                    data[k] = False
                elif args.value_as_int:
                    try:
                        data[k] = int(v)
                    except ValueError:
                        print(f"Cannot encode value '{v}' as int")
                        failed = True
                        break
                else:
                    data[k] = v
            if not failed and data:
                await client.set_control_values(data=data)
        elif args.command == "device-info":
            await handle_device_info_command(args)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if client:
            await client.shutdown()


def main() -> None:
    # Configure logging only when run as a program, never on import.
    logging.basicConfig(level=logging.WARNING)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(async_main())
