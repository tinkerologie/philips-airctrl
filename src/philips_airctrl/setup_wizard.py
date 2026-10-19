"""Interactive setup wizard for Home Assistant integration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import click
import yaml
from tabulate import tabulate

from philips_airctrl.device_info import DeviceInfoExtractor
from philips_airctrl.discovery import DeviceDiscovery

if TYPE_CHECKING:
    from philips_airctrl.models import DeviceInfo, DeviceReport


class SetupWizard:
    """Interactive setup wizard for discovering and configuring devices."""

    def __init__(self) -> None:
        self.discovered_devices: list[DeviceInfo] = []
        self.selected_device: DeviceInfo | None = None
        self.device_info: DeviceReport | None = None

    def _require_device(self) -> DeviceInfo:
        """Return the selected device, failing loudly if a step ran out of order."""
        if self.selected_device is None:
            raise RuntimeError("No device selected")
        return self.selected_device

    def _require_report(self) -> DeviceReport:
        """Return the gathered device report, failing loudly if a step ran out of order."""
        if self.device_info is None:
            raise RuntimeError("No device information gathered")
        return self.device_info

    async def run(self) -> None:
        """Run the interactive setup wizard."""
        click.echo("Philips Air Purifier Setup Wizard")
        click.echo("=" * 50)
        click.echo()

        await self._discovery_step()

        if not self.discovered_devices:
            click.echo("No devices found. Please check:")
            click.echo("   Your air purifier is connected to the same network")
            click.echo("   The device is powered on")
            click.echo("   Your firewall allows UDP traffic on port 5683")
            return

        self._device_selection_step()

        if not self.selected_device:
            click.echo("No device selected. Exiting.")
            return

        await self._device_info_step()

        await self._configuration_step()

        self._next_steps()

    async def _discovery_step(self) -> None:
        """Step 1: Discover devices on the network."""
        click.echo("Step 1: Discovering devices...")
        click.echo()

        if click.confirm("Do you want to scan all local networks? (recommended)", default=True):
            networks = None
        else:
            network = click.prompt("Enter network to scan (e.g., 192.168.1.0/24)")
            networks = [network]

        discovery = DeviceDiscovery(timeout=3.0)

        with click.progressbar(length=100, label="Scanning network...") as bar:
            discovery_task = asyncio.create_task(discovery.discover_devices(networks))

            for i in range(100):
                await asyncio.sleep(0.1)
                bar.update(1)

                if discovery_task.done():
                    bar.update(100 - i)
                    break

            self.discovered_devices = await discovery_task

        click.echo()
        if self.discovered_devices:
            click.echo(f"Found {len(self.discovered_devices)} device(s)!")
            self._display_devices_table()
        else:
            click.echo("No devices found.")

    def _device_selection_step(self) -> None:
        """Step 2: Let user select a device."""
        click.echo()
        click.echo("Step 2: Select your device")
        click.echo()

        if len(self.discovered_devices) == 1:
            device = self.discovered_devices[0]
            if click.confirm(f"Use device '{device.name}' at {device.ip}?", default=True):
                self.selected_device = device
                return

        click.echo("Available devices:")
        for i, device in enumerate(self.discovered_devices, 1):
            click.echo(f"  {i}. {device.name} ({device.model}) at {device.ip}")

        while True:
            try:
                choice = click.prompt("Select device number", type=int)
                if 1 <= choice <= len(self.discovered_devices):
                    self.selected_device = self.discovered_devices[choice - 1]
                    break
                click.echo(f"Please enter a number between 1 and {len(self.discovered_devices)}")
            except (ValueError, click.Abort):
                click.echo("Invalid selection. Please try again.")

    async def _device_info_step(self) -> None:
        """Step 3: Gather detailed device information."""
        click.echo()
        click.echo("Step 3: Gathering device information...")
        click.echo()

        device = self._require_device()
        extractor = DeviceInfoExtractor(device.ip, device.port)

        try:
            with click.progressbar(length=100, label="Analyzing device...") as bar:
                info_task = asyncio.create_task(extractor.get_device_info())

                for i in range(100):
                    await asyncio.sleep(0.05)
                    bar.update(1)

                    if info_task.done():
                        bar.update(100 - i)
                        break

                self.device_info = await info_task

            click.echo()
            click.echo("Device analysis complete!")
            self._display_device_summary()

        except Exception as e:
            click.echo(f"Error gathering device info: {e}")
            self.device_info = None

    async def _configuration_step(self) -> None:
        """Step 4: Generate and save configuration."""
        click.echo()
        click.echo("Step 4: Generating configuration...")
        click.echo()

        if not self.device_info:
            click.echo("No device information available.")
            return

        output_dir = Path.home() / "philips_airpurifier_config"
        output_dir.mkdir(exist_ok=True)

        device = self._require_device()
        device_name = (device.name or device.ip).replace(" ", "_").lower()

        json_file = output_dir / f"{device_name}_device_info.json"
        with open(json_file, "w") as f:
            json.dump(self.device_info.model_dump(mode="json"), f, indent=2)

        ha_config = self.device_info.home_assistant
        ha_config_data = ha_config.model_dump(mode="json") if ha_config else {}
        yaml_file = output_dir / f"{device_name}_ha_config.yaml"
        with open(yaml_file, "w") as f:
            yaml.safe_dump({"air_purifier": ha_config_data}, f, default_flow_style=False)

        summary_file = output_dir / f"{device_name}_summary.txt"
        with open(summary_file, "w") as f:
            f.write(self._generate_summary_report())

        click.echo(f"Configuration saved to: {output_dir}")
        click.echo(f"   Device info: {json_file.name}")
        click.echo(f"   HA config:   {yaml_file.name}")
        click.echo(f"   Summary:     {summary_file.name}")

    def _next_steps(self) -> None:
        """Step 5: Show next steps for Home Assistant integration."""
        click.echo()
        click.echo("Setup Complete!")
        click.echo("=" * 50)
        click.echo()
        click.echo("Next steps for Home Assistant integration:")
        click.echo()
        click.echo("1. Share your device information:")
        click.echo("   Visit: https://github.com/domalab/ha-philips-airpurifier")
        click.echo("   Create a new issue with your device info")
        click.echo("   Attach the generated JSON file")
        click.echo()
        click.echo("2. Install Home Assistant integration:")
        click.echo("   Add the custom integration to HACS")
        click.echo("   Use the generated YAML configuration")
        click.echo("   Restart Home Assistant")
        click.echo()
        click.echo("3. Test the integration:")
        click.echo("   Check if your device appears in Home Assistant")
        click.echo("   Test basic controls (power, fan speed)")
        click.echo("   Monitor sensor readings")
        click.echo()
        click.echo("4. Help improve the integration:")
        click.echo("   Report any issues on GitHub")
        click.echo("   Share feedback about missing features")
        click.echo("   Help test new device models")
        click.echo()

        if click.confirm("Would you like to open the GitHub repository now?", default=False):
            click.launch("https://github.com/domalab/ha-philips-airpurifier")

    def _display_devices_table(self) -> None:
        """Display discovered devices in a table."""
        headers = ["IP Address", "Model", "Name", "Firmware", "Signal"]
        rows = []

        for device in self.discovered_devices:
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

        click.echo()
        click.echo(tabulate(rows, headers=headers, tablefmt="grid"))

    def _display_device_summary(self) -> None:
        """Display a summary of the selected device."""
        device = self._require_device()
        info = self._require_report()

        click.echo(f"Device: {device.name} ({device.model})")
        click.echo(f"IP: {device.ip}")
        click.echo(f"Firmware: {device.firmware_version}")
        click.echo()

        capabilities = info.capabilities
        click.echo("Capabilities:")
        for cap_name, enabled in capabilities.model_dump().items():
            if isinstance(enabled, bool):
                status = "Yes" if enabled else "No"
                display_name = cap_name.replace("has_", "").replace("_", " ").title()
                click.echo(f"  [{status}] {display_name}")

        sensor_count = len(info.sensors)
        control_count = len(info.controls)
        click.echo()
        click.echo(f"Sensors: {sensor_count}")
        click.echo(f"Controls: {control_count}")

    def _generate_summary_report(self) -> str:
        """Generate a text summary report."""
        device = self._require_device()
        info = self._require_report()

        report = f"""Philips Air Purifier Device Report
