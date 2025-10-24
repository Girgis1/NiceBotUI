"""Minimal IK solver utilities for SO-series arms using PyBullet."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
try:
    import pybullet as p  # type: ignore
except ImportError as exc:  # pragma: no cover - pybullet is an optional dependency
    raise RuntimeError(
        "pybullet is required for IK operations. Install the phosphobot dependencies first."
    ) from exc


PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCES_ROOT = PACKAGE_ROOT / "resources"
SO100_URDF = RESOURCES_ROOT / "so-100" / "urdf" / "so-100.urdf"


class IKSolver:
    """Wrapper around PyBullet's calculateInverseKinematics for SO-series arms."""

    def __init__(self, urdf_path: Optional[Path] = None) -> None:
        self._client = p.connect(p.DIRECT)
        self._setup_search_paths()

        self.urdf_path = Path(urdf_path or SO100_URDF)
        if not self.urdf_path.exists():  # pragma: no cover - guarded by packaging
            raise FileNotFoundError(f"URDF not found: {self.urdf_path}")

        self.robot_id = p.loadURDF(
            str(self.urdf_path), useFixedBase=True, flags=p.URDF_USE_INERTIA_FROM_FILE
        )
        self.end_effector_link = 4  # matches phosphobot definition
        self.joint_indices: list[int] = []
        self.lower_limits: list[float] = []
        self.upper_limits: list[float] = []
        self.joint_ranges: list[float] = []
        self.rest_poses: list[float] = []

        self._extract_joint_limits()

    # ------------------------------------------------------------------ helpers
    def _setup_search_paths(self) -> None:
        p.setAdditionalSearchPath(str(RESOURCES_ROOT))
        mesh_path = RESOURCES_ROOT / "so-100"
        p.setAdditionalSearchPath(str(mesh_path))

    def _extract_joint_limits(self) -> None:
        num_joints = p.getNumJoints(self.robot_id)
        for idx in range(num_joints):
            info = p.getJointInfo(self.robot_id, idx)
            joint_type = info[2]
            if joint_type not in (p.JOINT_REVOLUTE, p.JOINT_PRISMATIC):
                continue

            lower = info[8]
            upper = info[9]
            if math.isclose(lower, upper):
                lower = -math.pi
                upper = math.pi
            self.joint_indices.append(idx)
            self.lower_limits.append(lower)
            self.upper_limits.append(upper)
            self.joint_ranges.append(abs(upper - lower))
            self.rest_poses.append(0.0)

    # ------------------------------------------------------------------ public API
    def solve(
        self,
        position: Iterable[float],
        orientation_rpy: Optional[Iterable[float]] = None,
    ) -> np.ndarray:
        """Compute joint angles (radians) to reach ``position`` with optional orientation."""

        pos = np.array(position, dtype=float).tolist()
        if orientation_rpy is None:
            quat = None
        else:
            roll, pitch, yaw = orientation_rpy
            quat = p.getQuaternionFromEuler([roll, pitch, yaw])

        result = p.calculateInverseKinematics(
            self.robot_id,
            self.end_effector_link,
            pos,
            targetOrientation=quat,
            lowerLimits=self.lower_limits,
            upperLimits=self.upper_limits,
            jointRanges=self.joint_ranges,
            restPoses=self.rest_poses,
            maxNumIterations=200,
            residualThreshold=1e-6,
        )
        joint_values = np.array(result)[self.joint_indices]
        return joint_values

    def disconnect(self) -> None:
        if p.isConnected(self._client):
            p.disconnect(self._client)

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.disconnect()
        except Exception:
            pass
