"""
test_ctc_minimal.py - Minimal CTC EcoPart diagnostic script

Tests ONE register at a time with proper delays between reads.
CTC heat pumps have a slow Modbus TCP server that needs:
  - A delay after connect before first read (2-3 seconds)
  - A delay between consecutive reads (0.5-1 second)
  - Only ONE TCP connection at a time

Usage:
    python test_ctc_minimal.py
"""
from __future__ import annotations
import asyncio
import logging
import sys

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

# Enable full debug logging for pymodbus
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("ctc_test")

# --- Configuration ---
HOST = "192.168.2.74"
PORT = 502
UNIT_ID = 1
TIMEOUT = 10          # generous timeout for slow CTC
DELAY_AFTER_CONNECT = 3.0   # seconds to wait after TCP connect
DELAY_BETWEEN_READS = 1.0   # seconds between register reads

# Test registers - a few safe read-only sensor registers
TEST_REGISTERS = [
    (62253, "Product type",          1,   ""),
    (62000, "Outdoor temperature",   0.1, "\u00b0C"),
    (62003, "DHW temperature",       0.1, "\u00b0C"),
    (62005, "System status",         1,   ""),
    (62017, "HP1 status",            1,   ""),
]


def to_int16(raw: int) -> int:
    return raw - 65536 if raw > 32767 else raw


async def test_single_register(client, address, name, factor, unit):
    """Read a single register and print the result."""
    try:
        # Try device_id first (pymodbus 3.12+), then slave
        try:
            result = await client.read_holding_registers(
                address=address, count=1, device_id=UNIT_ID
            )
        except TypeError:
            result = await client.read_holding_registers(
                address=address, count=1, slave=UNIT_ID
            )

        if result.isError():
            print(f"  \u2717 {name} (reg {address}): Modbus error: {result}")
            return False

        raw = result.registers[0]
        if factor != 1:
            val = round(to_int16(raw) * factor, 1)
            print(f"  \u2713 {name} (reg {address}): raw={raw} \u2192 {val} {unit}")
        else:
            print(f"  \u2713 {name} (reg {address}): {raw} {unit}")
        return True

    except ModbusException as exc:
        print(f"  \u2717 {name} (reg {address}): ModbusException: {exc}")
        return False
    except Exception as exc:
        print(f"  \u2717 {name} (reg {address}): {type(exc).__name__}: {exc}")
        return False


async def test_block_read(client, start_address, count, name):
    """Read a block of registers in one request (more efficient)."""
    try:
        try:
            result = await client.read_holding_registers(
                address=start_address, count=count, device_id=UNIT_ID
            )
        except TypeError:
            result = await client.read_holding_registers(
                address=start_address, count=count, slave=UNIT_ID
            )

        if result.isError():
            print(f"  \u2717 Block {name} (reg {start_address}, count={count}): Modbus error: {result}")
            return False

        print(f"  \u2713 Block {name} (reg {start_address}, count={count}): got {len(result.registers)} registers")
        for i, raw in enumerate(result.registers):
            addr = start_address + i
            print(f"      [{addr}] = {raw} (signed: {to_int16(raw)})")
        return True

    except ModbusException as exc:
        print(f"  \u2717 Block {name}: ModbusException: {exc}")
        return False
    except Exception as exc:
        print(f"  \u2717 Block {name}: {type(exc).__name__}: {exc}")
        return False


async def main():
    print("=" * 60)
    print("CTC EcoPart i612M - Minimal Modbus TCP Diagnostic")
    print(f"Target: {HOST}:{PORT}  unit_id={UNIT_ID}")
    print(f"Timeout: {TIMEOUT}s, delay after connect: {DELAY_AFTER_CONNECT}s")
    print(f"Delay between reads: {DELAY_BETWEEN_READS}s")
    print("=" * 60)

    # --- Phase 1: Connect ---
    print("\n--- Phase 1: TCP Connection ---")
    client = AsyncModbusTcpClient(
        host=HOST,
        port=PORT,
        timeout=TIMEOUT,
    )
    connected = await client.connect()
    if not connected:
        print("\u2717 FAILED to connect. Check IP/port/network.")
        return

    print(f"\u2713 Connected to {HOST}:{PORT}")
    print(f"  Waiting {DELAY_AFTER_CONNECT}s before first read...")
    await asyncio.sleep(DELAY_AFTER_CONNECT)

    # --- Phase 2: Single register reads with delays ---
    print("\n--- Phase 2: Single Register Reads (with delays) ---")
    passed = 0
    total = len(TEST_REGISTERS)

    for i, (addr, name, factor, unit) in enumerate(TEST_REGISTERS):
        ok = await test_single_register(client, addr, name, factor, unit)
        if ok:
            passed += 1
        if i < total - 1:
            await asyncio.sleep(DELAY_BETWEEN_READS)

    print(f"\nResult: {passed}/{total} registers read successfully")

    # --- Phase 3: Block read test (more efficient) ---
    if passed > 0:
        print("\n--- Phase 3: Block Read Test ---")
        print(f"  Waiting {DELAY_BETWEEN_READS}s...")
        await asyncio.sleep(DELAY_BETWEEN_READS)

        # Read 62000-62007 as a block (8 registers)
        ok = await test_block_read(client, 62000, 8, "Sensors 62000-62007")
        if ok:
            print("  \u2192 Block read works - can use batch reads for efficiency")

    # --- Cleanup ---
    print("\n--- Cleanup ---")
    client.close()
    print("\u2713 Disconnected cleanly")

    if passed == 0:
        print("\n\u26a0 All reads failed. Possible causes:")
        print("  1. CTC Modbus TCP not enabled (check display menu 'Definiera fj\u00e4rr')")
        print("  2. Previous connection not closed properly (CTC allows only 1 connection)")
        print("     \u2192 Try power-cycling the CTC display or wait ~5 minutes")
        print("  3. Wrong VLAN / firewall blocking Modbus")
        print("  4. unit_id might not be 1 (check CTC settings)")
    elif passed == total:
        print("\n\u2713 All reads successful. CTC Modbus is working.")
        print("  Next step: update ctc_client.py with delays between reads")


if __name__ == "__main__":
    asyncio.run(main())
