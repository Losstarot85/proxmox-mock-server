"""
Proxmox VE API Mock Server
Exposes the same REST endpoints as a real Proxmox cluster,
returning realistic, smoothly fluctuating fake data.
"""

import hashlib
import math
import time
from functools import lru_cache, wraps

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware

from clusters import CLUSTERS

BOOT_TIME = time.time()
GB = 1024**3
MB = 1024**2

# ──────────────────────────────────────────────────────────────────────
# Caching and Helpers
# ──────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1024)
def _seed(name: str) -> float:
    """Deterministic phase from a string seed (cached)."""
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _flux(base: float, amp: float, seed_str: str, period: float = 90.0) -> float:
    """Smooth multi-sine fluctuation around a base value (0-100 scale)."""
    t = time.time()
    p = _seed(seed_str) * 2 * math.pi
    v = (
        math.sin(t / period + p) * 0.55
        + math.sin(t / (period * 2.7) + p * 1.3) * 0.30
        + math.sin(t / (period * 7.1) + p * 0.7) * 0.15
    )
    return max(0.0, min(100.0, base + v * amp))


def ttl_cache(ttl=2.0):
    """Simple time-to-live cache for expensive endpoints with basic GC."""
    def decorator(func):
        cache = {}
        @wraps(func)
        async def wrapper(*args, **kwargs):
            now = time.time()
            
            # Basic Garbage Collection to prevent memory leak
            if len(cache) > 200:
                keys_to_delete = [k for k, v in cache.items() if now - v[1] >= ttl]
                for k in keys_to_delete:
                    del cache[k]
                    
            key = str(args) + str(kwargs)
            if key in cache:
                val, timestamp = cache[key]
                if now - timestamp < ttl:
                    return val
            val = await func(*args, **kwargs)
            cache[key] = (val, now)
            return val
        return wrapper
    return decorator

# Data access helpers

def _cluster(cluster_name: str):
    return CLUSTERS[cluster_name]

def _node_def(cluster_name: str, node_name: str):
    for n in _cluster(cluster_name)["nodes"]:
        if n["name"] == node_name:
            return n
    return None

def _resources_on_node(cluster_name: str, node_name: str):
    nodes = _cluster(cluster_name)["nodes"]
    idx = next((i for i, n in enumerate(nodes) if n["name"] == node_name), None)
    if idx is None:
        return []
    return [r for r in _cluster(cluster_name)["resources"] if r[3] == idx]

def _make_vm(r, cluster_name: str, node_name: str) -> dict:
    vmid, name, kind, _, vcpus, ram_gb, tags, pool, status, bcpu, bram = r
    seed = f"{cluster_name}:{name}"
    if status != "running":
        return {
            "vmid": vmid, "name": name, "status": status,
            "cpu": 0, "maxcpu": vcpus, "mem": 0, "maxmem": ram_gb * GB,
            "netin": 0, "netout": 0, "diskread": 0, "diskwrite": 0,
            "uptime": 0, "tags": tags, "template": 0,
        }
    cpu_pct = _flux(bcpu, 12, seed + ":cpu") / 100.0
    ram_pct = _flux(bram, 8, seed + ":ram") / 100.0
    net_base = vcpus * 2 * MB
    disk_read = int(_flux(50, 30, seed + ":dr") * MB * 10)
    disk_write = int(_flux(30, 20, seed + ":dw") * MB * 10)
    
    return {
        "vmid": vmid,
        "name": name,
        "status": "running",
        "cpu": round(cpu_pct, 4),
        "maxcpu": vcpus,
        "mem": int(ram_gb * GB * ram_pct),
        "maxmem": ram_gb * GB,
        "netin": int(_flux(net_base / MB, net_base / MB * 0.4, seed + ":ni") * MB),
        "netout": int(_flux(net_base / MB * 0.6, net_base / MB * 0.3, seed + ":no") * MB),
        "diskread": disk_read,
        "diskwrite": disk_write,
        "uptime": int(time.time() - BOOT_TIME + _seed(seed) * 86400 * 30),
        "tags": tags,
        "template": 0,
    }

def _err_not_found(msg: str):
    return ORJSONResponse(status_code=500, content={"data": None, "errors": msg})

# ──────────────────────────────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────────────────────────────

