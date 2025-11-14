"""Toggle Feetech Goal_Velocity/Acceleration for follower + leader arms."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Set


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - CLI helper
        print(f"❌ Failed to read {path}: {exc}")
        sys.exit(1)


def gather_ports(config: dict, arm_type: str) -> List[str]:
    ports: List[str] = []
    seen: Set[str] = set()

    def append_port(port: str) -> None:
        port = (port or "").strip()
        if port and port not in seen:
            ports.append(port)
            seen.add(port)

    if arm_type in ("followers", "both"):
        for arm in (config.get("robot", {}) or {}).get("arms", []) or []:
            append_port(arm.get("port", ""))

    if arm_type in ("leaders", "both"):
        for arm in (config.get("teleop", {}) or {}).get("arms", []) or []:
            append_port(arm.get("port", ""))

    return ports


def set_goal_velocity(port: str, velocity: int, acceleration: int) -> None:
    try:
        from HomePos import create_motor_bus, MOTOR_NAMES  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        print(f"❌ Unable to import HomePos helpers: {exc}")
        sys.exit(1)

    path = Path(port)
    if not path.exists():
        print(f"⚠️  Port {port} not found; skipping.")
        return

    print(f"→ {port}: Goal_Velocity={velocity}, Acceleration={acceleration}")
    try:
        bus = create_motor_bus(port)
    except Exception as exc:
        print(f"   ⚠️  Failed to connect: {exc}")
        return

    try:
        for name in MOTOR_NAMES:
            bus.write("Goal_Velocity", name, velocity, normalize=False)
            bus.write("Acceleration", name, acceleration, normalize=False)
    except Exception as exc:
        print(f"   ⚠️  Failed to write registers: {exc}")
    finally:
        try:
            bus.disconnect()
        except Exception:
            pass


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Toggle Goal_Velocity/Acceleration for all configured robot/teleop arms."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to config.json (default: ./config.json)",
    )
    parser.add_argument(
        "--arm-type",
        choices=("followers", "leaders", "both"),
        default="followers",
        help="Which arm group to update (default: followers).",
    )
    parser.add_argument(
        "--mode",
        choices=("max", "custom"),
        default="max",
        help="max=Goal_Velocity 4000 / Accel 255, custom=use --velocity/--acceleration.",
    )
    parser.add_argument(
        "--velocity",
        type=int,
        default=None,
        help="Goal_Velocity value (required when --mode custom).",
    )
    parser.add_argument(
        "--acceleration",
        type=int,
        default=255,
        help="Acceleration register value (default: 255).",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.mode == "max":
        goal_velocity = 4000
        acceleration = 255
    else:
        if args.velocity is None:
            print("❌ --velocity is required when --mode custom")
            return 1
        goal_velocity = max(1, min(4000, args.velocity))
        acceleration = max(1, min(255, args.acceleration))

    config = load_config(args.config)
    ports = gather_ports(config, args.arm_type)
    if not ports:
        print(f"⚠️  No ports found for arm_type={args.arm_type}.")
        return 0

    print(f"Updating {len(ports)} port(s) → Goal_Velocity={goal_velocity}, Acceleration={acceleration}")
    for port in ports:
        set_goal_velocity(port, goal_velocity, acceleration)
    print("Done.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
