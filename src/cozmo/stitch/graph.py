"""Pose graph construction and Gauss–Newton optimisation.

A pose graph represents the spatial relationships between rooms.  Each node is
a room (carrying a 2D rigid transform: x, y, theta), and each edge is an
observation constraining the relative pose of two rooms (from shared walls,
doorways, or feature matches).

The graph is optimised by iterative linearisation (Gauss–Newton on SE(2)),
which is both simple and adequate for the scale of problem we see — up to ~15
rooms in a large property.

Design decisions:

1. **SE(2) not SE(3).** Floor plans are planar; allowing a z rotation and
   translations out of plane invites drift in directions that have no signal
   rather than suppressing it.

2. **Information-weighted edges.** A shared 6-metre wall is a stronger
   constraint than a 1-metre doorway, so the edge weight scales with the
   observation length.

3. **Anchor the first room.** Without a fixed node the system is under-
   determined (a rigid-body transformation of the whole graph costs nothing).
   We pin room 0 to the origin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger("cozmo.stitch.graph")


@dataclass
class PoseNode:
    """A room's pose in the global frame: (x, y, theta)."""

    room_id: str
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.theta])

    @staticmethod
    def from_array(room_id: str, arr: np.ndarray) -> "PoseNode":
        return PoseNode(room_id=room_id, x=float(arr[0]), y=float(arr[1]), theta=float(arr[2]))


@dataclass
class PoseEdge:
    """A constraint between two rooms: the measured relative pose and its weight."""

    room_i: str
    room_j: str
    dx: float
    dy: float
    dtheta: float
    information: float = 1.0
    source: str = "shared_wall"


@dataclass
class PoseGraph:
    """The full set of room poses and inter-room constraints."""

    nodes: dict[str, PoseNode] = field(default_factory=dict)
    edges: list[PoseEdge] = field(default_factory=list)

    def add_node(self, room_id: str, x: float = 0.0, y: float = 0.0, theta: float = 0.0) -> None:
        self.nodes[room_id] = PoseNode(room_id=room_id, x=x, y=y, theta=theta)

    def add_edge(
        self,
        room_i: str,
        room_j: str,
        dx: float,
        dy: float,
        dtheta: float,
        information: float = 1.0,
        source: str = "shared_wall",
    ) -> None:
        self.edges.append(
            PoseEdge(
                room_i=room_i,
                room_j=room_j,
                dx=dx,
                dy=dy,
                dtheta=dtheta,
                information=information,
                source=source,
            )
        )

    @property
    def room_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


def _rotation_2d(theta: float) -> np.ndarray:
    """2×2 rotation matrix for angle theta."""
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s], [s, c]])


def _edge_residual(
    pose_i: np.ndarray, pose_j: np.ndarray, edge: PoseEdge
) -> np.ndarray:
    """Compute the residual for a single edge.

    The residual is the difference between the observed and predicted relative
    pose, expressed in room_i's frame.
    """
    xi, yi, ti = pose_i
    xj, yj, tj = pose_j

    ri = _rotation_2d(ti)
    d_global = np.array([xj - xi, yj - yi])
    d_local = ri.T @ d_global

    residual = np.array([
        d_local[0] - edge.dx,
        d_local[1] - edge.dy,
        _wrap_angle(tj - ti - edge.dtheta),
    ])
    return residual


def _wrap_angle(a: float) -> float:
    """Wrap an angle to [-pi, pi]."""
    return float((a + np.pi) % (2 * np.pi) - np.pi)


