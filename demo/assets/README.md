# Demo video assets (frozen copies; `out/` is regenerated on every run)

| Folder | What | Made from |
|---|---|---|
| `01_scan_venue/` | RoomPlan scan of the venue (USDZ + JSON), plan as scanned, empty-shell plan | RoomScan app, Oct 9 2026 |
| `02_rgbd_venue/` | Fused LiDAR point cloud (`fused.ply`, 2.0M points, 2 cm voxels), Rerun walkthrough (`walkthrough.rrd`), overhead overlay on the RoomPlan outline, alignment | RoomScan RGB-D recording, 1,092 frames / 109 s |

View the walkthrough: `uv run rerun demo/assets/02_rgbd_venue/walkthrough.rrd`
