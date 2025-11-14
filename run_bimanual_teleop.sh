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
LEFT_FOLLOWER_ID="${LEFT_FOLLOWER_ID:-left_follower}"
RIGHT_FOLLOWER_ID="${RIGHT_FOLLOWER_ID:-right_follower}"
LEFT_LEADER_ID="${LEFT_LEADER_ID:-left_leader}"
RIGHT_LEADER_ID="${RIGHT_LEADER_ID:-right_leader}"
LEFT_FOLLOWER_TYPE="${LEFT_FOLLOWER_TYPE:-so100_follower}"
RIGHT_FOLLOWER_TYPE="${RIGHT_FOLLOWER_TYPE:-so100_follower}"
LEFT_LEADER_TYPE="${LEFT_LEADER_TYPE:-so100_leader}"
RIGHT_LEADER_TYPE="${RIGHT_LEADER_TYPE:-so100_leader}"
ROBOT_CALIB_ID="${ROBOT_CALIB_ID:-bimanual_follower}"
TELEOP_CALIB_ID="${TELEOP_CALIB_ID:-bimanual_leader}"
TELEOP_FPS="${TELEOP_FPS:-50}"

# Pick up ports from config.json when not overridden
CONFIG_JSON="${PROJECT_ROOT}/config.json"
if [[ -f "${CONFIG_JSON}" ]]; then
  assignments=$("${PYTHON_BIN}" - "${CONFIG_JSON}" <<'PY'
import json, pathlib, sys
cfg=json.load(pathlib.Path(sys.argv[1]).open())
robot_arms=(cfg.get("robot") or {}).get("arms") or []
teleop_arms=(cfg.get("teleop") or {}).get("arms") or []
def arm_value(seq, idx, key, default=""):
    if idx >= len(seq) or not isinstance(seq[idx], dict):
        return default
    return (seq[idx].get(key) or default).strip() if key == "port" else seq[idx].get(key, default)
print(f"LEFT_FOLLOWER_PORT={arm_value(robot_arms,0,'port','')!r}")
print(f"RIGHT_FOLLOWER_PORT={arm_value(robot_arms,1,'port','')!r}")
print(f"LEFT_LEADER_PORT={arm_value(teleop_arms,0,'port','')!r}")
print(f"RIGHT_LEADER_PORT={arm_value(teleop_arms,1,'port','')!r}")
print(f"LEFT_FOLLOWER_ID={arm_value(robot_arms,0,'id','left_follower')!r}")
print(f"RIGHT_FOLLOWER_ID={arm_value(robot_arms,1,'id','right_follower')!r}")
print(f"LEFT_LEADER_ID={arm_value(teleop_arms,0,'id','left_leader')!r}")
print(f"RIGHT_LEADER_ID={arm_value(teleop_arms,1,'id','right_leader')!r}")
print(f"LEFT_FOLLOWER_TYPE={arm_value(robot_arms,0,'type','so100_follower')!r}")
print(f"RIGHT_FOLLOWER_TYPE={arm_value(robot_arms,1,'type','so100_follower')!r}")
print(f"LEFT_LEADER_TYPE={arm_value(teleop_arms,0,'type','so100_leader')!r}")
print(f"RIGHT_LEADER_TYPE={arm_value(teleop_arms,1,'type','so100_leader')!r}")
PY
)
  eval "${assignments}"
fi

determine_bi_type() {
  local left_type="$1"
  local right_type="$2"
  local default="$3"
  if [[ -z "${left_type}" ]]; then
    echo "${default}"
    return
  fi
  if [[ -n "${right_type}" && "${right_type}" != "${left_type}" ]]; then
    echo "⚠️ Mixed arm types detected (${left_type} vs ${right_type}); defaulting to ${left_type}" >&2
  fi
  local normalized="${left_type}"
  if [[ "${normalized}" == "so101_follower" || "${normalized}" == "so101_leader" ]]; then
    echo "${default/100/101}"
  else
    echo "${default}"
  fi
}

FOLLOWER_TYPE="$(determine_bi_type "${LEFT_FOLLOWER_TYPE}" "${RIGHT_FOLLOWER_TYPE}" "bi_so100_follower")"
LEADER_TYPE="$(determine_bi_type "${LEFT_LEADER_TYPE}" "${RIGHT_LEADER_TYPE}" "bi_so100_leader")"

CALIB_ROOT="${HOME}/.cache/huggingface/lerobot/calibration"

ensure_port_access() {
  local port="$1"
  if [[ -z "${port}" ]]; then
    echo "❌ Missing port assignment." >&2
    exit 1
  fi
  if [[ ! -e "${port}" ]]; then
    echo "❌ Serial device ${port} not found." >&2
    exit 1
  fi
  if [[ ! -r "${port}" || ! -w "${port}" ]]; then
    echo "❌ ${port} is not RW-accessible. Run 'sudo chmod 666 ${port}' or apply the udev rule in udev/99-so100.rules." >&2
    exit 1
  fi
}

