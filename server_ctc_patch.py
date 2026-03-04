"""
server_ctc_patch.py — Instruktioner för CTC EcoPart integration i server.py
===========================================================================
DO NOT run this file — det är en referens.

Filer som ska finnas i /Users/peterlejon/Zoo Home/algvagen-mcp/:
  - ctc_client.py  (Modbus TCP-klient med block-reads och delays)
  - ctc_tool.py    (FastMCP-verktygsmodul, 12 tools)
  - server.py      (befintlig — ändra enligt nedan)
  - config.json    (befintlig — lägg till "ctc"-sektion)

STEG 1 — Lägg till import i server.py (nära befintliga tool-imports)
=====================================================================
"""

from ctc_tool import register_ctc_tools  # CTC EcoPart i612M heat pump

"""
STEG 2 — Anropa registrering efter befintliga tool-registreringar
==================================================================
Hitta raden där du anropar t.ex. register_fronius_tools(mcp) och lägg
till raden nedan direkt efter:
"""

# register_fronius_tools(mcp)     # <-- befintlig
# register_weather_tools(mcp)     # <-- befintlig
# register_homey_tools(mcp)       # <-- befintlig
register_ctc_tools(mcp, config.get("ctc", {}))  # <-- LÄGG TILL

"""
STEG 3 — Lägg till CTC-sektion i config.json
==============================================
Öppna config.json och lägg till "ctc"-blocket:
"""

# {
#   "fronius": { ... },
#   "smhi": { ... },
#   "ctc": {
#     "host": "192.168.2.74",
#     "port": 502,
#     "unit_id": 1,
#     "timeout": 10
#   }
# }

"""
STEG 4 — Installera pymodbus (om det inte redan finns)
=======================================================
"""
# cd "/Users/peterlejon/Zoo Home/algvagen-mcp"
# .venv/bin/pip install "pymodbus>=3.6.0"

"""
STEG 5 — Starta om MCP-servern
================================
"""
# Stoppa befintlig server-process och starta om.
# CTC-verktygen registreras automatiskt vid uppstart.

"""
STEG 6 — Testa CTC-verktygen
==============================
Kör test_ctc.py för att verifiera att allt fungerar:

    cd "/Users/peterlejon/Zoo Home/algvagen-mcp"
    .venv/bin/python test_ctc.py

OBS: Homey Modbus MÅSTE vara avaktiverat innan test/drift.
CTC tillåter bara EN Modbus TCP-anslutning åt gången.

VERKTYG SOM REGISTRERAS (13 st):
  Läsning:
    - get_heat_pump_overview       Komplett sensoröversikt (temps, tryck, status, el)
    - get_heat_pump_temperatures   Värmekrets HS1 (framledning, börvärde, returtemp)
    - get_heat_pump_hp_status      Kompressor/kylkrets (RPS, brine, tryck)
    - get_heat_pump_electrical     Eldata (ström L1-L3, tilläggskvärme, elspot)
    - get_heat_pump_dhw            Varmvatten (temp, mode, pump)
    - get_heat_pump_alarms         Aktiva larm
    - get_heat_pump_system_info    Mjukvaruversion, produkttyp, drifttid

  Styrning:
    - set_heat_pump_el_price_mode  Elprisläge (1=Low, 2=Normal, 3=High) [5 min timeout]
    - set_heat_pump_dhw_mode       VV-läge (0=Economy, 1=Normal, 2=Comfort) [5 min timeout]
    - set_heat_pump_room_temp      Rumstemperatur börvärde (persistent)
    - set_heat_pump_heating_curve  Värmekurva lutning (persistent)
    - set_heat_pump_smartgrid      SmartGrid (0=Normal, 1=Block, 2=LågPris, 3=HögKap) [5 min timeout]
"""
