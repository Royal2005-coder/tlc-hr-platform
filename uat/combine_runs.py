"""Assemble the deliverable evidence pack from the best run of each module.

Every case row keeps the run it really came from, the pack records the per-module source, and the deck prints that
source next to each module, so a pack built from several runs never reads as one run. Reads existing runs, writes only
out/<PACK_ID>/ (files are hardlinked when the filesystem allows it), and never edits a finished run.

Usage: DEMO_PASSWORD=x python3 combine_runs.py [--prefix DELIVERABLE]
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import sys
import time
import types

# lib pulls in playwright; the pack only needs its account and workspace tables, so stub the browser module.
pkg = types.ModuleType("playwright")
stub = types.ModuleType("playwright.sync_api")
stub.expect = None
stub.sync_playwright = lambda *a, **k: None
pkg.sync_api = stub
sys.modules.setdefault("playwright", pkg)
sys.modules.setdefault("playwright.sync_api", stub)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from best_runs import BASE, ORDER, best_runs, module_of  # noqa: E402
from lib import ACCOUNTS, EXPECTED_SECTIONS, SECTION_LABEL, SECTIONS  # noqa: E402
from uat_report import write_xlsx  # noqa: E402

SESSION = re.compile(r"^(\d+)_(\w+?)_([\w.-]+)\.webm$")


def link(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def media(run_dir, row_video):
    """The MP4 the deck plays for a session recording of that run."""
    name = (row_video or "").split("/")[-1].replace(".webm", ".mp4")
    if not name:
        return None
    for sub in ("videos", "videos/raw", "."):
        cand = run_dir / sub / name
        if cand.is_file():
            return cand
    return None


def build(pack_id):
    out = BASE / pack_id
    best = best_runs()
    rows, videos, sources, missing = [], [], {}, []
    matrix = {}
    seen, seen_video = set(), set()
    base_url = None
    for m in ORDER:
        if m not in best:
            missing.append(m)
            continue
        n, run, ok, ui, filmed, _ = best[m]
        sources[m] = {"run": run, "cases": n, "passed": ok, "with_ui": ui, "with_video": filmed}
        data = json.loads((BASE / run / "results.json").read_text(encoding="utf-8"))
        base_url = base_url or data.get("base")
        matrix.update(data.get("matrix") or {})
        declared = {v.get("file", "").split("/")[-1]: v for v in data.get("videos", [])}
        for r in data["results"]:
            if module_of(r["id"]) != m or r["id"] in seen:
                continue
            seen.add(r["id"])
            r = dict(r)
            r["run"] = run
            r["module"] = m
            rows.append(r)
            if r.get("shot"):
                src = BASE / run / r["shot"]
                if src.is_file():
                    link(src, out / r["shot"])
            key = (r.get("video") or "").split("/")[-1]
            if not key or key in seen_video:
                continue
            src = media(BASE / run, r.get("video"))
            if src is None:
                continue
            seen_video.add(key)
            link(src, out / "videos" / src.name)
            entry = dict(declared.get(key) or {})
            match = SESSION.match(src.name)
            entry.setdefault("code", match.group(2) if match else m.upper()[:3])
            entry.setdefault("account", match.group(3) if match else r["account"].split("@")[0])
            entry.setdefault("role", r.get("role", ""))
            entry.setdefault("device", "Máy tính 1366x820")
            # the rows point at the session recording by its .webm name and coverage.video_media finds the .mp4 next to it,
            # so the registry keeps the original name even though only the MP4 is packed
            entry["file"] = f"videos/{pathlib.Path(key).name}"
            entry["run"] = run
            videos.append(entry)
    order = {m: i for i, m in enumerate(ORDER)}
    rows.sort(key=lambda r: (order.get(r["module"], 99), r["id"]))
    pack = {"run": pack_id, "base": base_url, "results": rows, "matrix": matrix, "videos": videos,
            "source_runs": sources, "missing_modules": missing,
            "note": "Từng phân hệ lấy lượt chứng minh tốt nhất: số ca đạt BẰNG thao tác UI, rồi số ca có video, rồi lượt mới nhất."}
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    write_xlsx(out, pack_id, rows, matrix, videos, ACCOUNTS, SECTIONS, SECTION_LABEL, EXPECTED_SECTIONS)
    passed = sum(1 for r in rows if r["status"] == "Đạt")
    print(f"{out} · {len(rows)} ca · {passed} đạt · {len(videos)} video · thiếu: {', '.join(missing) or '—'}")
    for m, s in sources.items():
        print(f"  {m:20s} {s['run']} {s['passed']}/{s['cases']} đạt · {s['with_ui']} UI · {s['with_video']} video")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="DELIVERABLE")
    args = ap.parse_args()
    build(f"{args.prefix}-{time.strftime('%Y%m%d-%H%M')}")
