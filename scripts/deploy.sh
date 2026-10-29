#!/bin/sh
# Roll the manifests out and leave the desk able to load its own assets.
#
# A new image changes every bundle hash, but Frappe caches the asset manifest in Redis: the page then references a
# stylesheet that no longer exists, nginx answers 404 with HTML, and the whole desk renders bare. That cost two UAT
# runs, so the flush and a smoke check are part of the deploy rather than something to remember.
set -eu
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
cd "$(dirname "$0")/.."

kubectl apply -k deploy/k8s >/dev/null
for d in backend worker scheduler frontend websocket; do
  printf "%-10s " "$d"
  kubectl -n tlc-hr rollout status "deploy/$d" --timeout=600s | tail -1
done

smoke() {
  url=$(curl -s -H "Host: tlc-hr.local" http://127.0.0.1:30080/login \
        | grep -oE '/assets/frappe/dist/css/website\.bundle\.[A-Z0-9]*\.css' | head -1)
  [ -n "$url" ] || { echo "smoke: login page lists no website bundle"; return 1; }
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: tlc-hr.local" "http://127.0.0.1:30080$url")
  echo "smoke: $url -> $code"
  [ "$code" = "200" ]
}

redis=$(kubectl -n tlc-hr get pod -l app=redis-cache --field-selector=status.phase=Running \
        -o jsonpath='{.items[0].metadata.name}')
kubectl -n tlc-hr exec "$redis" -- redis-cli FLUSHALL >/dev/null

if ! smoke; then
  echo "asset manifest stale after the rollout: restarting the processes that render it"
  kubectl -n tlc-hr rollout restart deploy/backend deploy/frontend >/dev/null
  kubectl -n tlc-hr rollout status deploy/backend --timeout=600s | tail -1
  kubectl -n tlc-hr rollout status deploy/frontend --timeout=600s | tail -1
  smoke
fi

echo "public:$(curl -s -o /dev/null -w '%{http_code}' https://hr.royalai.dev/login)"
