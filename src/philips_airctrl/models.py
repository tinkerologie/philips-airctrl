"""Pydantic models for Philips air purifier data structures."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Port = Annotated[int, Field(ge=1, le=65535)]
"""A valid TCP/UDP port number."""

StatusDict = dict[str, JsonValue]
"""A decoded device status payload (JSON object keyed by status field)."""


class _FrozenModel(BaseModel):
    """Base for all library models.

    Models are immutable once built (``frozen=True``) and reject unknown
    keyword arguments (``extra="forbid"``) so typos fail loudly instead of
    being silently dropped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class DeviceInfo(_FrozenModel):
    """Information about a discovered device."""

    ip: str
    port: Port = 5683
    model: str | None = None
    name: str | None = None
    device_id: str | None = None
    product_id: str | None = None
    firmware_version: str | None = None
    wifi_version: str | None = None
    serial_number: str | None = None
    status: StatusDict | None = None
    reachable: bool = False


class FieldDefinition(_FrozenModel):
    """Definition of a device status field."""

    name: str
    type: Literal["string", "integer", "boolean"]
    description: str


class FieldValue(_FrozenModel):
    """A resolved device field with its value."""

    value: JsonValue
    type: str
    description: str
    raw_key: str


class DeviceCapabilities(_FrozenModel):
    """Analyzed device capabilities based on available status fields."""

    has_humidifier: bool = False
    has_purifier: bool = False
    has_pm25_sensor: bool = False
    has_humidity_sensor: bool = False
    has_allergen_sensor: bool = False
    has_gas_sensor: bool = False
    has_display: bool = False
    has_timer: bool = False
    has_schedule: bool = False
    has_child_lock: bool = False
    has_sleep_mode: bool = False
    has_turbo_mode: bool = False
    has_allergen_mode: bool = False
    has_bacteria_virus_mode: bool = False
    filter_types: list[str] = Field(default_factory=list)


class SensorConfig(_FrozenModel):
    """Home Assistant sensor configuration."""

    name: str
    key: str
    unit: str
    device_class: str


class HADeviceInfo(_FrozenModel):
    """Home Assistant device info block."""

    identifiers: list[str]
    name: str
    manufacturer: str = "Philips"
    model: str
    sw_version: str
    hw_version: str


class HAConfig(_FrozenModel):
    """Home Assistant configuration suggestion."""

    platform: str = "philips_airpurifier"
    host: str
    name: str
    model: str
    unique_id: str
    device_info: HADeviceInfo
    supported_features: list[str] = Field(default_factory=list)
    sensors: list[SensorConfig] = Field(default_factory=list)
    binary_sensors: list[dict[str, str]] = Field(default_factory=list)
    switches: list[dict[str, str]] = Field(default_factory=list)


class ConnectionInfo(_FrozenModel):
    """Device connection information."""

    host: str
    port: Port
    max_age: Annotated[int, Field(ge=0)]
    protocol: str = "CoAP"
    encryption: str = "AES-CBC"


class DeviceReport(_FrozenModel):
    """Comprehensive device information report."""

    connection: ConnectionInfo
    device: dict[str, FieldValue] = Field(default_factory=dict)
    sensors: dict[str, FieldValue] = Field(default_factory=dict)
    controls: dict[str, FieldValue] = Field(default_factory=dict)
    filters: dict[str, FieldValue] = Field(default_factory=dict)
    system: dict[str, FieldValue] = Field(default_factory=dict)
    raw_status: StatusDict = Field(default_factory=dict)
    capabilities: DeviceCapabilities = Field(default_factory=DeviceCapabilities)
    home_assistant: HAConfig | None = None
