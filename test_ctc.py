"""
test_ctc.py - Standalone test script for CTC EcoPart i612M Modbus TCP integration

Usage::

    python test_ctc.py

The script reads connection parameters from config.json (key "ctc") if present,
otherwise falls back to the compiled-in defaults (192.168.2.74:502, unit 1).

IMPORTANT:
    - CTC allows only ONE Modbus TCP connection at a time.
    - If Homey or another Modbus client is active, disable it first.
    - The client uses delays between requests (built into ctc_client.py).

Tests performed:
    1. TCP connection to the heat pump
    2. Read sensor overview (block reads — ~20 requests instead of 30+)
    3. Read heat-pump (refrigeration circuit) status
    4. Read electrical measurements
    5. Read DHW status
    6. Read heating circuit status
    7. Read alarm register
    8. Read system info
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Ensure ctc_client is importable when run from workspace root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ctc_client import CTCClient

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

def _ok(msg: str) -> str:
    return f"{_GREEN}\u2713 {msg}{_RESET}"

def _fail(msg: str) -> str:
    return f"{_RED}\u2717 {msg}{_RESET}"

def _section(title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'\u2500' * 60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {title}{_RESET}")
    print(f"{_BOLD}{_CYAN}{'\u2500' * 60}{_RESET}")

def _pretty(data: Any, indent: int = 2) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load CTC connection parameters from config.json if it exists."""
    defaults = {
        "host": "192.168.2.74",
        "port": 502,
        "unit_id": 1,
        "timeout": 10,
    }
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                full_config = json.load(fh)
            ctc_cfg = full_config.get("ctc", {})
            defaults.update(ctc_cfg)
            print(f"{_YELLOW}Loaded config from {config_path}{_RESET}")
        except Exception as exc:
            print(f"{_YELLOW}Could not parse config.json: {exc} – using defaults{_RESET}")
    else:
        print(f"{_YELLOW}config.json not found – using compiled-in defaults{_RESET}")
    return defaults


# ---------------------------------------------------------------------------
# Individual test functions
# ---------------------------------------------------------------------------

async def test_connection(client: CTCClient) -> bool:
    """Test 1: Establish a Modbus TCP connection."""
    _section("Test 1: Connection")
    connected = await client.connect()
    if connected:
        print(_ok(f"Connected to {client.host}:{client.port} (unit {client.unit_id})"))
    else:
        print(_fail(f"Could NOT connect to {client.host}:{client.port}"))
    return connected


async def test_sensor_overview(client: CTCClient) -> bool:
    """Test 2: Read full sensor overview (block reads)."""
    _section("Test 2: Sensor Overview (block reads)")
    try:
        data = await client.get_sensor_overview()
        if data:
            print(_ok(f"Sensor overview: {len(data)} fields read"))
            fields = [
                ("Outdoor temperature",      "outdoor_temp_c",        "\u00b0C"),
                ("DHW temperature",           "dhw_temp_c",            "\u00b0C"),
                ("DHW upper tank",            "dhw_upper_temp_c",      "\u00b0C"),
                ("HS1 primary flow",          "hs1_primary_flow_c",    "\u00b0C"),
                ("HS1 setpoint",              "hs1_setpoint_c",        "\u00b0C"),
                ("Return temperature",        "return_temp_c",         "\u00b0C"),
                ("Room temperature 1",        "room_temp_1_c",         "\u00b0C"),
                ("HP1 brine in",              "hp1_brine_in_c",        "\u00b0C"),
                ("HP1 brine out",             "hp1_brine_out_c",       "\u00b0C"),
                ("HP1 discharge gas",         "hp1_discharge_gas_c",   "\u00b0C"),
                ("HP1 suction gas",           "hp1_suction_gas_c",     "\u00b0C"),
                ("HP1 high pressure",         "hp1_high_pressure_bar", "bar"),
                ("HP1 low pressure",          "hp1_low_pressure_bar",  "bar"),
                ("Degree minute",             "degree_minute",         ""),
                ("HP1 RPS",                   "hp1_rps",               ""),
                ("Immersion heater",          "immersion_heater_kw",   "kW"),
                ("Current L1",                "current_l1_a",          "A"),
                ("System status",             "system_status",         ""),
                ("HP1 status",                "hp1_status",            ""),
                ("HS1 status",                "hs1_status",            ""),
                ("SmartGrid mode",            "sg_mode",               ""),
                ("SW version",                "sw_version",            ""),
                ("Product type",              "product_type",          ""),
                ("Compressor total hours",    "hp1_comp_total_hours",  "h"),
                ("Compressor last 24 h",      "hp1_comp_24h_hours",    "h"),
            ]
            for label, key, unit in fields:
                val = data.get(key)
                suffix = f" {unit}" if unit and val is not None else ""
                print(f"  {label:<30} {val}{suffix}")
            return True
        else:
            print(_fail("Empty response from sensor overview"))
            return False
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


async def test_hp_status(client: CTCClient) -> bool:
    """Test 3: Read heat-pump refrigeration circuit status."""
    _section("Test 3: Heat-Pump (Refrigeration) Status")
    try:
        data = await client.get_hp_status()
        if data:
            print(_ok("HP status read successfully"))
            print(_pretty(data))
            return True
        print(_fail("Empty HP status response"))
        return False
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


