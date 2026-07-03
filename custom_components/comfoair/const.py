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
DEFAULT_DEWPOINT_DELTA = 1.0

ATTR_MANUFACTURER = "Zehnder ComfoAir E300/E400 Modbus Integration"
ATTR_COPYRIGHT = "Mischa Bommer"
CONF_COMFOAIR_HUB = "comfoair_hub"
CONF_DEWPOINT_DELTA = "dewpoint_delta"

# Notification configuration - Alarms
CONF_NOTIFY_ALARMS_MOBILE = "notify_alarms_mobile"
CONF_NOTIFY_ALARMS_PERSISTENT = "notify_alarms_persistent"
CONF_NOTIFY_ALARMS_SERVICES = "notify_alarms_services"
CONF_ALARM_NOTIFICATION_TITLE = "alarm_notification_title"
CONF_ALARM_DELAY = "alarm_delay"

# Notification configuration - Connection errors
CONF_NOTIFY_CONNECTION_ERRORS_MOBILE = "notify_connection_errors_mobile"
CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT = "notify_connection_errors_persistent"
CONF_NOTIFY_CONNECTION_ERRORS_SERVICES = "notify_connection_errors_services"
CONF_CONNECTION_ERROR_NOTIFICATION_TITLE = "connection_error_notification_title"
CONF_CONNECTION_ERROR_DELAY = "connection_error_delay"

DEFAULT_NOTIFY_ALARMS_MOBILE = False
DEFAULT_NOTIFY_ALARMS_PERSISTENT = False
DEFAULT_NOTIFY_ALARMS_SERVICES = ""
DEFAULT_ALARM_NOTIFICATION_TITLE = "ComfoAir in storing!"
DEFAULT_ALARM_DELAY = 60

DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE = False
DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT = False
DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES = ""
DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE = "ComfoAir verbindingsfout!"
DEFAULT_CONNECTION_ERROR_DELAY = 60

# Warning notifications (filter warning / frost protection warning) may only be
# sent between WARNING_QUIET_HOUR_END and WARNING_QUIET_HOUR_START; outside that
# window they are held and sent at WARNING_QUIET_HOUR_END instead.
WARNING_QUIET_HOUR_START = 23
WARNING_QUIET_HOUR_END = 7

ALLOWED_DEVICE_IDS = [1]
ALLOWED_BAUDRATES = [19200]
ALLOWED_BYTESIZES = [8]
ALLOWED_PARITIES = ["E"]
ALLOWED_STOPBITS = [1]

PLATFORMS = ["sensor", "binary_sensor"]

STATIC_READ_RANGES = [
    (105, 1),
    (110, 4),
    (115, 16),
]

READ_RANGES = [
    (101, 1),
    (300, 23),
    (325, 3),
    (328, 7),
    (336, 3),
    (344, 2),
    (400, 3),
]

ALARM_BITS: dict[str, list[tuple[int, str]]] = {
    "400": [
        (0, "T20 temperature sensor"),
        (1, "T21 temperature sensor"),
        (2, "T22 temperature sensor"),
        (3, "T11 temperature sensor"),
        (4, "T12 temperature sensor"),
        (5, "RH20 humidity sensor"),
        (6, "RH22 humidity sensor"),
        (7, "RH11 humidity sensor"),
        (8, "RH12 humidity sensor"),
        (9, "dp12 pressure sensor"),
        (10, "dp22 pressure sensor"),
        (11, "exhaust fan speed sensor"),
        (12, "supply fan speed sensor"),
        (13, "filter warning"),
        (14, "filter error"),
    ],
    "402": [
        (0, "preheater overheat"),
        (1, "preheater location"),
        (2, "preheater error"),
        (3, "bypass motor extract"),
        (4, "bypass motor outdoor"),
        (5, "frost protection warning"),
    ],
}

def alarm_data_key(reg_str: str | int, bit_pos: int) -> str:
    """Coordinator data key for a single ALARM_BITS entry."""
    return f"alarm_{reg_str}_{bit_pos}"


# Alarm bit data keys whose description contains "warning"; these are gated to
# the 07:00-23:00 notification window.
GATED_WARNING_KEYS: set[str] = {
    alarm_data_key(reg_str, bit_pos)
    for reg_str, bits in ALARM_BITS.items()
    for bit_pos, description in bits
    if "warning" in description.lower()
}

ON_OFF_STATUS = {
    0: "OFF",
    1: "ON",
}

