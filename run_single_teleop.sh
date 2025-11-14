#!/bin/bash
# Single-arm teleoperation launcher (SO-100/SO-101)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_TELEOP_BIN="${VENV_DIR}/bin/lerobot-teleoperate"
PYTHON_BIN="${PYTHON_BIN:-}"
TELEOP_BIN="${TELEOP_BIN:-}"
TARGET_ARM="${TARGET_ARM:-left}"
TELEOP_FPS="${TELEOP_FPS:-50}"

if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${VENV_PYTHON}" ]]; then
    PYTHON_BIN="${VENV_PYTHON}"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi

if [[ -z "${TELEOP_BIN}" ]]; then
  if [[ -x "${VENV_TELEOP_BIN}" ]]; then
    TELEOP_BIN="${VENV_TELEOP_BIN}"
  else
    TELEOP_BIN="$(command -v lerobot-teleoperate || true)"
  fi
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "❌ python3 not found. Install Python or create the venv before running teleop." >&2
  exit 1
fi

if [[ -z "${TELEOP_BIN}" ]]; then
  echo "❌ lerobot-teleoperate not found. Ensure lerobot is installed in the venv or export TELEOP_BIN." >&2
  exit 1
fi

if [[ "${TARGET_ARM}" != "left" && "${TARGET_ARM}" != "right" ]]; then
  echo "❌ TARGET_ARM must be 'left' or 'right' (got '${TARGET_ARM}')" >&2
  exit 1
fi

CONFIG_JSON="${PROJECT_ROOT}/config.json"
assignments="$("${PYTHON_BIN}" - <<'PY' "${CONFIG_JSON}" "${TARGET_ARM}")"
import json
import pathlib
import sys

config = json.loads(pathlib.Path(sys.argv[1]).read_text())
target = sys.argv[2]
index = 0 if target == "left" else 1

robot_cfg = config.get("robot", {}) or {}
teleop_cfg = config.get("teleop", {}) or {}
robot_arms = robot_cfg.get("arms", []) or []
teleop_arms = teleop_cfg.get("arms", []) or []

def resolve_arm(arms, idx, role):
    if idx >= len(arms):
        raise SystemExit(f"❌ No {role} arm configured at index {idx}")
    arm = arms[idx] or {}
    port = (arm.get("port") or "").strip()
    if not port:
        raise SystemExit(f"❌ {role.title()} arm at index {idx} missing port in config.json")
    arm_type = arm.get("type") or ("so101_follower" if role == "follower" else "so100_leader")
    arm_id = arm.get("id") or f"{target}_{role}"
    return port, arm_type, arm_id

follower_port, follower_type, follower_id = resolve_arm(robot_arms, index, "follower")
leader_port, leader_type, leader_id = resolve_arm(teleop_arms, index, "leader")

print(f"FOLLOWER_PORT='{follower_port}'")
print(f"FOLLOWER_TYPE='{follower_type}'")
print(f"FOLLOWER_ID='{follower_id}'")
print(f"LEADER_PORT='{leader_port}'")
print(f"LEADER_TYPE='{leader_type}'")
print(f"LEADER_ID='{leader_id}'")
PY
)"
eval "${assignments}"

cat <<INFO
🎮 Starting ${TARGET_ARM^} Arm Teleoperation
==================================
Follower Port: ${FOLLOWER_PORT}
Leader Port  : ${LEADER_PORT}
INFO

AUTO_ACCEPT_CALIBRATION="${AUTO_ACCEPT_CALIBRATION:-0}"
teleop_cmd=(
  "${TELEOP_BIN}"
  --robot.type=${FOLLOWER_TYPE} \
  --robot.port=${FOLLOWER_PORT} \
  --robot.id=${FOLLOWER_ID} \
  --teleop.type=${LEADER_TYPE} \
  --teleop.port=${LEADER_PORT} \
  --teleop.id=${LEADER_ID} \
  --display_data=false \
  --fps=${TELEOP_FPS}
)

if [[ "${AUTO_ACCEPT_CALIBRATION}" == "1" ]]; then
  printf '\n' | "${teleop_cmd[@]}"
else
  "${teleop_cmd[@]}"
fi
