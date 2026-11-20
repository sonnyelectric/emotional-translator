#!/usr/bin/env python3
"""Offline preflight inspection for the local emotion2vec+ Large runtime (B-01).

Standard library only. ``--check`` never imports the model stack, never opens a
network connection and never reads, loads or downloads weights. It only reads
installed-distribution metadata and stats the configured cache path.

B-04 extends this CLI with ``--download`` and ``--score``; they are intentionally
not implemented here.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

MODEL_ID = "iic/emotion2vec_plus_large"
CACHE_ENV = "EMOTION_MODEL_CACHE_DIR"
# Distributions that matter for the live stack. Metadata lookup only: no import.
RELEVANT_DISTRIBUTIONS = (
    "funasr", "modelscope", "torch", "torchaudio", "numpy",
    "huggingface-hub", "soundfile", "librosa",
)
REQUIRED_DISTRIBUTIONS = ("funasr", "modelscope", "torch", "torchaudio", "numpy")
REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.stdout.strip()
    return text if out.returncode == 0 and text else None


def read_ram_bytes() -> int | None:
    system = platform.system()
    if system == "Darwin":
        value = _run(["sysctl", "-n", "hw.memsize"])
        return int(value) if value and value.isdigit() else None
    if system == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError):
            return None
    return None


def read_cpu() -> dict:
    system = platform.system()
    info: dict = {"model": None, "logical_cores": os.cpu_count()}
    if system == "Darwin":
        info["model"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    elif system == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.lower().startswith("model name"):
                    info["model"] = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
    info["model"] = info["model"] or platform.processor() or None
    return info


def read_gpu() -> list[str]:
    """Discoverable GPU names; empty list means 'not discoverable', not 'none'."""
    system = platform.system()
    names: list[str] = []
    if system == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"])
        if out:
            names = [m.group(1).strip() for m in re.finditer(r"Chipset Model:\s*(.+)", out)]
    elif system == "Linux":
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if out:
            names = out.splitlines()
    return names


def distribution_versions() -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for name in RELEVANT_DISTRIBUTIONS:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = None
    return found


def inspect_cache(raw: str | None) -> dict:
    """Stat the configured cache path only. Never lists, opens or hashes files."""
    if not raw:
        return {"configured": False, "path": None, "exists": False, "in_repo": None,
                "is_dir": False}
    path = Path(raw).expanduser()
    resolved = path.resolve()
    try:
        in_repo = resolved.is_relative_to(REPO_ROOT)
    except ValueError:
        in_repo = False
    return {"configured": True, "path": str(resolved), "exists": path.exists(),
            "is_dir": path.is_dir(), "in_repo": in_repo}


def build_report(cache_arg: str | None) -> dict:
    raw_cache = cache_arg if cache_arg is not None else os.environ.get(CACHE_ENV)
    ram = read_ram_bytes()
    versions = distribution_versions()
    cache = inspect_cache(raw_cache)
    findings: list[str] = []
    for name in REQUIRED_DISTRIBUTIONS:
        if versions.get(name) is None:
            findings.append(f"missing optional package: {name}")
    if not cache["configured"]:
        findings.append(f"no cache configured (set {CACHE_ENV} or --cache-dir)")
    elif not cache["exists"]:
        findings.append(f"configured cache path does not exist: {cache['path']}")
    elif not cache["is_dir"]:
        findings.append(f"configured cache path is not a directory: {cache['path']}")
    if cache["in_repo"]:
        findings.append("cache path is inside the repository; weights must stay out of Git")
    if ram is None:
        findings.append("RAM not discoverable on this OS")
    return {
        "check": "emotion-model-preflight",
        "model_id": MODEL_ID,
        "network_contacted": False,
        "weights_loaded": False,
        "python": {"version": platform.python_version(),
                   "implementation": platform.python_implementation(),
                   "executable": sys.executable,
                   "in_venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix)},
        "os": {"system": platform.system(), "release": platform.release(),
               "version": platform.version(), "mac_ver": platform.mac_ver()[0] or None},
        "machine": platform.machine(),
        "cpu": read_cpu(),
        "gpu": read_gpu(),
        "ram_bytes": ram,
        "distributions": versions,
        "cache": cache,
        "findings": findings,
    }


def render_text(r: dict) -> str:
    def mark(v):  # noqa: ANN001
        return v if v else "MISSING"

    ram = f"{r['ram_bytes'] / 2**30:.1f} GiB" if r["ram_bytes"] else "unknown"
    lines = [
        f"Emotion model preflight (offline; model {r['model_id']})",
        f"  network contacted : {r['network_contacted']}",
        f"  weights loaded    : {r['weights_loaded']}",
        f"Python   : {r['python']['implementation']} {r['python']['version']} "
        f"(venv: {r['python']['in_venv']}) {r['python']['executable']}",
        f"OS       : {r['os']['system']} {r['os']['mac_ver'] or r['os']['release']} "
        f"[{r['os']['version'][:60]}]",
        f"Machine  : {r['machine']}",
        f"CPU      : {r['cpu']['model'] or 'unknown'} ({r['cpu']['logical_cores']} logical cores)",
        f"GPU      : {'; '.join(r['gpu']) if r['gpu'] else 'not discoverable'}",
        f"RAM      : {ram}",
        "Distributions (metadata only, nothing imported):",
    ]
    lines += [f"  {n:<16} {mark(v)}" for n, v in r["distributions"].items()]
    c = r["cache"]
    if not c["configured"]:
        lines.append(f"Cache    : not configured ({CACHE_ENV} unset)")
    else:
        state = "present" if c["exists"] else "ABSENT"
        lines.append(f"Cache    : {c['path']} -> {state}")
    lines.append("Findings:" if r["findings"] else "Findings: none")
    lines += [f"  - {f}" for f in r["findings"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true",
                   help="offline environment inventory (no network, no weights)")
    p.add_argument("--cache-dir", default=None,
                   help=f"override {CACHE_ENV}; only stat'ed, never read")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = p.parse_args(argv)
    if not args.check:
        p.error("only --check exists in B-01; --download and --score arrive in B-04")
    report = build_report(args.cache_dir)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0  # findings are reported, not fatal


if __name__ == "__main__":
    raise SystemExit(main())