ENUM_REGISTERS: dict[str, dict[int, str]] = {
    "101": {
        0: "Error",
        1: "Initializing",
        2: "Self Test",
        3: "Waiting",
        10: "Normal",
        20: "Standby",
        42: "Maintenance",
    },
    "105": {0: "NL", 1: "DE", 2: "FR", 3: "EN"},
    "111": {0: "Right", 1: "Left"},
    "112": {0: "E300 P", 2: "E300 RF", 3: "E400 RF"},
    "325": {0: "Reset bypass position", 1: "End position reached", 2: "Active"},
    "344": {0: "HRV", 1: "ERV"},
    "345": {0: "Disabled", 1: "Enabled"},
}

FIRMWARE_REGISTER = 110

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
    "firmware_version": ComfoAirModbusSensorEntityDescription(
        key="firmware_version",
        name="firmware version",
        icon="mdi:chip",
    ),
    "serial_number": ComfoAirModbusSensorEntityDescription(
        key="serial_number",
        name="serial number",
        icon="mdi:barcode",
    ),
    "bootloader_version": ComfoAirModbusSensorEntityDescription(
        key="bootloader_version",
        name="bootloader version",
        icon="mdi:chip",
    ),
    "hardware_version": ComfoAirModbusSensorEntityDescription(
        key="hardware_version",
        name="hardware version",
        icon="mdi:chip",
    ),
    "extract_absolute_humidity": ComfoAirModbusSensorEntityDescription(
        key="extract_absolute_humidity",
        name="extract air absolute humidity",
        icon="mdi:water",
        native_unit_of_measurement="kg/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        scale=1.0,
    ),
    "extract_enthalpy": ComfoAirModbusSensorEntityDescription(
        key="extract_enthalpy",
        name="extract air enthalpy",
        icon="mdi:fire",
        native_unit_of_measurement="kJ/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "extract_dewpoint": ComfoAirModbusSensorEntityDescription(
        key="extract_dewpoint",
        name="extract air dew point",
        icon="mdi:thermometer-water",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "exhaust_absolute_humidity": ComfoAirModbusSensorEntityDescription(
        key="exhaust_absolute_humidity",
        name="exhaust air absolute humidity",
        icon="mdi:water",
        native_unit_of_measurement="kg/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        scale=1.0,
    ),
    "exhaust_enthalpy": ComfoAirModbusSensorEntityDescription(
        key="exhaust_enthalpy",
        name="exhaust air enthalpy",
        icon="mdi:fire",
        native_unit_of_measurement="kJ/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "exhaust_dewpoint": ComfoAirModbusSensorEntityDescription(
        key="exhaust_dewpoint",
        name="exhaust air dew point",
        icon="mdi:thermometer-water",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "intake_absolute_humidity": ComfoAirModbusSensorEntityDescription(
        key="intake_absolute_humidity",
        name="intake air absolute humidity",
        icon="mdi:water",
        native_unit_of_measurement="kg/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        scale=1.0,
    ),
    "intake_enthalpy": ComfoAirModbusSensorEntityDescription(
        key="intake_enthalpy",
        name="intake air enthalpy",
        icon="mdi:fire",
        native_unit_of_measurement="kJ/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "intake_dewpoint": ComfoAirModbusSensorEntityDescription(
        key="intake_dewpoint",
        name="intake air dew point",
        icon="mdi:thermometer-water",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "supply_absolute_humidity": ComfoAirModbusSensorEntityDescription(
        key="supply_absolute_humidity",
        name="supply air absolute humidity",
        icon="mdi:water",
        native_unit_of_measurement="kg/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        scale=1.0,
    ),
    "supply_enthalpy": ComfoAirModbusSensorEntityDescription(
        key="supply_enthalpy",
        name="supply air enthalpy",
        icon="mdi:fire",
        native_unit_of_measurement="kJ/kg",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "supply_dewpoint": ComfoAirModbusSensorEntityDescription(
        key="supply_dewpoint",
        name="supply air dew point",
        icon="mdi:thermometer-water",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "temperature_efficiency": ComfoAirModbusSensorEntityDescription(
        key="temperature_efficiency",
        name="efficiency",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=1.0,
    ),
    "flow_balance": ComfoAirModbusSensorEntityDescription(
        key="flow_balance",
        name="air flow balance",
        icon="mdi:scale-balance",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "101": ComfoAirModbusSensorEntityDescription(
        key="101",
        name="device status",
        icon="mdi:information-outline",
    ),
    "105": ComfoAirModbusSensorEntityDescription(
        key="105",
        name="language",
        icon="mdi:translate",
    ),
    "111": ComfoAirModbusSensorEntityDescription(
        key="111",
        name="orientation",
        icon="mdi:rotate-3d-variant",
    ),
    "112": ComfoAirModbusSensorEntityDescription(
        key="112",
        name="model",
        icon="mdi:information",
    ),
    "300": ComfoAirModbusSensorEntityDescription(
        key="300",
        name="intake air temperature",
        icon="mdi:thermometer",
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
        icon="mdi:thermometer",
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
        icon="mdi:thermometer",
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
        icon="mdi:thermometer",
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
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "306": ComfoAirModbusSensorEntityDescription(
        key="306",
        name="intake air humidity",
        icon="mdi:water-percent",
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
        name="supply air humidity",
        icon="mdi:water-percent",
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
        icon="mdi:water-percent",
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
        name="exhaust air humidity",
        icon="mdi:water-percent",
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
        icon="mdi:fan",
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
        icon="mdi:fan",
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
        icon="mdi:weather-windy",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "313": ComfoAirModbusSensorEntityDescription(
        key="313",
        name="supply air flow",
        icon="mdi:weather-windy",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "314": ComfoAirModbusSensorEntityDescription(
        key="314",
        name="extract air fan speed",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "315": ComfoAirModbusSensorEntityDescription(
        key="315",
        name="supply air fan speed",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "316": ComfoAirModbusSensorEntityDescription(
        key="316",
        name="analog voltage C1",
        icon="mdi:flash-triangle-outline",
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.01,
    ),
    "317": ComfoAirModbusSensorEntityDescription(
        key="317",
        name="rf voltage",
        icon="mdi:flash-triangle-outline",
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.01,
    ),
    "318": ComfoAirModbusSensorEntityDescription(
        key="318",
        name="RF enabled",
        icon="mdi:toggle-switch-outline",
    ),
    "319": ComfoAirModbusSensorEntityDescription(
        key="319",
        name="pre-heater state",
        icon="mdi:toggle-switch-outline",
    ),
    "320": ComfoAirModbusSensorEntityDescription(
        key="320",
        name="extract air flow setpoint +- balance offset",
        icon="mdi:weather-windy",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "321": ComfoAirModbusSensorEntityDescription(
        key="321",
        name="supply air flow setpoint",
        icon="mdi:weather-windy",
        native_unit_of_measurement="m³/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
    ),
    "322": ComfoAirModbusSensorEntityDescription(
        key="322",
        name="running mean outdoor temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        scale=0.1,
        signed=True,
    ),
    "325": ComfoAirModbusSensorEntityDescription(
        key="325",
        name="bypass motor active",
        icon="mdi:valve",
    ),
    "326": ComfoAirModbusSensorEntityDescription(
        key="326",
        name="bypass setpoint",
        icon="mdi:valve-open",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
        native_min_value=0,
        native_max_value=100,
    ),
    "327": ComfoAirModbusSensorEntityDescription(
        key="327",
        name="bypass position",
        icon="mdi:valve-open",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        scale=1.0,
        native_min_value=0,
        native_max_value=100,
    ),
    "328": ComfoAirModbusSensorEntityDescription(
        key="328",
        name="0-10 v speed setting",
        icon="mdi:speedometer",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "329": ComfoAirModbusSensorEntityDescription(
        key="329",
        name="rf speed setting",
        icon="mdi:speedometer",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "330": ComfoAirModbusSensorEntityDescription(
        key="330",
        name="3-way switch",
        icon="mdi:toggle-switch-outline",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "331": ComfoAirModbusSensorEntityDescription(
        key="331",
        name="bathroom switch",
        icon="mdi:toggle-switch-outline",
        suggested_display_precision=0,
        scale=1.0,
    ),
    "334": ComfoAirModbusSensorEntityDescription(
        key="334",
        name="defrost cycles last 24h",
        icon="mdi:snowflake-melt",
        state_class=SensorStateClass.MEASUREMENT,
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
        name="fireplace present",
        icon="mdi:fireplace",
    ),
    "338": ComfoAirModbusSensorEntityDescription(
        key="338",
        name="pre-heater present",
        icon="mdi:radiator",
    ),
    "344": ComfoAirModbusSensorEntityDescription(
        key="344",
        name="heat exchanger type",
        icon="mdi:heat-wave",
    ),
    "345": ComfoAirModbusSensorEntityDescription(
        key="345",
        name="comfort humidity control",
        icon="mdi:water-percent",
    ),
}