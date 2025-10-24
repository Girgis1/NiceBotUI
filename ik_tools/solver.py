"""Minimal IK solver utilities for SO-series arms using PyBullet."""

from __future__ import annotations

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

    def __init__(self, urdf_path: Optional[Path] = None, use_gui: bool = False) -> None:
        self.urdf_path = Path(urdf_path or SO100_URDF)
        if not self.urdf_path.exists():  # pragma: no cover - guarded by packaging
            raise FileNotFoundError(f"URDF not found: {self.urdf_path}")

        self._client: Optional[int] = None
        self.robot_id: Optional[int] = None
        self.use_gui = use_gui
        self.end_effector_link = 4  # matches phosphobot definition
        self.joint_indices: list[int] = []
        self.lower_limits: list[float] = []
        self.upper_limits: list[float] = []
        self.joint_ranges: list[float] = []
        self.rest_poses: list[float] = []

        self.reinitialize(use_gui=use_gui)

    # ------------------------------------------------------------------ lifecycle helpers
    def reinitialize(self, use_gui: Optional[bool] = None) -> None:
        """Reconnect to PyBullet and reload the URDF."""
        if use_gui is not None:
            self.use_gui = use_gui

        if self._client is not None and p.isConnected(self._client):
            p.disconnect(self._client)

        connection_mode = p.GUI if self.use_gui else p.DIRECT
        self._client = p.connect(connection_mode)
        if self.use_gui:
            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)

        self._setup_search_paths()
        self.robot_id = p.loadURDF(
            str(self.urdf_path), useFixedBase=True, flags=p.URDF_USE_INERTIA_FROM_FILE
        )

        self.joint_indices.clear()
        self.lower_limits.clear()
        self.upper_limits.clear()
        self.joint_ranges.clear()
        self.rest_poses.clear()
        self._extract_joint_limits()

    def disconnect(self) -> None:
        if self._client is not None and p.isConnected(self._client):
            p.disconnect(self._client)
            self._client = None

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.disconnect()
        except Exception:
            pass

    # ------------------------------------------------------------------ helpers
    def _setup_search_paths(self) -> None:
        p.setAdditionalSearchPath(str(RESOURCES_ROOT))
        mesh_path = RESOURCES_ROOT / "so-100"
        p.setAdditionalSearchPath(str(mesh_path))

    def _extract_joint_limits(self) -> None:
        assert self.robot_id is not None
        num_joints = p.getNumJoints(self.robot_id)
        for idx in range(num_joints):
            info = p.getJointInfo(self.robot_id, idx)
            joint_type = info[2]
            if joint_type not in (p.JOINT_REVOLUTE, p.JOINT_PRISMATIC):
                continue

            lower = info[8]
            upper = info[9]
            if abs(lower - upper) < 1e-6:
                lower, upper = -np.pi, np.pi

            self.joint_indices.append(idx)
            self.lower_limits.append(float(lower))
            self.upper_limits.append(float(upper))
            self.joint_ranges.append(abs(float(upper) - float(lower)))
            self.rest_poses.append(0.0)

    # ------------------------------------------------------------------ public API
    def solve(
        self,
        position: Iterable[float],
        orientation_rpy: Optional[Iterable[float]] = None,
    ) -> np.ndarray:
        """Compute joint angles (radians) to reach ``position`` with optional orientation."""

        if self.robot_id is None:
            raise RuntimeError("Solver is not initialized. Call reinitialize() first.")

        pos = np.array(position, dtype=float).tolist()
        if orientation_rpy is None:
            quat = None
        else:
            quat = p.getQuaternionFromEuler(list(orientation_rpy))

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
