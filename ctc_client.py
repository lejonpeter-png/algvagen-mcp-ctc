"""
ctc_client.py - CTC EcoPart i612M Modbus TCP Client

Communicates with a CTC EcoPart i612M ground-source heat pump via Modbus TCP.

Connection details:
    IP:      192.168.2.74
    Port:    502
    Unit ID: 1

Register map overview:
    1000-series  Control registers  (write-only, timeout after 5 min – must be refreshed)
    610xx-619xx  Settings registers (RW, persistent)
    620xx-629xx  Sensor registers   (read-only)
    650xx-659xx  Alarm registers    (read-only)

All addresses are 0-based (no offset).
Values are signed 16-bit integers scaled by a factor:
    real_value = raw_int16_value * factor

IMPORTANT:
    - CTC allows only ONE Modbus TCP connection at a time.
    - Use the connect-per-request pattern: connect → read batch → disconnect.
    - A short delay (0.3 s) between Modbus requests prevents overload.
    - Auto-reconnect is disabled to avoid fighting another client for the port.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_HOST = "192.168.2.74"
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
DEFAULT_TIMEOUT = 10  # seconds (generous for slow CTC)

DELAY_BETWEEN_REQUESTS = 0.3  # seconds between Modbus requests
DELAY_AFTER_CONNECT = 1.0     # seconds after TCP connect before first read

# Control register addresses (write-only; reset to defaults after ~5 min if not refreshed)
REG_MAX_RPS_COMPRESSOR = 1002
REG_MAX_POWER_IMM_UPPER = 1003
REG_EL_PRICE_MODE = 1005        # 1=Low, 2=Normal, 3=High
REG_EXTRA_DHW = 1006
REG_DHW_MODE = 1007             # 0=Economy, 1=Normal, 2=Comfort
REG_SETPOINT_HEAT_HC1 = 1010
REG_SETPOINT_COOL = 1014
REG_ZONE_MODE_HC1 = 1015
REG_SETPOINT_OFFSET_HEAT_HC1 = 1023
REG_SETPOINT_FLOW_HC1 = 1029
REG_SETPOINT_DHW_TANK = 1033
REG_VIRTUAL_DIGITAL_INPUTS = 1100  # SmartGrid via bits 6+7

# Settings register addresses (RW, persistent)
REG_HOT_WATER_MODE = 61500
REG_MANUAL_STOP_TEMP_DHW = 61501      # factor 0.1 °C
REG_HS1_ROOM_TEMP_SETPOINT = 61509   # factor 0.1 °C
REG_HS1_INCLINATION = 61513          # factor 0.1
REG_ROOM1_ADJUSTMENT = 61517         # factor 0.1 °C
REG_HS1_MAX_PRIMARY_FLOW = 61534     # factor 0.1 °C
REG_HS1_MIN_PRIMARY_FLOW = 61538     # factor 0.1 °C
REG_HS1_HEATING_MODE = 61542         # 0=Auto, 1=On, 2=Off
REG_HP1_MAX_RPS = 61572              # factor 0.1
REG_MAX_IMM_KW_LOWER = 61590         # factor 0.1 kW
REG_MAX_IMM_DHW_KW_UPPER = 61591     # factor 0.1 kW
REG_HEATING_PROGRAM_HC1 = 61671      # 0=Economy, 1=Normal, 2=Comfort, 3=Custom

# Sensor register addresses (read-only)
REG_OUTDOOR_TEMP = 62000             # factor 0.1 °C
REG_DHW_STOP_TEMP = 62001            # factor 0.1 °C
REG_DHW_TEMP = 62003                 # factor 0.1 °C
REG_SYSTEM_STATUS = 62005            # see STATUS_SYSTEM_MAP
REG_RADIATOR_TEMP = 62006            # factor 0.1 °C
REG_HS1_SETPOINT = 62007             # factor 0.1 °C
REG_HS1_PRIMARY_FLOW = 62011         # factor 0.1 °C
REG_RETURN_TEMP = 62015              # factor 0.1 °C
REG_DHW_PUMP = 62016                 # pump state
REG_HP1_STATUS = 62017               # see STATUS_HP1_MAP
REG_HP1_TEMP_IN = 62027              # factor 0.1 °C
REG_HP1_TEMP_OUT = 62037             # factor 0.1 °C
REG_HP1_DISCHARGE_GAS = 62047        # factor 0.1 °C
REG_HP1_SUCTION_GAS = 62057          # factor 0.1 °C
REG_HP1_HIGH_PRESSURE = 62067        # factor 0.1 bar
REG_HP1_LOW_PRESSURE = 62077         # factor 0.1 bar
REG_HP1_BRINE_IN = 62087             # factor 0.1 °C
REG_HP1_BRINE_OUT = 62097            # factor 0.1 °C
REG_HP1_CHARGE_PUMP = 62107          # factor 0.1
REG_HP1_BRINE_PUMP = 62117           # factor 0.1
REG_HP1_OUTDOOR_TEMP = 62147         # factor 0.1 °C
REG_HP1_SW_VERSION = 62157           # factor 1
REG_DEGREE_MINUTE = 62167            # factor 0.1
REG_IMM_HEATER_POWER = 62168         # factor 0.1 kW
REG_MAX_CURRENT = 62170              # factor 0.1 A
REG_CURRENT_L1 = 62171               # factor 0.1 A
REG_CURRENT_L2 = 62172               # factor 0.1 A
REG_CURRENT_L3 = 62173               # factor 0.1 A
REG_TOTAL_TIME_LSB = 62186           # factor 1 h
REG_IMM_HEATER_KWH = 62191          # factor 1 kWh
REG_HP1_RPS = 62193                  # factor 0.1
REG_ROOM_TEMP_1 = 62203              # factor 0.1 °C
REG_HP1_COMP_TIME_LSB = 62214        # factor 1 h
REG_HP1_COMP_TIME_MSB = 62215        # factor 1 h
REG_HP1_COMP_24H = 62234             # factor 1 h
REG_SW_VERSION_MD = 62244            # factor 1
REG_SW_VERSION_YEAR = 62245          # factor 1
REG_HS1_STATUS = 62246               # 0=HeatingOff, 1=Vacation, 2=NightReduction, 3=Normal
REG_PRODUCT_TYPE = 62253             # factor 1
REG_HP1_TYPE = 62254                 # factor 1
REG_TANK_LOWER_SETPOINT = 62274      # factor 0.1 °C
REG_DHW_UPPER_TEMP = 62276           # factor 0.1 °C
REG_COOLING_TANK_SETPOINT = 62288    # factor 0.1 °C
REG_COOLING_TANK_TEMP = 62289        # factor 0.1 °C
REG_SG_MODE = 62301                  # 0=Normal, 1=Block, 2=LowPrice, 3=HighCap
REG_ELSPOT_PRICE = 62302             # factor 1
REG_ELSPOT_PRICE_DEC = 62303         # factor 1
REG_RADIATOR_PUMP_1 = 62304          # factor 1
REG_RADIATOR_PUMP_2 = 62305          # factor 1

# Alarm register addresses
REG_ALARM_COUNT = 65133              # hex: first 2 digits=info count, last 2=alarm count
REG_ALARM1_HP_FLAG = 65010
REG_ALARM1_CODE = 65011
REG_ALARM2_HP_FLAG = 65012
REG_ALARM2_CODE = 65013

# Human-readable status maps
STATUS_SYSTEM_MAP: dict[int, str] = {
    0: "HP upper", 1: "HP lower", 2: "Add heat", 3: "HP + Add",
    4: "HC", 5: "DHW", 6: "Pool", 7: "Off", 8: "Heating mix",
    9: "Wood", 10: "DHW/HC", 11: "Cooling", 12: "Swap",
}
STATUS_HP1_MAP: dict[int, str] = {
    0: "Off (start delay)", 1: "Off (ready)", 2: "Wait for flow",
    3: "On (heating)", 4: "Defrost", 5: "On (cooling)",
    6: "Blocked", 7: "Alarm", 8: "Function test",
    30: "Not defined", 31: "Not enabled", 32: "Comm error", 33: "Charging DHW",
}
STATUS_HS1_MAP: dict[int, str] = {
    0: "Heating off", 1: "Vacation", 2: "Night reduction", 3: "On (normal)",
}
EL_PRICE_MODE_MAP: dict[int, str] = {1: "Low", 2: "Normal", 3: "High"}
DHW_MODE_MAP: dict[int, str] = {0: "Economy", 1: "Normal", 2: "Comfort"}
SG_MODE_MAP: dict[int, str] = {0: "Normal", 1: "Block", 2: "Low price", 3: "High cap"}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _to_int16(raw: int) -> int:
    """Convert an unsigned 16-bit integer to a signed int16."""
    if raw > 32767:
        return raw - 65536
    return raw


def _scale(raw: int, factor: float) -> float:
    """Return ``raw`` as a signed int16, scaled by ``factor``."""
    return round(_to_int16(raw) * factor, 4)


def _combine_32(lsb: int, msb: int) -> int:
    """Combine two 16-bit words into a 32-bit unsigned integer (MSB << 16 | LSB)."""
    return (msb << 16) | lsb


# ---------------------------------------------------------------------------
# CTCClient
# ---------------------------------------------------------------------------

class CTCClient:
    """
    Async Modbus TCP client for the CTC EcoPart i612M heat pump.

    Usage (async)::

        async with CTCClient() as client:
            overview = await client.get_sensor_overview()

    Usage (sync wrapper)::

        client = CTCClient()
        overview = client.get_sensor_overview_sync()

    .. note::
        CTC only allows ONE Modbus TCP connection at a time.
        The async context manager connects on enter and disconnects on exit.
        Auto-reconnect is disabled — if the connection drops, reconnect explicitly.

    .. note::
        Control registers (1000-series) must be written at least every **5 minutes**
        or the heat pump reverts them to its internal defaults.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        unit_id: int = DEFAULT_UNIT_ID,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._client: Optional[AsyncModbusTcpClient] = None
        self._connected = False
        self._unit_kw: Optional[str] = None  # Cached keyword for unit id

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "CTCClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """
        Open the Modbus TCP connection.

        Waits DELAY_AFTER_CONNECT seconds after establishing the TCP link
        before returning, giving the CTC time to be ready.

        Returns:
            True if connected successfully, False otherwise.
        """
        try:
            self._client = AsyncModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
                # Disable auto-reconnect — CTC allows only 1 TCP connection
                reconnect_delay=0,
                reconnect_delay_max=0,
            )
            connected = await self._client.connect()
            if connected:
                self._connected = True
                logger.info("Connected to CTC EcoPart at %s:%d", self.host, self.port)
                # Give the CTC time to be ready after TCP handshake
                await asyncio.sleep(DELAY_AFTER_CONNECT)
            else:
                self._connected = False
                logger.error("Failed to connect to CTC EcoPart at %s:%d", self.host, self.port)
            return connected
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Connection error: %s", exc)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection."""
        self._connected = False
        if self._client is not None:
            self._client.close()
            logger.info("Disconnected from CTC EcoPart")
            self._client = None

    @property
    def is_connected(self) -> bool:
        """Return True if the underlying client is connected."""
        if self._client is None:
            return False
        return self._connected

    # ------------------------------------------------------------------
    # Low-level read / write with inter-request delay
    # ------------------------------------------------------------------

    async def _read_holding(self, address: int, count: int):
        """Call read_holding_registers with the correct keyword for the unit id.

        pymodbus renamed the parameter across versions:
          - 3.6 and earlier: ``slave``
          - 3.7+:           ``slave`` (still accepted)
          - 3.12+:          ``device_id`` (``slave`` removed)

        We detect once which keyword to use and cache it.
        """
        if self._unit_kw is None:
            # Auto-detect on first call
            for kw in ("device_id", "slave"):
                try:
                    result = await self._client.read_holding_registers(
                        address=address, count=count, **{kw: self.unit_id}
                    )
                    self._unit_kw = kw
                    logger.info("pymodbus unit keyword detected: %s", kw)
                    return result
                except TypeError:
                    continue
            # Last resort: no keyword at all (uses default device_id=1)
            self._unit_kw = ""
            return await self._client.read_holding_registers(
                address=address, count=count
            )
        elif self._unit_kw:
            return await self._client.read_holding_registers(
                address=address, count=count, **{self._unit_kw: self.unit_id}
            )
        else:
            return await self._client.read_holding_registers(
                address=address, count=count
            )

    async def read_register(self, address: int, count: int = 1) -> list[int]:
        """
        Read *count* holding registers starting at *address*.

        A short delay is inserted after each read to avoid overloading
        the CTC Modbus TCP server.

        Args:
            address: 0-based register address.
            count:   Number of registers to read (max 100 per call).

        Returns:
            List of raw unsigned 16-bit integers, or an empty list on error.
        """
        if not self.is_connected:
            logger.warning("read_register called while disconnected")
            return []
        count = min(count, 100)
        try:
            result = await self._read_holding(address, count)
            if result.isError():
                logger.error("Modbus read error at address %d: %s", address, result)
                return []
            # Delay after each request to give CTC breathing room
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            return list(result.registers)
        except ModbusException as exc:
            logger.error("Modbus exception reading address %d: %s", address, exc)
            return []
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unexpected error reading address %d: %s", address, exc)
            return []

    async def write_register(self, address: int, value: int) -> bool:
        """
        Write a single holding register.

        Args:
            address: 0-based register address.
            value:   Unsigned 16-bit integer to write.

        Returns:
            True on success, False on failure.

        .. warning::
            Control registers (1000-series) reset to hardware defaults after ~5 min.
        """
        if not self.is_connected:
            logger.warning("write_register called while disconnected")
            return False
        try:
            kw = self._unit_kw or "device_id"
            try:
                if kw:
                    result = await self._client.write_register(
                        address=address,
                        value=int(value) & 0xFFFF,
                        **{kw: self.unit_id},
                    )
                else:
                    result = await self._client.write_register(
                        address=address,
                        value=int(value) & 0xFFFF,
                    )
            except TypeError:
                result = await self._client.write_register(
                    address=address,
                    value=int(value) & 0xFFFF,
                )
            if result.isError():
                logger.error("Modbus write error at address %d: %s", address, result)
                return False
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            logger.debug("Wrote %d to register %d", value, address)
            return True
        except ModbusException as exc:
            logger.error("Modbus exception writing address %d: %s", address, exc)
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unexpected error writing address %d: %s", address, exc)
            return False

    async def read_scaled(self, address: int, factor: float) -> Optional[float]:
        """
        Read a single register and apply factor scaling (signed int16).

        Args:
            address: 0-based register address.
            factor:  Scaling factor (real_value = raw_int16 * factor).

        Returns:
            Scaled float value, or None on read failure.
        """
        raw = await self.read_register(address, count=1)
        if not raw:
            return None
        return _scale(raw[0], factor)

    # ------------------------------------------------------------------
    # Block-read helpers
    # ------------------------------------------------------------------

    async def _read_block(self, start: int, count: int) -> dict[int, int]:
        """Read a contiguous block and return {address: raw_value} dict."""
        raw = await self.read_register(start, count)
        if not raw or len(raw) != count:
            return {}
        return {start + i: raw[i] for i in range(count)}

    def _get_scaled(self, block: dict[int, int], addr: int, factor: float) -> Optional[float]:
        """Get a scaled value from a block-read result."""
        if addr not in block:
            return None
        return _scale(block[addr], factor)

    def _get_raw(self, block: dict[int, int], addr: int) -> Optional[int]:
        """Get a raw value from a block-read result."""
        return block.get(addr)

    # ------------------------------------------------------------------
    # Sensor overview (optimised with block reads)
    # ------------------------------------------------------------------

    async def get_sensor_overview(self) -> dict:
        """
        Return a comprehensive snapshot of all key sensor values.

        Uses block reads to minimise the number of Modbus requests:
          - Block 1: 62000-62017 (18 regs) — temps, status, pump, HP1 status
          - Block 2: 62027-62037 (11 regs) — HP1 temp in/out
          - Block 3: 62047-62057 (11 regs) — discharge/suction gas
          - Block 4: 62067-62077 (11 regs) — high/low pressure
          - Block 5: 62087-62097 (11 regs) — brine in/out
          - Block 6: 62107-62117 (11 regs) — charge/brine pump
          - Block 7: 62147 (1 reg) — HP1 outdoor temp
          - Block 8: 62157-62173 (17 regs) — SW version, degree minute, heater, currents
          - Block 9: 62186-62193 (8 regs) — total time, IMM kWh, HP1 RPS
          - Block 10: 62203 (1 reg) — room temp
          - Block 11: 62214-62215 (2 regs) — comp time LSB/MSB
          - Block 12: 62234 (1 reg) — comp 24h
          - Block 13: 62244-62254 (11 regs) — SW version, HS1 status, product type
          - Block 14: 62274-62276 (3 regs) — tank lower setpoint, DHW upper
          - Block 15: 62301-62305 (5 regs) — SG mode, elspot, radiator pumps

        Total: ~15 requests instead of ~30+.

        Returns:
            Dict with human-readable keys and scaled values.
        """
        data: dict = {}

        # --- Block 1: 62000-62017 (18 registers) ---
        b1 = await self._read_block(62000, 18)
        if b1:
            data["outdoor_temp_c"] = self._get_scaled(b1, 62000, 0.1)
            data["dhw_stop_temp_c"] = self._get_scaled(b1, 62001, 0.1)
            data["dhw_temp_c"] = self._get_scaled(b1, 62003, 0.1)
            sv = self._get_raw(b1, 62005)
            if sv is not None:
                data["system_status_code"] = sv
                data["system_status"] = STATUS_SYSTEM_MAP.get(sv, f"Unknown({sv})")
            data["radiator_temp_c"] = self._get_scaled(b1, 62006, 0.1)
            data["hs1_setpoint_c"] = self._get_scaled(b1, 62007, 0.1)
            data["hs1_primary_flow_c"] = self._get_scaled(b1, 62011, 0.1)
            data["return_temp_c"] = self._get_scaled(b1, 62015, 0.1)
            dhw_pump = self._get_raw(b1, 62016)
            if dhw_pump is not None:
                data["dhw_pump_state"] = dhw_pump
            hv = self._get_raw(b1, 62017)
            if hv is not None:
                data["hp1_status_code"] = hv
                data["hp1_status"] = STATUS_HP1_MAP.get(hv, f"Unknown({hv})")

        # --- Block 2: HP1 temp in (62027) ---
        data["hp1_temp_in_c"] = await self.read_scaled(62027, 0.1)

        # --- Block 3: HP1 temp out (62037) ---
        data["hp1_temp_out_c"] = await self.read_scaled(62037, 0.1)

        # --- Block 4: Discharge gas (62047) ---
        data["hp1_discharge_gas_c"] = await self.read_scaled(62047, 0.1)

        # --- Block 5: Suction gas (62057) ---
        data["hp1_suction_gas_c"] = await self.read_scaled(62057, 0.1)

        # --- Block 6: High pressure (62067) ---
        data["hp1_high_pressure_bar"] = await self.read_scaled(62067, 0.1)

        # --- Block 7: Low pressure (62077) ---
        data["hp1_low_pressure_bar"] = await self.read_scaled(62077, 0.1)

        # --- Block 8: Brine in (62087) ---
        data["hp1_brine_in_c"] = await self.read_scaled(62087, 0.1)

        # --- Block 9: Brine out (62097) ---
        data["hp1_brine_out_c"] = await self.read_scaled(62097, 0.1)

        # --- Block 10: Charge pump (62107) ---
        data["hp1_charge_pump_pct"] = await self.read_scaled(62107, 0.1)

        # --- Block 11: Brine pump (62117) ---
        data["hp1_brine_pump_pct"] = await self.read_scaled(62117, 0.1)

        # --- Block 12: HP1 outdoor temp (62147) ---
        data["hp1_outdoor_temp_c"] = await self.read_scaled(62147, 0.1)

        # --- Block 13: 62157-62173 (17 regs) — SW ver, degree min, heater, currents ---
        b13 = await self._read_block(62157, 17)
        if b13:
            data["hp1_sw_version"] = self._get_raw(b13, 62157)
            data["degree_minute"] = self._get_scaled(b13, 62167, 0.1)
            data["immersion_heater_kw"] = self._get_scaled(b13, 62168, 0.1)
            data["max_current_a"] = self._get_scaled(b13, 62170, 0.1)
            data["current_l1_a"] = self._get_scaled(b13, 62171, 0.1)
            data["current_l2_a"] = self._get_scaled(b13, 62172, 0.1)
            data["current_l3_a"] = self._get_scaled(b13, 62173, 0.1)

        # --- Block 14: 62186-62193 (8 regs) — total time, IMM kWh, HP1 RPS ---
        b14 = await self._read_block(62186, 8)
        if b14:
            data["total_operation_hours"] = self._get_raw(b14, 62186)
            data["immersion_heater_kwh"] = self._get_raw(b14, 62191)
            data["hp1_rps"] = self._get_scaled(b14, 62193, 0.1)

        # --- Block 15: Room temp (62203) ---
        data["room_temp_1_c"] = await self.read_scaled(62203, 0.1)

        # --- Block 16: 62214-62215 (2 regs) — comp time LSB/MSB ---
        b16 = await self._read_block(62214, 2)
        if b16 and 62214 in b16 and 62215 in b16:
            data["hp1_comp_total_hours"] = _combine_32(b16[62214], b16[62215])

        # --- Block 17: Comp 24h (62234) ---
        raw_24h = await self.read_register(62234)
        if raw_24h:
            data["hp1_comp_24h_hours"] = raw_24h[0]

        # --- Block 18: 62244-62254 (11 regs) — SW ver MD/Year, HS1 status, product/HP1 type ---
        b18 = await self._read_block(62244, 11)
        if b18:
            sw_md = self._get_raw(b18, 62244)
            sw_year = self._get_raw(b18, 62245)
            if sw_md is not None and sw_year is not None:
                data["sw_version"] = f"{sw_year}-{sw_md:04d}"
            hs1_st = self._get_raw(b18, 62246)
            if hs1_st is not None:
                data["hs1_status_code"] = hs1_st
                data["hs1_status"] = STATUS_HS1_MAP.get(hs1_st, f"Unknown({hs1_st})")
            data["product_type"] = self._get_raw(b18, 62253)
            data["hp1_type"] = self._get_raw(b18, 62254)

        # --- Block 19: 62274-62276 (3 regs) — tank lower setpoint, DHW upper temp ---
        b19 = await self._read_block(62274, 3)
        if b19:
            data["tank_lower_setpoint_c"] = self._get_scaled(b19, 62274, 0.1)
            data["dhw_upper_temp_c"] = self._get_scaled(b19, 62276, 0.1)

        # --- Block 20: 62301-62305 (5 regs) — SG mode, elspot, radiator pumps ---
        b20 = await self._read_block(62301, 5)
        if b20:
            sg = self._get_raw(b20, 62301)
            if sg is not None:
                data["sg_mode_code"] = sg
                data["sg_mode"] = SG_MODE_MAP.get(sg, f"Unknown({sg})")
            data["elspot_price_mwh"] = self._get_raw(b20, 62302)
            data["elspot_price_mwh_dec"] = self._get_raw(b20, 62303)
            data["radiator_pump_1"] = self._get_raw(b20, 62304)
            data["radiator_pump_2"] = self._get_raw(b20, 62305)

        return data

    # ------------------------------------------------------------------
    # Heat-pump status (optimised)
    # ------------------------------------------------------------------

    async def get_hp_status(self) -> dict:
        """
        Return compressor / refrigeration circuit status.

        Uses individual reads for registers that are far apart (10-register gaps).
        """
        data: dict = {}
        try:
            hv_raw = await self.read_register(REG_HP1_STATUS)
            if hv_raw:
                hv = hv_raw[0]
                data["hp1_status_code"] = hv
                data["hp1_status"] = STATUS_HP1_MAP.get(hv, f"Unknown({hv})")

            data["hp1_rps"] = await self.read_scaled(REG_HP1_RPS, 0.1)
            data["hp1_brine_in_c"] = await self.read_scaled(REG_HP1_BRINE_IN, 0.1)
            data["hp1_brine_out_c"] = await self.read_scaled(REG_HP1_BRINE_OUT, 0.1)
            data["hp1_high_pressure_bar"] = await self.read_scaled(REG_HP1_HIGH_PRESSURE, 0.1)
            data["hp1_low_pressure_bar"] = await self.read_scaled(REG_HP1_LOW_PRESSURE, 0.1)
            data["hp1_discharge_gas_c"] = await self.read_scaled(REG_HP1_DISCHARGE_GAS, 0.1)
            data["hp1_suction_gas_c"] = await self.read_scaled(REG_HP1_SUCTION_GAS, 0.1)
            data["hp1_temp_in_c"] = await self.read_scaled(REG_HP1_TEMP_IN, 0.1)
            data["hp1_temp_out_c"] = await self.read_scaled(REG_HP1_TEMP_OUT, 0.1)

            b_comp = await self._read_block(REG_HP1_COMP_TIME_LSB, 2)
            if b_comp and REG_HP1_COMP_TIME_LSB in b_comp and REG_HP1_COMP_TIME_MSB in b_comp:
                data["hp1_comp_total_hours"] = _combine_32(
                    b_comp[REG_HP1_COMP_TIME_LSB], b_comp[REG_HP1_COMP_TIME_MSB]
                )
            raw_24h = await self.read_register(REG_HP1_COMP_24H)
            if raw_24h:
                data["hp1_comp_24h_hours"] = raw_24h[0]

            data["hp1_charge_pump_pct"] = await self.read_scaled(REG_HP1_CHARGE_PUMP, 0.1)
            data["hp1_brine_pump_pct"] = await self.read_scaled(REG_HP1_BRINE_PUMP, 0.1)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_hp_status error: %s", exc)
            data["error"] = str(exc)
        return data

    # ------------------------------------------------------------------
    # Electrical (optimised with block read)
    # ------------------------------------------------------------------

    async def get_electrical(self) -> dict:
        """
        Return electrical measurements.

        Uses a block read for the current registers (62170-62173).
        """
        data: dict = {}
        try:
            # Block read: 62168-62173 (6 regs: IMM power, [gap], max current, L1, L2, L3)
            b = await self._read_block(62168, 6)
            if b:
                data["immersion_heater_kw"] = self._get_scaled(b, 62168, 0.1)
                data["max_current_a"] = self._get_scaled(b, 62170, 0.1)
                data["current_l1_a"] = self._get_scaled(b, 62171, 0.1)
                data["current_l2_a"] = self._get_scaled(b, 62172, 0.1)
                data["current_l3_a"] = self._get_scaled(b, 62173, 0.1)

            raw_kwh = await self.read_register(REG_IMM_HEATER_KWH)
            if raw_kwh:
                data["immersion_heater_kwh"] = raw_kwh[0]

            # Block read: 62302-62303 (2 regs: elspot price + decimals)
            b_price = await self._read_block(62302, 2)
            if b_price:
                data["elspot_price_mwh"] = self._get_raw(b_price, 62302)
                data["elspot_price_mwh_dec"] = self._get_raw(b_price, 62303)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_electrical error: %s", exc)
            data["error"] = str(exc)
        return data

    # ------------------------------------------------------------------
    # DHW status (optimised)
    # ------------------------------------------------------------------

    async def get_dhw_status(self) -> dict:
        """
        Return domestic hot-water (DHW) status.

        Uses block reads where registers are adjacent.
        """
        data: dict = {}
        try:
            # Block 62000-62003: outdoor, dhw_stop, [gap], dhw_temp
            b = await self._read_block(62000, 4)
            if b:
                data["dhw_stop_temp_c"] = self._get_scaled(b, 62001, 0.1)
                data["dhw_temp_c"] = self._get_scaled(b, 62003, 0.1)

            data["dhw_upper_temp_c"] = await self.read_scaled(REG_DHW_UPPER_TEMP, 0.1)
            data["tank_lower_setpoint_c"] = await self.read_scaled(REG_TANK_LOWER_SETPOINT, 0.1)

            raw_mode = await self.read_register(REG_HOT_WATER_MODE)
            if raw_mode:
                mv = raw_mode[0]
                data["dhw_mode_code"] = mv
                data["dhw_mode"] = DHW_MODE_MAP.get(mv, f"Unknown({mv})")

            raw_pump = await self.read_register(REG_DHW_PUMP)
            if raw_pump:
                data["dhw_pump_state"] = raw_pump[0]
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_dhw_status error: %s", exc)
            data["error"] = str(exc)
        return data

    # ------------------------------------------------------------------
    # Heating circuit status (optimised with block read)
    # ------------------------------------------------------------------

    async def get_heating_status(self) -> dict:
        """
        Return heating circuit (HS1) status.

        Uses block reads for adjacent registers.
        """
        data: dict = {}
        try:
            # Block 62006-62017 covers: radiator_temp, hs1_setpoint, ..., hs1_flow, ..., return_temp, dhw_pump, hp1_status
            # But we only need a few from 62006-62016
            b = await self._read_block(62006, 10)  # 62006-62015
            if b:
                data["radiator_temp_c"] = self._get_scaled(b, 62006, 0.1)
                data["hs1_setpoint_c"] = self._get_scaled(b, 62007, 0.1)
                data["hs1_primary_flow_c"] = self._get_scaled(b, 62011, 0.1)
                data["return_temp_c"] = self._get_scaled(b, 62015, 0.1)

            data["room_temp_1_c"] = await self.read_scaled(REG_ROOM_TEMP_1, 0.1)
            data["degree_minute"] = await self.read_scaled(REG_DEGREE_MINUTE, 0.1)

            # Settings registers (61xxx) — read individually
            data["heating_curve_inclination"] = await self.read_scaled(REG_HS1_INCLINATION, 0.1)
            data["room_temp_setpoint_c"] = await self.read_scaled(REG_HS1_ROOM_TEMP_SETPOINT, 0.1)

            raw_hs1 = await self.read_register(REG_HS1_STATUS)
            if raw_hs1:
                hv = raw_hs1[0]
                data["hs1_status_code"] = hv
                data["hs1_status"] = STATUS_HS1_MAP.get(hv, f"Unknown({hv})")

            # Block 62304-62305: radiator pumps
            b_pumps = await self._read_block(62304, 2)
            if b_pumps:
                data["radiator_pump_1"] = self._get_raw(b_pumps, 62304)
                data["radiator_pump_2"] = self._get_raw(b_pumps, 62305)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_heating_status error: %s", exc)
            data["error"] = str(exc)
        return data

    # ------------------------------------------------------------------
    # Control register writes
    # ------------------------------------------------------------------

    async def set_el_price_mode(self, mode: int) -> bool:
        """Set the electricity price mode (1=Low, 2=Normal, 3=High)."""
        if mode not in (1, 2, 3):
            raise ValueError(f"Invalid el_price_mode {mode!r}: must be 1=Low, 2=Normal, 3=High")
        logger.info("Setting ElPriceMode to %s (%d)", EL_PRICE_MODE_MAP.get(mode), mode)
        return await self.write_register(REG_EL_PRICE_MODE, mode)

    async def set_dhw_mode(self, mode: int) -> bool:
        """Set the DHW operation mode (0=Economy, 1=Normal, 2=Comfort)."""
        if mode not in (0, 1, 2):
            raise ValueError(f"Invalid dhw_mode {mode!r}: must be 0=Economy, 1=Normal, 2=Comfort")
        logger.info("Setting DHW mode to %s (%d)", DHW_MODE_MAP.get(mode), mode)
        return await self.write_register(REG_DHW_MODE, mode)

    async def set_room_temp_setpoint(self, temp: float) -> bool:
        """Set the HS1 room temperature setpoint (persistent, factor 0.1 °C)."""
        raw = int(round(temp / 0.1))
        if raw < 0:
            raw = raw & 0xFFFF
        logger.info("Setting room temp setpoint to %.1f °C (raw=%d)", temp, raw)
        return await self.write_register(REG_HS1_ROOM_TEMP_SETPOINT, raw)

    async def set_heating_curve(self, inclination: float) -> bool:
        """Set the HS1 heating curve inclination (persistent, factor 0.1)."""
        raw = int(round(inclination / 0.1))
        logger.info("Setting heating curve inclination to %.2f (raw=%d)", inclination, raw)
        return await self.write_register(REG_HS1_INCLINATION, raw)

    async def set_smartgrid(self, mode: int) -> bool:
        """Set SmartGrid mode (0=Normal, 1=Block, 2=LowPrice, 3=HighCap) via reg 1100 bits 6-7."""
        if mode not in (0, 1, 2, 3):
            raise ValueError(f"Invalid SmartGrid mode {mode!r}: must be 0–3")
        current_raw = await self.read_register(REG_VIRTUAL_DIGITAL_INPUTS)
        current_val = current_raw[0] if current_raw else 0
        new_val = current_val & ~(0b11 << 6)
        if mode == 1:
            new_val |= (0b01 << 6)
        elif mode == 2:
            new_val |= (0b10 << 6)
        elif mode == 3:
            new_val |= (0b11 << 6)
        logger.info(
            "Setting SmartGrid mode to %s (%d), register 1100 value: 0x%04X",
            SG_MODE_MAP.get(mode), mode, new_val,
        )
        return await self.write_register(REG_VIRTUAL_DIGITAL_INPUTS, new_val)

    # ------------------------------------------------------------------
    # Alarms (optimised with block reads)
    # ------------------------------------------------------------------

    async def get_alarms(self) -> dict:
        """Read alarm and info counts, plus the first two alarm entries."""
        data: dict = {
            "alarm_count": 0,
            "info_count": 0,
            "alarms": [],
        }
        try:
            raw_count = await self.read_register(REG_ALARM_COUNT)
            if raw_count:
                combined = raw_count[0]
                data["alarm_count"] = combined & 0xFF
                data["info_count"] = (combined >> 8) & 0xFF
                data["raw_count_hex"] = f"0x{combined:04X}"

            # Block read alarm 1+2: 65010-65013 (4 regs)
            b = await self._read_block(65010, 4)
            if b:
                if 65010 in b and 65011 in b:
                    data["alarms"].append({
                        "index": 1,
                        "hp_flag": b[65010],
                        "code": b[65011],
                    })
                if 65012 in b and 65013 in b:
                    data["alarms"].append({
                        "index": 2,
                        "hp_flag": b[65012],
                        "code": b[65013],
                    })
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_alarms error: %s", exc)
            data["error"] = str(exc)
        return data

    # ------------------------------------------------------------------
    # System info (optimised)
    # ------------------------------------------------------------------

    async def get_system_info(self) -> dict:
        """Return software version, product type, and total operation time."""
        data: dict = {}
        try:
            # Block: 62244-62254 (11 regs)
            b = await self._read_block(62244, 11)
            if b:
                sw_md = self._get_raw(b, 62244)
                sw_year = self._get_raw(b, 62245)
                if sw_md is not None and sw_year is not None:
                    data["sw_version"] = f"{sw_year}-{sw_md:04d}"
                data["product_type"] = self._get_raw(b, 62253)
                data["hp1_type"] = self._get_raw(b, 62254)

            raw_hp1_sw = await self.read_register(62157)
            if raw_hp1_sw:
                data["hp1_sw_version"] = raw_hp1_sw[0]

            raw_total = await self.read_register(REG_TOTAL_TIME_LSB)
            if raw_total:
                data["total_operation_hours"] = raw_total[0]
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_system_info error: %s", exc)
            data["error"] = str(exc)
        return data

    # ------------------------------------------------------------------
    # Synchronous wrappers
    # ------------------------------------------------------------------

    def _run(self, coro):
        """Run an async coroutine from a synchronous context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    async def _fetch_with_connection(self, coro_factory):
        """Connect, run *coro_factory*, disconnect.  Returns the result."""
        await self.connect()
        try:
            return await coro_factory()
        finally:
            await self.disconnect()

    def get_sensor_overview_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_sensor_overview`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_sensor_overview)
        return self._run(_inner())

    def get_hp_status_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_hp_status`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_hp_status)
        return self._run(_inner())

    def get_electrical_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_electrical`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_electrical)
        return self._run(_inner())

    def get_dhw_status_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_dhw_status`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_dhw_status)
        return self._run(_inner())

    def get_heating_status_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_heating_status`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_heating_status)
        return self._run(_inner())

    def get_alarms_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_alarms`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_alarms)
        return self._run(_inner())

    def get_system_info_sync(self) -> dict:
        """Synchronous wrapper for :meth:`get_system_info`."""
        async def _inner():
            return await self._fetch_with_connection(self.get_system_info)
        return self._run(_inner())
