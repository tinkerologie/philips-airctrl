"""Tests for the Pydantic models."""

import pytest
from pydantic import ValidationError

from philips_airctrl.models import (
    ConnectionInfo,
    DeviceCapabilities,
    DeviceInfo,
    DeviceReport,
    FieldDefinition,
    FieldValue,
    HAConfig,
    HADeviceInfo,
    SensorConfig,
)


class TestDeviceInfo:
    def test_defaults(self):
        info = DeviceInfo(ip="192.168.1.1")
        assert info.ip == "192.168.1.1"
        assert info.port == 5683
        assert info.model is None
        assert info.name is None
        assert info.device_id is None
        assert info.product_id is None
        assert info.firmware_version is None
        assert info.wifi_version is None
        assert info.serial_number is None
        assert info.status is None
        assert info.reachable is False

    def test_full_construction(self):
        info = DeviceInfo(
            ip="10.0.0.1",
            port=1234,
            model="AC4220",
            name="Living Room",
            device_id="abc123",
            product_id="prod1",
            firmware_version="1.0.0",
            wifi_version="2.0.0",
            serial_number="SN123",
            status={"power": True},
            reachable=True,
        )
        assert info.ip == "10.0.0.1"
        assert info.port == 1234
        assert info.model == "AC4220"
        assert info.reachable is True
        assert info.status == {"power": True}


class TestFieldDefinition:
    def test_creation(self):
        fd = FieldDefinition(name="power", type="boolean", description="Power on/off")
        assert fd.name == "power"
        assert fd.type == "boolean"
        assert fd.description == "Power on/off"


class TestFieldValue:
    def test_creation(self):
        fv = FieldValue(value=True, type="boolean", description="Power", raw_key="D03102")
        assert fv.value is True
        assert fv.type == "boolean"
        assert fv.raw_key == "D03102"


class TestDeviceCapabilities:
    def test_defaults(self):
        caps = DeviceCapabilities()
        assert caps.has_humidifier is False
        assert caps.has_purifier is False
        assert caps.filter_types == []

    def test_full(self):
        caps = DeviceCapabilities(
            has_humidifier=True,
            has_purifier=True,
            has_pm25_sensor=True,
            filter_types=["main_filter", "hepa_filter"],
        )
        assert caps.has_humidifier is True
        assert len(caps.filter_types) == 2


class TestSensorConfig:
    def test_creation(self):
        sc = SensorConfig(name="PM2.5", key="D03224", unit="ug/m3", device_class="pm25")
        assert sc.name == "PM2.5"
        assert sc.device_class == "pm25"


class TestHADeviceInfo:
    def test_creation(self):
        di = HADeviceInfo(
            identifiers=["abc"],
            name="Purifier",
            model="AC4220",
            sw_version="1.0",
            hw_version="2.0",
        )
        assert di.manufacturer == "Philips"
        assert di.identifiers == ["abc"]


class TestHAConfig:
    def test_defaults(self):
        config = HAConfig(
            host="192.168.1.1",
            name="Purifier",
            model="AC4220",
            unique_id="test123",
            device_info=HADeviceInfo(
                identifiers=["id1"],
                name="Purifier",
                model="AC4220",
                sw_version="1.0",
                hw_version="2.0",
            ),
        )
        assert config.platform == "philips_airpurifier"
        assert config.supported_features == []
        assert config.sensors == []
        assert config.binary_sensors == []
        assert config.switches == []


class TestConnectionInfo:
    def test_defaults(self):
        ci = ConnectionInfo(host="192.168.1.1", port=5683, max_age=60)
        assert ci.protocol == "CoAP"
        assert ci.encryption == "AES-CBC"


class TestDeviceReport:
    def test_defaults(self):
        report = DeviceReport(
            connection=ConnectionInfo(host="192.168.1.1", port=5683, max_age=60),
        )
        assert report.device == {}
        assert report.sensors == {}
        assert report.controls == {}
        assert report.filters == {}
        assert report.system == {}
        assert report.raw_status == {}
        assert report.capabilities.has_humidifier is False
        assert report.home_assistant is None

    def test_serialization(self):
        report = DeviceReport(
            connection=ConnectionInfo(host="192.168.1.1", port=5683, max_age=60),
            raw_status={"power": True},
        )
        data = report.model_dump(mode="json")
        assert data["connection"]["host"] == "192.168.1.1"
        assert data["raw_status"]["power"] is True

        json_str = report.model_dump_json()
        assert "192.168.1.1" in json_str


class TestModelConfig:
    """Models keep the pre-1.3 mutability and extra-field behaviour (no breaking change)."""

    def test_assignment_allowed(self):
        info = DeviceInfo(ip="192.168.1.1")
        info.reachable = True
        assert info.reachable is True

    def test_extra_fields_ignored(self):
        info = DeviceInfo(ip="192.168.1.1", unknown="value")  # type: ignore[call-arg]
        assert not hasattr(info, "unknown")

    def test_model_copy_update(self):
        info = DeviceInfo(ip="192.168.1.1")
        updated = info.model_copy(update={"reachable": True})
        assert updated.reachable is True
        assert info.reachable is False

    @pytest.mark.parametrize("port", [0, 65536, -1])
    def test_port_out_of_range(self, port):
        with pytest.raises(ValidationError):
            DeviceInfo(ip="192.168.1.1", port=port)
        with pytest.raises(ValidationError):
            ConnectionInfo(host="192.168.1.1", port=port, max_age=60)

    def test_negative_max_age_rejected(self):
        with pytest.raises(ValidationError):
            ConnectionInfo(host="192.168.1.1", port=5683, max_age=-1)

    def test_field_definition_type_is_constrained(self):
        with pytest.raises(ValidationError):
            FieldDefinition(name="x", type="float", description="x")  # type: ignore[arg-type]

    def test_status_must_be_json(self):
        with pytest.raises(ValidationError):
            DeviceInfo(ip="192.168.1.1", status={"bad": object()})

    def test_round_trip(self):
        report = DeviceReport(
            connection=ConnectionInfo(host="192.168.1.1", port=5683, max_age=60),
            raw_status={"pwr": "1", "nested": {"a": [1, 2.5, None]}},
        )
        assert DeviceReport.model_validate_json(report.model_dump_json()) == report
