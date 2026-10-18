"""Tests for the CLI module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from philips_airctrl.cli import (
    async_main,
    handle_device_info_command,
    handle_device_info_raw_command,
    handle_discover_command,
    handle_setup_command,
    main,
    parse_args,
)
from philips_airctrl.models import DeviceInfo, DeviceReport


class TestParseArgs:
    def test_status(self):
        args = parse_args(["status", "-H", "192.168.1.100"])
        assert args.host == "192.168.1.100"
        assert args.port == 5683
        assert args.command == "status"
        assert args.debug is False
        assert args.json is False

    def test_status_with_options(self):
        args = parse_args(["-D", "status", "-H", "192.168.1.100", "-P", "1234", "-J"])
        assert args.host == "192.168.1.100"
        assert args.port == 1234
        assert args.command == "status"
        assert args.debug is True
        assert args.json is True

    def test_status_observe(self):
        args = parse_args(["status-observe", "-H", "192.168.1.100", "--json"])
        assert args.host == "192.168.1.100"
        assert args.command == "status-observe"
        assert args.json is True

    def test_set_single_value(self):
        args = parse_args(["set", "-H", "192.168.1.100", "power=true"])
        assert args.host == "192.168.1.100"
        assert args.command == "set"
        assert args.values == ["power=true"]
        assert args.value_as_int is False

    def test_set_multiple_values(self):
        args = parse_args(["set", "-H", "192.168.1.100", "power=true", "mode=auto", "speed=3"])
        assert args.values == ["power=true", "mode=auto", "speed=3"]

    def test_set_with_int_flag(self):
        args = parse_args(["set", "-H", "192.168.1.100", "--int", "speed=3"])
        assert args.value_as_int is True

    def test_missing_host(self):
        with pytest.raises(SystemExit):
            parse_args(["status"])

    def test_missing_command(self):
        with pytest.raises(SystemExit):
            parse_args(["-H", "192.168.1.100"])

    def test_discover(self):
        args = parse_args(["discover"])
        assert args.command == "discover"
        assert args.network is None
        assert args.timeout == 5.0

    def test_discover_with_network(self):
        args = parse_args(["discover", "-n", "192.168.1.0/24", "-t", "10.0"])
        assert args.network == "192.168.1.0/24"
        assert args.timeout == 10.0

    def test_device_info(self):
        args = parse_args(["device-info", "-H", "192.168.1.100"])
        assert args.command == "device-info"
        assert args.format == "json"
        assert args.output is None

    def test_device_info_yaml(self):
        args = parse_args(["device-info", "-H", "192.168.1.100", "-f", "yaml", "-o", "out.yaml"])
        assert args.format == "yaml"
        assert args.output == "out.yaml"

    def test_setup(self):
        args = parse_args(["setup"])
        assert args.command == "setup"


class TestAsyncMain:
    @pytest.mark.asyncio
    async def test_status(self):
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ({"power": True}, 60)

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch("builtins.print") as mock_print,
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "status"
            mock_args.json = False
            mock_parse.return_value = mock_args

            await async_main()

            mock_client.get_status.assert_called_once()
            mock_client.shutdown.assert_called_once()
            assert mock_print.call_count == 2
            mock_print.assert_any_call({"power": True})
            mock_print.assert_any_call("max_age = 60")

    @pytest.mark.asyncio
    async def test_status_json(self):
        mock_client = AsyncMock()
        mock_client.get_status.return_value = ({"power": True}, 60)

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch("builtins.print") as mock_print,
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "status"
            mock_args.json = True
            mock_parse.return_value = mock_args

            await async_main()

            # JSON output
            mock_print.assert_called_once()
            output = mock_print.call_args[0][0]
            assert json.loads(output) == {"power": True}

    @pytest.mark.asyncio
    async def test_set_values(self):
        mock_client = AsyncMock()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "set"
            mock_args.values = ["power=true", "mode=auto", "speed=3"]
            mock_args.value_as_int = False
            mock_parse.return_value = mock_args

            await async_main()

            mock_client.set_control_values.assert_called_once_with(
                data={"power": True, "mode": "auto", "speed": "3"}
            )

    @pytest.mark.asyncio
    async def test_set_values_as_int(self):
        mock_client = AsyncMock()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "set"
            mock_args.values = ["speed=3", "level=5"]
            mock_args.value_as_int = True
            mock_parse.return_value = mock_args

            await async_main()

            mock_client.set_control_values.assert_called_once_with(data={"speed": 3, "level": 5})

    @pytest.mark.asyncio
    async def test_set_boolean_false(self):
        mock_client = AsyncMock()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "set"
            mock_args.values = ["power=true", "auto=false"]
            mock_args.value_as_int = False
            mock_parse.return_value = mock_args

            await async_main()

            mock_client.set_control_values.assert_called_once_with(
                data={"power": True, "auto": False}
            )

    @pytest.mark.asyncio
    async def test_set_invalid_int_value(self):
        mock_client = AsyncMock()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch("builtins.print") as mock_print,
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "set"
            mock_args.values = ["speed=notanint"]
            mock_args.value_as_int = True
            mock_parse.return_value = mock_args

            await async_main()

            mock_print.assert_any_call("Cannot encode value 'notanint' as int")
            mock_client.set_control_values.assert_not_called()

    @pytest.mark.asyncio
    async def test_keyboard_interrupt(self):
        mock_client = AsyncMock()
        mock_client.get_status.side_effect = KeyboardInterrupt()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "status"
            mock_args.json = False
            mock_parse.return_value = mock_args

            await async_main()
            mock_client.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_error(self):
        mock_client = AsyncMock()
        mock_client.get_status.side_effect = asyncio.CancelledError()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "status"
            mock_args.json = False
            mock_parse.return_value = mock_args

            await async_main()
            mock_client.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_command(self):
        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.handle_discover_command", new_callable=AsyncMock) as mock_hd,
        ):
            mock_args = MagicMock()
            mock_args.debug = False
            mock_args.command = "discover"
            mock_parse.return_value = mock_args

            await async_main()
            mock_hd.assert_called_once_with(mock_args)

    @pytest.mark.asyncio
    async def test_setup_command(self):
        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.handle_setup_command", new_callable=AsyncMock) as mock_hs,
        ):
            mock_args = MagicMock()
            mock_args.debug = False
            mock_args.command = "setup"
            mock_parse.return_value = mock_args

            await async_main()
            mock_hs.assert_called_once()

    @pytest.mark.asyncio
    async def test_debug_mode(self):
        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.handle_discover_command", new_callable=AsyncMock),
            patch("philips_airctrl.cli.logger") as mock_logger,
        ):
            mock_args = MagicMock()
            mock_args.debug = True
            mock_args.command = "discover"
            mock_parse.return_value = mock_args

            await async_main()
            mock_logger.setLevel.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_observe(self):
        mock_client = AsyncMock()

        async def mock_observe():
            yield {"power": True}
            yield {"power": False}

        mock_client.observe_status = mock_observe

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch("builtins.print") as mock_print,
            patch("sys.stdout"),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "status-observe"
            mock_args.json = False
            mock_parse.return_value = mock_args

            await async_main()

            assert mock_print.call_count == 2
            mock_print.assert_any_call({"power": True})
            mock_print.assert_any_call({"power": False})

    @pytest.mark.asyncio
    async def test_status_observe_json(self):
        mock_client = AsyncMock()

        async def mock_observe():
            yield {"power": True}

        mock_client.observe_status = mock_observe

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch("builtins.print") as mock_print,
            patch("sys.stdout"),
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "status-observe"
            mock_args.json = True
            mock_parse.return_value = mock_args

            await async_main()

            output = mock_print.call_args[0][0]
            assert json.loads(output) == {"power": True}

    @pytest.mark.asyncio
    async def test_device_info_command_from_main(self):
        mock_client = AsyncMock()

        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch(
                "philips_airctrl.cli.handle_device_info_command", new_callable=AsyncMock
            ) as mock_hdi,
        ):
            mock_args = MagicMock()
            mock_args.host = "192.168.1.100"
            mock_args.port = 5683
            mock_args.debug = False
            mock_args.command = "device-info"
            mock_parse.return_value = mock_args

            await async_main()
            mock_hdi.assert_called_once_with(mock_args)


class TestHandleDiscoverCommand:
    @pytest.mark.asyncio
    async def test_with_network(self):
        mock_discovery = MagicMock()
        mock_discovery.discover_single_network = AsyncMock(return_value=[])

        with (
            patch("philips_airctrl.cli.DeviceDiscovery", return_value=mock_discovery),
            patch("builtins.print"),
        ):
            args = MagicMock()
            args.timeout = 5.0
            args.network = "192.168.1.0/24"

            await handle_discover_command(args)
            mock_discovery.discover_single_network.assert_called_once_with("192.168.1.0/24")

    @pytest.mark.asyncio
    async def test_without_network(self):
        mock_discovery = MagicMock()
        mock_discovery.discover_devices = AsyncMock(return_value=[])
        mock_discovery.get_network_ranges.return_value = ["192.168.1.0/24"]

        with (
            patch("philips_airctrl.cli.DeviceDiscovery", return_value=mock_discovery),
            patch("builtins.print"),
        ):
            args = MagicMock()
            args.timeout = 5.0
            args.network = None

            await handle_discover_command(args)
            mock_discovery.discover_devices.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_devices_found(self):
        device = DeviceInfo(
            ip="192.168.1.50",
            model="AC4220",
            name="Living Room",
            firmware_version="1.0",
            status={"rssi": -50},
            reachable=True,
        )
        mock_discovery = MagicMock()
        mock_discovery.discover_devices = AsyncMock(return_value=[device])
        mock_discovery.get_network_ranges.return_value = ["192.168.1.0/24"]

        with (
            patch("philips_airctrl.cli.DeviceDiscovery", return_value=mock_discovery),
            patch("builtins.print") as mock_print,
        ):
            args = MagicMock()
            args.timeout = 5.0
            args.network = None

            await handle_discover_command(args)

            printed = [str(c) for c in mock_print.call_args_list]
            assert any("Found 1 device(s)" in s for s in printed)

    @pytest.mark.asyncio
    async def test_device_with_no_status(self):
        device = DeviceInfo(ip="192.168.1.50", status=None, reachable=False)
        mock_discovery = MagicMock()
        mock_discovery.discover_single_network = AsyncMock(return_value=[device])

        with (
            patch("philips_airctrl.cli.DeviceDiscovery", return_value=mock_discovery),
            patch("builtins.print"),
        ):
            args = MagicMock()
            args.timeout = 5.0
            args.network = "192.168.1.0/24"

            await handle_discover_command(args)


class TestHandleDeviceInfoCommand:
    @pytest.mark.asyncio
    async def test_json_output(self):
        mock_report = MagicMock(spec=DeviceReport)
        mock_extractor = MagicMock()
        mock_extractor.get_device_info = AsyncMock(return_value=mock_report)
        mock_extractor.export_json.return_value = '{"test": true}'

        with (
            patch("philips_airctrl.cli.DeviceInfoExtractor", return_value=mock_extractor),
            patch("builtins.print") as mock_print,
        ):
            args = MagicMock()
            args.host = "192.168.1.100"
            args.port = 5683
            args.format = "json"
            args.output = None

            await handle_device_info_command(args)

            mock_extractor.export_json.assert_called_once_with(mock_report, pretty=True)
            mock_print.assert_any_call('{"test": true}')

    @pytest.mark.asyncio
    async def test_yaml_output(self):
        mock_report = MagicMock(spec=DeviceReport)
        mock_extractor = MagicMock()
        mock_extractor.get_device_info = AsyncMock(return_value=mock_report)
        mock_extractor.export_yaml.return_value = "test: true\n"

        with (
            patch("philips_airctrl.cli.DeviceInfoExtractor", return_value=mock_extractor),
            patch("builtins.print"),
        ):
            args = MagicMock()
            args.host = "192.168.1.100"
            args.port = 5683
            args.format = "yaml"
            args.output = None

            await handle_device_info_command(args)
            mock_extractor.export_yaml.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_output(self, tmp_path):
        mock_report = MagicMock(spec=DeviceReport)
        mock_extractor = MagicMock()
        mock_extractor.get_device_info = AsyncMock(return_value=mock_report)
        mock_extractor.export_json.return_value = '{"test": true}'

        output_file = str(tmp_path / "output.json")

        with (
            patch("philips_airctrl.cli.DeviceInfoExtractor", return_value=mock_extractor),
            patch("builtins.print"),
        ):
            args = MagicMock()
            args.host = "192.168.1.100"
            args.port = 5683
            args.format = "json"
            args.output = output_file

            await handle_device_info_command(args)

            with open(output_file) as f:
                assert f.read() == '{"test": true}'


class TestHandleSetupCommand:
    @pytest.mark.asyncio
    async def test_runs_wizard(self):
        mock_wizard = MagicMock()
        mock_wizard.run = AsyncMock()

        with patch("philips_airctrl.cli.SetupWizard", return_value=mock_wizard):
            await handle_setup_command()
            mock_wizard.run.assert_called_once()


class TestMain:
    def test_main_runs(self):
        # Close the coroutine handed to the mocked asyncio.run so it is not
        # reported as "never awaited".
        with patch(
            "philips_airctrl.cli.asyncio.run", side_effect=lambda coro: coro.close()
        ) as mock_run:
            main()
            mock_run.assert_called_once()

    def test_main_keyboard_interrupt(self):
        def _interrupt(coro):
            coro.close()
            raise KeyboardInterrupt

        with patch("philips_airctrl.cli.asyncio.run", side_effect=_interrupt):
            main()  # Should not raise


class TestAsyncMainNoHost:
    @pytest.mark.asyncio
    async def test_no_host_attribute(self):
        """Test when host attribute is missing from args."""
        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch("builtins.print") as mock_print,
        ):
            mock_args = MagicMock(spec=[])  # no attributes
            mock_args.debug = False
            mock_args.command = "status"
            mock_parse.return_value = mock_args

            await async_main()
            mock_print.assert_any_call("Error: Host is required for this command")


class TestDeviceInfoRawParseArgs:
    def test_device_info_raw(self):
        args = parse_args(["device-info-raw", "-H", "192.168.1.100"])
        assert args.command == "device-info-raw"
        assert args.host == "192.168.1.100"
        assert args.port == 5683

    def test_device_info_raw_custom_port(self):
        args = parse_args(["device-info-raw", "-H", "192.168.1.100", "-P", "5684"])
        assert args.port == 5684


class TestHandleDeviceInfoRawCommand:
    @pytest.mark.asyncio
    async def test_prints_json(self):
        mock_client = AsyncMock()
        mock_client.get_device_info.return_value = {
            "modelid": "CX7550/01",
            "name": "My Fan",
            "device_id": "abc123",
        }

        with (
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
            patch("builtins.print") as mock_print,
        ):
            args = MagicMock()
            args.host = "192.168.1.100"
            args.port = 5683

            await handle_device_info_raw_command(args)

            mock_client.get_device_info.assert_called_once()
            mock_client.shutdown.assert_called_once()
            mock_print.assert_called_once()
            output = json.loads(mock_print.call_args[0][0])
            assert output["modelid"] == "CX7550/01"

    @pytest.mark.asyncio
    async def test_create_called_with_sync_false(self):
        """device-info-raw must create the client without the sync handshake."""
        mock_client = AsyncMock()
        mock_client.get_device_info.return_value = {"modelid": "AC1715/10"}

        with (
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client) as mock_create,
            patch("builtins.print"),
        ):
            args = MagicMock()
            args.host = "192.168.1.100"
            args.port = 5683

            await handle_device_info_raw_command(args)

            mock_create.assert_called_once_with(host="192.168.1.100", port=5683, sync=False)

    @pytest.mark.asyncio
    async def test_shutdown_called_on_error(self):
        """shutdown() must be called even when get_device_info() raises."""
        mock_client = AsyncMock()
        mock_client.get_device_info.side_effect = RuntimeError("boom")

        with (
            patch("philips_airctrl.cli.CoAPClient.create", return_value=mock_client),
        ):
            args = MagicMock()
            args.host = "192.168.1.100"
            args.port = 5683

            with pytest.raises(RuntimeError):
                await handle_device_info_raw_command(args)

            mock_client.shutdown.assert_called_once()


class TestAsyncMainDeviceInfoRaw:
    @pytest.mark.asyncio
    async def test_device_info_raw_dispatched(self):
        with (
            patch("philips_airctrl.cli.parse_args") as mock_parse,
            patch(
                "philips_airctrl.cli.handle_device_info_raw_command",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_args = MagicMock()
            mock_args.debug = False
            mock_args.command = "device-info-raw"
            mock_parse.return_value = mock_args

            await async_main()
            mock_handler.assert_called_once_with(mock_args)
