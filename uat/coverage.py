"""Evidence-based traceability. Private catalogues are read at report time, never copied into source.

A story link is a proposed relationship, not proof of a whole requirement. To attest a
reference, declare coverage.brd / coverage.blueprint_uat keyed by its ID, each with
an assertion and cases. Every referenced case and every AC must have passing recorded
evidence. Missing catalogue, duplicate results and missing media remain visible.
"""

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CATALOG = Path(os.environ.get("TLC_CATALOG", Path.home() / "tlc-hr" / "catalog"))
WAVE_OF_DOMAIN = {"WF": "W1", "PAY": "W2", "FIN": "W3", "TRV": "W3", "CORE": "W4", "ORG": "W4", "TAL": "W4", "OB": "W4", "EXIT": "W4", "AST": "W5", "DEV": "W5", "BEN": "W5", "CMP": "W5", "SVC": "W6", "SUR": "W6", "ANL": "W7–W8", "GOV": "W8"}
DOMAIN_LABEL = {"WF": "Chấm công – nghỉ – tăng ca", "PAY": "Lương", "FIN": "Tạm ứng – chi phí", "TRV": "Công tác", "CORE": "Hồ sơ nhân sự", "ORG": "Tổ chức", "TAL": "Tuyển dụng", "OB": "Hội nhập", "EXIT": "Nghỉ việc", "AST": "Tài sản", "DEV": "Đào tạo – đánh giá", "BEN": "Phúc lợi", "CMP": "Tuân thủ", "SVC": "Dịch vụ nội bộ", "SUR": "Khảo sát", "ANL": "Báo cáo – AI", "GOV": "Quản trị"}
OUTSIDE = {"HR-NFR-08": "Cần bằng chứng tích hợp thực tế; mô phỏng không chứng minh tích hợp.", "HR-NFR-09": "Cần đối soát nguồn di chuyển đã ký.", "HR-NFR-03": "Cần bằng chứng SSO và MFA ở hạ tầng.", "HR-NFR-07": "Cần bằng chứng sao lưu, khôi phục và SLO vận hành."}
PASSED, PARTIAL = "Đạt UAT", "Có story – chưa đạt"


def load_stories():
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((HERE / "stories").glob("*.yaml"))]


def load_roles():
    return yaml.safe_load((HERE / "roles.yaml").read_text(encoding="utf-8"))["roles"]


def read_csv(name):
    path = CATALOG / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def local_media(root, name):
    """Reject paths escaping the run directory, including symlinks."""
    if not name or not isinstance(name, str):
        return None
    root = Path(root).resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.is_file() else None


def video_media(root, name):
    source = local_media(root, name)
    if name:
        mp4 = local_media(root, str(Path(name).with_suffix(".mp4")))
        if mp4:
            return mp4
    return source


def case_issues(row, root=None, videos=None):
    issues = []
    if row.get("status") != "Đạt":
        issues.append("không đạt" if row.get("status") else "chưa có kết quả")
    for key in ("steps", "expected", "actual", "run_at", "account", "shot", "video"):
        if not row.get(key):
            issues.append("thiếu " + key)
    stamp = str(row.get("time", ""))
    if not stamp or any(not part.isdigit() for part in stamp.split(":")) or len(stamp.split(":")) not in (2, 3):
        issues.append("thiếu/sai mốc video")
    if videos is not None and row.get("video") not in videos:
        issues.append("video chưa đăng ký")
    if root is not None:
        if not local_media(root, row.get("shot")):
            issues.append("thiếu tệp ảnh")
        if not video_media(root, row.get("video")):
            issues.append("thiếu tệp video")
    return issues


def story_status(story, status_of_case):
    cases = story.get("cases") or []
    ac = story.get("ac") or []
    complete_ac = bool(ac) and all(a.get("cases") and set(a["cases"]) <= set(cases) for a in ac)
    return PASSED if cases and complete_ac and all(status_of_case.get(c) == "Đạt" for c in cases) else PARTIAL


