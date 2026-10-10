"""Generate a World Labs Marble world from images and download its assets.

    uv run python scripts/worldlabs.py out/05_world/a --name "Design A robotics lab" --prompt "..." \
        --images 0:view_000.png 90:view_090.png 180:view_180.png 270:view_270.png
    uv run python scripts/worldlabs.py out/05_world/venue --name "Venue (empty)" --pano pano.jpg --prompt "..."

Reads WORLDLABS_API_KEY from .env. Writes <dir>/world.json and downloads pano, thumbnail and 500k splat.
Marble worlds are visualization only: every accessibility check runs on the metric SpaceSpec.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.worldlabs.ai/marble/v1"


def key() -> str:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("WORLDLABS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("WORLDLABS_API_KEY missing from .env")


def call(method: str, path: str, body: dict | None = None, tries: int = 6) -> dict:
    for attempt in range(tries):
        req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"WLT-Api-Key": key(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or attempt == tries - 1:
                raise
            time.sleep(10 * 2 ** attempt)  # rate limited: back off


def upload(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower()
    prep = call("POST", "/media-assets:prepare_upload", {"file_name": path.name, "kind": "image", "extension": ext})
    info = prep["upload_info"]
    req = urllib.request.Request(info["upload_url"], method=info.get("upload_method", "PUT"), data=path.read_bytes(),
                                 headers=info.get("required_headers") or {})
    urllib.request.urlopen(req, timeout=300).read()
    return prep["media_asset"].get("media_asset_id") or prep["media_asset"]["id"]


def download(url: str | None, dest: Path) -> None:
    if url:
        urllib.request.urlretrieve(url, dest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--name", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--images", nargs="*", default=[], help="azimuth:file pairs")
    ap.add_argument("--pano", help="equirectangular panorama file")
    ap.add_argument("--model", default="marble-1.1")
    args = ap.parse_args()
    d = Path(args.dir)

    if args.pano:
        prompt = {"type": "image", "image_prompt": {"source": "media_asset", "media_asset_id": upload(d / args.pano)},
                  "is_pano": True}
    else:
        items = []
        for pair in args.images:
            az, f = pair.split(":", 1)
            items.append({"azimuth": float(az), "content": {"source": "media_asset", "media_asset_id": upload(d / f)}})
        prompt = {"type": "multi-image", "multi_image_prompt": items}
    if args.prompt:
        prompt["text_prompt"] = args.prompt
    op = call("POST", "/worlds:generate", {"display_name": args.name, "model": args.model, "world_prompt": prompt})
    print("operation", op.get("operation_id"), flush=True)
    while not op.get("done"):
        time.sleep(15)
        op = call("GET", f"/operations/{op['operation_id']}")
        print(".", end="", flush=True)
    if op.get("error"):
        raise SystemExit(f"\nfailed: {op['error']}")
    wid = (op.get("response") or {}).get("id") or (op.get("response") or {}).get("world_id") or op["metadata"]["world_id"]
    world = call("GET", f"/worlds/{wid}")
    world = world.get("world", world)
    (d / "world.json").write_text(json.dumps(world, indent=1))
    a = world.get("assets", {})
    download((a.get("imagery") or {}).get("pano_url"), d / "marble_pano.jpg")
    download(a.get("thumbnail_url") or world.get("thumbnail_url"), d / "marble_thumb.jpg")
    download(((a.get("splats") or {}).get("spz_urls") or {}).get("500k"), d / "marble_500k.spz")
    print(f"\nworld {wid}: {world.get('world_marble_url')}")


if __name__ == "__main__":
    main()
