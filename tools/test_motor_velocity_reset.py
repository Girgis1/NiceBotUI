#!/usr/bin/env python3
"""Set Goal_Velocity/Acceleration for one arm (optionally single motor)."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from HomePos import create_motor_bus, MOTOR_NAMES
except Exception as exc:  # pragma: no cover - needs hardware deps
    raise SystemExit(f"❌ Unable to import motor helpers: {exc}")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set Goal_Velocity for a single arm/motor.")
    parser.add_argument("port", help="Serial port (e.g., /dev/ttyACM0)")
    parser.add_argument(
        "--motor",
        choices=MOTOR_NAMES,
        help="Specific motor name (default: all motors on the bus).",
    )
    parser.add_argument(
        "--velocity",
        type=int,
        default=4000,
        help="Goal_Velocity value (default: 4000).",
    )
    parser.add_argument(
        "--acceleration",
        type=int,
        default=255,
        help="Acceleration register value (default: 255).",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Read current Goal_Velocity without writing.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    targets = [args.motor] if args.motor else MOTOR_NAMES

    try:
        bus = create_motor_bus(args.port)
    except Exception as exc:
        print(f"❌ Failed to connect to {args.port}: {exc}")
        return 1

    try:
        for name in targets:
            try:
                current = bus.read("Goal_Velocity", name, normalize=False)
            except Exception as exc:
                print(f"   ❌ {name}: unable to read ({exc})")
                continue

            if args.read_only:
                print(f"   ℹ️  {name}: Goal_Velocity={current}")
                continue

            try:
                bus.write("Goal_Velocity", name, max(1, min(4000, args.velocity)), normalize=False)
                bus.write("Acceleration", name, max(1, min(255, args.acceleration)), normalize=False)
                updated = bus.read("Goal_Velocity", name, normalize=False)
                print(f"   ✓ {name}: {current} → {updated}")
            except Exception as exc:
                print(f"   ❌ {name}: write failed ({exc})")
    finally:
        try:
            bus.disconnect()
        except Exception:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
