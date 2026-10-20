#!/bin/sh
# Run one Job of deploy/jobs with the image set in deploy/k8s/kustomization.yaml and wait for it.
# Usage: scripts/job.sh configure|create-site|migrate|seed
set -eu
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
cd "$(dirname "$0")/.."
TAG=$(awk '/newTag:/{print $2}' deploy/k8s/kustomization.yaml)
NAME=$(sed "s|image: IMAGE|image: docker.io/library/tlc-hr:$TAG|" "deploy/jobs/$1.yaml" | kubectl create -f - -o name)
echo "$NAME"
kubectl -n tlc-hr wait --for=condition=complete --timeout=1800s "$NAME" || { kubectl -n tlc-hr logs "$NAME" --tail=60; exit 1; }
kubectl -n tlc-hr logs "$NAME" --tail=15