def create_app(cluster_name: str) -> FastAPI:
    app = FastAPI(title=f"Proxmox Mock — {cluster_name}", default_response_class=ORJSONResponse)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api2/json/version")
    async def version():
        return {"data": {"version": "8.2.7", "release": "1", "repoid": "a]b\x3845dc2f"}}
        
    @app.get("/api2/json/cluster/status")
    async def cluster_status():
        data = []
        data.append({
            "type": "cluster",
            "name": cluster_name,
            "version": 4,
            "nodes": len(_cluster(cluster_name)["nodes"]),
            "quorate": 1
        })
        for n in _cluster(cluster_name)["nodes"]:
            data.append({
                "type": "node",
                "name": n["name"],
                "nodeid": 1,
                "online": 1,
                "local": 0
            })
        return {"data": data}

    @app.get("/api2/json/nodes")
    @ttl_cache(ttl=2.0)
    async def list_nodes():
        nodes = _cluster(cluster_name)["nodes"]
        data = []
        for n in nodes:
            seed = f"{cluster_name}:{n['name']}"
            maxmem = n["maxmem_gb"] * GB
            cpu_pct = 0
            mem_used = 0
            # Aggregate CPU/RAM from running VMs on this node
            for r in _resources_on_node(cluster_name, n["name"]):
                if r[8] == "running":
                    cpu_pct += _flux(r[9], 12, f"{cluster_name}:{r[1]}:cpu") / 100.0 * r[4]
                    mem_used += int(r[5] * GB * _flux(r[10], 8, f"{cluster_name}:{r[1]}:ram") / 100.0)
            # Node overhead
            cpu_pct = min(cpu_pct / n["maxcpu"], 0.98)
            mem_used = min(mem_used + int(4 * GB), maxmem)  # 4GB OS overhead
            data.append({
                "node": n["name"],
                "status": "online",
                "type": "node",
                "cpu": round(cpu_pct, 4),
                "maxcpu": n["maxcpu"],
                "mem": mem_used,
                "maxmem": maxmem,
                "uptime": int(time.time() - BOOT_TIME + _seed(seed) * 86400 * 90),
            })
        return {"data": data}

    @app.get("/api2/json/nodes/{node}/rrddata")
    @ttl_cache(ttl=5.0)
    async def node_rrddata(node: str, timeframe: str = "hour"):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
        
        seed = f"{cluster_name}:{node}"
        now = time.time()
        data = []
        points = 70 if timeframe == "hour" else 300
        step = 3600 / points if timeframe == "hour" else 86400 / points
        for i in range(points):
            t = now - (points - i) * step
            data.append({
                "time": int(t),
                "cpu": round(_flux(30, 20, seed + f":c:{i}") / 100.0, 4),
                "mem": int(_flux(nd["maxmem_gb"] * 0.4, nd["maxmem_gb"] * 0.2, seed + f":m:{i}") * GB),
                "maxcpu": nd["maxcpu"],
                "maxmem": nd["maxmem_gb"] * GB,
                "loadavg": round(_flux(nd["maxcpu"] * 0.3, nd["maxcpu"] * 0.15, seed + f":la:{i}"), 2),
                "netin": int(_flux(500, 300, seed + f":ni:{i}") * MB),
                "netout": int(_flux(300, 200, seed + f":no:{i}") * MB),
                "iowait": round(_flux(3, 2, seed + f":io:{i}"), 2),
                "pressurecpusome": round(_flux(2.5, 1.5, seed + f":pc:{i}"), 2),
                "pressurememorysome": round(_flux(1.0, 0.8, seed + f":pm:{i}"), 2),
                "pressureiosome": round(_flux(1.8, 1.2, seed + f":pi:{i}"), 2),
            })
        return {"data": data}

    @app.get("/api2/json/nodes/{node}/storage")
    @ttl_cache(ttl=2.0)
    async def node_storage(node: str):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
        storage = _cluster(cluster_name)["storage_gb"]
        type_map = {"local": "dir", "local-lvm": "lvmthin", "ceph-pool": "rbd"}
        data = []
        for name, total_gb in storage.items():
            seed = f"{cluster_name}:{node}:{name}"
            used_pct = _flux(55, 15, seed) / 100.0
            total = total_gb * GB
            used = int(total * used_pct)
            data.append({
                "storage": name,
                "type": type_map.get(name, "dir"),
                "active": 1,
                "total": total,
                "used": used,
                "avail": total - used,
                "content": "images,rootdir,vztmpl,iso,backup",
            })
        return {"data": data}

    @app.get("/api2/json/nodes/{node}/network")
    async def node_network(node: str):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
        subnet = nd["subnet"]
        return {"data": [
            {"iface": "lo", "type": "loopback", "active": 1, "address": "127.0.0.1"},
            {"iface": "eno1", "type": "eth", "active": 1, "address": f"{subnet}.1"},
            {"iface": "eno2", "type": "eth", "active": 1, "address": f"{subnet}.2"},
            {"iface": "vmbr0", "type": "bridge", "active": 1, "address": f"{subnet}.1",
             "bridge_ports": "eno1", "bridge_stp": "off"},
        ]}

    @app.get("/api2/json/nodes/{node}/qemu")
    @ttl_cache(ttl=2.0)
    async def list_qemu(node: str):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
        resources = _resources_on_node(cluster_name, node)
        return {"data": [_make_vm(r, cluster_name, node) for r in resources if r[2] == "q"]}

    @app.get("/api2/json/nodes/{node}/lxc")
    @ttl_cache(ttl=2.0)
    async def list_lxc(node: str):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
        resources = _resources_on_node(cluster_name, node)
        return {"data": [_make_vm(r, cluster_name, node) for r in resources if r[2] == "l"]}

    @app.get("/api2/json/nodes/{node}/qemu/{vmid}/status/current")
    @ttl_cache(ttl=2.0)
    async def qemu_status(node: str, vmid: int):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
        resources = _resources_on_node(cluster_name, node)
        r = next((x for x in resources if x[0] == vmid), None)
        if not r:
            return _err_not_found(f"Configuration file 'nodes/{node}/qemu-server/{vmid}.conf' does not exist")
        
        # _make_vm ora restituisce tutte le metriche
        return {"data": _make_vm(r, cluster_name, node)}

    @app.get("/api2/json/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces")
    async def qemu_agent_net(node: str, vmid: int):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
            
        resources = _resources_on_node(cluster_name, node)
        if not any(x[0] == vmid for x in resources):
            return _err_not_found(f"Configuration file 'nodes/{node}/qemu-server/{vmid}.conf' does not exist")
            
        subnet = nd["subnet"]
        host_part = (vmid % 200) + 10
        return {"data": {"result": [
            {"name": "lo", "ip-addresses": [
                {"ip-address": "127.0.0.1", "ip-address-type": "ipv4", "prefix": 8}
            ]},
            {"name": "eth0", "ip-addresses": [
                {"ip-address": f"{subnet}.{host_part}", "ip-address-type": "ipv4", "prefix": 24}
            ]},
        ]}}

    @app.get("/api2/json/nodes/{node}/lxc/{vmid}/interfaces")
    async def lxc_interfaces(node: str, vmid: int):
        nd = _node_def(cluster_name, node)
        if not nd:
            return _err_not_found(f"Node '{node}' does not exist")
            
        resources = _resources_on_node(cluster_name, node)
        if not any(x[0] == vmid for x in resources):
            return _err_not_found(f"Configuration file 'nodes/{node}/lxc/{vmid}.conf' does not exist")
            
        subnet = nd["subnet"]
        host_part = (vmid % 200) + 10
        return {"data": [
            {"name": "lo", "inet": "127.0.0.1/8"},
            {"name": "eth0", "inet": f"{subnet}.{host_part}/24"},
        ]}

    @app.get("/api2/json/cluster/resources")
    @ttl_cache(ttl=2.0)
    async def cluster_resources():
        data = []
        nodes = _cluster(cluster_name)["nodes"]
        for r in _cluster(cluster_name)["resources"]:
            vmid, name, kind, node_idx, vcpus, ram_gb, tags, pool, status, *_ = r
            data.append({
                "type": "qemu" if kind == "q" else "lxc",
                "vmid": vmid,
                "name": name,
                "node": nodes[node_idx]["name"],
                "pool": pool,
                "status": status,
            })
        return {"data": data}

    @app.api_route("/api2/json/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def catch_all(path: str, request: Request):
        return ORJSONResponse(
            status_code=501, 
            content={"data": None, "errors": f"Not Implemented in Mock: /api2/json/{path}"}
        )

    return app
