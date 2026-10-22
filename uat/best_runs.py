"""Which run proves which module best.

Case ids of this suite are named per role journey (CN1-, HR-, QL-, ...), not per module, so the module of a case comes
from the journey file that declares it, or from the "module" tag newer runs store on each row.

Ranking puts the number of cases that are BOTH passing and backed by real clicks/keystrokes first, then the number of
those cases with a playable MP4 in that run, then the passing count, then the run id. An old run that finished cases
through the API cannot outrank a UI run, and a UI run whose videos were never converted cannot outrank one that kept
them -- the deck has to show the recording, not just the table.

Read-only over out/*/results.json.
"""
import json
import pathlib
import re

BASE = pathlib.Path("/home/ai1/tlc-hr/tlc-hr-platform/uat/out")
HERE = pathlib.Path(__file__).resolve().parent
ORDER = ["leave", "overtime", "attendance", "payroll", "payroll_compliance", "travel_finance", "organization",
         "recruitment", "lifecycle", "people_ops", "services", "survey", "role_experience", "roles"]

# Older runs declare no module, and their case ids are named after the role journey that plays them, so the prefix is
# the fallback map: the leave journey is told through the people (CN1, CN2, NV, QL, HR, HT, CEO), the closing cases
# of attendance carry PD, and travel covers TRV (business), FIN (money) and GOV (governance).
PREFIX = {"CN1": "leave", "CN2": "leave", "NV": "leave", "QL": "leave", "HR": "leave", "HT": "leave", "CEO": "leave",
          "OT": "overtime", "AT": "attendance", "PD": "attendance", "PR": "payroll", "PC": "payroll_compliance",
          "TRV": "travel_finance", "FIN": "travel_finance", "GOV": "travel_finance", "ORG": "organization",
          "TD": "recruitment", "W4": "lifecycle", "W5": "people_ops", "SVC": "services", "SUR": "survey",
          "RX": "role_experience", "RV": "roles"}


def journey_ids():
    """module -> the case ids its journey file declares."""
    out = {}
    for m in ORDER:
        path = HERE / "journeys" / f"{m}.py"
        if path.is_file():
            out[m] = set(re.findall(r'case\(\s*\w+\s*,\s*"([^"]+)"', path.read_text(encoding="utf-8")))
    return out


def module_of(case_id, ids=None):
    ids = ids or journey_ids()
    for m in ORDER:
        if case_id in ids.get(m, ()):
            return m
    return PREFIX.get(case_id.split("-")[0])


def has_mp4(run_dir, row):
    """The recording of that case as played by the deck: <videos|videos/raw>/<name>.mp4."""
    name = (row.get("video") or "").split("/")[-1].replace(".webm", ".mp4")
    if not name:
        return False
    return any((run_dir / sub / name).is_file() for sub in ("videos", "videos/raw")) or (run_dir / name).is_file()


def best_runs():
    ids = journey_ids()
    best = {}
    for d in sorted(BASE.iterdir(), key=lambda p: p.name):
        f = d / "results.json"
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("source_runs"):
            continue  # an assembled pack cites other runs; it is never a source itself
        for m in ORDER:
            rows = [r for r in data["results"] if (r.get("module") or module_of(r["id"], ids)) == m]
            if not rows:
                continue
            ok = sum(r["status"] == "Đạt" for r in rows)
            ui = sum(1 for r in rows if r.get("ui_ops"))
            proven = sum(1 for r in rows if r["status"] == "Đạt" and r.get("ui_ops"))
            filmed = sum(1 for r in rows if r["status"] == "Đạt" and r.get("ui_ops") and has_mp4(d, r))
            key = (proven, filmed, ok, ui, d.name)
            if m not in best or key > best[m][0]:
                best[m] = (key, len(rows), d.name, ok, ui, filmed)
    return {m: v[1:] + (v[0],) for m, v in best.items()}


if __name__ == "__main__":
    for m in ORDER:
        best = best_runs().get(m)
        if best:
            n, run, ok, ui, filmed, _ = best
            print(f"{m:20s} {run}  {ok}/{n} đạt · {ui} có UI · {filmed} có video mp4")
        else:
            print(f"{m:20s} (chưa có lượt nào)")
