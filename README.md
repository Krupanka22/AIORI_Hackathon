# AIORI

AIORI is a privacy-aware IPv6 IoT security monitoring prototype. It observes
connection metadata rather than application payloads, extracts behavioral
features, resolves devices across controlled IPv6 address rotations, detects
behavioral deviations, and exposes the results through a FastAPI and React
dashboard.

## Architecture

```text
Linux namespaces / veth bridge
        |
   iPerf3 traffic
        |
 tcpdump -> Zeek conn.log
        |
 metadata feature extraction
        |
 fingerprint + identity resolution + anomaly detection
        |
 SQLite / optional Fabric audit / WebSocket dashboard
```

The backend is in [`backend/`](./backend), the React application is in
[`frontend/`](./frontend), Zeek configuration is in
[`networking/zeek_config/`](./networking/zeek_config), and Fabric chaincode is
in [`blockchain/chaincode/`](./blockchain/chaincode/).

## Requirements

* Windows 11 with WSL2
* Ubuntu 24.04 installed as the WSL distribution (`Ubuntu-24.04`)
* Python 3.10 or newer inside WSL2
* Node.js 20 or newer and npm on Windows
* Linux packages: `iproute2`, `iputils-ping`, `iperf3`, `tcpdump`, `curl`
* Zeek installed inside WSL2 for connection-log processing
* Root or equivalent capabilities in WSL2 for namespaces, bridges, and packet
  capture

Install Node.js 20 or newer on Windows if `node --version` and `npm --version`
do not work in PowerShell.

Mininet and Open vSwitch are optional. AIORI currently creates Linux network
namespaces and a Linux bridge directly, which avoids an unnecessary Mininet
dependency for the prototype.

## Installation

### 1. Verify WSL2 and Ubuntu

Run these commands in PowerShell:

```powershell
wsl --list --verbose
wsl --set-default Ubuntu-24.04
wsl -d Ubuntu-24.04
```

The Ubuntu entry must show `VERSION 2`. If it does not:

```powershell
wsl --set-version Ubuntu-24.04 2
```

The commands below are run inside the Ubuntu terminal, not the Windows
PowerShell terminal.

### 2. Install Linux dependencies

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  iproute2 \
  iputils-ping \
  iperf3 \
  tcpdump \
  curl \
  git
```

Install Zeek using the official Zeek package instructions for Ubuntu 24.04.
The `zeek` executable must be on the WSL `PATH`; installing Zeek only on
Windows is not sufficient:

```bash
zeek --version
```

If that command is not found, install Zeek before running traffic experiments.
After installing it, copy the project policy into the Zeek site directory and
load it according to the installed Zeek package layout:

[`networking/zeek_config/local.zeek`](./networking/zeek_config/local.zeek)

### 3. Create the backend environment

The Windows project folder `E:\AIORI` is mounted in WSL2 as `/mnt/e/AIORI`:

```bash
cd /mnt/e/AIORI/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and use the installed distribution name:

```env
WSL_DISTRO=Ubuntu-24.04
MININET_ENABLED=false
BLOCKCHAIN_ENABLED=false
```

The `.env` file is required. Do not skip the `cp` command: without it, the
backend falls back to defaults and device commands may target the wrong WSL
distribution.

Keep blockchain disabled until a Fabric network and Gateway client are
configured. The Windows environment at `E:\AIORI\.venv` is separate and is not
used for Linux namespaces or packet capture.

### 4. Verify the WSL prerequisites

Run this in Ubuntu before starting either application:

```bash
test "$(wsl.exe -l -q 2>/dev/null | tr -d '\r' | grep -Fx 'Ubuntu-24.04')" = "Ubuntu-24.04"
python --version
zeek --version
iperf3 --version
tcpdump --version
sudo ip netns add aiori-check
sudo ip netns delete aiori-check
```

If any command fails, fix that prerequisite before running AIORI. The
namespace check must not print an error.

### 5. Install frontend dependencies

Run these commands in PowerShell:

```powershell
cd E:\AIORI\frontend
npm ci
npm run build
```

