"""Procedural substitutes for Cascadeur's license-gated AI physics/inbetween.

These operate on baked per-frame world data (from anim.bake / transform.get) and
re-apply corrected controller positions. Pure math — no Cascadeur AI needed.

- foot_lock: freeze a planted foot's world XZ over a contact interval (de-slide)
- ballistic_arc: gravity parabola for the root over an airborne interval
- secondary_motion: lag + damped overshoot on child points (overlap/follow-through)
- procedural_breakdown: an arc breakdown between two keys (life vs raw bezier)
"""

from __future__ import annotations

import math

GRAVITY = 980.0  # cm/s^2


def foot_lock_positions(foot_world_by_frame: dict[int, list], frames: list[int],
                        anchor: str = "median") -> dict[int, list]:
    """Given a foot point's world pos over the planted frames, return corrected
    positions with constant XZ (Y kept) so it doesn't slide."""
    xs = [foot_world_by_frame[f][0] for f in frames]
    zs = [foot_world_by_frame[f][2] for f in frames]
    if anchor == "first":
        ax, az = xs[0], zs[0]
    else:
        ax = sorted(xs)[len(xs) // 2]
        az = sorted(zs)[len(zs) // 2]
    return {f: [round(ax, 3), round(foot_world_by_frame[f][1], 3), round(az, 3)]
            for f in frames}


def ballistic_arc(launch, land, n_frames: int, fps: int = 30) -> list[list]:
    """Root positions for an airborne interval following gravity. launch/land =
    world [x,y,z] at takeoff/touchdown. Returns n_frames positions (inclusive)."""
    if n_frames < 2:
        return [list(launch), list(land)]
    dt = 1.0 / fps
    T = (n_frames - 1) * dt
    # y(t) = y0 + vy*t - 0.5 g t^2 ; solve vy so y(T)=land_y
    vy = (land[1] - launch[1] + 0.5 * GRAVITY * T * T) / T
    out = []
    for i in range(n_frames):
        t = i * dt
        u = i / (n_frames - 1)
        x = launch[0] + (land[0] - launch[0]) * u
        z = launch[2] + (land[2] - launch[2]) * u
        y = launch[1] + vy * t - 0.5 * GRAVITY * t * t
        out.append([round(x, 3), round(y, 3), round(z, 3)])
    return out


def apex_frame(launch, land, n_frames: int, fps: int = 30) -> int:
    dt = 1.0 / fps
    T = (n_frames - 1) * dt
    vy = (land[1] - launch[1] + 0.5 * GRAVITY * T * T) / T
    t_apex = vy / GRAVITY
    return max(0, min(n_frames - 1, round(t_apex / dt)))


def secondary_motion(parent_world: list[list], lag_frames: int = 3,
                     overshoot: float = 0.35, damping: float = 0.6) -> list[list]:
    """Apply overlap/drag: output follows the parent trajectory with a lag and a
    damped overshoot after the parent decelerates. parent_world = list of [x,y,z]
    per frame. Returns same length."""
    n = len(parent_world)
    if n < 3:
        return [list(p) for p in parent_world]
    out = [list(parent_world[0])]
    vel = [0.0, 0.0, 0.0]
    pos = list(parent_world[0])
    stiffness = 1.0 / max(1, lag_frames)
    for i in range(1, n):
        target = parent_world[i]
        for k in range(3):
            # critically-ish damped spring toward the lagged target
            acc = (target[k] - pos[k]) * stiffness - vel[k] * damping
            vel[k] += acc
            pos[k] += vel[k] * (1.0 + overshoot)
        out.append([round(pos[0], 3), round(pos[1], 3), round(pos[2], 3)])
    return out


def procedural_breakdown(a: list, b: list, arc_up: float = 0.0,
                         bias: float = 0.62):
    """A breakdown point between key positions a and b: placed at `bias` of the
    travel with `arc_up` added to Y (an arc, not a straight line)."""
    p = [a[i] + (b[i] - a[i]) * bias for i in range(3)]
    p[1] += arc_up
    return [round(p[0], 3), round(p[1], 3), round(p[2], 3)]


def ease(u: float, k: float = 2.0) -> float:
    """Smooth ease-in-out in [0,1] (for our own inbetweening spacing)."""
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0
    return u ** k / (u ** k + (1 - u) ** k)