ensure_calibration_link() {
  local category="$1"          # robots or teleoperators
  local target_type="$2"       # so100_follower, so100_leader, etc
  local target_base="$3"       # e.g. bimanual_follower
  local side="$4"              # left/right
  local source_type="$5"
  local source_id="$6"
  local source_path="${CALIB_ROOT}/${category}/${source_type}/${source_id}.json"
  if [[ ! -f "${source_path}" ]]; then
    local alt_type=""
    if [[ "${source_type}" == *"100"* ]]; then
      alt_type="${source_type/100/101}"
    elif [[ "${source_type}" == *"101"* ]]; then
      alt_type="${source_type/101/100}"
    fi
    if [[ -n "${alt_type}" ]]; then
      local alt_path="${CALIB_ROOT}/${category}/${alt_type}/${source_id}.json"
      if [[ -f "${alt_path}" ]]; then
        echo "⚠️ ${source_id}: ${source_type} calibration missing, using ${alt_type}" >&2
        source_type="${alt_type}"
        source_path="${alt_path}"
      fi
    fi
  fi
  if [[ ! -f "${source_path}" ]]; then
    shopt -s nullglob
    local matches=("${CALIB_ROOT}/${category}"/*/"${source_id}.json")
    shopt -u nullglob
    if [[ ${#matches[@]} -gt 0 ]]; then
      source_path="${matches[0]}"
      source_type=$(basename "$(dirname "${source_path}")")
      echo "⚠️ ${source_id}: using calibration from ${source_type} (auto-detected)" >&2
    fi
  fi
  local dest_path="${CALIB_ROOT}/${category}/${target_type}/${target_base}_${side}.json"
  if [[ ! -f "${source_path}" ]]; then
    echo "❌ Missing calibration file: ${source_path}" >&2
    return 1
  fi
  mkdir -p "$(dirname "${dest_path}")"
  ln -sf "${source_path}" "${dest_path}"
  return 0
}

target_follower_type="so100_follower"
if [[ "${FOLLOWER_TYPE}" == "bi_so101_follower" ]]; then
  target_follower_type="so101_follower"
fi
target_leader_type="so100_leader"
if [[ "${LEADER_TYPE}" == "bi_so101_leader" ]]; then
  target_leader_type="so101_leader"
fi

ensure_calibration_link "robots" "${target_follower_type}" "${ROBOT_CALIB_ID}" "left" "${LEFT_FOLLOWER_TYPE}" "${LEFT_FOLLOWER_ID}" || exit 1
ensure_calibration_link "robots" "${target_follower_type}" "${ROBOT_CALIB_ID}" "right" "${RIGHT_FOLLOWER_TYPE}" "${RIGHT_FOLLOWER_ID}" || exit 1
ensure_calibration_link "teleoperators" "${target_leader_type}" "${TELEOP_CALIB_ID}" "left" "${LEFT_LEADER_TYPE}" "${LEFT_LEADER_ID}" || exit 1
ensure_calibration_link "teleoperators" "${target_leader_type}" "${TELEOP_CALIB_ID}" "right" "${RIGHT_LEADER_TYPE}" "${RIGHT_LEADER_ID}" || exit 1

ensure_port_access "${LEFT_FOLLOWER_PORT}"
ensure_port_access "${RIGHT_FOLLOWER_PORT}"
ensure_port_access "${LEFT_LEADER_PORT}"
ensure_port_access "${RIGHT_LEADER_PORT}"

cat <<INFO
🤖 Starting Bimanual Teleoperation
==================================
Robot Configuration:
  Left follower : ${LEFT_FOLLOWER_PORT} (type ${LEFT_FOLLOWER_TYPE}, calib ${ROBOT_CALIB_ID}_left → ${LEFT_FOLLOWER_ID})
  Right follower: ${RIGHT_FOLLOWER_PORT} (type ${RIGHT_FOLLOWER_TYPE}, calib ${ROBOT_CALIB_ID}_right → ${RIGHT_FOLLOWER_ID})
Teleop Configuration:
  Left leader   : ${LEFT_LEADER_PORT} (type ${LEFT_LEADER_TYPE}, calib ${TELEOP_CALIB_ID}_left → ${LEFT_LEADER_ID})
  Right leader  : ${RIGHT_LEADER_PORT} (type ${RIGHT_LEADER_TYPE}, calib ${TELEOP_CALIB_ID}_right → ${RIGHT_LEADER_ID})
INFO

AUTO_ACCEPT_CALIBRATION="${AUTO_ACCEPT_CALIBRATION:-0}"
teleop_cmd=(
  "${TELEOP_BIN}"
  --robot.type=${FOLLOWER_TYPE} \
  --robot.left_arm_port=${LEFT_FOLLOWER_PORT} \
  --robot.right_arm_port=${RIGHT_FOLLOWER_PORT} \
  --robot.id=${ROBOT_CALIB_ID} \
  --teleop.type=${LEADER_TYPE} \
  --teleop.left_arm_port=${LEFT_LEADER_PORT} \
  --teleop.right_arm_port=${RIGHT_LEADER_PORT} \
  --teleop.id=${TELEOP_CALIB_ID} \
  --display_data=false \
  --fps=${TELEOP_FPS}
)

if [[ "${AUTO_ACCEPT_CALIBRATION}" == "1" ]]; then
  printf '\n' | "${teleop_cmd[@]}"
else
  "${teleop_cmd[@]}"
fi