Generated by philips-airctrl setup wizard

DEVICE INFORMATION
==================
Name: {device.name}
Model: {device.model}
IP Address: {device.ip}
Serial Number: {device.serial_number}
Firmware Version: {device.firmware_version}
WiFi Version: {device.wifi_version}
Device ID: {device.device_id}
Product ID: {device.product_id}

CAPABILITIES
============
"""

        capabilities = info.capabilities
        for cap_name, enabled in capabilities.model_dump().items():
            if isinstance(enabled, bool):
                status = "Yes" if enabled else "No"
                display_name = cap_name.replace("has_", "").replace("_", " ").title()
                report += f"{display_name}: {status}\n"

        report += f"""
SENSORS ({len(info.sensors)})
=======
"""
        for _name, sensor in info.sensors.items():
            report += f"  {sensor.description}: {sensor.value} (Key: {sensor.raw_key})\n"

        report += f"""
CONTROLS ({len(info.controls)})
========
"""
        for _name, control in info.controls.items():
            report += f"  {control.description}: {control.value} (Key: {control.raw_key})\n"

        report += """
HOME ASSISTANT INTEGRATION
==========================
This device information can be used to improve the Home Assistant
Philips Air Purifier integration. Please share this data at:
https://github.com/domalab/ha-philips-airpurifier

The generated configuration files can be used directly with the
Home Assistant integration once it supports your device model.
"""

        return report
