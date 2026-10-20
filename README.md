# tlc-hr-platform

Build and k3s deployment of the TLC HRM MVP on Frappe HR v16 (apps: erpnext, hrms, erpnextvn, tlc_hr).

Everything runs on the k3s node (ai1); no registry: the image is built there and imported into the k3s containerd.

    scripts/build.sh              # build the image from apps.json, import it, pin the tag in deploy/k8s/kustomization.yaml
    scripts/secret.sh             # once: Secret tlc-hr with random DB root, Administrator and demo passwords
    kubectl apply -f deploy/k8s/namespace.yaml -f deploy/k8s/data.yaml
    scripts/job.sh configure      # after every new image
    scripts/job.sh create-site    # once
    scripts/job.sh migrate        # after every new image
    kubectl apply -k deploy/k8s
    scripts/job.sh seed           # TLC demo company and people (idempotent)
    scripts/job.sh test           # tests of tlc_hr inside the site

Access over Tailscale: http://100.77.166.27:30080 (site tlc-hr.local, TLC home at /tlc).
Passwords: kubectl -n tlc-hr get secret tlc-hr -o jsonpath={.data.admin-password} | base64 -d

## UAT end to end

    uat/run_uat.sh --reset     # Playwright in a container: 7 accounts, 11 recorded sessions, 47 test cases with real assertions

Evidence (videos, screenshots, Excel UAT sheet) for the tailnet: http://100.77.166.27:30081 (deploy/k8s/evidence.yaml).
Accounts: an (office), binh (factory 1, phone), f2w01 (factory 2, phone), hung (head of factory 1), hoa (HR lead), lan (HR officer),
thanh (CEO), all @demo.example with the demo password of the Secret tlc-hr.
