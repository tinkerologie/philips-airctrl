"""Device information extraction and formatting for Home Assistant integration."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from philips_airctrl.coap.client import Client
from philips_airctrl.models import (
    ConnectionInfo,
    DeviceCapabilities,
    DeviceReport,
    FieldDefinition,
    FieldValue,
    HAConfig,
    HADeviceInfo,
    SensorConfig,
)

logger = logging.getLogger(__name__)


# Known device status fields and their meanings.
# Covers Gen 1 (string keys), Gen 2 (D01-xx/D03-xx), and Gen 3 (D01Sxx/D03xxx).
# Descriptions are aligned with the ha-philips-airpurifier Home Assistant integration.
DEVICE_FIELDS: dict[str, FieldDefinition] = {
    # ── Gen 3 device identification (D01Sxx) ──────────────────────────
    "D01S03": FieldDefinition(name="device_name", type="string", description="Device name"),
    "D01S04": FieldDefinition(name="device_nickname", type="string", description="Device nickname"),
    "D01S05": FieldDefinition(name="model_number", type="string", description="Model number"),
    "D01S0D": FieldDefinition(name="serial_number", type="string", description="Serial number"),
    "D01S12": FieldDefinition(
        name="firmware_version", type="string", description="Firmware version"
    ),
    # ── Gen 2 device identification (D01-xx) ──────────────────────────
    "D01-03": FieldDefinition(name="device_name", type="string", description="Device name"),
    "D01-05": FieldDefinition(name="model_number", type="string", description="Model number"),
    "D01-07": FieldDefinition(name="language", type="string", description="Language setting"),
    "D01-21": FieldDefinition(
        name="firmware_version", type="string", description="Firmware version"
    ),
    # ── Gen 1 device identification ───────────────────────────────────
    "name": FieldDefinition(name="device_name", type="string", description="Device name"),
    "type": FieldDefinition(name="device_type", type="string", description="Device type"),
    "modelid": FieldDefinition(name="model_number", type="string", description="Model ID"),
    "swversion": FieldDefinition(
        name="firmware_version", type="string", description="Firmware version"
    ),
    # ── Common device identification ──────────────────────────────────
    "DeviceId": FieldDefinition(name="device_id", type="string", description="Unique device ID"),
    "DeviceVersion": FieldDefinition(
        name="device_version", type="string", description="Device hardware version"
    ),
    "ProductId": FieldDefinition(name="product_id", type="string", description="Product ID"),
    "WifiVersion": FieldDefinition(
        name="wifi_version", type="string", description="WiFi module version"
    ),
    # ── Gen 3 device status (D011xx / D012xx) ─────────────────────────
    "D01102": FieldDefinition(name="error_code", type="integer", description="Error code"),
    "D01107": FieldDefinition(name="warning_code", type="integer", description="Warning code"),
    "D01108": FieldDefinition(name="device_status", type="integer", description="Device status"),
    "D01109": FieldDefinition(
        name="connection_status", type="integer", description="Connection status"
    ),
    "D0110A": FieldDefinition(
        name="update_available", type="integer", description="Update available"
    ),
    "D0110C": FieldDefinition(
        name="temperature_device", type="integer", description="Temperature (°C)"
    ),
    "D0110F": FieldDefinition(name="language", type="integer", description="Language setting"),
    "D01213": FieldDefinition(
        name="child_lock_device", type="integer", description="Child lock (device level)"
    ),
    # ── Gen 3 sensors (D03xxx) ────────────────────────────────────────
    "D03120": FieldDefinition(
        name="indoor_allergen_index",
        type="integer",
        description="Indoor Allergen Index (IAI)",
    ),
    "D03122": FieldDefinition(name="gas_level", type="integer", description="Gas/TVOC level"),
    "D03125": FieldDefinition(name="humidity", type="integer", description="Current humidity (%)"),
    "D03221": FieldDefinition(name="pm25", type="integer", description="PM2.5 (µg/m³)"),
    "D03224": FieldDefinition(
        name="temperature", type="integer", description="Temperature (value/10 = °C)"
    ),
    "D0312C": FieldDefinition(
        name="air_quality_index", type="integer", description="Air quality index"
    ),
    # ── Gen 3 controls (D03xxx) ───────────────────────────────────────
    "D03102": FieldDefinition(name="power", type="integer", description="Power (1=ON, 0=OFF)"),
    "D03103": FieldDefinition(
        name="child_lock", type="integer", description="Child lock (1=locked, 0=unlocked)"
    ),
    "D03105": FieldDefinition(
        name="display_backlight",
        type="integer",
        description="Display backlight brightness (0-100, 101=auto)",
    ),
    "D03106": FieldDefinition(
        name="child_lock_alt",
        type="integer",
        description="Child lock alternate (model-specific)",
    ),
    "D0310A": FieldDefinition(
        name="mode_a",
        type="integer",
        description="Function selector (1=fan, 2=purify, 3=auto, 4=humidify)",
    ),
    "D0310C": FieldDefinition(
        name="mode_b",
        type="integer",
        description="Speed preset (0=auto, 17=sleep, 18=turbo)",
    ),
    "D0310D": FieldDefinition(
        name="mode_c", type="integer", description="Fan speed / secondary mode"
    ),
    "D0310E": FieldDefinition(
        name="target_temperature",
        type="integer",
        description="Target temperature (1-37 °C)",
    ),
    "D03110": FieldDefinition(
        name="timer",
        type="integer",
        description="Timer setting (0=off, 1=30min, 2-13=1h-12h)",
    ),
    "D03112": FieldDefinition(
        name="function_mode", type="integer", description="Function mode setting"
    ),
    "D03115": FieldDefinition(name="auto_mode", type="integer", description="Auto mode"),
    "D0311F": FieldDefinition(name="sleep_mode", type="integer", description="Sleep mode"),
    "D03128": FieldDefinition(
        name="humidity_target", type="integer", description="Target humidity (30-70%)"
    ),
    "D03130": FieldDefinition(
        name="beep", type="integer", description="Beep/sound (100=ON, 0=OFF)"
    ),
    "D03134": FieldDefinition(
        name="standby_sensors",
        type="integer",
        description="Standby sensors monitoring (1=ON, 0=OFF)",
    ),
    "D03135": FieldDefinition(
        name="lamp_mode",
        type="integer",
        description="Lamp mode (0=off, 1=air quality, 2=ambient)",
    ),
    "D03136": FieldDefinition(
        name="lamp_mode_alt",
        type="integer",
        description="Lamp mode alternate (model-specific)",
    ),
    "D03137": FieldDefinition(
        name="ambient_light_mode",
        type="integer",
        description="Ambient light (1=warm, 2=dawn, 3=calm, 4=breath)",
    ),
    "D03138": FieldDefinition(
        name="auto_quickdry_mode",
        type="integer",
        description="Auto quick-dry mode (1=ON, 0=OFF)",
    ),
    "D03139": FieldDefinition(
        name="quickdry_mode",
        type="integer",
        description="Quick-dry mode (1=ON, 0=OFF)",
    ),
    "D0312A": FieldDefinition(
        name="preferred_index",
        type="integer",
        description="Preferred air quality index (0=IAI, 1=PM2.5, 2=Gas)",
    ),
    "D0312B": FieldDefinition(name="humidifying", type="integer", description="Humidifying status"),
    "D0312D": FieldDefinition(
        name="display_backlight_alt",
        type="integer",
        description="Display backlight alternate (0-100)",
    ),
    "D0313B": FieldDefinition(
        name="timer_remaining_alt",
        type="integer",
        description="Timer remaining (model-specific, minutes)",
    ),
    "D0313F": FieldDefinition(
        name="heating_status",
        type="integer",
        description="Heating status (0=not heating, 65=high, 66=low, 67=medium)",
    ),
    "D03180": FieldDefinition(
        name="auto_plus_ai", type="integer", description="Auto Plus AI mode (1=ON, 0=OFF)"
    ),
    "D03182": FieldDefinition(
        name="schedule_enabled", type="integer", description="Schedule enabled"
    ),
    "D03211": FieldDefinition(
        name="timer_remaining",
        type="integer",
        description="Timer remaining (minutes)",
    ),
    "D03240": FieldDefinition(
        name="error_code_device",
        type="integer",
        description="Error code bitmask (bit 8 = out of water)",
    ),
    "D0320F": FieldDefinition(
        name="oscillation",
        type="integer",
        description="Oscillation/swing angle (0=OFF, 30-350 degrees)",
    ),
    "D03R81": FieldDefinition(
        name="schedule_data", type="string", description="Schedule/mode data (base64)"
    ),
    # ── Gen 2 sensors (D03-xx) ────────────────────────────────────────
    "D03-32": FieldDefinition(
        name="indoor_allergen_index",
        type="integer",
        description="Indoor Allergen Index (IAI)",
    ),
    "D03-33": FieldDefinition(name="pm25", type="integer", description="PM2.5 (µg/m³)"),
    # ── Gen 2 controls (D03-xx) ───────────────────────────────────────
    "D03-02": FieldDefinition(name="power", type="string", description="Power (ON/OFF)"),
    "D03-05": FieldDefinition(
        name="display_backlight",
        type="integer",
        description="Display backlight brightness (0-100)",
    ),
    "D03-12": FieldDefinition(name="mode", type="string", description="Operating mode"),
    "D03-42": FieldDefinition(
        name="preferred_index", type="string", description="Preferred display index"
    ),
    # ── Gen 1 sensors ─────────────────────────────────────────────────
    "pm25": FieldDefinition(name="pm25", type="integer", description="PM2.5 (µg/m³)"),
    "iaql": FieldDefinition(
        name="indoor_allergen_index",
        type="integer",
        description="Indoor Allergen Index (1-12)",
    ),
    "tvoc": FieldDefinition(
        name="tvoc", type="integer", description="Total Volatile Organic Compounds"
    ),
    "rh": FieldDefinition(name="humidity", type="integer", description="Relative humidity (%)"),
    "temp": FieldDefinition(name="temperature", type="integer", description="Temperature (°C)"),
    # ── Gen 1 controls ────────────────────────────────────────────────
    "pwr": FieldDefinition(name="power", type="string", description="Power (1=ON, 0=OFF)"),
    "mode": FieldDefinition(
        name="mode",
        type="string",
        description="Mode (P=auto, A=allergen, S=sleep, M=manual, T=turbo)",
    ),
    "om": FieldDefinition(
        name="fan_speed",
        type="string",
        description="Fan speed (1-3, s=silent, t=turbo)",
    ),
    "func": FieldDefinition(
        name="function",
        type="string",
        description="Function (P=purify, PH=purify+humidify)",
    ),
    "aqil": FieldDefinition(
        name="light_brightness",
        type="integer",
        description="Light brightness (0-100)",
    ),
    "aqit": FieldDefinition(
        name="air_quality_threshold",
        type="integer",
        description="Air quality notification threshold",
    ),
    "uil": FieldDefinition(
        name="button_light", type="string", description="Button light/beep (1=ON, 0=OFF)"
    ),
    "ddp": FieldDefinition(
        name="preferred_index",
        type="string",
        description="Display index (0=IAI, 1=PM2.5, 2=Gas, 3=Humidity)",
    ),
    "cl": FieldDefinition(name="child_lock", type="boolean", description="Child lock"),
    "dt": FieldDefinition(name="timer", type="integer", description="Timer setting (hours)"),
    "dtrs": FieldDefinition(
        name="timer_remaining",
        type="integer",
        description="Timer remaining (minutes)",
    ),
    "rhset": FieldDefinition(
        name="humidity_target", type="integer", description="Target humidity (%)"
    ),
    "wl": FieldDefinition(name="water_level", type="integer", description="Water level (%)"),
    "err": FieldDefinition(name="error_code", type="integer", description="Error code"),
    "language": FieldDefinition(name="language", type="string", description="Language setting"),
    "ota": FieldDefinition(name="ota_update", type="string", description="OTA update status"),
    # ── Gen 1 filters ─────────────────────────────────────────────────
    "fltsts0": FieldDefinition(
        name="pre_filter_remaining",
        type="integer",
        description="Pre-filter hours remaining",
    ),
    "fltsts1": FieldDefinition(
        name="hepa_filter_remaining",
        type="integer",
        description="HEPA filter hours remaining",
    ),
    "fltsts2": FieldDefinition(
        name="carbon_filter_remaining",
        type="integer",
        description="Active carbon filter hours remaining",
    ),
    "flttotal0": FieldDefinition(
        name="pre_filter_total",
        type="integer",
        description="Pre-filter total hours",
    ),
    "flttotal1": FieldDefinition(
        name="hepa_filter_total",
        type="integer",
        description="HEPA filter total hours",
    ),
    "flttotal2": FieldDefinition(
        name="carbon_filter_total",
        type="integer",
        description="Active carbon filter total hours",
    ),
    "fltt0": FieldDefinition(name="pre_filter_type", type="string", description="Pre-filter type"),
    "fltt1": FieldDefinition(
        name="hepa_filter_type", type="string", description="HEPA filter type"
    ),
    "fltt2": FieldDefinition(
        name="carbon_filter_type",
        type="string",
        description="Active carbon filter type",
    ),
    "wicksts": FieldDefinition(
        name="wick_filter_remaining",
        type="integer",
        description="Wick filter hours remaining",
    ),
    "wicktotal": FieldDefinition(
        name="wick_filter_total",
        type="integer",
        description="Wick filter total hours",
    ),
    "wickt": FieldDefinition(
        name="wick_filter_type", type="string", description="Wick filter type"
    ),
    # ── Gen 2 filters (D05-xx) ────────────────────────────────────────
    "D05-02": FieldDefinition(
        name="nanoprotect_filter_type",
        type="string",
        description="NanoProtect filter type",
    ),
    "D05-07": FieldDefinition(
        name="nanoprotect_prefilter_total",
        type="integer",
        description="NanoProtect pre-filter total hours",
    ),
    "D05-08": FieldDefinition(
        name="nanoprotect_filter_total",
        type="integer",
        description="NanoProtect filter total hours",
    ),
    "D05-13": FieldDefinition(
        name="nanoprotect_prefilter_remaining",
        type="integer",
        description="NanoProtect pre-filter hours remaining",
    ),
    "D05-14": FieldDefinition(
        name="nanoprotect_filter_remaining",
        type="integer",
        description="NanoProtect filter hours remaining",
    ),
    # ── Gen 3 filters (D05xxx) ────────────────────────────────────────
    "D05102": FieldDefinition(name="filter_type", type="integer", description="Filter type"),
    "D05207": FieldDefinition(
        name="nanoprotect_prefilter_total",
        type="integer",
        description="NanoProtect pre-filter total hours",
    ),
    "D05408": FieldDefinition(
        name="nanoprotect_filter_total",
        type="integer",
        description="NanoProtect filter total hours",
    ),
    "D0520D": FieldDefinition(
        name="nanoprotect_prefilter_remaining",
        type="integer",
        description="NanoProtect pre-filter hours remaining",
    ),
    "D0540E": FieldDefinition(
        name="nanoprotect_filter_remaining",
        type="integer",
        description="NanoProtect filter hours remaining",
    ),
    # ── System / diagnostic fields ────────────────────────────────────
    "Runtime": FieldDefinition(
        name="runtime", type="integer", description="Device runtime (milliseconds)"
    ),
    "rssi": FieldDefinition(
        name="wifi_signal", type="integer", description="WiFi signal strength (dBm)"
    ),
    "free_memory": FieldDefinition(
        name="free_memory", type="integer", description="Free memory (bytes)"
    ),
    "StatusType": FieldDefinition(
        name="status_type", type="string", description="Status message type"
    ),
    "ConnectType": FieldDefinition(
        name="connect_type", type="string", description="Connection type"
    ),
    "otacheck": FieldDefinition(
        name="ota_check", type="boolean", description="OTA update check flag"
    ),
    "wifilog": FieldDefinition(name="wifi_log", type="boolean", description="WiFi logging enabled"),
    "blelog": FieldDefinition(name="ble_log", type="integer", description="BLE logging level"),
}

DEVICE_FIELD_KEYS = frozenset(
    [
        # Gen 3
        "D01S03",
        "D01S04",
        "D01S05",
        "D01S0D",
        "D01S12",
        # Gen 2
        "D01-03",
        "D01-05",
        "D01-21",
        # Gen 1
        "name",
        "type",
        "modelid",
        "swversion",
        # Common
        "DeviceId",
        "DeviceVersion",
        "ProductId",
        "WifiVersion",
    ]
)
SENSOR_FIELD_KEYS = frozenset(
    [
        # Gen 3
        "D03120",
        "D03122",
        "D03125",
        "D03221",
        "D03224",
        "D0312C",
        # Gen 2
        "D03-32",
        "D03-33",
        # Gen 1
        "pm25",
        "iaql",
        "tvoc",
        "rh",
        "temp",
        # Common
        "rssi",
    ]
)
CONTROL_FIELD_KEYS = frozenset(
    [
        # Gen 3
        "D03102",
        "D03103",
        "D03105",
        "D03106",
        "D0310A",
        "D0310C",
        "D0310D",
        "D0310E",
        "D03110",
        "D03112",
        "D03115",
        "D0311F",
        "D03128",
        "D03130",
        "D03134",
        "D03135",
        "D03136",
        "D03137",
        "D03138",
        "D03139",
        "D0312A",
        "D0312B",
        "D0312D",
        "D0313B",
        "D0313F",
        "D03180",
        "D03182",
        "D03211",
        "D03240",
        "D0320F",
        # Gen 2
        "D03-02",
        "D03-05",
        "D03-12",
        "D03-42",
        # Gen 1
        "pwr",
        "mode",
        "om",
        "func",
        "aqil",
        "aqit",
        "uil",
        "ddp",
        "cl",
        "dt",
        "dtrs",
        "rhset",
        "wl",
        "err",
        "language",
        "ota",
    ]
)
FILTER_FIELD_KEYS = frozenset(
    [
        # Gen 3
        "D05102",
        "D05207",
        "D05408",
        "D0520D",
        "D0540E",
        # Gen 2
        "D05-02",
        "D05-07",
        "D05-08",
        "D05-13",
        "D05-14",
        # Gen 1
        "fltsts0",
        "fltsts1",
        "fltsts2",
        "flttotal0",
        "flttotal1",
        "flttotal2",
        "fltt0",
        "fltt1",
        "fltt2",
        "wicksts",
        "wicktotal",
        "wickt",
    ]
)


def get_field_category(key: str) -> str:
    """Determine the category for a field."""
    if key in DEVICE_FIELD_KEYS:
        return "device"
    if key in SENSOR_FIELD_KEYS:
        return "sensors"
    if key in CONTROL_FIELD_KEYS:
        return "controls"
    if key in FILTER_FIELD_KEYS:
        return "filters"
    return "system"


def analyze_capabilities(status: dict[str, Any]) -> DeviceCapabilities:
    """Analyze device capabilities based on available status fields."""
    filter_types: list[str] = []
    # Gen 3 NanoProtect filters
    if "D0520D" in status:
        filter_types.append("nanoprotect_prefilter")
    if "D0540E" in status:
        filter_types.append("nanoprotect_filter")
    # Gen 1 filters
    if "fltsts0" in status:
        filter_types.append("pre_filter")
    if "fltsts1" in status:
        filter_types.append("hepa_filter")
    if "fltsts2" in status:
        filter_types.append("carbon_filter")
    if "wicksts" in status:
        filter_types.append("wick_filter")

    return DeviceCapabilities(
        has_humidifier="D03128" in status
        or "D0312B" in status
        or "rhset" in status
        or "func" in status,
        has_purifier="D0312B" in status or "D0310A" in status or "func" in status,
        has_pm25_sensor="D03221" in status or "pm25" in status or "D03-33" in status,
        has_humidity_sensor="D03125" in status or "rh" in status,
        has_allergen_sensor="D03120" in status or "iaql" in status or "D03-32" in status,
        has_gas_sensor="D03122" in status or "tvoc" in status,
        has_display="D03105" in status or "D0312D" in status or "aqil" in status,
        has_timer="D03110" in status or "dt" in status,
        has_schedule="D03182" in status or "D03R81" in status,
        has_child_lock="D03103" in status or "cl" in status or "D01213" in status,
        has_sleep_mode="D0311F" in status,
        has_turbo_mode="D03211" in status,
        has_allergen_mode="D03120" in status or "iaql" in status,
        has_bacteria_virus_mode="D03240" in status or "err" in status,
        filter_types=filter_types,
    )


def generate_ha_config(host: str, status: dict[str, Any]) -> HAConfig:
    """Generate Home Assistant configuration suggestions."""
    model = status.get("D01S05") or status.get("D01-05") or status.get("modelid", "Unknown")
    name = status.get("D01S03") or status.get("D01-03") or status.get("name", "Air Purifier")
    capabilities = analyze_capabilities(status)

    supported_features: list[str] = []
    if capabilities.has_purifier:
        supported_features.extend(["fan_speed", "power"])
    if capabilities.has_humidifier:
        supported_features.append("humidity_target")
    if capabilities.has_display:
        supported_features.append("display_brightness")

    sensors: list[SensorConfig] = []
    if capabilities.has_pm25_sensor:
        pm25_key = "D03221" if "D03221" in status else "pm25"
        sensors.append(SensorConfig(name="PM2.5", key=pm25_key, unit="µg/m³", device_class="pm25"))
    if capabilities.has_humidity_sensor:
        humidity_key = "D03125" if "D03125" in status else "rh"
        sensors.append(
            SensorConfig(name="Humidity", key=humidity_key, unit="%", device_class="humidity")
        )
    for filter_type in capabilities.filter_types:
        if filter_type == "nanoprotect_filter":
            sensors.append(
                SensorConfig(
                    name="NanoProtect Filter",
                    key="D0540E",
                    unit="hours",
                    device_class="duration",
                )
            )

    return HAConfig(
        host=host,
        name=name,
        model=model,
        unique_id=status.get("DeviceId", f"philips_{host.replace('.', '_')}"),
        device_info=HADeviceInfo(
            identifiers=[status.get("DeviceId", f"philips_{host}")],
            name=name,
            model=model,
            sw_version=status.get("D01S12")
            or status.get("D01-21")
            or status.get("swversion", "Unknown"),
            hw_version=status.get("WifiVersion", "Unknown"),
        ),
        supported_features=supported_features,
        sensors=sensors,
    )


class DeviceInfoExtractor:
    """Extract comprehensive device information for Home Assistant integration."""

    def __init__(self, host: str, port: int = 5683) -> None:
        self.host = host
        self.port = port

    async def get_device_info(self) -> DeviceReport:
        """Get comprehensive device information."""
        client = await Client.create(host=self.host, port=self.port)

        try:
            status, max_age = await client.get_status(observe=False)

            categories: dict[str, dict[str, FieldValue]] = {
                "device": {},
                "sensors": {},
                "controls": {},
                "filters": {},
                "system": {},
            }
            for key, value in status.items():
                if key in DEVICE_FIELDS:
                    field_def = DEVICE_FIELDS[key]
                    categories[get_field_category(key)][field_def.name] = FieldValue(
                        value=value,
                        type=field_def.type,
                        description=field_def.description,
                        raw_key=key,
                    )
                else:
                    categories["system"][key] = FieldValue(
                        value=value,
                        type=type(value).__name__,
                        description="Unknown field",
                        raw_key=key,
                    )

            return DeviceReport(
                connection=ConnectionInfo(
                    host=self.host,
                    port=self.port,
                    max_age=max_age,
                ),
                device=categories["device"],
                sensors=categories["sensors"],
                controls=categories["controls"],
                filters=categories["filters"],
                system=categories["system"],
                raw_status=status,
                capabilities=analyze_capabilities(status),
                home_assistant=generate_ha_config(self.host, status),
            )

        finally:
            await client.shutdown()

    def export_json(self, device_info: DeviceReport, pretty: bool = True) -> str:
        """Export device info as JSON."""
        if pretty:
            return device_info.model_dump_json(indent=2)
        return device_info.model_dump_json()

    def export_yaml(self, device_info: DeviceReport) -> str:
        """Export device info as YAML."""
        return yaml.safe_dump(
            device_info.model_dump(mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
