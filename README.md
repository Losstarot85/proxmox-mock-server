# Proxmox VE API Mock Server 🚀

![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

A lightweight, high-performance FastAPI server that emulates the Proxmox VE REST API. It returns realistic, smoothly fluctuating metrics (CPU, RAM, Network, Disk I/O) using multi-sine wave generation.

Designed specifically for testing and demonstrating monitoring dashboards without needing a real, hardware-heavy Proxmox cluster.

## ✨ Features

*   **Ultra Lightweight**: Runs 3 entire datacenter clusters inside a **single Python process** using `asyncio`, consuming only ~60MB of RAM.
*   **Realistic Fluctuations**: No static data. Metrics dynamically change over time using deterministic mathematical waves.
*   **Production Ready Mock**: Implements proper CORS, rigorous Proxmox JSON error formatting (500/501 errors), and uses `orjson` for fast serialization.
*   **Zero Configuration**: Works out of the box with `docker-compose`. Ignores authentication tokens intentionally to simplify frontend demos.

## 🏢 What's Inside?

Out of the box, the server simulates 3 distinct Datacenters on 3 different ports, fully populated with Nodes, VMs, and LXC containers.

| Cluster Name | Nodes per Cluster | Resources per Node | Exposed Port |
| :--- | :--- | :--- | :--- |
| `datacenter-milan` | 3 (64c / 256GB RAM) | ~15 VMs/LXC | `8006` |
| `datacenter-rome` | 3 (32c / 128GB RAM) | ~15 VMs/LXC | `8007` |
| `datacenter-naples`| 3 (48c / 192GB RAM) | ~15 VMs/LXC | `8008` |

## 🚀 Quick Start

Ensure you have Docker and Docker Compose installed.

```bash
git clone https://github.com/yourusername/proxmox-mock-server.git
cd proxmox-mock-server

# Use the Makefile for convenience
make run

# Or use standard Docker commands
docker compose up -d --build
```

## 🔗 How to Connect

Because the mock server exposes ports `8006`, `8007`, and `8008` directly to the host, the connection URL depends on where your client/dashboard is running:

1. **From a local program (same machine, no Docker):**
   * `http://localhost:8006` (Milan)
   * `http://localhost:8007` (Rome)
   * `http://localhost:8008` (Naples)

2. **From the outside (Browser, external server):**
   Replace `localhost` with the public or LAN IP address of the host machine running the mock server.
   * `http://<HOST-IP>:8006`

3. **From another Docker container on the same host:**
   * You can use the host's LAN IP address (`http://<HOST-IP>:8006`).
   * Or, use the default Docker gateway IP (usually `http://172.17.0.1:8006` on Linux).
   * Alternatively, configure `--add-host host.docker.internal:host-gateway` in your client container and use `http://host.docker.internal:8006`.

## 🔌 Supported API Endpoints

The server strictly follows the Proxmox VE API schema. Currently supported:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api2/json/version` | PVE version info |
| `GET` | `/api2/json/cluster/status` | Cluster topology and quorum |
| `GET` | `/api2/json/cluster/resources` | Global list of VMs, LXCs, and Nodes |
| `GET` | `/api2/json/nodes` | List of nodes with aggregated CPU/RAM usage |
| `GET` | `/api2/json/nodes/{node}/rrddata` | Historical RRD metrics (CPU, RAM, Load, I/O) |
| `GET` | `/api2/json/nodes/{node}/storage` | Storage pools (local, ceph, lvm) |
| `GET` | `/api2/json/nodes/{node}/network` | Network interfaces |
| `GET` | `/api2/json/nodes/{node}/qemu` | QEMU VMs list |
| `GET` | `/api2/json/nodes/{node}/lxc` | LXC containers list |
| `GET` | `/api2/json/nodes/{node}/qemu/{id}/status/current` | Deep VM metrics (CPU, Disk I/O, uptime) |
| `GET` | `/api2/json/nodes/{node}/qemu/{id}/agent/network-get-interfaces` | VM IP Addresses |
| `GET` | `/api2/json/nodes/{node}/lxc/{id}/interfaces` | LXC IP Addresses |

*(Any unsupported endpoint will return a clean HTTP 501 Not Implemented error).*

## 🤝 Contributing

Contributions are welcome! If your monitoring tool requires a specific Proxmox endpoint that isn't mocked yet:
1. Open an Issue using the Feature Request template.
2. Submit a Pull Request ensuring the data perfectly matches the real Proxmox API response format.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
