#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path


def bytes_to_gib(value: int) -> float:
    return round(value / (1024**3), 2)


PROC_ROOT = Path(os.getenv("BOLTZ_HOST_PROC_ROOT", "/host/proc"))
SYS_ROOT = Path(os.getenv("BOLTZ_HOST_SYS_ROOT", "/host/sys"))


def proc_file(path: str) -> Path:
    candidate = PROC_ROOT / path.lstrip("/")
    return candidate if candidate.exists() else Path("/proc") / path.lstrip("/")


def sys_file(path: str) -> Path:
    candidate = SYS_ROOT / path.lstrip("/")
    return candidate if candidate.exists() else Path("/sys") / path.lstrip("/")


def cpu_snapshot() -> dict[str, tuple[int, int]]:
    values: dict[str, tuple[int, int]] = {}
    for line in proc_file("stat").read_text().splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("cpu"):
            continue
        numbers = [int(value) for value in parts[1:8]]
        idle = numbers[3] + numbers[4]
        total = sum(numbers)
        values[parts[0]] = (total, idle)
    return values


def read_cpu(interval: float = 0.2) -> dict:
    model = platform.processor() or platform.machine()
    try:
        for line in proc_file("cpuinfo").read_text(errors="ignore").splitlines():
            if line.lower().startswith(("model name", "hardware", "processor")):
                model = line.split(":", 1)[1].strip() or model
                break
    except Exception:
        pass
    first = cpu_snapshot()
    time.sleep(interval)
    second = cpu_snapshot()
    cores = []
    for core_id, (total, idle) in sorted(second.items()):
        previous_total, previous_idle = first.get(core_id, (total, idle))
        delta_total = max(total - previous_total, 0)
        delta_idle = max(idle - previous_idle, 0)
        used = round(((delta_total - delta_idle) / delta_total) * 100, 1) if delta_total else 0
        if core_id != "cpu":
            cores.append({"id": core_id, "used_percent": used})
    total, idle = second.get("cpu", (0, 0))
    previous_total, previous_idle = first.get("cpu", (total, idle))
    delta_total = max(total - previous_total, 0)
    delta_idle = max(idle - previous_idle, 0)
    total_used = round(((delta_total - delta_idle) / delta_total) * 100, 1) if delta_total else 0
    return {
        "model": model,
        "architecture": platform.machine(),
        "logical_count": os.cpu_count() or len(cores),
        "used_percent": total_used,
        "cores": cores,
    }


def read_memory() -> dict:
    values: dict[str, int] = {}
    try:
        for line in proc_file("meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except Exception:
        return {}
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0)
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "total_gib": bytes_to_gib(total),
        "available_gib": bytes_to_gib(available),
        "used_gib": bytes_to_gib(used),
        "used_percent": round((used / total) * 100, 1) if total else 0,
    }


def read_disks(paths: list[str]) -> list[dict]:
    disks = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        try:
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            usage = shutil.disk_usage(path)
            disks.append(
                {
                    "path": resolved,
                    "total_gib": bytes_to_gib(usage.total),
                    "used_gib": bytes_to_gib(usage.used),
                    "free_gib": bytes_to_gib(usage.free),
                    "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
                },
            )
        except Exception as exc:
            disks.append({"path": raw, "error": str(exc)})
    return disks


def command_json(args: list[str]) -> dict | None:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def host_command(args: list[str], timeout: int = 3) -> subprocess.CompletedProcess[str] | None:
    commands = [["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", *args], args]
    for command in commands:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except Exception:
            continue
        if result.returncode == 0:
            return result
    return None


def read_nvidia_gpus() -> list[dict]:
    query = "name,driver_version,memory.total,memory.used,utilization.gpu,power.draw,power.limit,clocks.current.graphics"
    result = host_command(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    if result is None:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 8:
            continue
        name, driver, mem_total, mem_used, util, power_draw, power_limit, clock = parts
        rows.append(
            {
                "name": name,
                "driver_version": driver,
                "memory_total_mib": mem_total,
                "memory_used_mib": mem_used,
                "utilization_percent": util,
                "power_draw_w": power_draw,
                "power_limit_w": power_limit,
                "graphics_clock_mhz": clock,
                "backend": "host:nvidia-smi",
            },
        )
    return rows


def read_rocm_gpus() -> list[dict]:
    result = host_command(["rocm-smi", "--showproductname", "--showmemuse", "--showuse", "--json"])
    if result is None or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    rows = []
    for key, value in payload.items():
        if isinstance(value, dict):
            rows.append(
                {
                    "name": value.get("Card series") or value.get("Card model") or key,
                    "backend": "host:rocm-smi",
                    "memory_used_mib": value.get("GPU Memory Allocated (VRAM%)") or "",
                    "utilization_percent": value.get("GPU use (%)") or "",
                },
            )
    return rows


def read_jetson_gpus() -> list[dict]:
    result = host_command(["tegrastats", "--interval", "100", "--count", "1"])
    if result is None or not result.stdout.strip():
        return []
    return [{"name": "Jetson integrated GPU", "backend": "host:tegrastats", "raw": result.stdout.strip().splitlines()[-1]}]


def collect(paths: list[str]) -> dict:
    gpus = read_nvidia_gpus() or read_rocm_gpus() or read_jetson_gpus()
    return {
        "host": platform.node(),
        "platform": platform.platform(),
        "metrics_source": "host-metrics-json",
        "timestamp": int(time.time()),
        "cpu": read_cpu(),
        "memory": read_memory(),
        "gpus": gpus,
        "gpu_note": "" if gpus else "No host GPU tool returned data. Install/enable nvidia-smi, rocm-smi, or tegrastats on the host metrics runner.",
        "disks": read_disks(paths),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.getenv("BOLTZ_HOST_METRICS_OUT", "/data/system-metrics/host.json"))
    parser.add_argument("--disk", action="append", default=[])
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    disks = args.disk or [str(output.parent.parent), "/"]
    while True:
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(".tmp")
        tmp.write_text(json.dumps(collect(disks), ensure_ascii=False, indent=2))
        tmp.replace(output)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
