# Three-Node ESP32 BLE Intrusion Detection System

A real-time BLE device localization and perimeter monitoring system built with three ESP32 nodes arranged in a triangular configuration. Detects, identifies, and tracks BLE devices within a defined indoor space using RSSI-based positioning.

![System Overview](docs/system_overview.png)

---

## How It Works

Three ESP32 nodes act as passive BLE **Observers**, continuously scanning for advertising packets on channels 37, 38, and 39. When a BLE device (**Broadcaster**) is detected, each node measures the RSSI of the received packets and forwards the data to a central **Master ESP32** via ESP-NOW. The Master relays the data over UART to a Python backend, which estimates the device's position using three algorithms running in parallel: **Trilateration (LST)**, **Weighted Centroid Localization (WCL)**, and **Fuzzy WCL**.

```
[BLE Device] --ADV_IND--> [Node 1] \
[BLE Device] --ADV_IND--> [Node 2]  --> ESP-NOW --> [Master ESP32] --> UART --> [Python Backend]
[BLE Device] --ADV_IND--> [Node 3] /                                               |
                                                                            [Dash Web Dashboard]
```

---

## Features

- **Passive BLE scanning** — nodes are invisible to scanned devices
- **Device identification** via MAC address, address type (public/random/resolvable), device name, and manufacturer ID (resolved against the official Bluetooth SIG YAML database)
- **Three positioning algorithms** running simultaneously:
  - Trilateration using L-BFGS-B optimization (LST)
  - Weighted Centroid Localization (WCL)
  - Fuzzy logic-enhanced WCL
- **Kalman filtering** on RSSI measurements at the firmware level
- **Intrusion alerts** confirmed by a minimum of 2 nodes within a configurable time window
- **Live Dash dashboard** with real-time spatial map, device table, and system logs
- **CSV session logging**

---

## Repository Structure

```
├── firmware/
│   ├── Scanare_Bluetooth_kalman.c   # Observer node — BLE scanning + Kalman filter
│   └── receptie_esp_now.c           # Master node — ESP-NOW receiver + UART bridge
│
├── backend/
│   ├── main.py                      # Entry point — Dash app + serial engine
│   ├── serial_reader.py             # UART connection and line parser
│   ├── node_state.py                # Device state, distance estimation, position calculation
│   ├── alert_manager.py             # Multi-node intrusion alert confirmation
│   ├── wcl.py                       # Weighted Centroid Localization
│   ├── trilateration.py             # Trilateration via scipy L-BFGS-B
│   ├── fuzzy_wcl.py                 # Fuzzy logic weight computation (scikit-fuzzy)
│   ├── visualizer.py                # Legacy matplotlib visualizer
│   ├── manufacturer_db.py           # Bluetooth SIG manufacturer ID resolver
│   ├── logger.py                    # CSV session logger
│   └── config.py                    # System configuration (port, RSSI params, thresholds)
│
└── docs/
    └── system_overview.png
```

---

## Hardware Requirements

- 4× ESP32 development boards (3 Observer nodes + 1 Master)
- USB-Serial adapter for Master → PC connection

---

## Backend Setup

**Requirements:** Python 3.9+

```bash
pip install dash plotly pyserial numpy scipy scikit-fuzzy pyyaml
```

**Configuration** — edit `backend/config.py`:

```python
PORT = 'COM5'          # Serial port of the Master ESP32
BAUD_RATE = 460800
RSSI_1M = -65          # RSSI at 1 meter (calibrate per environment)
PATH_LOSS_INDEX = 2.7  # Path loss exponent (2.0 = free space, ~3-4 = indoor)
MIN_CONFIRMARI = 2     # Minimum nodes to confirm an alert
WINDOW_ALERTA_MS = 10000
```

**Run:**

```bash
cd backend
python main.py
```

Open `http://localhost:8050` in your browser.

---

## Firmware Setup

The firmware is written for the **ESP-IDF** framework.

- `Scanare_Bluetooth_kalman.c` — flash to each of the 3 Observer nodes
- `receptie_esp_now.c` — flash to the Master node

Make sure to set the Master's MAC address in each Observer node before flashing.

---

## Positioning Algorithms

| Algorithm | Min Nodes | Notes |
|-----------|-----------|-------|
| WCL | 2 | Weighted by 1/d², fast and stable |
| Fuzzy WCL | 2 | Weights computed via fuzzy rules on RSSI + distance |
| Trilateration (LST) | 3 | L-BFGS-B optimization, most geometrically accurate |

Distance is estimated from RSSI using the **log-distance path loss model**:

```
d = d₀ × 10^((RSSI₀ - RSSI) / (10 × n))
```

where `RSSI₀` is calibrated at `d₀ = 1m` and `n` is the path loss exponent configured in `config.py`.

---

## Serial Protocol

The Master ESP32 forwards data over UART in a simple pipe-delimited format:

| Type | Format | Description |
|------|--------|-------------|
| `0` | `0\|NOD:X\|STATUS:START` | Calibration start |
| `1` | `1\|NOD:X\|STATUS:CALIBRAT\|RSSI_1M:XX.XX` | Calibration result |
| `2` | `2\|NOD:X\|MAC:XX:XX:XX:XX:XX:XX\|RSSI:XX.XX` | RSSI snapshot |
| `3` | `3\|NOD:X\|MAC:...\|TYPE:X\|MFG:0xXXXX\|NAME:...` | Intrusion alert |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
