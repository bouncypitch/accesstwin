"""One World Labs Marble world per photoreal finding frame, generated in parallel; links each into tour.json.

    uv run python scripts/stop_worlds.py out/04_tour/explainer

Each world's origin is the hero camera that rendered its frame, so the director can overlay agents and markers in
plan coordinates. Costs ~1,500 World Labs credits per world.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import worldlabs as wl  # noqa: E402

tour_dir = Path(sys.argv[1])
hero = tour_dir / "hero"
tour = json.loads((tour_dir / "tour.json").read_text())
stops = [s for s in tour["segments"] if s.get("hero")]
PROMPT = ("Photorealistic interior of a modern university robotics research lab: cream walls, white ceiling with "
          "recessed downlights, sealed grey concrete floor with yellow and black safety tape, workbenches, robot arms. "
          "Sharp, clean, evenly lit. No people.")


def generate(seg: dict) -> tuple[int, dict | None]:
    i = seg["hero"]["index"]
    photo = hero / f"stop_{i:02d}_photo.jpg"
    if not photo.exists():
        return i, None
    spz = hero / f"stop_{i:02d}_world.spz"
    meta = hero / f"stop_{i:02d}_world.json"
    if spz.exists() and meta.exists():
        return i, json.loads(meta.read_text())
    prompt = {"type": "image", "image_prompt": {"source": "media_asset", "media_asset_id": wl.upload(photo)},
              "is_pano": False, "text_prompt": PROMPT}
    op = wl.call("POST", "/worlds:generate", {"display_name": f"AccessTwin finding {i}", "model": "marble-1.1",
                                             "world_prompt": prompt})
    while not op.get("done"):
        time.sleep(15)
        op = wl.call("GET", f"/operations/{op['operation_id']}")
    if op.get("error"):
        print(f"stop {i}: failed {op['error']}", flush=True)
        return i, None
    wid = (op.get("response") or {}).get("id") or op["metadata"]["world_id"]
    world = wl.call("GET", f"/worlds/{wid}")
    world = world.get("world", world)
    sp = world["assets"]["splats"]
    wl.download(sp["spz_urls"]["500k"], spz)
    info = {"url": f"hero/{spz.name}", "scale": sp["semantics_metadata"]["metric_scale_factor"],
            "ground": sp["semantics_metadata"]["ground_plane_offset"], "marble_url": world.get("world_marble_url"),
            "world_id": wid}
    meta.write_text(json.dumps(info, indent=1))
    print(f"stop {i}: {info['marble_url']}", flush=True)
    return i, info


with ThreadPoolExecutor(2) as ex:
    results = dict(ex.map(generate, stops))
for s in stops:
    if results.get(s["hero"]["index"]):
        s["world"] = results[s["hero"]["index"]]
(tour_dir / "tour.json").write_text(json.dumps(tour, indent=1))
print(f"{sum(1 for v in results.values() if v)} of {len(stops)} stops have photoreal worlds")
