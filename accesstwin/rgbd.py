"""RGB-D walkthroughs from the RoomScan recorder: load frames, fuse a metric colored point cloud, align it to the
RoomPlan scan, and play it back in Rerun.

Recording layout (from ios/RoomScan/RGBDRecorder.swift): frames.jsonl, color/NNNNNN.jpg, depth/NNNNNN.u16 (mm),
conf/NNNNNN.u8 (0 low, 1 medium, 2 high). Poses are ARKit camera-to-world, column-major, camera looks down -z.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .roomplan import _Frame, _matrix


@dataclass
class RGBDFrame:
    index: int
    timestamp: float
    color: Path
    depth_path: Path
    conf_path: Path
    depth_size: tuple[int, int]
    image_size: tuple[int, int]
    intrinsics: tuple[float, float, float, float]  # fx, fy, cx, cy for the color image
    pose: np.ndarray  # 4x4 camera-to-world
    tracking: str

    def depth(self) -> np.ndarray:
        w, h = self.depth_size
        return np.fromfile(self.depth_path, dtype="<u2").reshape(h, w).astype(np.float32) / 1000.0

    def confidence(self) -> np.ndarray | None:
        if not self.conf_path.exists():
            return None
        w, h = self.depth_size
        return np.fromfile(self.conf_path, dtype=np.uint8).reshape(h, w)

    def rgb(self, size: tuple[int, int] | None = None) -> np.ndarray:
        im = Image.open(self.color).convert("RGB")
        return np.asarray(im.resize(size, Image.BILINEAR) if size else im)

    def depth_intrinsics(self) -> tuple[float, float, float, float]:
        fx, fy, cx, cy = self.intrinsics
        sx = self.depth_size[0] / self.image_size[0]
        sy = self.depth_size[1] / self.image_size[1]
        return fx * sx, fy * sy, cx * sx, cy * sy

    def points(self, min_conf: int = 2, max_depth: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
        """World-space points (N, 3) and colors (N, 3 uint8) from this frame's depth map."""
        d = self.depth()
        h, w = d.shape
        fx, fy, cx, cy = self.depth_intrinsics()
        v, u = np.mgrid[0:h, 0:w]
        ok = (d > 0.1) & (d < max_depth)
        conf = self.confidence()
        if conf is not None:
            ok &= conf >= min_conf
        z = d[ok]
        x = (u[ok] + 0.5 - cx) / fx * z
        y = (v[ok] + 0.5 - cy) / fy * z
        cam = np.stack([x, -y, -z, np.ones_like(z)], axis=1)  # image (right, down, forward) -> ARKit camera
        world = (self.pose @ cam.T).T[:, :3]
        colors = self.rgb((w, h))[ok]
        return world, colors


