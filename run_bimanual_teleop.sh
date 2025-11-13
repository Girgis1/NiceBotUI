#!/bin/bash
# Bimanual SO100/SO101 Teleoperation Script
# Auto-generated for NiceBotUI

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_TELEOP_BIN="${VENV_DIR}/bin/lerobot-teleoperate"
PYTHON_BIN="${PYTHON_BIN:-}"
TELEOP_BIN="${TELEOP_BIN:-}"

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

LEFT_FOLLOWER_PORT="${LEFT_FOLLOWER_PORT:-/dev/ttyACM0}"
RIGHT_FOLLOWER_PORT="${RIGHT_FOLLOWER_PORT:-/dev/ttyACM2}"
LEFT_LEADER_PORT="${LEFT_LEADER_PORT:-/dev/ttyACM1}"
RIGHT_LEADER_PORT="${RIGHT_LEADER_PORT:-/dev/ttyACM3}"
FOLLOWER_TYPE="bi_so101_follower"
LEADER_TYPE="bi_so100_leader"
TELEOP_FPS="${TELEOP_FPS:-50}"

# Pick up ports from config.json when not overridden
CONFIG_JSON="${PROJECT_ROOT}/config.json"
if [[ -f "${CONFIG_JSON}" ]]; then
  LEFT_FOLLOWER_PORT=$("${PYTHON_BIN}" - <<PY
import json, pathlib
cfg=json.load(pathlib.Path('${CONFIG_JSON}').open())
arms = cfg.get('robot', {}).get('arms', [])
print(arms[0].get('port', '${LEFT_FOLLOWER_PORT}') if len(arms) else '${LEFT_FOLLOWER_PORT}')
PY
)
  RIGHT_FOLLOWER_PORT=$("${PYTHON_BIN}" - <<PY
import json, pathlib
cfg=json.load(pathlib.Path('${CONFIG_JSON}').open())
arms = cfg.get('robot', {}).get('arms', [])
print(arms[1].get('port', '${RIGHT_FOLLOWER_PORT}') if len(arms) > 1 else '${RIGHT_FOLLOWER_PORT}')
PY
)
  LEFT_LEADER_PORT=$("${PYTHON_BIN}" - <<PY
import json, pathlib
cfg=json.load(pathlib.Path('${CONFIG_JSON}').open())
arms = cfg.get('teleop', {}).get('arms', [])
print(arms[0].get('port', '${LEFT_LEADER_PORT}') if len(arms) else '${LEFT_LEADER_PORT}')
PY
)
  RIGHT_LEADER_PORT=$("${PYTHON_BIN}" - <<PY
import json, pathlib
cfg=json.load(pathlib.Path('${CONFIG_JSON}').open())
arms = cfg.get('teleop', {}).get('arms', [])
print(arms[1].get('port', '${RIGHT_LEADER_PORT}') if len(arms) > 1 else '${RIGHT_LEADER_PORT}')
PY
)
fi

cat <<INFO
🤖 Starting Bimanual Teleoperation
==================================
Robot Configuration:
  Left follower : ${LEFT_FOLLOWER_PORT}
  Right follower: ${RIGHT_FOLLOWER_PORT}
Teleop Configuration:
  Left leader   : ${LEFT_LEADER_PORT}
  Right leader  : ${RIGHT_LEADER_PORT}
INFO

sudo chmod 666 ${LEFT_FOLLOWER_PORT} ${RIGHT_FOLLOWER_PORT} ${LEFT_LEADER_PORT} ${RIGHT_LEADER_PORT}

"${TELEOP_BIN}" \
  --robot.type=${FOLLOWER_TYPE} \
  --robot.left_arm_port=${LEFT_FOLLOWER_PORT} \
  --robot.right_arm_port=${RIGHT_FOLLOWER_PORT} \
  --robot.id=follower \
  --teleop.type=${LEADER_TYPE} \
  --teleop.left_arm_port=${LEFT_LEADER_PORT} \
  --teleop.right_arm_port=${RIGHT_LEADER_PORT} \
  --teleop.id=leader \
  --display_data=false \
  --fps=${TELEOP_FPS}
