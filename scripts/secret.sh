#!/bin/sh
# Create the Secret tlc-hr once with random passwords. Nothing is printed; read them with kubectl when needed.
set -eu
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
kubectl -n tlc-hr get secret tlc-hr >/dev/null 2>&1 && { echo "secret exists"; exit 0; }
kubectl -n tlc-hr create secret generic tlc-hr \
  --from-literal=db-root-password="$(openssl rand -hex 20)" --from-literal=admin-password="$(openssl rand -hex 12)" --from-literal=demo-password="$(openssl rand -hex 8)" >/dev/null
echo "secret created"