def _edge_jacobian(
    pose_i: np.ndarray, pose_j: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Jacobian of the edge residual w.r.t. pose_i and pose_j.

    Returns (J_i, J_j) each of shape (3, 3).
    """
    xi, yi, ti = pose_i
    xj, yj, _ = pose_j

    c, s = np.cos(ti), np.sin(ti)
    dx = xj - xi
    dy = yj - yi

    # J w.r.t. pose_i
    j_i = np.array([
        [-c, -s, -s * dx + c * dy],
        [s, -c, -c * dx - s * dy],
        [0.0, 0.0, -1.0],
    ])

    # J w.r.t. pose_j
    j_j = np.array([
        [c, s, 0.0],
        [-s, c, 0.0],
        [0.0, 0.0, 1.0],
    ])

    return j_i, j_j


def optimise_pose_graph(
    graph: PoseGraph,
    max_iterations: int = 50,
    convergence_threshold: float = 1e-6,
    anchor_room: Optional[str] = None,
) -> PoseGraph:
    """Optimise the pose graph using Gauss–Newton on SE(2).

    The first room (or ``anchor_room``) is fixed to prevent gauge freedom.
    Returns a new graph with updated poses.
    """
    if graph.room_count == 0:
        return graph
    if graph.edge_count == 0:
        log.warning("pose graph has no edges; returning unchanged")
        return graph

    room_ids = sorted(graph.nodes.keys())
    n = len(room_ids)
    idx = {rid: i for i, rid in enumerate(room_ids)}

    if anchor_room is None:
        anchor_room = room_ids[0]
    anchor_idx = idx[anchor_room]

    # Flatten poses into a single vector.
    state = np.zeros(3 * n)
    for rid, node in graph.nodes.items():
        i = idx[rid]
        state[3 * i: 3 * i + 3] = node.as_array()

    for iteration in range(max_iterations):
        h = np.zeros((3 * n, 3 * n))
        b = np.zeros(3 * n)
        total_cost = 0.0

        for edge in graph.edges:
            if edge.room_i not in idx or edge.room_j not in idx:
                continue

            i = idx[edge.room_i]
            j = idx[edge.room_j]
            pi = state[3 * i: 3 * i + 3]
            pj = state[3 * j: 3 * j + 3]

            r = _edge_residual(pi, pj, edge)
            ji, jj = _edge_jacobian(pi, pj)
            omega = edge.information * np.eye(3)

            total_cost += float(r @ omega @ r)

            # Accumulate into the normal equations.
            h[3 * i: 3 * i + 3, 3 * i: 3 * i + 3] += ji.T @ omega @ ji
            h[3 * i: 3 * i + 3, 3 * j: 3 * j + 3] += ji.T @ omega @ jj
            h[3 * j: 3 * j + 3, 3 * i: 3 * i + 3] += jj.T @ omega @ ji
            h[3 * j: 3 * j + 3, 3 * j: 3 * j + 3] += jj.T @ omega @ jj

            b[3 * i: 3 * i + 3] += ji.T @ omega @ r
            b[3 * j: 3 * j + 3] += jj.T @ omega @ r

        # Fix the anchor.
        h[3 * anchor_idx: 3 * anchor_idx + 3, :] = 0.0
        h[:, 3 * anchor_idx: 3 * anchor_idx + 3] = 0.0
        h[3 * anchor_idx: 3 * anchor_idx + 3, 3 * anchor_idx: 3 * anchor_idx + 3] = np.eye(3) * 1e6
        b[3 * anchor_idx: 3 * anchor_idx + 3] = 0.0

        # Solve.
        try:
            delta = np.linalg.solve(h, -b)
        except np.linalg.LinAlgError:
            log.warning("pose graph: singular system at iteration %d", iteration)
            break

        state += delta

        step_size = float(np.linalg.norm(delta))
        log.debug(
            "pose graph iteration %d: cost=%.6f, step=%.6f",
            iteration,
            total_cost,
            step_size,
        )

        if step_size < convergence_threshold:
            log.info(
                "pose graph converged after %d iterations (step=%.2e)",
                iteration + 1,
                step_size,
            )
            break

    # Build result graph.
    result = PoseGraph()
    for rid in room_ids:
        i = idx[rid]
        result.add_node(rid, *state[3 * i: 3 * i + 3].tolist())
    result.edges = list(graph.edges)
    return result
