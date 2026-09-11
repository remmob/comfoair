"""Register model for the ComfoAir integration.

Each address in `READ_RANGES` / `STATIC_READ_RANGES` gets its own field on a
`ManualComponent`. The library plans the actual block reads itself (gap/span
batching), so there is no manual register-block bookkeeping here — the two
range lists in const.py only state *which* addresses are read, matching the
coverage of the historical hand-rolled implementation.

`SENSOR_TYPES` already carries the scale/signed info entity descriptions need
for display, so it doubles as the source for how each field decodes — one
definition, not two.
"""

from __future__ import annotations

from modbus_connection import ModbusUnit
from modbus_connection.model import ManualComponent, gauge, raw_register

from .const import READ_RANGES, SENSOR_TYPES, STATIC_READ_RANGES


def _field_for(address: int):
    """The field for one address: a scaled/signed number where SENSOR_TYPES
    describes one, otherwise a raw register (alarm bits, static data the
    entity layer never reads directly, and gaps within a read span).

    `gauge()`, not `integer()`, since it is the one that takes a static
    `scale` factor; a description with the default scale of 1.0 decodes to
    the same raw passthrough `integer()` would give (see NumberField._scale
    in modbus_connection.model.fields), so ENUM_REGISTERS/BOOLEAN_REGISTERS
    lookups in hub.py still see the untouched raw value.
    """
    description = SENSOR_TYPES.get(str(address))
    if description is not None:
        return gauge(address, description.scale, signed=description.signed)
    return raw_register(address)


def _build_component(unit: ModbusUnit, ranges: list[tuple[int, int]]) -> ManualComponent:
    component = ManualComponent(unit)
    for start, count in ranges:
        for address in range(start, start + count):
            component.add(str(address), _field_for(address))
    return component


def build_realtime_component(unit: ModbusUnit) -> ManualComponent:
    """The registers polled every scan_interval (device status, measurements,
    alarm/warning bitmasks)."""
    return _build_component(unit, READ_RANGES)


def build_static_component(unit: ModbusUnit) -> ManualComponent:
    """The registers read once and cached (language/orientation/model,
    firmware/bootloader version, serial number)."""
    return _build_component(unit, STATIC_READ_RANGES)
