#!/usr/bin/env python3
"""Diagnose Goal_Velocity values for follower/leader arms."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from HomePos import create_motor_bus, MOTOR_NAMES
except Exception as exc:  # pragma: no cover - requires hardware libs
    raise SystemExit(f"❌ Unable to import motor helpers: {exc}")


def _read_config(config_path: Path) -> dict:
    try:
        return json.loads(config_path.read_text())
    except Exception as exc:
        raise SystemExit(f"❌ Failed to read {config_path}: {exc}")


def _gather_ports(cfg: dict, scope: str) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    if scope in ("followers", "both"):
        for idx, arm in enumerate((cfg.get("robot", {}) or {}).get("arms", []) or []):
            port = (arm.get("port") or "").strip()
            if port:
                name = arm.get("name") or f"Follower {idx + 1}"
                entries.append((name, port))
    if scope in ("leaders", "both"):
        for idx, arm in enumerate((cfg.get("teleop", {}) or {}).get("arms", []) or []):
            port = (arm.get("port") or "").strip()
            if port:
                name = arm.get("name") or f"Leader {idx + 1}"
                entries.append((name, port))
    return entries


def diagnose_port(port: str, label: str) -> Dict:
    info = {
        "label": label,
        "port": port,
        "velocity": {},
        "errors": [],
    }
    try:
        bus = create_motor_bus(port)
    except Exception as exc:
        info["errors"].append(f"connect: {exc}")
        return info

    try:
        for name in MOTOR_NAMES:
            try:
                velocity = bus.read("Goal_Velocity", name, normalize=False)
                info["velocity"][name] = int(velocity)
            except Exception as exc:
                info["errors"].append(f"{name}: {exc}")
    finally:
        try:
            bus.disconnect()
        except Exception:
            pass
    return info


def _format_motor_id(name: str) -> int:
    try:
        return MOTOR_NAMES.index(name) + 1
    except ValueError:
        return -1


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect Goal_Velocity across configured arms.")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config.json",
        help="Path to config.json (default: repo root).",
    )
    parser.add_argument(
        "--scope",
        choices=("followers", "leaders", "both"),
        default="followers",
        help="Which arm set to inspect.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = _read_config(args.config)
    ports = _gather_ports(cfg, args.scope)
    if not ports:
        print(f"⚠️  No ports found for scope={args.scope}")
        return 0

    print("🤖 Goal_Velocity Diagnostics")
    print("=" * 40)
    reports = []
    for label, port in ports:
        print(f"\n🔍 {label} ({port})")
        report = diagnose_port(port, label)
        reports.append(report)
        if report["velocity"]:
            for name, value in report["velocity"].items():
                status = "⚠️ " if value < 4000 else "✓ "
                mid = _format_motor_id(name)
                print(f"   {status}Motor ID {mid:>2} ({name}): {value}")
        if report["errors"]:
            for err in report["errors"]:
                print(f"   ❌ {err}")

    print("\n📊 Summary")
    print("-" * 40)
    for report in reports:
        limited = [name for name, vel in report["velocity"].items() if vel < 4000]
        print(f"{report['label']} ({report['port']}):")
        print(f"   motors checked: {len(report['velocity'])}/{len(MOTOR_NAMES)}")
        print(f"   limited: {len(limited)}")
        if limited:
            for name in limited:
                mid = _format_motor_id(name)
                print(f"      Motor ID {mid} ({name}) = {report['velocity'][name]}")
        if report["errors"]:
            print(f"   errors: {len(report['errors'])}")
    print("\n🎯 Expectation: all Goal_Velocity = 4000 for full-speed teleop.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
