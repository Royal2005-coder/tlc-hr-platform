#!/bin/sh
# Run one Job of deploy/jobs with the image set in deploy/k8s/kustomization.yaml, wait until it succeeds or fails, show its log.
# Usage: scripts/job.sh configure|create-site|migrate|seed|test
set -eu
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
cd "$(dirname "$0")/.."
TAG=$(awk '/newTag:/{print $2}' deploy/k8s/kustomization.yaml)
NAME=$(sed "s|\"IMAGE\"|\"docker.io/library/tlc-hr:$TAG\"|" "deploy/jobs/$1.yaml" | kubectl create -f - -o name)
echo "$NAME"
while :; do
  STATE=$(kubectl -n tlc-hr get "$NAME" -o jsonpath='{.status.succeeded}/{.status.failed}')
  case "$STATE" in
    1/*) kubectl -n tlc-hr logs "$NAME" --tail="${TAIL:-20}"; exit 0 ;;
    */[1-9]*) kubectl -n tlc-hr logs "$NAME" --tail=80; echo "FAILED: $NAME"; exit 1 ;;
  esac
  sleep 5
done