def load(rec_dir: str | Path) -> list[RGBDFrame]:
    rec = Path(rec_dir)
    if not (rec / "frames.jsonl").exists() and (rec / "rgbd" / "frames.jsonl").exists():
        rec = rec / "rgbd"
    frames = []
    for line in (rec / "frames.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        m = json.loads(line)
        name = f"{m['index']:06d}"
        frames.append(RGBDFrame(
            index=m["index"], timestamp=m["timestamp"], color=rec / "color" / f"{name}.jpg",
            depth_path=rec / "depth" / f"{name}.u16", conf_path=rec / "conf" / f"{name}.u8",
            depth_size=tuple(m["depth_size"]), image_size=tuple(int(x) for x in m["image_size"]),
            intrinsics=tuple(m["intrinsics"]), pose=np.array(m["camera_to_world"]).reshape(4, 4).T,
            tracking=m.get("tracking", "normal"),
        ))
    return [f for f in frames if f.color.exists() and f.depth_path.exists()]


def fuse(frames: list[RGBDFrame], voxel: float = 0.02, stride: int = 1, min_conf: int = 2,
         chunk: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """Voxel-averaged colored point cloud from every `stride`-th frame with normal tracking.

    Frames are reduced in chunks so memory stays bounded by the number of occupied voxels."""
    keys = np.zeros((0, 3), dtype=np.int64)
    sums = np.zeros((0, 6))
    counts = np.zeros(0, dtype=np.int64)

    def reduce(k, s, n):
        u, inv = np.unique(k, axis=0, return_inverse=True)
        inv = inv.ravel()
        out_s = np.zeros((len(u), 6))
        out_n = np.zeros(len(u), dtype=np.int64)
        np.add.at(out_s, inv, s)
        np.add.at(out_n, inv, n)
        return u, out_s, out_n

    usable = [f for f in frames[::stride] if f.tracking == "normal"]
    for i in range(0, len(usable), chunk):
        ps, cs = zip(*(f.points(min_conf=min_conf) for f in usable[i:i + chunk]))
        p, c = np.concatenate(ps), np.concatenate(cs).astype(np.float64)
        k = np.floor(p / voxel).astype(np.int64)
        k, s_, n_ = reduce(k, np.c_[p, c], np.ones(len(p), dtype=np.int64))
        keys, sums, counts = reduce(np.r_[keys, k], np.r_[sums, s_], np.r_[counts, n_])
    keep = counts >= 2  # drop single-hit voxels (mostly flying pixels at depth edges)
    mean = sums[keep] / counts[keep, None]
    return mean[:, :3], mean[:, 3:].round().astype(np.uint8)


def save_ply(path: str | Path, points: np.ndarray, colors: np.ndarray) -> None:
    header = (f"ply\nformat binary_little_endian 1.0\nelement vertex {len(points)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    rec = np.zeros(len(points), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec["x"], rec["y"], rec["z"] = points.T
    rec["r"], rec["g"], rec["b"] = colors.T
    with open(path, "wb") as fh:
        fh.write(header.encode())
        fh.write(rec.tobytes())


# Alignment to the RoomPlan scan ----------------------------------------------------------------------------

@dataclass
class Alignment:
    """Maps recording world coordinates onto RoomPlan world coordinates: yaw about +y, then translate."""

    yaw: float
    t: np.ndarray  # (3,)
    rms: float  # wall-point fit error, meters

    def matrix(self) -> np.ndarray:
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        m = np.eye(4)
        m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
        m[:3, 3] = self.t
        return m

    def apply(self, p: np.ndarray) -> np.ndarray:
        return (self.matrix() @ np.c_[p, np.ones(len(p))].T).T[:, :3]


def _wall_samples(roomplan: dict, step: float = 0.05) -> np.ndarray:
    """2D (x, z) samples along every RoomPlan wall in RoomPlan world coordinates."""
    out = []
    for w in roomplan["walls"]:
        m = _matrix(w)
        half = w["dimensions"][0] / 2
        axis, c = m[:3, 0], m[:3, 3]
        for s in np.arange(-half, half + 1e-9, step):
            p = c + axis * s
            out.append((p[0], p[2]))
    return np.array(out)


def _floor_height(roomplan: dict) -> float:
    f = roomplan["floors"][0]
    m = _matrix(f)
    return float(np.mean([(m @ np.array([*c, 1.0]))[1] for c in f["polygonCorners"]]))


def floor_height(points: np.ndarray, bin_size: float = 0.02) -> float:
    """Height of the floor: the lowest thin horizontal layer that is much denser than the space just above it.

    Walls spread points evenly over height, while a floor concentrates them in one or two bins. Isolated
    stray points below the floor are ignored by requiring a minimum count."""
    y = points[:, 1]
    hist, edges = np.histogram(y, bins=np.arange(y.min(), y.max() + 2 * bin_size, bin_size))
    floor_min = max(20, 0.5 * np.median(hist[hist > 0]))
    for i in range(len(hist) - 7):
        layer = hist[i] + hist[i + 1]
        above = hist[i + 2:i + 7].mean() * 2
        if layer >= floor_min and layer >= 3 * max(above, 1):
            j = i if hist[i] >= hist[i + 1] else i + 1
            return float((edges[j] + edges[j + 1]) / 2)
    return float(np.percentile(y, 2))


def align(points: np.ndarray, roomplan_path: str | Path, iters: int = 40) -> Alignment:
    """Fit the fused cloud to the RoomPlan walls. Both sessions are gravity-aligned (y up), so only yaw and a
    translation are unknown: floors are matched by height, then 2D ICP on wall points tries yaws every 15 degrees."""
    from scipy.spatial import cKDTree

    rp = json.loads(Path(roomplan_path).read_text())
    target = _wall_samples(rp)
    tree = cKDTree(target)
    floor_rec = floor_height(points)
    dy = _floor_height(rp) - floor_rec
    # Wall points: 0.8-2.2 m above the floor, where furniture rarely is.
    h = points[:, 1] - floor_rec
    src = points[(h > 0.8) & (h < 2.2)][:, [0, 2]]
    if len(src) > 40000:
        src = src[np.random.default_rng(0).choice(len(src), 40000, replace=False)]

    fits: list[Alignment] = []
    for deg in range(0, 360, 15):
        yaw = math.radians(deg)
        t2 = target.mean(axis=0) - _rot2(yaw) @ src.mean(axis=0)
        for _ in range(iters):
            moved = src @ _rot2(yaw).T + t2
            dist, idx = tree.query(moved, distance_upper_bound=1.0)
            ok = np.isfinite(dist)
            if ok.sum() < 50:
                break
            a, b = src[ok], target[idx[ok]]
            # Closed-form 2D rigid fit (Kabsch).
            ca, cb = a.mean(axis=0), b.mean(axis=0)
            hmat = (a - ca).T @ (b - cb)
            u, _, vt = np.linalg.svd(hmat)
            r = vt.T @ u.T
            if np.linalg.det(r) < 0:
                vt[1] *= -1
                r = vt.T @ u.T
            yaw = math.atan2(r[1, 0], r[0, 0])
            t2 = cb - r @ ca
        moved = src @ _rot2(yaw).T + t2
        dist, _ = tree.query(moved, distance_upper_bound=1.0)
        inl = dist[np.isfinite(dist)]
        if len(inl) < 0.3 * len(src):
            continue
        rms = float(np.sqrt(np.mean(np.minimum(inl, 0.3) ** 2)))
        # 2D rotation in (x, z) by +yaw equals a 3D rotation about +y by -yaw.
        fits.append(Alignment(yaw=-yaw, t=np.array([t2[0], dy, t2[1]]), rms=rms))
    if not fits:
        raise RuntimeError("could not align the recording to the RoomPlan walls")
    # Rectangular rooms fit equally well rotated 180 degrees. Among near-equal fits, prefer the one closest to
    # the identity: both recordings start where the phone was when you tapped Start, facing the same way.
    # Collapse starts that converged to the same orientation, keeping each one's best fit.
    modes: list[Alignment] = []
    for f in sorted(fits, key=lambda f: f.rms):
        if all(abs(math.remainder(f.yaw - m.yaw, 2 * math.pi)) > math.radians(5) for m in modes):
            modes.append(f)
    best = modes[0].rms
    near = [m for m in modes if m.rms <= best + 0.01]
    return min(near, key=lambda m: abs(math.remainder(m.yaw, 2 * math.pi)))


def wall_offsets(points: np.ndarray, roomplan_path: str | Path, min_points: int = 200) -> list[dict]:
    """For each RoomPlan wall, where the LiDAR wall surface sits along the wall's inward normal (meters).

    Positive means the measured surface is inside the RoomPlan wall. Uses the densest 1 cm layer within 40 cm,
    at 0.8-2.2 m above the floor, ignoring 30 cm at each end (corners and door frames)."""
    rp = json.loads(Path(roomplan_path).read_text())
    fl = floor_height(points)
    h = points[:, 1] - fl
    p = points[(h > 0.8) & (h < 2.2)]
    walls = rp["walls"]
    centre = np.mean([_matrix(w)[:3, 3] for w in walls], axis=0)
    out = []
    for w in sorted(walls, key=lambda w: -w["dimensions"][0]):
        m = _matrix(w)
        ax, n, c = m[:3, 0], m[:3, 2], m[:3, 3]
        if (centre - c) @ n < 0:
            n = -n
        length = w["dimensions"][0]
        rel = p - c
        along, off = rel @ ax, rel @ n
        sel = (np.abs(along) < length / 2 - 0.3) & (np.abs(off) < 0.4)
        if sel.sum() < min_points:
            continue
        hist, edges = np.histogram(off[sel], bins=np.arange(-0.4, 0.41, 0.01))
        out.append({"length": round(float(length), 3), "points": int(sel.sum()),
                    "offset": round(float(edges[hist.argmax()] + 0.005), 3)})
    return out


def _rot2(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


# Rerun playback --------------------------------------------------------------------------------------------

def to_rerun(frames: list[RGBDFrame], points: np.ndarray, colors: np.ndarray, out: str | Path,
             roomplan_path: str | Path | None = None, alignment: Alignment | None = None, stride: int = 1) -> None:
    """Writes an .rrd: the fused room, the RoomPlan walls, and the camera moving through it with RGB and depth."""
    import rerun as rr

    rr.init("accesstwin_walkthrough")
    rr.save(str(out))
    rr.log("world", rr.ViewCoordinates.RIGHT_HAND_Y_UP, static=True)
    m = alignment.matrix() if alignment else np.eye(4)
    pts = alignment.apply(points) if alignment else points
    rr.log("world/room", rr.Points3D(pts, colors=colors, radii=0.008), static=True)
    if roomplan_path:
        rp = json.loads(Path(roomplan_path).read_text())
        strips = []
        for w in rp["walls"]:
            wm = _matrix(w)
            half, hgt = w["dimensions"][0] / 2, w["dimensions"][1] / 2
            ax, up, c = wm[:3, 0], wm[:3, 1], wm[:3, 3]
            corners = [c - ax * half - up * hgt, c + ax * half - up * hgt, c + ax * half + up * hgt,
                       c - ax * half + up * hgt, c - ax * half - up * hgt]
            strips.append(np.array(corners))
        rr.log("world/roomplan_walls", rr.LineStrips3D(strips, colors=[[46, 160, 67]], radii=0.01), static=True)
    trail = []
    for f in frames[::stride]:
        rr.set_time("time", duration=f.timestamp - frames[0].timestamp)
        pose = m @ f.pose
        trail.append(pose[:3, 3])
        fx, fy, cx, cy = f.intrinsics
        rr.log("world/camera", rr.Transform3D(translation=pose[:3, 3], mat3x3=pose[:3, :3]))
        rr.log("world/camera/image", rr.Pinhole(focal_length=[fx, fy], principal_point=[cx, cy],
                                                resolution=list(f.image_size), camera_xyz=rr.ViewCoordinates.RUB,
                                                image_plane_distance=0.4))
        rr.log("world/camera/image/rgb", rr.EncodedImage(path=f.color))
        rr.log("depth", rr.DepthImage(f.depth(), meter=1.0, colormap="turbo"))
        rr.log("world/trajectory", rr.LineStrips3D([np.array(trail)], colors=[[230, 113, 10]], radii=0.015))