def compute(results, modules=None, evidence_root=None, videos=None):
    modules = load_stories() if modules is None else modules
    stories = [s for m in modules for s in m.get("stories", [])]
    errors = []
    counts = Counter(r["id"] for r in results)
    duplicate_cases = {key for key, count in counts.items() if count > 1}
    errors.extend("Résultat dupliqué: " + key for key in sorted(duplicate_cases))
    duplicate_stories = [key for key, count in Counter(s["id"] for s in stories).items() if count > 1]
    errors.extend("Story trùng: " + key for key in duplicate_stories)
    video_files = {v["file"] for v in videos} if videos is not None else None
    evidence = {r["id"]: case_issues(r, evidence_root, video_files) for r in results}
    for cid in duplicate_cases:
        evidence[cid].append("kết quả trùng mã; không chọn kết quả thuận lợi")
    statuses = {cid: "Đạt" for cid, issues in evidence.items() if not issues}
    state_of_story = {s["id"]: story_status(s, statuses) for s in stories}
    catalogs = {"brd": read_csv("brd_322_traceability.csv"), "blueprint_uat": read_csv("uat_scenarios.csv")}
    expected = {"brd": 322, "blueprint_uat": 42}
    for kind, rows in catalogs.items():
        if len(rows) != expected[kind]:
            errors.append(f"Catalogue {kind}: {len(rows)}/{expected[kind]} dòng")
        ids = [r["requirement_id" if kind == "brd" else "test_id"] for r in rows]
        if len(set(ids)) != len(ids):
            errors.append("Catalogue trùng ID: " + kind)
    indexes = {"brd": {}, "blueprint_uat": {}}
    for s in stories:
        declared = set(s.get("cases") or [])
        for ac in s.get("ac") or []:
            if not ac.get("cases") or not set(ac["cases"]) <= declared:
                errors.append(s["id"] + ": AC chưa ánh xạ đầy đủ case")
        for kind, index in indexes.items():
            linked = s.get(kind) or []
            claims = (s.get("coverage") or {}).get(kind) or {}
            known = {r["requirement_id" if kind == "brd" else "test_id"] for r in catalogs[kind]}
            for ref in set(linked) | set(claims):
                if catalogs[kind] and ref not in known:
                    errors.append(s["id"] + ": tham chiếu không có trong catalogue " + ref)
                claim = claims.get(ref) or {}
                cases = claim.get("cases") or []
                attested = bool(claim.get("assertion", "").strip()) and bool(cases) and set(cases) <= declared
                passed = attested and state_of_story[s["id"]] == PASSED and all(statuses.get(c) == "Đạt" for c in cases)
                index.setdefault(ref, []).append({"story": s["id"], "status": PASSED if passed else PARTIAL,
                                                   "cases": cases, "assertion": claim.get("assertion", ""),
                                                   "reason": "" if passed else "Chưa có xác nhận hành vi đầy đủ và bằng chứng cho từng AC/case"})
    def rows_for(kind):
        rows = []
        for source in catalogs[kind]:
            rid = source["requirement_id" if kind == "brd" else "test_id"]
            links = indexes[kind].get(rid, [])
            # All declared obligations must pass. One happy-path story cannot hide a failing linked story.
            status = PASSED if links and all(link["status"] == PASSED for link in links) else PARTIAL if links else "Chưa có story"
            row = {"id": rid, "domain": source["domain"], "status": status, "stories": [link["story"] for link in links],
                   "evidence": links, "note": OUTSIDE.get(rid, "")}
            if kind == "brd":
                row.update(priority=source["original_priority"], text=source["source_text_verbatim"])
            else:
                row.update(scenario=source["scenario"], assertion=source["acceptance_assertion"], requirements=source["requirement_links"].split(","))
            rows.append(row)
        return rows
    brd_rows, uat_rows = rows_for("brd"), rows_for("blueprint_uat")
    domains = []
    for domain in sorted(set(DOMAIN_LABEL) | {r["domain"] for r in brd_rows}):
        rows = [r for r in brd_rows if r["domain"] == domain]
        domains.append({"domain": domain, "label": DOMAIN_LABEL.get(domain, domain), "wave": WAVE_OF_DOMAIN.get(domain, ""),
                        "total": len(rows), "p0": sum(r["priority"] == "P0" for r in rows), "passed": sum(r["status"] == PASSED for r in rows),
                        "partial": sum(r["status"] == PARTIAL for r in rows), "outside": 0})
    return {"brd": brd_rows, "uat": uat_rows, "domains": domains, "stories": state_of_story,
            "has_catalog": bool(brd_rows) and bool(uat_rows), "catalog_complete": all(len(catalogs[k]) == n for k, n in expected.items()),
            "errors": sorted(set(errors)), "case_issues": evidence,
            "missing_cases": sorted({c for s in stories for c in s.get("cases", [])} - set(counts)),
            "evidence_files_checked": evidence_root is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--require-complete", action="store_true", help="Fail unless all 322 BRD and 42 blueprint assertions have evidence")
    args = parser.parse_args()
    data = json.loads((args.run_dir / "results.json").read_text(encoding="utf-8"))
    cov = compute(data["results"], evidence_root=args.run_dir, videos=data.get("videos", []))
    summary = {"catalog_complete": cov["catalog_complete"], "brd": {"passed": sum(r["status"] == PASSED for r in cov["brd"]), "total": len(cov["brd"])},
               "blueprint": {"passed": sum(r["status"] == PASSED for r in cov["uat"]), "total": len(cov["uat"])},
               "errors": cov["errors"], "missing_cases": cov["missing_cases"],
               "evidence_issues": {k: v for k, v in cov["case_issues"].items() if v}}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failed = not cov["catalog_complete"] or bool(cov["errors"] or cov["missing_cases"] or summary["evidence_issues"])
    if args.require_complete:
        failed |= any(r["status"] != PASSED for r in cov["brd"] + cov["uat"])
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
