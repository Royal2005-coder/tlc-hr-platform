#!/bin/sh
# Build the TLC HR image on the k3s node and import it into the k3s containerd (no registry: pods use imagePullPolicy Never).
# Usage: scripts/build.sh  -> prints the image, tag = <tlc_hr main sha>-<date>
set -eu
cd "$(dirname "$0")/.."
DOCKER_DIR=${FRAPPE_DOCKER:-$HOME/tlc-hr/frappe_docker}
TAG=${TAG:-$(git ls-remote https://github.com/Royal2005-coder/tlc_hr refs/heads/main | cut -c1-8)-$(date +%Y%m%d%H%M)}
IMAGE=docker.io/library/tlc-hr:$TAG
DOCKER_BUILDKIT=1 docker build --build-arg=FRAPPE_BRANCH=version-16 --build-arg=CACHE_BUST="$TAG" \
  --secret=id=apps_json,src=apps.json --tag="$IMAGE" --file="$DOCKER_DIR/images/layered/Containerfile" "$DOCKER_DIR"
docker save "$IMAGE" | sudo k3s ctr -n k8s.io images import - >/dev/null
sed -i "s|newTag: .*|newTag: $TAG|" deploy/k8s/kustomization.yaml
echo "$IMAGE"
