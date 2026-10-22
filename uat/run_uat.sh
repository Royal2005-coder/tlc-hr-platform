#!/bin/sh
# Run the end-to-end UAT of TLC HRM in the Playwright container against the site on this node, then refresh the evidence index.
# Usage: ~/tlc-hr/uat/run_uat.sh [--reset]   --reset deletes every demo leave and overtime request first (expected numbers assume a clean demo)
# Debug knobs: ONLY=<module> runs one module (resets first), SLOW_MO=<ms> paces the clicks, QUICK=1 skips the MP4 and offline pack of a throwaway run.
set -eu
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
HERE=$(cd "$(dirname "$0")" && pwd)
# One run at a time: the journeys share the demo data of one site, so a second run would reset under the first.
exec 9>/tmp/tlc-uat.lock
flock 9
# A single module is only meaningful on clean demo data (the expected numbers assume it), so an ONLY= run resets too.
if [ "${1:-}" = "--reset" ] || [ -n "${ONLY:-}" ]; then
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-leave 2>/dev/null | tail -1
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-payroll 2>/dev/null | tail -1
  # closed periods first: a locked month refuses the demo overtime and corrections the next resets write
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-periods 2>/dev/null | tail -1
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-overtime 2>/dev/null | tail -1
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-travel 2>/dev/null | tail -1
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-recruitment 2>/dev/null | tail -1
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-lifecycle 2>/dev/null | tail -1
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local tlc seed reset-services 2>/dev/null | tail -1
fi
DEMO_PASSWORD=$(kubectl -n tlc-hr get secret tlc-hr -o jsonpath='{.data.demo-password}' | base64 -d)
# A locally baked image with playwright/openpyxl avoids a PyPI stall on every run; fall back to the upstream image.
UAT_IMAGE=${TLC_UAT_IMAGE:-tlc-uat:1.49}
docker image inspect "$UAT_IMAGE" >/dev/null 2>&1 || UAT_IMAGE=mcr.microsoft.com/playwright/python:v1.49.0-noble
if [ -z "${RUN_ID:-}" ]; then
  RUN_ID=$(date +%Y%m%d-%H%M)
  if [ -d "$HERE/out/$RUN_ID" ]; then
    RUN_ID=$(date +%Y%m%d-%H%M%S)
  fi
fi
IMAGE_TAG=$(awk '/newTag:/{print $2}' "$HERE/../deploy/k8s/kustomization.yaml")
mkdir -p "$HERE/out"
mkdir -p /tmp/tlc-pip-cache
# The password goes to the container in a 0600 file, never in argv: `ps` on this host used to print it.
ENVF=$(mktemp)
chmod 600 "$ENVF"
printf 'DEMO_PASSWORD=%s\n' "$DEMO_PASSWORD" > "$ENVF"
trap 'rm -f "$ENVF"' EXIT
docker run --rm --network host --ipc=host --env-file "$ENVF" -e RUN_ID="$RUN_ID" -e IMAGE_TAG="$IMAGE_TAG" -e ONLY="${ONLY:-}" \
  -e SLOW_MO="${SLOW_MO:-250}" -e TZ=Asia/Ho_Chi_Minh \
  -v "$HERE:/uat" -v /tmp/tlc-pip-cache:/root/.cache/pip -w /uat "$UAT_IMAGE" \
  sh -c "pip install -q --root-user-action=ignore playwright==1.49.0 openpyxl==3.1.5 2>/dev/null; python run_uat.py; RC=\$?; rm -rf /uat/out/$RUN_ID/videos/raw; chown -R $(id -u):$(id -g) /uat/out/$RUN_ID; exit \$RC" || STATUS=$?
if [ -z "${QUICK:-}" ]; then
  # Playwright WebM has no index (players cannot seek): an H.264 MP4 copy of each video, small and seekable.
  docker run --rm --user "$(id -u):$(id -g)" -v "$HERE/out/$RUN_ID/videos:/v" --entrypoint sh jrottenberg/ffmpeg:6.1-ubuntu -c \
    'for f in /v/*.webm; do ffmpeg -loglevel error -y -i "$f" -c:v libx264 -preset veryfast -crf 30 -pix_fmt yuv420p \
     -movflags +faststart -an "${f%.webm}.mp4"; done' || true
  # The same run packed into one HTML file (cases, screenshots, videos, Excel) to send and open offline.
  python3 "$HERE/offline_html.py" "$HERE/out/$RUN_ID" || true
fi
# Index of every run, newest first.
{
  echo '<!doctype html><html lang="vi"><meta charset="utf-8"><title>UAT TLC HRM</title><body style="font:16px system-ui;max-width:800px;margin:32px auto">'
  echo '<h1>Bằng chứng UAT TLC HRM</h1><ul>'
  for d in $(ls -1r "$HERE/out" | grep -E '^[0-9]{8}-[0-9]{4}([0-9]{2})?$'); do
    SUMMARY=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); r=d['results']; print(sum(x['status']=='Đạt' for x in r), '/', len(r), 'đạt')" "$HERE/out/$d/results.json" 2>/dev/null || echo "chưa xong")
    echo "<li><a href=\"$d/index.html\">$d</a> - $SUMMARY</li>"
  done
  echo '</ul></body></html>'
} > "$HERE/out/index.html"
echo "evidence: http://100.77.166.27:30081/$RUN_ID/index.html"
exit "${STATUS:-0}"
