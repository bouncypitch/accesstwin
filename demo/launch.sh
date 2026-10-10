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
  "file://$SITE/media/twin_design_a.html" \
  "https://marble.worldlabs.ai/world/b27aa033-6df7-4464-9ca1-1122f1719a1c" \
  "file://$SITE/media/twin_design_b.html" \
  "file://$SITE/index.html#ch10" \
  "file://$SITE/index.html"

# A terminal in the project with the two live commands ready to paste.
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$ROOT'; clear; printf '\\\\n  AccessTwin live demo\\\\n\\\\n  1) Audit Design A:   uv run accesstwin audit specs/design_a.json\\\\n  2) Fix -> Design B:  uv run python scripts/make_design_b.py\\\\n\\\\n  Backup video: ~/Downloads/AccessTwin_demo.mp4\\\\n\\\\n'"
  set font size of selected tab of front window to 20
end tell
EOF
echo "Demo ready: Chrome tabs = scan · Design A · photoreal finding · Design B · before/after · site"
