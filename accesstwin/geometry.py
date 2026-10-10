"""Free-space analysis: clearance field, widest routes, and exact aisle widths at bottlenecks."""

from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from .spec import Space, Vec2

CELL = 0.025  # grid resolution in meters; exact widths are recomputed analytically at bottlenecks


@dataclass
class Bottleneck:
    width: float  # exact clear width between the two closest obstacles
    location: Vec2
    between: tuple[str, str]


@dataclass
class Route:
    reachable: bool
    path: list[Vec2]
    bottleneck: Bottleneck | None
    length: float


class FreeSpace:
    """Grid clearance field for one space. `clearance[i, j]` is the distance to the nearest obstacle or wall."""

    def __init__(self, space: Space):
        self.space = space
        floor = space.floor()
        self.obstacles: dict[str, Polygon] = {e.id: e.obstacle() for e in space.elements}
        minx, miny, maxx, maxy = floor.bounds
        self.walls = box(minx - 1, miny - 1, maxx + 1, maxy + 1).difference(floor)
        self.blocked = unary_union([self.walls, *self.obstacles.values()])
        self.origin = (minx, miny)
        nx, ny = int(np.ceil((maxx - minx) / CELL)), int(np.ceil((maxy - miny) / CELL))
        xs = minx + (np.arange(nx) + 0.5) * CELL
        ys = miny + (np.arange(ny) + 0.5) * CELL
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        from shapely import contains_xy

        free = ~contains_xy(self.blocked, gx, gy)
        self.free = free
        # Pad with a blocked border so the room's outer walls count as obstacles in the distance transform.
        padded = np.pad(free, 1, constant_values=False)
        self.clearance = (distance_transform_edt(padded)[1:-1, 1:-1] - 0.5).clip(min=0) * CELL
        self.clearance[~free] = 0
        self.shape = free.shape

    def to_cell(self, p: Vec2) -> tuple[int, int]:
        i = int((p[0] - self.origin[0]) / CELL)
        j = int((p[1] - self.origin[1]) / CELL)
        return min(max(i, 0), self.shape[0] - 1), min(max(j, 0), self.shape[1] - 1)

    def to_point(self, c: tuple[int, int]) -> Vec2:
        return (self.origin[0] + (c[0] + 0.5) * CELL, self.origin[1] + (c[1] + 0.5) * CELL)

    def nearest_free(self, p: Vec2) -> tuple[int, int]:
        i, j = self.to_cell(p)
        if self.free[i, j]:
            return i, j
        idx = np.argwhere(self.free)
        k = np.argmin((idx[:, 0] - i) ** 2 + (idx[:, 1] - j) ** 2)
        return int(idx[k, 0]), int(idx[k, 1])

    def widest_tree(self, source: Vec2) -> tuple[np.ndarray, np.ndarray]:
        """Maximin (widest-path) search from `source`: best achievable bottleneck clearance to every cell."""
        best = np.full(self.shape, -1.0)
        parent = np.full(self.shape + (2,), -1, dtype=np.int32)
        s = self.nearest_free(source)
        best[s] = self.clearance[s]
        heap = [(-best[s], s)]
        steps = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
        nx, ny = self.shape
        clear = self.clearance
        while heap:
            negb, (i, j) = heapq.heappop(heap)
            b = -negb
            if b < best[i, j]:
                continue
            for di, dj in steps:
                a, c = i + di, j + dj
                if 0 <= a < nx and 0 <= c < ny and clear[a, c] > 0:
                    nb = min(b, clear[a, c])
                    if nb > best[a, c]:
                        best[a, c] = nb
                        parent[a, c] = (i, j)
                        heapq.heappush(heap, (-nb, (a, c)))
        return best, parent

    def widths_along(self, pts: list[Vec2]) -> list[Bottleneck]:
        """Clear width at each point: distance to the nearest obstacle plus distance to the next-nearest
        different obstacle. For a point anywhere between two parallel faces this is exactly the gap."""
        import shapely

        names = [*self.obstacles, "wall"]
        geoms = [*self.obstacles.values(), self.walls]
        xy = shapely.points(np.asarray(pts))
        d = np.stack([shapely.distance(g, xy) for g in geoms], axis=1)  # (n_pts, n_geoms)
        order = np.argsort(d, axis=1)
        out = []
        for k, p in enumerate(pts):
            a, b = order[k, 0], order[k, 1]
            out.append(Bottleneck(float(d[k, a] + d[k, b]), p, (names[a], names[b])))
        return out


class RoutePlanner:
    """Routes from one origin (e.g. the entrance) for a body that needs `min_width` of clear floor."""

    def __init__(self, fs: FreeSpace, origin: Vec2):
        self.fs = fs
        self.best, self.parent = fs.widest_tree(origin)
        self.origin = origin

    def route(self, target: Vec2, min_width: float, tolerance: float = 0.15) -> Route:
        """Widest route to `target`. A route is reachable if its narrowest point is at least `min_width`.

        `tolerance` lets the end of the route stop short of the target (you approach a bench, not enter it).
        """
        fs = self.fs
        ti, tj = fs.to_cell(target)
        r = int(np.ceil(tolerance / CELL)) + 1
        window = self.best[max(ti - r, 0): ti + r + 1, max(tj - r, 0): tj + r + 1]
        if window.size == 0 or window.max() <= 0:
            return Route(False, [], None, float("inf"))
        k = np.unravel_index(np.argmax(window), window.shape)
        end = (max(ti - r, 0) + k[0], max(tj - r, 0) + k[1])
        cells = []
        c = end
        while c[0] >= 0:
            cells.append(c)
            p = tuple(self.parent[c])
            if p[0] < 0:
                break
            c = p
        cells.reverse()
        path = [fs.to_point(c) for c in cells]
        length = float(sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])))
        # Bottleneck: the narrowest clear width anywhere along the route, measured between obstacles.
        bottleneck = min(fs.widths_along(path[::2] or path), key=lambda b: b.width)
        return Route(bottleneck.width >= min_width - 1e-6, path, bottleneck, length)

    def has_turning_space(self, near: Vec2, diameter: float, within: float) -> Vec2 | None:
        """A reachable spot within `within` meters of `near` where a circle of `diameter` fits."""
        fs = self.fs
        i, j = fs.to_cell(near)
        r = int(np.ceil(within / CELL))
        sl = (slice(max(i - r, 0), i + r + 1), slice(max(j - r, 0), j + r + 1))
        ok = (fs.clearance[sl] >= diameter / 2) & (self.best[sl] > 0)
        if not ok.any():
            return None
        k = np.argwhere(ok)[0]
        return fs.to_point((sl[0].start + int(k[0]), sl[1].start + int(k[1])))
