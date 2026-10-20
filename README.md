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

## Interface per role (standard Frappe)

| Role | Lands on | Works with |
|---|---|---|
| Office employee, factory worker | `/hrms` (Frappe HR app, phone friendly) | leave requests, balance, payslips, attendance |
| Line / factory manager | desk, workspace TLC Quản lý | requests to approve, team calendar, people in scope |
| HR (lead, officer) | desk, workspace TLC Nhân sự | HR level approvals, company numbers, leave balance report, VN payroll settings |
| Director | desk, workspace TLC Điều hành | company numbers and charts, approvals of direct reports |

## UAT end to end

    uat/run_uat.sh --reset     # Playwright in a container: 7 accounts, 11 recorded sessions on /hrms and the desk

Evidence (videos, screenshots, Excel UAT sheet) for the tailnet: http://100.77.166.27:30081 (deploy/k8s/evidence.yaml).
Notification e-mails of the demo land in Mailpit: http://100.77.166.27:30082 (deploy/k8s/mailpit.yaml).
Realtime: nginx sends the site name as Host on /socket.io (deploy/k8s/nginx-template.conf) and the websocket pod resolves the
site name to the frontend service (hostAliases, pinned ClusterIP in deploy/k8s/frappe.yaml).
Accounts: an (office), binh (factory 1, phone), f2w01 (factory 2, phone), hung (head of factory 1), hoa (HR lead), lan (HR officer),
thanh (CEO), all @demo.example with the demo password of the Secret tlc-hr.
