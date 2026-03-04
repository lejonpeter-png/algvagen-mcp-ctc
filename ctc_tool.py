"""
ctc_tool.py - MCP Tool Module for CTC EcoPart i612M Heat Pump

Registers FastMCP tools that expose the CTC heat pump data and controls
to the algvagen-mcp MCP server.

Integration with server.py::

    from ctc_tool import register_ctc_tools
    register_ctc_tools(mcp, config)

Each tool creates a short-lived CTCClient (connect → read → disconnect)
to avoid holding the single allowed Modbus TCP connection open.

.. note::
    Control register writes (set_heat_pump_el_price_mode,
    set_heat_pump_dhw_mode, set_heat_pump_smartgrid) affect registers
    that reset to hardware defaults after approximately **5 minutes**.
    The BMS/automation layer is responsible for periodic refresh if
    sustained control is required.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ctc_client import CTCClient

logger = logging.getLogger(__name__)

# Default connection parameters – override via config.json "ctc" section
_DEFAULT_HOST = "192.168.2.74"
_DEFAULT_PORT = 502
_DEFAULT_UNIT_ID = 1
_DEFAULT_TIMEOUT = 10

# Module-level config, set by register_ctc_tools()
_config: dict = {}


def _make_client() -> CTCClient:
    """Construct a CTCClient using module config (set by register_ctc_tools)."""
    return CTCClient(
        host=_config.get("host", _DEFAULT_HOST),
        port=_config.get("port", _DEFAULT_PORT),
        unit_id=_config.get("unit_id", _DEFAULT_UNIT_ID),
        timeout=_config.get("timeout", _DEFAULT_TIMEOUT),
    )


def _json(data: Any) -> str:
    """Serialise *data* to a compact, human-readable JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def _error(message: str) -> str:
    """Return a JSON error payload."""
    return _json({"error": message})


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_ctc_tools(mcp, config: dict | None = None) -> None:
    """
    Register all CTC heat-pump MCP tools with the given FastMCP instance.

    Call this from server.py after creating the mcp object::

        from ctc_tool import register_ctc_tools
        register_ctc_tools(mcp, config.get("ctc", {}))

    Args:
        mcp: A FastMCP instance.
        config: Optional dict with keys host, port, unit_id, timeout.
    """
    global _config
    _config = config or {}
    host = _config.get("host", _DEFAULT_HOST)
    port = _config.get("port", _DEFAULT_PORT)
    logger.info("Registering CTC tools (target: %s:%d)", host, port)

    @mcp.tool()
    async def get_heat_pump_overview() -> str:
        """
        Get a full sensor overview of the CTC EcoPart i612M heat pump.

        Returns all key temperatures (°C), pressures (bar), system status,
        HP1 status, SmartGrid mode, degree minute, compressor RPS,
        electrical measurements, and pump states.

        Returns:
            JSON string with the complete sensor snapshot.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_sensor_overview()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_overview error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def get_heat_pump_temperatures() -> str:
        """
        Get current heating circuit (HS1) status and temperatures.

        Returns HS1 flow temperature, setpoint, return temperature,
        room temperature, heating curve inclination, degree minute,
        and radiator pump states.

        Returns:
            JSON string with heating circuit data.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_heating_status()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_temperatures error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def get_heat_pump_hp_status() -> str:
        """
        Get compressor and refrigeration circuit status.

        Returns HP1 operating status, compressor RPS, brine inlet/outlet
        temperatures, high/low pressures, discharge gas temperature, and
        suction gas temperature.

        Returns:
            JSON string with heat-pump refrigeration data.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_hp_status()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_hp_status error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def get_heat_pump_electrical() -> str:
        """
        Get electrical measurements from the heat pump.

        Returns phase currents L1–L3 (A), maximum current (A), immersion
        heater power (kW), immersion heater cumulative energy (kWh), and
        the current elspot price.

        Returns:
            JSON string with electrical data.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_electrical()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_electrical error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def get_heat_pump_dhw() -> str:
        """
        Get domestic hot-water (DHW) status.

        Returns DHW temperature, stop temperature, upper tank temperature,
        lower tank setpoint, current DHW mode, and circulation pump state.

        Returns:
            JSON string with DHW status.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_dhw_status()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_dhw error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def get_heat_pump_alarms() -> str:
        """
        Get current alarm and info count from the heat pump.

        Returns:
            JSON string with alarm_count, info_count, and list of alarms.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_alarms()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_alarms error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def get_heat_pump_system_info() -> str:
        """
        Get system information: software version, product type, operation hours.

        Returns:
            JSON string with version strings, product/HP types, and total hours.
        """
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            data = await client.get_system_info()
            return _json(data)
        except Exception as exc:
            logger.error("get_heat_pump_system_info error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def set_heat_pump_el_price_mode(mode: int) -> str:
        """
        Set the electricity price mode on the heat pump.

        Writes control register 1005. Resets after ~5 minutes unless refreshed.

        Args:
            mode: 1=Low, 2=Normal, 3=High

        Returns:
            JSON string with success status and mode info.
        """
        if mode not in (1, 2, 3):
            return _error(f"Invalid mode {mode!r}: must be 1=Low, 2=Normal, 3=High")
        mode_labels = {1: "Low", 2: "Normal", 3: "High"}
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            success = await client.set_el_price_mode(mode)
            return _json({
                "success": success,
                "mode": mode,
                "mode_label": mode_labels[mode],
                "note": "Control register resets after ~5 min without refresh",
            })
        except Exception as exc:
            logger.error("set_heat_pump_el_price_mode error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def set_heat_pump_dhw_mode(mode: int) -> str:
        """
        Set the domestic hot-water (DHW) operation mode.

        Writes control register 1007. Resets after ~5 minutes unless refreshed.

        Args:
            mode: 0=Economy, 1=Normal, 2=Comfort

        Returns:
            JSON string with success status and mode info.
        """
        if mode not in (0, 1, 2):
            return _error(f"Invalid mode {mode!r}: must be 0=Economy, 1=Normal, 2=Comfort")
        mode_labels = {0: "Economy", 1: "Normal", 2: "Comfort"}
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            success = await client.set_dhw_mode(mode)
            return _json({
                "success": success,
                "mode": mode,
                "mode_label": mode_labels[mode],
                "note": "Control register resets after ~5 min without refresh",
            })
        except Exception as exc:
            logger.error("set_heat_pump_dhw_mode error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def set_heat_pump_room_temp(temp: float) -> str:
        """
        Set the HS1 room temperature setpoint (persistent).

        Writes settings register 61509. This setting survives power cycles.

        Args:
            temp: Desired room temperature in °C (e.g. 21.0, 21.5, 22.0).

        Returns:
            JSON string with success status.
        """
        if not (10.0 <= temp <= 30.0):
            return _error(f"Temperature {temp} °C out of reasonable range (10–30 °C)")
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            success = await client.set_room_temp_setpoint(temp)
            return _json({
                "success": success,
                "setpoint_c": temp,
                "note": "Persistent settings register 61509",
            })
        except Exception as exc:
            logger.error("set_heat_pump_room_temp error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def set_heat_pump_heating_curve(inclination: float) -> str:
        """
        Set the HS1 heating curve inclination (persistent).

        A higher inclination raises the supply temperature more steeply
        as outdoor temperature drops. Writes register 61513.

        Args:
            inclination: Heating curve value (typical range 0.2–2.5).

        Returns:
            JSON string with success status.
        """
        if not (0.1 <= inclination <= 5.0):
            return _error(f"Inclination {inclination} out of reasonable range (0.1–5.0)")
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            success = await client.set_heating_curve(inclination)
            return _json({
                "success": success,
                "inclination": inclination,
                "note": "Persistent settings register 61513",
            })
        except Exception as exc:
            logger.error("set_heat_pump_heating_curve error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()

    @mcp.tool()
    async def set_heat_pump_smartgrid(mode: int) -> str:
        """
        Set the SmartGrid operating mode.

        Encodes mode into bits 6 and 7 of control register 1100.
        Resets after ~5 minutes unless refreshed.

        Args:
            mode: 0=Normal, 1=Block, 2=Low price, 3=High cap

        Returns:
            JSON string with success status.
        """
        if mode not in (0, 1, 2, 3):
            return _error(f"Invalid SmartGrid mode {mode!r}: must be 0=Normal, 1=Block, 2=LowPrice, 3=HighCap")
        mode_labels = {0: "Normal", 1: "Block", 2: "Low price", 3: "High cap"}
        client = _make_client()
        try:
            connected = await client.connect()
            if not connected:
                return _error(f"Failed to connect to CTC heat pump at {host}:{port}")
            success = await client.set_smartgrid(mode)
            return _json({
                "success": success,
                "mode": mode,
                "mode_label": mode_labels[mode],
                "note": "Control register (bits 6+7 of reg 1100) resets after ~5 min without refresh",
            })
        except Exception as exc:
            logger.error("set_heat_pump_smartgrid error: %s", exc)
            return _error(str(exc))
        finally:
            await client.disconnect()
