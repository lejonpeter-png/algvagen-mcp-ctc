# CTC EcoPart i612M — Modbus TCP Integration

Modbus TCP-klient och FastMCP-verktyg för CTC EcoPart i612M bergvärmepump.
Integreras i [algvagen-mcp](file:///Users/peterlejon/Zoo%20Home/algvagen-mcp/) servern.

## Filer

| Fil | Beskrivning |
|-----|-------------|
| `ctc_client.py` | Async Modbus TCP-klient med block-reads och 0.3s delay mellan requests |
| `ctc_tool.py` | FastMCP tool-modul — 12 verktyg (7 läs + 5 skriv) |
| `test_ctc.py` | Fullständigt testsvit (8 tester) |
| `test_ctc_minimal.py` | Minimal diagnostik — enskilda register + block-read |
| `server_ctc_patch.py` | Instruktioner för integration i server.py |
| `config_ctc_section.json` | CTC-sektion att lägga i config.json |

## Snabbstart

### 1. Kopiera filer till algvagen-mcp

```bash
cd "/Users/peterlejon/Zoo Home/algvagen-mcp"
git clone git@github.com:lejonpeter-png/algvagen-mcp-ctc.git /tmp/ctc-tmp
cp /tmp/ctc-tmp/ctc_client.py /tmp/ctc-tmp/ctc_tool.py .
cp /tmp/ctc-tmp/test_ctc.py /tmp/ctc-tmp/test_ctc_minimal.py .
```

### 2. Installera pymodbus

```bash
.venv/bin/pip install "pymodbus>=3.6.0"
```

### 3. Testa (Homey Modbus måste vara AV)

```bash
.venv/bin/python test_ctc.py
```

### 4. Integrera i server.py

Lägg till import:
```python
from ctc_tool import register_ctc_tools
```

Efter befintliga tool-registreringar:
```python
register_ctc_tools(mcp, config.get("ctc", {}))
```

### 5. Lägg till i config.json

```json
"ctc": {
  "host": "192.168.2.74",
  "port": 502,
  "unit_id": 1,
  "timeout": 10
}
```

### 6. Starta om MCP-servern

## Tekniska detaljer

- **IP**: 192.168.2.74, **Port**: 502, **Modbus ID**: 1
- **Protokoll**: Modbus TCP, Holding Registers (FC 0x03 read / FC 0x10 write)
- **Max 1 TCP-anslutning** — CTC stänger ner extra anslutningar
- **Block-reads**: ~20 requests istället för 30+ per overview
- **0.3s delay** mellan varje Modbus-request
- **1.0s delay** efter TCP connect innan första read
- **pymodbus 3.12.1**: använder `device_id=` keyword (inte `slave=`)

## MCP-verktyg

### Läsning
- `get_heat_pump_overview` — Komplett sensoröversikt
- `get_heat_pump_temperatures` — Värmekrets HS1
- `get_heat_pump_hp_status` — Kompressor/kylkrets
- `get_heat_pump_electrical` — Eldata (ström, tillsats, elspot)
- `get_heat_pump_dhw` — Varmvatten
- `get_heat_pump_alarms` — Aktiva larm
- `get_heat_pump_system_info` — Version, produkttyp, drifttid

### Styrning (control registers — 5 min timeout)
- `set_heat_pump_el_price_mode` — Elprisläge
- `set_heat_pump_dhw_mode` — VV-läge
- `set_heat_pump_room_temp` — Rumstemperatur (persistent)
- `set_heat_pump_heating_curve` — Värmekurva (persistent)
- `set_heat_pump_smartgrid` — SmartGrid-läge