async def test_electrical(client: CTCClient) -> bool:
    """Test 4: Read electrical measurements."""
    _section("Test 4: Electrical Measurements")
    try:
        data = await client.get_electrical()
        if data:
            print(_ok("Electrical data read successfully"))
            fields = [
                ("Current L1",           "current_l1_a",          "A"),
                ("Current L2",           "current_l2_a",          "A"),
                ("Current L3",           "current_l3_a",          "A"),
                ("Max current",          "max_current_a",         "A"),
                ("Immersion heater",     "immersion_heater_kw",   "kW"),
                ("Immersion heater kWh", "immersion_heater_kwh",  "kWh"),
                ("Elspot price",         "elspot_price_mwh",      "SEK/MWh"),
            ]
            for label, key, unit in fields:
                val = data.get(key)
                suffix = f" {unit}" if unit and val is not None else ""
                print(f"  {label:<30} {val}{suffix}")
            return True
        print(_fail("Empty electrical response"))
        return False
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


async def test_dhw_status(client: CTCClient) -> bool:
    """Test 5: Read DHW status."""
    _section("Test 5: DHW Status")
    try:
        data = await client.get_dhw_status()
        if data:
            print(_ok("DHW status read successfully"))
            print(_pretty(data))
            return True
        print(_fail("Empty DHW response"))
        return False
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


async def test_heating_status(client: CTCClient) -> bool:
    """Test 6: Read heating circuit status."""
    _section("Test 6: Heating Circuit (HS1) Status")
    try:
        data = await client.get_heating_status()
        if data:
            print(_ok("Heating status read successfully"))
            print(_pretty(data))
            return True
        print(_fail("Empty heating status response"))
        return False
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


async def test_alarms(client: CTCClient) -> bool:
    """Test 7: Read alarm register."""
    _section("Test 7: Alarms")
    try:
        data = await client.get_alarms()
        alarm_count = data.get("alarm_count", "?")
        info_count = data.get("info_count", "?")
        print(_ok(f"Alarm register read – alarms: {alarm_count}, info: {info_count}"))
        if data.get("alarms"):
            print("  Active alarms:")
            for alarm in data["alarms"]:
                print(f"    Alarm {alarm['index']}: HP flag={alarm['hp_flag']}, code={alarm['code']}")
        else:
            print("  No active alarms")
        return True
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


async def test_system_info(client: CTCClient) -> bool:
    """Test 8: Read system information."""
    _section("Test 8: System Info")
    try:
        data = await client.get_system_info()
        if data:
            print(_ok("System info read successfully"))
            print(_pretty(data))
            return True
        print(_fail("Empty system info response"))
        return False
    except Exception as exc:
        print(_fail(f"Exception: {exc}"))
        return False


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

async def run_all_tests() -> None:
    """Run all tests against the CTC EcoPart heat pump."""
    config = load_config()

    print(f"\n{_BOLD}CTC EcoPart i612M – Modbus TCP Integration Test{_RESET}")
    print(f"Target: {config['host']}:{config['port']}  unit_id={config['unit_id']}")
    print(f"{_YELLOW}NOTE: CTC allows only ONE Modbus TCP connection.{_RESET}")
    print(f"{_YELLOW}Ensure Homey Modbus is disabled before running this test.{_RESET}")

    client = CTCClient(
        host=config["host"],
        port=config["port"],
        unit_id=config["unit_id"],
        timeout=config["timeout"],
    )

    # Test 1: Connection (must succeed for all subsequent tests)
    connected = await test_connection(client)
    if not connected:
        print(f"\n{_RED}{_BOLD}ABORT: Cannot connect – check IP address and Modbus TCP settings.{_RESET}")
        print("Possible causes:")
        print("  1. Homey or another Modbus client is holding the connection")
        print(f"  2. IP {config['host']} is wrong (check router DHCP / static assignment)")
        print(f"  3. Modbus TCP is not enabled on the CTC (check BMS/Fj\u00e4rrstyrning menu)")
        print(f"  4. Port {config['port']} is blocked by firewall or wrong VLAN")
        return

    results: dict[str, bool] = {}

    try:
        results["sensor_overview"] = await asyncio.wait_for(
            test_sensor_overview(client), timeout=60
        )
        results["hp_status"] = await asyncio.wait_for(
            test_hp_status(client), timeout=30
        )
        results["electrical"] = await asyncio.wait_for(
            test_electrical(client), timeout=15
        )
        results["dhw_status"] = await asyncio.wait_for(
            test_dhw_status(client), timeout=15
        )
        results["heating_status"] = await asyncio.wait_for(
            test_heating_status(client), timeout=15
        )
        results["alarms"] = await asyncio.wait_for(
            test_alarms(client), timeout=15
        )
        results["system_info"] = await asyncio.wait_for(
            test_system_info(client), timeout=15
        )
    except asyncio.TimeoutError:
        print(_fail("Test timed out – the heat pump stopped responding"))
    finally:
        await client.disconnect()

    # Summary
    _section("Test Summary")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = _ok("PASS") if ok else _fail("FAIL")
        print(f"  {name:<30} {status}")
    colour = _GREEN if passed == total else _RED
    print(f"\n{colour}{_BOLD}Result: {passed}/{total} tests passed{_RESET}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
