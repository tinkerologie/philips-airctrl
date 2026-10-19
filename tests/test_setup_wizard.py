"""Tests for the setup wizard module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from philips_airctrl.models import (
    ConnectionInfo,
    DeviceCapabilities,
    DeviceInfo,
    DeviceReport,
    FieldValue,
    HAConfig,
    HADeviceInfo,
)
from philips_airctrl.setup_wizard import SetupWizard


def _make_device(name="Living Room", model="AC4220", ip="192.168.1.50"):
    return DeviceInfo(
        ip=ip,
        model=model,
        name=name,
        device_id="abc123",
        product_id="prod1",
        firmware_version="1.0.0",
        wifi_version="2.0.0",
        serial_number="SN123",
        status={"rssi": -50},
        reachable=True,
    )


def _make_report():
    return DeviceReport(
        connection=ConnectionInfo(host="192.168.1.50", port=5683, max_age=60),
        capabilities=DeviceCapabilities(
            has_purifier=True, has_pm25_sensor=True, filter_types=["main_filter"]
        ),
        sensors={
            "pm25": FieldValue(
                value=25, type="integer", description="PM2.5 sensor", raw_key="D03103"
            )
        },
        controls={
            "power": FieldValue(
                value=True, type="boolean", description="Power on/off", raw_key="D03102"
            )
        },
        home_assistant=HAConfig(
            host="192.168.1.50",
            name="Living Room",
            model="AC4220",
            unique_id="abc123",
            device_info=HADeviceInfo(
                identifiers=["abc123"],
                name="Living Room",
                model="AC4220",
                sw_version="1.0.0",
                hw_version="2.0.0",
            ),
        ),
    )


class TestSetupWizardInit:
    def test_init(self):
        wizard = SetupWizard()
        assert wizard.discovered_devices == []
        assert wizard.selected_device is None
        assert wizard.device_info is None


class TestSetupWizardRun:
    @pytest.mark.asyncio
    async def test_run_no_devices(self):
        wizard = SetupWizard()

        with (
            patch.object(wizard, "_discovery_step", new_callable=AsyncMock),
            patch("philips_airctrl.setup_wizard.click") as mock_click,
        ):
            wizard.discovered_devices = []
            await wizard.run()
            calls = [str(c) for c in mock_click.echo.call_args_list]
            assert any("No devices found" in s for s in calls)

    @pytest.mark.asyncio
    async def test_run_no_device_selected(self):
        wizard = SetupWizard()
        device = _make_device()

        with (
            patch.object(wizard, "_discovery_step", new_callable=AsyncMock),
            patch.object(wizard, "_device_selection_step"),
            patch("philips_airctrl.setup_wizard.click") as mock_click,
        ):
            wizard.discovered_devices = [device]
            wizard.selected_device = None
            await wizard.run()
            calls = [str(c) for c in mock_click.echo.call_args_list]
            assert any("No device selected" in s for s in calls)

    @pytest.mark.asyncio
    async def test_run_full_flow(self):
        wizard = SetupWizard()
        device = _make_device()
        report = _make_report()

        with (
            patch.object(wizard, "_discovery_step", new_callable=AsyncMock),
            patch.object(wizard, "_device_selection_step"),
            patch.object(wizard, "_device_info_step", new_callable=AsyncMock),
            patch.object(wizard, "_configuration_step", new_callable=AsyncMock),
            patch.object(wizard, "_next_steps"),
        ):
            wizard.discovered_devices = [device]
            wizard.selected_device = device
            wizard.device_info = report
            await wizard.run()


class TestDiscoveryStep:
    @pytest.mark.asyncio
    async def test_scan_all_networks(self):
        wizard = SetupWizard()
        device = _make_device()

        mock_discovery = MagicMock()

        async def mock_discover(networks):
            return [device]

        mock_discovery.discover_devices = mock_discover

        with (
            patch("philips_airctrl.setup_wizard.click") as mock_click,
            patch("philips_airctrl.setup_wizard.DeviceDiscovery", return_value=mock_discovery),
        ):
            mock_click.confirm.return_value = True

            mock_bar = MagicMock()
            mock_click.progressbar.return_value.__enter__ = MagicMock(return_value=mock_bar)
            mock_click.progressbar.return_value.__exit__ = MagicMock(return_value=False)

            await wizard._discovery_step()

            assert len(wizard.discovered_devices) == 1
            assert wizard.discovered_devices[0].ip == "192.168.1.50"

    @pytest.mark.asyncio
    async def test_scan_specific_network(self):
        wizard = SetupWizard()

        mock_discovery = MagicMock()

        async def mock_discover(networks):
            return []

        mock_discovery.discover_devices = mock_discover

        with (
            patch("philips_airctrl.setup_wizard.click") as mock_click,
            patch("philips_airctrl.setup_wizard.DeviceDiscovery", return_value=mock_discovery),
        ):
            mock_click.confirm.return_value = False
            mock_click.prompt.return_value = "192.168.1.0/24"

            mock_bar = MagicMock()
            mock_click.progressbar.return_value.__enter__ = MagicMock(return_value=mock_bar)
            mock_click.progressbar.return_value.__exit__ = MagicMock(return_value=False)

            await wizard._discovery_step()
            assert wizard.discovered_devices == []


class TestDeviceSelectionStep:
    def test_single_device_confirmed(self):
        wizard = SetupWizard()
        device = _make_device()
        wizard.discovered_devices = [device]

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            mock_click.confirm.return_value = True
            wizard._device_selection_step()
            assert wizard.selected_device == device

    def test_multiple_devices(self):
        wizard = SetupWizard()
        d1 = _make_device(name="D1", ip="192.168.1.1")
        d2 = _make_device(name="D2", ip="192.168.1.2")
        wizard.discovered_devices = [d1, d2]

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            mock_click.prompt.return_value = 2
            wizard._device_selection_step()
            assert wizard.selected_device == d2

    def test_invalid_then_valid_selection(self):
        wizard = SetupWizard()
        d1 = _make_device(name="D1", ip="192.168.1.1")
        d2 = _make_device(name="D2", ip="192.168.1.2")
        wizard.discovered_devices = [d1, d2]

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            mock_click.prompt.side_effect = [99, 1]
            wizard._device_selection_step()
            assert wizard.selected_device == d1

    def test_value_error_then_valid(self):
        import click as real_click

        wizard = SetupWizard()
        d1 = _make_device(name="D1", ip="192.168.1.1")
        wizard.discovered_devices = [d1, _make_device(name="D2", ip="192.168.1.2")]

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            mock_click.Abort = real_click.Abort
            mock_click.prompt.side_effect = [ValueError("bad"), 1]
            wizard._device_selection_step()
            assert wizard.selected_device == d1


class TestDeviceInfoStep:
    @pytest.mark.asyncio
    async def test_success(self):
        wizard = SetupWizard()
        wizard.selected_device = _make_device()
        report = _make_report()

        mock_extractor = MagicMock()

        async def mock_get_info():
            return report

        mock_extractor.get_device_info = mock_get_info

        with (
            patch("philips_airctrl.setup_wizard.click") as mock_click,
            patch("philips_airctrl.setup_wizard.DeviceInfoExtractor", return_value=mock_extractor),
        ):
            mock_bar = MagicMock()
            mock_click.progressbar.return_value.__enter__ = MagicMock(return_value=mock_bar)
            mock_click.progressbar.return_value.__exit__ = MagicMock(return_value=False)

            await wizard._device_info_step()
            assert wizard.device_info is not None

    @pytest.mark.asyncio
    async def test_failure(self):
        wizard = SetupWizard()
        wizard.selected_device = _make_device()

        mock_extractor = MagicMock()

        async def mock_get_info_fail():
            raise Exception("fail")

        mock_extractor.get_device_info = mock_get_info_fail

        with (
            patch("philips_airctrl.setup_wizard.click") as mock_click,
            patch("philips_airctrl.setup_wizard.DeviceInfoExtractor", return_value=mock_extractor),
        ):
            mock_bar = MagicMock()
            mock_click.progressbar.return_value.__enter__ = MagicMock(return_value=mock_bar)
            mock_click.progressbar.return_value.__exit__ = MagicMock(return_value=False)

            await wizard._device_info_step()
            assert wizard.device_info is None


class TestConfigurationStep:
    @pytest.mark.asyncio
    async def test_no_device_info(self):
        wizard = SetupWizard()
        wizard.device_info = None

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            await wizard._configuration_step()
            calls = [str(c) for c in mock_click.echo.call_args_list]
            assert any("No device information" in s for s in calls)

    @pytest.mark.asyncio
    async def test_saves_files(self, tmp_path):
        wizard = SetupWizard()
        wizard.selected_device = _make_device()
        wizard.device_info = _make_report()

        with (
            patch("philips_airctrl.setup_wizard.click"),
            patch("philips_airctrl.setup_wizard.Path") as mock_path_class,
        ):
            mock_path_class.home.return_value = tmp_path
            await wizard._configuration_step()

            output_dir = tmp_path / "philips_airpurifier_config"
            assert output_dir.exists()
            json_files = list(output_dir.glob("*_device_info.json"))
            yaml_files = list(output_dir.glob("*_ha_config.yaml"))
            summary_files = list(output_dir.glob("*_summary.txt"))
            assert len(json_files) == 1
            assert len(yaml_files) == 1
            assert len(summary_files) == 1


class TestNextSteps:
    def test_no_open(self):
        wizard = SetupWizard()

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            mock_click.confirm.return_value = False
            wizard._next_steps()
            mock_click.launch.assert_not_called()

    def test_open_github(self):
        wizard = SetupWizard()

        with patch("philips_airctrl.setup_wizard.click") as mock_click:
            mock_click.confirm.return_value = True
            wizard._next_steps()
            mock_click.launch.assert_called_once()


class TestDisplayDevicesTable:
    def test_with_status(self):
        wizard = SetupWizard()
        wizard.discovered_devices = [_make_device()]

        with patch("philips_airctrl.setup_wizard.click"):
            wizard._display_devices_table()

    def test_without_status(self):
        wizard = SetupWizard()
        wizard.discovered_devices = [DeviceInfo(ip="192.168.1.50")]

        with patch("philips_airctrl.setup_wizard.click"):
            wizard._display_devices_table()


class TestDisplayDeviceSummary:
    def test_display(self):
        wizard = SetupWizard()
        wizard.selected_device = _make_device()
        wizard.device_info = _make_report()

        with patch("philips_airctrl.setup_wizard.click"):
            wizard._display_device_summary()


class TestGenerateSummaryReport:
    def test_report_content(self):
        wizard = SetupWizard()
        wizard.selected_device = _make_device()
        wizard.device_info = _make_report()

        report = wizard._generate_summary_report()
        assert "Living Room" in report
        assert "AC4220" in report
        assert "SN123" in report
        assert "DEVICE INFORMATION" in report
        assert "CAPABILITIES" in report
        assert "SENSORS" in report
        assert "CONTROLS" in report
        assert "HOME ASSISTANT INTEGRATION" in report


class TestRequireState:
    """Steps that run out of order fail with a clear error, not AttributeError."""

    def test_require_device_raises_without_selection(self):
        with pytest.raises(RuntimeError, match="No device selected"):
            SetupWizard()._require_device()

    def test_require_report_raises_without_info(self):
        wizard = SetupWizard()
        wizard.selected_device = _make_device()
        with pytest.raises(RuntimeError, match="No device information gathered"):
            wizard._require_report()


class TestConfigurationStepEdgeCases:
    @pytest.mark.asyncio
    async def test_unnamed_device_without_ha_config(self, tmp_path):
        wizard = SetupWizard()
        wizard.selected_device = DeviceInfo(ip="192.168.1.50")
        wizard.device_info = _make_report().model_copy(update={"home_assistant": None})

        with (
            patch("philips_airctrl.setup_wizard.click"),
            patch("philips_airctrl.setup_wizard.Path") as mock_path_class,
        ):
            mock_path_class.home.return_value = tmp_path
            await wizard._configuration_step()

        yaml_file = tmp_path / "philips_airpurifier_config" / "192.168.1.50_ha_config.yaml"
        assert yaml_file.read_text() == "air_purifier: {}\n"
