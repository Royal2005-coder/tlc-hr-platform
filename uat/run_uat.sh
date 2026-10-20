#!/bin/sh
# Run the end-to-end UAT of TLC HRM in the Playwright container against the site on this node, then refresh the evidence index.
# Usage: ~/tlc-hr/uat/run_uat.sh [--reset]   --reset deletes every demo leave request first (expected numbers assume a clean demo)
set -eu
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
HERE=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" = "--reset" ]; then
  kubectl -n tlc-hr exec deploy/backend -- bench --site tlc-hr.local execute tlc_hr.seed.reset_leave_requests 2>/dev/null | tail -1
fi
DEMO_PASSWORD=$(kubectl -n tlc-hr get secret tlc-hr -o jsonpath='{.data.demo-password}' | base64 -d)
RUN_ID=$(date +%Y%m%d-%H%M)
IMAGE_TAG=$(awk '/newTag:/{print $2}' "$HERE/../deploy/k8s/kustomization.yaml")
mkdir -p "$HERE/out"
docker run --rm --network host --ipc=host -e DEMO_PASSWORD="$DEMO_PASSWORD" -e RUN_ID="$RUN_ID" -e IMAGE_TAG="$IMAGE_TAG" -e TZ=Asia/Ho_Chi_Minh \
  -v "$HERE:/uat" -w /uat mcr.microsoft.com/playwright/python:v1.49.0-noble \
  sh -c "pip install -q --root-user-action=ignore playwright==1.49.0 openpyxl==3.1.5 2>/dev/null; python run_uat.py; RC=\$?; rm -rf /uat/out/$RUN_ID/videos/raw; chown -R $(id -u):$(id -g) /uat/out/$RUN_ID; exit \$RC" || STATUS=$?
# Index of every run, newest first.
{
  echo '<!doctype html><html lang="vi"><meta charset="utf-8"><title>UAT TLC HRM</title><body style="font:16px system-ui;max-width:800px;margin:32px auto">'
  echo '<h1>Bằng chứng UAT TLC HRM</h1><ul>'
  for d in $(ls -1r "$HERE/out" | grep -E '^[0-9]{8}-[0-9]{4}$'); do
    SUMMARY=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); r=d['results']; print(sum(x['status']=='Đạt' for x in r), '/', len(r), 'đạt')" "$HERE/out/$d/results.json" 2>/dev/null || echo "chưa xong")
    echo "<li><a href=\"$d/index.html\">$d</a> - $SUMMARY</li>"
  done
  echo '</ul></body></html>'
} > "$HERE/out/index.html"
echo "evidence: http://100.77.166.27:30081/$RUN_ID/index.html"
exit "${STATUS:-0}"
