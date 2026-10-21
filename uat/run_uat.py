"""End-to-end UAT of TLC HRM on the standard Frappe HR interface: user journeys per role and module, recorded, with real assertions.

Employees work in the Frappe HR app (/hrms); managers, HR and the CEO work on the Frappe desk in the workspace of their role.
Run (on the k3s node): ~/tlc-hr/tlc-hr-platform/uat/run_uat.sh --reset   (expected numbers assume the clean TLC demo)
ONLY=leave,overtime limits the run to some modules (journeys/<module>.py), in this order.
"""

import importlib
import json
import os
import traceback

from playwright.sync_api import sync_playwright

from lib import ACCOUNTS, BASE, EXPECTED_SECTIONS, MATRIX, OUT, RESULTS, RUN_ID, SECTION_LABEL, SECTIONS, SLOW_MO, VIDEOS

# Run order: later modules use what earlier ones leave behind (approved leave, locked periods, payroll ...).
MODULES = ["leave", "overtime", "attendance"]


def write_outputs():
    (OUT / "results.json").write_text(json.dumps({"run": RUN_ID, "base": BASE, "results": RESULTS, "matrix": MATRIX, "videos": VIDEOS},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    from uat_report import write_html, write_xlsx

    xlsx = write_xlsx(OUT, RUN_ID, RESULTS, MATRIX, VIDEOS, ACCOUNTS, SECTIONS, SECTION_LABEL, EXPECTED_SECTIONS)
    write_html(OUT, RUN_ID, RESULTS, VIDEOS, xlsx)


def main():
    for sub in ("videos/raw", "shots"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    only = [m for m in os.environ.get("ONLY", "").split(",") if m]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(slow_mo=SLOW_MO)
        for module in only or MODULES:
            for journey in importlib.import_module(f"journeys.{module}").JOURNEYS:
                try:
                    journey(browser)
                except Exception as exc:
                    print("SCENARIO ERROR", module, journey.__name__, exc, flush=True)
                    traceback.print_exc()
        browser.close()
    write_outputs()
    passed = sum(1 for r in RESULTS if r["status"] == "Đạt")
    print(f"UAT {RUN_ID}: {passed}/{len(RESULTS)} đạt", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
