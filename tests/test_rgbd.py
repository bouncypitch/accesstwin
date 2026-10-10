"""End-to-end check of RGB-D unprojection, fusion and RoomPlan alignment on a synthetic box room."""

import json
import math

import numpy as np
import pytest
from PIL import Image

from accesstwin import rgbd

W, D, H = 6.0, 4.0, 2.8  # room in RoomPlan world: x in [0, W], z in [0, D], floor at y = -1.4
FLOOR = -1.4
DW, DH = 64, 48  # depth resolution
IW, IH = 256, 192  # color resolution


def roomplan_box() -> dict:
    def surface(cx, cz, length, axis_x, axis_z, height=H):
        # Column-major transform: local x along the wall, y up, z = x cross y.
        t = [axis_x, 0, axis_z, 0, 0, 1, 0, 0, -axis_z, 0, axis_x, 0, cx, FLOOR + height / 2, cz, 1]
        return {"dimensions": [length, height, 0], "transform": t, "category": {"wall": {}}}

    walls = [surface(W / 2, 0, W, 1, 0), surface(W / 2, D, W, 1, 0), surface(0, D / 2, D, 0, 1), surface(W, D / 2, D, 0, 1)]
    floor = {"transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, FLOOR, 0, 1],
             "polygonCorners": [[0, 0, 0], [W, 0, 0], [W, 0, D], [0, 0, D]], "dimensions": [W, D, 0]}
    return {"walls": walls, "floors": [floor], "doors": [], "openings": [], "objects": []}


def ray_depth(origin, dirs):
    """Distance along each unit ray to the box (walls, floor, ceiling); returns t."""
    t = np.full(len(dirs), np.inf)
    for axis, lo, hi in ((0, 0, W), (1, FLOOR, FLOOR + H), (2, 0, D)):
        d = dirs[:, axis]
        with np.errstate(divide="ignore", invalid="ignore"):
            for plane in (lo, hi):
                tt = (plane - origin[axis]) / d
                tt[(tt <= 0) | ~np.isfinite(tt)] = np.inf
                t = np.minimum(t, tt)
    return t


def make_recording(tmp_path, yaw_deg=33.0, shift=(1.7, 0.4, -2.2)):
    """Records a loop inside the box. The recording's world is the RoomPlan world rotated by yaw and shifted,
    the way two separate ARKit sessions disagree."""
    rec = tmp_path / "rgbd"
    for sub in ("color", "depth", "conf"):
        (rec / sub).mkdir(parents=True)
    a = math.radians(yaw_deg)
    # rec_from_rp: rotation about y by `a`, then shift.
    rec_from_rp = np.eye(4)
    rec_from_rp[0, 0], rec_from_rp[0, 2], rec_from_rp[2, 0], rec_from_rp[2, 2] = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    rec_from_rp[:3, 3] = shift
    fx = fy = 200.0
    cx, cy = IW / 2, IH / 2
    lines = []
    for i, heading in enumerate(np.linspace(0, 2 * math.pi, 24, endpoint=False)):
        pos = np.array([W / 2 + 1.2 * math.cos(heading), FLOOR + 1.4, D / 2 + 0.8 * math.sin(heading)])
        yaw = heading + math.pi / 2
        # Camera looks along -z of its frame; rotate about y.
        r = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]])
        cam_to_rp = np.eye(4)
        cam_to_rp[:3, :3], cam_to_rp[:3, 3] = r, pos
        sx, sy = DW / IW, DH / IH
        v, u = np.mgrid[0:DH, 0:DW]
        x = (u + 0.5 - cx * sx) / (fx * sx)
        y = (v + 0.5 - cy * sy) / (fy * sy)
        dirs_cam = np.stack([x, -y, -np.ones_like(x)], axis=-1).reshape(-1, 3)
        dirs = dirs_cam @ r.T
        norm = np.linalg.norm(dirs, axis=1)
        t = ray_depth(pos, dirs / norm[:, None])
        depth = (t / norm).reshape(DH, DW)  # z-depth, as LiDAR reports
        name = f"{i:06d}"
        np.round(depth * 1000).astype("<u2").tofile(rec / "depth" / f"{name}.u16")
        np.full((DH, DW), 2, np.uint8).tofile(rec / "conf" / f"{name}.u8")
        Image.fromarray(np.full((IH, IW, 3), 180, np.uint8)).save(rec / "color" / f"{name}.jpg")
        pose = rec_from_rp @ cam_to_rp
        lines.append(json.dumps({
            "index": i, "timestamp": i * 0.1, "tracking": "normal", "image_size": [IW, IH],
            "intrinsics": [fx, fy, cx, cy], "depth_size": [DW, DH],
            "camera_to_world": pose.T.ravel().tolist(),
        }))
    (rec / "frames.jsonl").write_text("\n".join(lines))
    rp = tmp_path / "roomplan.json"
    rp.write_text(json.dumps(roomplan_box()))
    return rec, rp, rec_from_rp


def test_fused_points_lie_on_the_box_and_align(tmp_path):
    rec, rp, rec_from_rp = make_recording(tmp_path)
    frames = rgbd.load(rec)
    assert len(frames) == 24
    pts, cols = rgbd.fuse(frames, voxel=0.02)
    assert len(pts) > 1000

    al = rgbd.align(pts, rp)
    # The fitted alignment should undo the session offset.
    np.testing.assert_allclose(al.matrix(), np.linalg.inv(rec_from_rp), atol=0.03)
    p = al.apply(pts)
    # Every point is on one of the six faces of the box, to within a voxel.
    dist = np.min(np.stack([np.abs(p[:, 0]), np.abs(p[:, 0] - W), np.abs(p[:, 2]), np.abs(p[:, 2] - D),
                            np.abs(p[:, 1] - FLOOR), np.abs(p[:, 1] - FLOOR - H)]), axis=0)
    assert np.percentile(dist, 99) < 0.025
    assert al.rms < 0.03