The build command runs TypeScript checks and creates the production bundle.

## Running the application

AIORI uses two terminals that must remain open.

### Terminal 1: FastAPI backend

Open Ubuntu:

```powershell
wsl -d Ubuntu-24.04
```

Then run:

```bash
cd /mnt/e/AIORI/backend
source .venv/bin/activate
sudo -E .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The backend must run as root because creating network namespaces, bridges, veth
pairs, and packet captures requires Linux network capabilities. Enter your
Ubuntu password when prompted. Keep this terminal open while using the
dashboard.

Verify the backend from PowerShell or a browser:

```powershell
curl.exe http://localhost:8000/api/health
```

API documentation is available at
[`http://localhost:8000/docs`](http://localhost:8000/docs).

### Terminal 2: React frontend

Open PowerShell:

```powershell
cd E:\AIORI\frontend
npm run dev
```

Open [`http://localhost:5173`](http://localhost:5173). Vite proxies `/api`
requests to port `8000` and WebSocket requests to `/ws/live`; the proxy is
configured in [`frontend/vite.config.ts`](./frontend/vite.config.ts). The
development server uses IPv4 loopback (`127.0.0.1`) so WebSocket forwarding
works reliably with WSL2.

Stop either service with `Ctrl+C`. To stop WSL after closing the application:

```powershell
wsl --shutdown
```

## How to use the application

### 1. Create and start devices

1. Open **Devices**.
2. Click **Create Device**.
3. Create the supported device types:
   * CCTV Camera
   * Temperature Sensor
   * Smart Door Lock
   * Smart Light
   * Motion Sensor
4. Click the play button to start each device.

Starting a device creates a real WSL network namespace, veth pair, bridge
connection, and IPv6 address. If a networking command fails, the backend
reports the error; it does not fabricate traffic.

Verify the networking resources in Ubuntu:

```bash
sudo ip netns list
sudo ip link show aiori-br0
```

### 2. Generate traffic

1. Open **Experiments**.
2. Use **Generate Traffic**.
3. Choose a duration between 5 and 300 seconds.
4. Choose `normal`, `heavy`, `periodic`, or `burst`.
5. Click **Generate**.

Traffic is intended to be generated by iPerf3 in the running namespaces.

### 3. Run a complete experiment

1. Click **New Experiment**.
2. Choose one of:
   * **Normal Traffic**: collect a normal behavioral baseline.
   * **IPv6 Rotation**: rotate addresses and test re-identification.
   * **Anomaly Injection**: generate unusual traffic for anomaly detection.
   * **Attack Test**: run controlled attack-like traffic in the lab.
   * **Full Pipeline**: run the complete workflow.
3. Create the experiment.
4. Click **Start**.

For `normal_traffic` and `full_pipeline`, the intended pipeline is:

```text
iPerf3 -> namespace/bridge -> tcpdump -> Zeek -> SQLite metadata
       -> feature extraction -> fingerprinting -> alerts/audit records
```

### 4. Inspect the results

* **Dashboard**: overall device, profile, rotation, and alert counts.
* **Network**: Zeek connection records, protocols, bytes, packets, and ports.
* **IPv6 History**: current and expired addresses with rotation timestamps.
* **AI Analysis**: behavioral fingerprints and IPv6 identity resolution.
* **Alerts**: anomaly severity, score, baseline, and explanation.
* **Blockchain**: local audit hashes or Fabric audit records.

Network, AI, Alerts, and Blockchain are populated by the real experiment
pipeline; starting a device alone only creates its initial profile and local
`profile_created` audit record. To populate all tabs, start at least one device,
run a `Full Pipeline` or `Normal Traffic` experiment, and ensure `zeek`,
`tcpdump`, and `iperf3` are installed inside Ubuntu. The local Blockchain tab
works with `BLOCKCHAIN_ENABLED=false` and verifies SHA-256 audit hashes without
requiring Fabric.

### 5. Rotate an IPv6 address manually

1. Open **Experiments**.
2. Under **Trigger IPv6 Rotation**, select one running device or all devices.
3. Click **Rotate**.
4. Open **IPv6 History** and confirm the old address is expired and the new
   address is current.
5. Open **AI Analysis**, enter the new address, and click **Resolve**.

### 6. Review local audit records

With `BLOCKCHAIN_ENABLED=false`, the Blockchain page uses local SHA-256
integrity records. This is useful for development but is not a deployed
Hyperledger Fabric ledger. Enable Fabric only after deploying the network and
configuring a Gateway client.

## Troubleshooting

### `wsl -d Ubuntu` says the distribution does not exist

Use the exact registered name:

```powershell
wsl --list --verbose
wsl -d Ubuntu-24.04
```

### The frontend shows `502 Bad Gateway`

Start the backend first and confirm:

```powershell
curl.exe http://localhost:8000/api/health
```

Then restart the Vite frontend.

### The dashboard shows `Disconnected`

The WebSocket connects through the backend. Confirm that the FastAPI process is
running on port `8000`, then refresh the frontend.

### A device fails to start

Inspect the backend terminal for the failed WSL command. Confirm that Ubuntu
is version 2 and that the current WSL user can run:

```bash
sudo ip netns add aiori-check
sudo ip netns delete aiori-check
```

If the error says that the distribution does not exist, confirm that
`backend/.env` contains the exact name from `wsl --list --verbose`, for example
`WSL_DISTRO=Ubuntu-24.04`, then restart the backend.

If the API reports that `sudo` needs a password, stop the backend and restart
it with the root command shown in the running instructions above. Starting
Uvicorn as a normal user cannot create the required Linux network resources.

### Network pages contain no records

No records are created until actual traffic is captured and processed. Confirm
that:

1. Devices are running.
2. iPerf3 is installed.
3. Zeek is installed and available as `zeek`.
4. A traffic or full-pipeline experiment has completed.

AIORI does not populate network pages with fabricated observations.

### `zeek: command not found`

Install Zeek inside Ubuntu using the official Zeek Ubuntu package
instructions, then open a new Ubuntu terminal and verify:

```bash
command -v zeek
zeek --version
```

The backend cannot process PCAP files until this check succeeds.

## Useful commands

```powershell
# WSL status
wsl --status
wsl --list --verbose

# Frontend checks
cd E:\AIORI\frontend
npm run build
npm run lint
```

```bash
# Backend checks
cd /mnt/e/AIORI/backend
source .venv/bin/activate
python -m compileall -q .

# API checks
curl http://localhost:8000/api/health
curl http://localhost:8000/api/status
```

## Privacy and limitations

Only Zeek connection metadata is persisted for behavioral analysis. Packet
payloads are not used in feature extraction or written to the audit ledger.
Behavioral fingerprints can still enable tracking, so production deployments
should add authentication, retention limits, and access controls.

IPv6 privacy extensions are environment-dependent in WSL2. AIORI provides a
manual controlled rotation trigger so experiments remain reproducible, but
the generated ULA addresses are not public routable IPv6 addresses.

Hyperledger Fabric support includes the privacy-aware chaincode and local
integration boundary. Fabric submission and verification require a deployed
Fabric network and a configured Gateway client; enabling the flag without
those prerequisites fails explicitly.

## Implementation status

The scaffold, metadata pipeline, namespace device lifecycle, controlled IPv6
rotation, iPerf3 traffic generation, tcpdump/Zeek ingestion, feature
extraction, similarity-based identity resolution, anomaly detection, REST
APIs, WebSockets, dashboard pages, and Fabric chaincode are present.

The following validation remains environment-dependent and must be run in the
target WSL2 installation before claiming the complete deliverable:

- [ ] Validate WSL2 namespace, bridge, IPv6, and packet-capture capabilities.
- [ ] Run a real multi-device traffic experiment and retain its results.
- [ ] Measure re-identification accuracy, false-positive/negative rates,
  anomaly precision/recall, and detection latencies.
- [ ] Deploy Fabric and verify ledger writes against the chaincode.
- [ ] Apply production authentication, retention, and access controls.

**The task is completed only when every item above has been executed and
verified in the target environment.**
