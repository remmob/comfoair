"""Constants for the ComfoAir integration."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, REVOLUTIONS_PER_MINUTE, UnitOfTemperature

DOMAIN = "comfoair"

CONF_MODE = "mode"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE = "device"
CONF_BAUDRATE = "baudrate"
CONF_BYTESIZE = "bytesize"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"
CONF_CONTROL_TYPE = "control_type"

MODE_TCP = "tcp"
MODE_SERIAL = "serial"
MODES = [MODE_TCP, MODE_SERIAL]

CONTROL_TYPE_0_10V = "0_10v"
CONTROL_TYPE_RF = "rf"
CONTROL_TYPE_MANUAL = "manual"

CONTROL_TYPE_SENSOR_KEY = {
    CONTROL_TYPE_0_10V: "328",
    CONTROL_TYPE_RF: "329",
    CONTROL_TYPE_MANUAL: "330",
}
CONTROL_TYPE_SENSOR_KEYS_BY_TYPE = {
    CONTROL_TYPE_0_10V: {"316", "328"},
    CONTROL_TYPE_RF: {"317", "329"},
    CONTROL_TYPE_MANUAL: {"318", "330"},
}
CONTROL_TYPE_SENSOR_KEYS = {"316", "317", "318", "328", "329", "330"}

DEFAULT_NAME = "zehnder"
DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_DEVICE_ID = 1
DEFAULT_BAUDRATE = 19200
DEFAULT_BYTESIZE = 8
DEFAULT_PARITY = "E"
DEFAULT_STOPBITS = 1
DEFAULT_CONTROL_TYPE = CONTROL_TYPE_MANUAL

ATTR_MANUFACTURER = "Zehnder ComfoAir E300/E400 Modbus Integration"
ATTR_COPYRIGHT = "Mischa Bommer"
CONF_COMFOAIR_HUB = "comfoair_hub"

ALLOWED_BAUDRATES = [19200]
ALLOWED_BYTESIZES = [8]
ALLOWED_PARITIES = ["E"]
ALLOWED_STOPBITS = [1]

PLATFORMS = ["sensor"]

READ_RANGES = [
    (110, 1),
    (300, 16),
    (316, 4),
    (320, 2),
    (328, 3),
    (336, 1),
    (337, 2),
]

ON_OFF_STATUS = {
    0: "OFF",
    1: "ON",
}

BOOLEAN_REGISTERS = {
    "318",
    "319",
    "337",
    "338",
}


@dataclass
class ComfoAirModbusSensorEntityDescription(SensorEntityDescription):
    """ComfoAir sensor entities."""

    scale: float = 1.0
    signed: bool = False
    native_min_value: float | None = None
    native_max_value: float | None = None


SENSOR_TYPES: dict[str, ComfoAirModbusSensorEntityDescription] = {
    "connection_status": ComfoAirModbusSensorEntityDescription(
        key="connection_status",
        name="connection status",
        icon="mdi:lan-connect",
    ),
    "300": ComfoAirModbusSensorEntityDescription(
        key="300",
        name="intake air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "301": ComfoAirModbusSensorEntityDescription(
        key="301",
        name="pre-heating temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "303": ComfoAirModbusSensorEntityDescription(
        key="303",
        name="supply air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "304": ComfoAirModbusSensorEntityDescription(
        key="304",
        name="extract air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "305": ComfoAirModbusSensorEntityDescription(
        key="305",
        name="exhaust air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "306": ComfoAirModbusSensorEntityDescription(
        key="306",
        name="supply air humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
    ),
    "307": ComfoAirModbusSensorEntityDescription(
        key="307",
        name="exhaust air humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
    ),
    "308": ComfoAirModbusSensorEntityDescription(
        key="308",
        name="extract air humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
    ),
    "309": ComfoAirModbusSensorEntityDescription(
        key="309",
        name="intake air humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
    ),
    "310": ComfoAirModbusSensorEntityDescription(
        key="310",
        name="extract air fan",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
    ),
    "311": ComfoAirModbusSensorEntityDescription(
        key="311",
        name="supply air fan",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
    ),
    "312": ComfoAirModbusSensorEntityDescription(
        key="312",
        name="extract air flow",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "313": ComfoAirModbusSensorEntityDescription(
        key="313",
        name="supply air flow",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "314": ComfoAirModbusSensorEntityDescription(
        key="314",
        name="extract air fan speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "315": ComfoAirModbusSensorEntityDescription(
        key="315",
        name="supply air fan speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "316": ComfoAirModbusSensorEntityDescription(
        key="316",
        name="analog voltage c1",
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
    ),
    "317": ComfoAirModbusSensorEntityDescription(
        key="317",
        name="rf voltage",
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
    ),
    "318": ComfoAirModbusSensorEntityDescription(
        key="318",
        name="RF enabled",
    ),
    "319": ComfoAirModbusSensorEntityDescription(
        key="319",
        name="pre-heater state",
    ),
    "320": ComfoAirModbusSensorEntityDescription(
        key="320",
        name="extract air flow setpoint +- balance offset",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "321": ComfoAirModbusSensorEntityDescription(
        key="321",
        name="supply air flow setpoint",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "328": ComfoAirModbusSensorEntityDescription(
        key="328",
        name="0-10 v speed setting",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "329": ComfoAirModbusSensorEntityDescription(
        key="329",
        name="rf speed setting",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "330": ComfoAirModbusSensorEntityDescription(
        key="330",
        name="3-way switch",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "336": ComfoAirModbusSensorEntityDescription(
        key="336",
        name="runtime in days",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "337": ComfoAirModbusSensorEntityDescription(
        key="337",
        name="fireplace mode on/off",
        icon="mdi:fireplace",
    ),
    "338": ComfoAirModbusSensorEntityDescription(
        key="338",
        name="pre-heater on/off",
        icon="mdi:radiator",
    ),
}