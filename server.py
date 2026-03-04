import json
import os
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from energy_manager import EnergyManager
from smhi_client import SmhiClient
from ctc_tool import register_ctc_tools

mcp = FastMCP("algvagen-mcp")

_energy = None
_smhi = None
_config = None

def _load_config():
    global _config
    if _config is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _config = json.load(f)
        except Exception:
            _config = {}
    return _config

def get_energy():
    global _energy
    if _energy is None:
        _energy = EnergyManager(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    return _energy

def get_smhi():
    global _smhi
    if _smhi is None:
        _smhi = SmhiClient()
    return _smhi

# Register CTC EcoPart heat pump tools (Modbus TCP)
register_ctc_tools(mcp, _load_config().get("ctc", {}))


@mcp.tool()
def get_energy_dashboard() -> str:
    """Get complete energy dashboard: solar production, heat pump, thermostats, temperatures and live energy data."""
    em = get_energy()
    result = {}
    result["timestamp"] = datetime.now().isoformat()
    result["solar"] = em.get_solar_production()
    result["heat_pump"] = em.get_heat_pump_status()
    result["thermostats"] = em.get_thermostats()
    result["temperatures"] = em.get_temperature_sensors()
    try:
        result["live_energy"] = em.get_live_energy()
    except Exception as e:
        result["live_energy"] = {"error": str(e)}
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def get_solar_production() -> str:
    """Get current solar panel production from Fronius inverters. Returns power in watts and total energy in kWh."""
    em = get_energy()
    return json.dumps(em.get_solar_production(), indent=2)


@mcp.tool()
def get_heat_pump_status() -> str:
    """Get CTC EcoPart heat pump status: power consumption per phase, temperatures (outdoor, supply, return)."""
    em = get_energy()
    return json.dumps(em.get_heat_pump_status(), indent=2, ensure_ascii=False)


@mcp.tool()
def get_thermostats() -> str:
    """Get all Danfoss Ally radiator thermostats with target and current temperatures."""
    em = get_energy()
    return json.dumps(em.get_thermostats(), indent=2, ensure_ascii=False)


@mcp.tool()
def get_temperatures() -> str:
    """Get all temperature and humidity sensors: Shelly HT, Netatmo, outdoor, floor heating etc."""
    em = get_energy()
    return json.dumps(em.get_temperature_sensors(), indent=2, ensure_ascii=False)


@mcp.tool()
def get_live_energy() -> str:
    """Get real-time energy consumption and generation from Homey Energy, broken down by zone."""
    em = get_energy()
    return json.dumps(em.get_live_energy(), indent=2, ensure_ascii=False)


@mcp.tool()
def get_all_devices() -> str:
    """Get all Homey devices with current state and capability values."""
    em = get_energy()
    devices = em.get_all_devices()
    summary = {}
    for did, dev in devices.items():
        caps = dev.get("capabilitiesObj", {})
        values = {}
        for cn, cd in caps.items():
            v = cd.get("value")
            if v is not None:
                values[cn] = v
        summary[dev.get("name", did)] = {
            "class": dev.get("class"),
            "zone": dev.get("zoneName", ""),
            "values": values
        }
    return json.dumps(summary, indent=2, ensure_ascii=False)


@mcp.tool()
def get_weather_forecast() -> str:
    """Get SMHI weather forecast for Sollentuna: temperature, wind, precipitation, cloud cover."""
    smhi = get_smhi()
    # Älgvägen, Sollentuna
    LAT, LON = 59.4281, 17.9507
    timeseries = smhi.get_timeseries(LAT, LON)
    forecast = []
    for point in timeseries[:24]:
        entry = {
            "time": point.get("validTime"),
            "temperature_c": smhi.get_parameter_value(point, "t"),
            "wind_speed_ms": smhi.get_parameter_value(point, "ws"),
            "wind_direction_deg": smhi.get_parameter_value(point, "wd"),
            "precipitation_mm": smhi.get_parameter_value(point, "pmean"),
            "weather_symbol": smhi.get_parameter_value(point, "Wsymb2"),
            "cloud_cover_octas": smhi.get_parameter_value(point, "tcc_mean"),
        }
        forecast.append(entry)
    return json.dumps(forecast, indent=2, ensure_ascii=False)


@mcp.tool()
def get_energy_advice() -> str:
    """Analyze current energy situation and provide recommendations based on solar, heat pump, temperatures and weather."""
    em = get_energy()
    solar = em.get_solar_production()
    ctc = em.get_heat_pump_status()
    thermos = em.get_thermostats()
    temps = em.get_temperature_sensors()

    total_solar_w = sum((d.get("current_power_w") or 0) for d in solar.values())

    total_ctc_w = 0
    for name, data in ctc.items():
        caps = data.get("capabilities", {})
        if "measure_power" in caps:
            total_ctc_w += caps["measure_power"].get("value") or 0

    outdoor_temp = None
    for name, data in temps.items():
        if "outdoor" in name.lower() or "ute" in name.lower():
            outdoor_temp = data.get("temperature")
            break
    if outdoor_temp is None:
        for name, data in ctc.items():
            caps = data.get("capabilities", {})
            if "measure_temperature.sensor0" in caps:
                outdoor_temp = caps["measure_temperature.sensor0"].get("value")

    advice = {
        "timestamp": datetime.now().isoformat(),
        "solar_production_w": total_solar_w,
        "heat_pump_consumption_w": total_ctc_w,
        "net_energy_w": total_solar_w - total_ctc_w,
        "outdoor_temperature_c": outdoor_temp,
        "recommendations": []
    }

    if total_solar_w > total_ctc_w and total_solar_w > 0:
        advice["recommendations"].append("Solar excess - good time for extra loads like EV charging or hot water")
    if total_solar_w == 0:
        advice["recommendations"].append("No solar production - minimize unnecessary consumption")
    if outdoor_temp is not None and outdoor_temp < 0:
        advice["recommendations"].append("Below freezing - heat pump at higher load, expect higher consumption")
    if outdoor_temp is not None and outdoor_temp > 10:
        advice["recommendations"].append("Mild weather - consider lowering thermostat targets to save energy")

    for name, data in thermos.items():
        target = data.get("target_temp")
        current = data.get("current_temp")
        if target and current and current > target + 1:
            advice["recommendations"].append(name + " is " + str(round(current - target, 1)) + "C above target")

    return json.dumps(advice, indent=2, ensure_ascii=False)


def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
