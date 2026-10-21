"""Coverage of the TLC blueprint by the UAT: every BRD requirement and blueprint UAT scenario gets a status.

Inputs: stories/*.yaml (story -> brd, blueprint_uat, cases), results.json of a run (case -> Đạt / Không đạt) and the blueprint
catalogue (brd_322_traceability.csv, uat_scenarios.csv) from TLC_CATALOG (default ~/tlc-hr/catalog). The catalogue is TLC
internal and stays out of this public repository; without it only the story side is reported.
"""

import csv
import os
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CATALOG = Path(os.environ.get("TLC_CATALOG", Path.home() / "tlc-hr" / "catalog"))
# Delivery wave of each blueprint domain (plan quiet-snuggling-glacier).
WAVE_OF_DOMAIN = {"WF": "W1 Kỳ công", "PAY": "W2 Lương", "FIN": "W3 Tạm ứng – chi phí", "TRV": "W3 Công tác", "CORE": "W4 Hồ sơ",
                  "ORG": "W4 Tổ chức", "TAL": "W4 Tuyển dụng", "OB": "W4 Hội nhập", "EXIT": "W4 Nghỉ việc", "AST": "W5 Tài sản",
                  "DEV": "W5 Đào tạo – đánh giá", "BEN": "W5 Phúc lợi", "CMP": "W5 Tuân thủ", "SVC": "W6 Dịch vụ nội bộ",
                  "SUR": "W6 Khảo sát", "ANL": "W7–W8 AI và báo cáo", "GOV": "W8 Quản trị"}
DOMAIN_LABEL = {"WF": "Chấm công – nghỉ – tăng ca", "PAY": "Lương", "FIN": "Tạm ứng – chi phí", "TRV": "Công tác", "CORE": "Hồ sơ nhân sự",
                "ORG": "Tổ chức", "TAL": "Tuyển dụng", "OB": "Hội nhập", "EXIT": "Nghỉ việc", "AST": "Tài sản", "DEV": "Đào tạo – đánh giá",
                "BEN": "Phúc lợi", "CMP": "Tuân thủ", "SVC": "Dịch vụ nội bộ", "SUR": "Khảo sát", "ANL": "Báo cáo – AI", "GOV": "Quản trị"}
# Requirements met outside Frappe: shown with the way TLC handles them instead of a UAT result.
OUTSIDE = {"HR-NFR-08": "Tích hợp máy chấm công, Microsoft 365, ngân hàng, Outlook: ngoài Frappe – xuất/nhập file, giả lập trong UAT",
           "HR-NFR-09": "Chuyển dữ liệu Bitrix24/Excel: công cụ Data Import của Frappe, làm khi go-live",
           "HR-NFR-03": "SSO Microsoft 365 + 2 lớp: cấu hình OIDC (Keycloak/Entra) ở hạ tầng",
           "HR-NFR-07": "Sẵn sàng 99,5%, sao lưu: vận hành hạ tầng k3s"}
PASSED, PARTIAL = "Đạt UAT", "Có story – chưa đạt"


def load_stories():
    modules = []
    for path in sorted((HERE / "stories").glob("*.yaml")):
        modules.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    return modules


def load_roles():
    return yaml.safe_load((HERE / "roles.yaml").read_text(encoding="utf-8"))["roles"]


def read_csv(name):
    path = CATALOG / name
    return list(csv.DictReader(path.open(encoding="utf-8-sig"))) if path.exists() else []


def story_status(story, status_of_case):
    states = [status_of_case.get(c) for c in story.get("cases", [])]
    if states and all(s == "Đạt" for s in states):
        return PASSED
    return PARTIAL


def compute(results, modules=None):
    modules = modules or load_stories()
    status_of_case = {r["id"]: r["status"] for r in results}
    stories = [s for m in modules for s in m["stories"]]
    by_brd, by_uat = {}, {}
    for s in stories:
        state = story_status(s, status_of_case)
        for key, index in (("brd", by_brd), ("blueprint_uat", by_uat)):
            for ref in s.get(key) or []:
                index.setdefault(ref, []).append((s["id"], state))

    def verdict(links):
        return PASSED if any(st == PASSED for _, st in links) else PARTIAL

    brd_rows = []
    for row in read_csv("brd_322_traceability.csv"):
        rid, links = row["requirement_id"], by_brd.get(row["requirement_id"], [])
        if links:
            status = verdict(links)
        elif rid in OUTSIDE:
            status = "Ngoài Frappe"
        else:
            status = "Kế hoạch " + WAVE_OF_DOMAIN.get(row["domain"], "")
        brd_rows.append({"id": rid, "priority": row["original_priority"], "domain": row["domain"], "text": row["source_text_verbatim"],
                         "status": status, "stories": [s for s, _ in links], "note": OUTSIDE.get(rid, "")})
    uat_rows = []
    for row in read_csv("uat_scenarios.csv"):
        links = by_uat.get(row["test_id"], [])
        uat_rows.append({"id": row["test_id"], "scenario": row["scenario"], "domain": row["domain"],
                         "assertion": row["acceptance_assertion"],
                         "status": verdict(links) if links else "Kế hoạch " + WAVE_OF_DOMAIN.get(row["domain"], ""),
                         "stories": [s for s, _ in links]})
    domains = {}
    for r in brd_rows:
        d = domains.setdefault(r["domain"], {"domain": r["domain"], "label": DOMAIN_LABEL.get(r["domain"], r["domain"]),
                                             "wave": WAVE_OF_DOMAIN.get(r["domain"], ""), "total": 0, "passed": 0, "partial": 0,
                                             "outside": 0, "p0": 0})
        d["total"] += 1
        d["p0"] += r["priority"] == "P0"
        d["passed"] += r["status"] == PASSED
        d["partial"] += r["status"] == PARTIAL
        d["outside"] += r["status"] == "Ngoài Frappe"
    return {"brd": brd_rows, "uat": uat_rows, "domains": sorted(domains.values(), key=lambda d: d["wave"]),
            "stories": {s["id"]: story_status(s, status_of_case) for s in stories}, "has_catalog": bool(brd_rows)}
