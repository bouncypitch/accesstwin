#!/bin/zsh
# Opens everything for the AccessTwin live demo, in presentation order.
#   ~/Code/Stanford-Hackathon/access-twin/demo/launch.sh
set -e
ROOT="${0:A:h:h}"
SITE="$ROOT/demo/site"

# Warm up Python so the live commands start instantly on stage.
(cd "$ROOT" && uv run accesstwin audit specs/design_a.json >/dev/null 2>&1 &)

# One new Chrome window, tabs in demo order (local files work offline).
open -na "Google Chrome" --args --new-window \
  "file://$SITE/scan.html" \
  "file://$SITE/media/twin_design_a.html#build" \
  "file://$SITE/media/twin_design_a.html#agents" \
  "file://$SITE/world.html" \
  "file://$SITE/media/twin_design_a.html#fix" \
  "file://$SITE/index.html#ch11"

# Rerun: the RGB-D walkthrough playback (camera path, color + depth, room building up).
(cd "$ROOT" && uv run rerun demo/assets/02_rgbd_venue/walkthrough.rrd >/dev/null 2>&1 &)

# A terminal in the project with the two live commands ready to paste.
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$ROOT'; clear; printf '\\\\n  AccessTwin live demo\\\\n\\\\n  1) Audit Design A:   uv run accesstwin audit specs/design_a.json\\\\n  2) Fix -> Design B:  uv run python scripts/make_design_b.py\\\\n\\\\n  Backup video: ~/Downloads/AccessTwin_demo.mp4\\\\n\\\\n'"
  set font size of selected tab of front window to 20
end tell
EOF
echo "Demo ready. Rerun: RGB-D walkthrough. Chrome tabs: scan · build · agents · photoreal finding · fixes · results"
