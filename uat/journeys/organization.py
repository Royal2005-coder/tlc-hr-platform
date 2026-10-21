"""Native Desk organization smoke journeys; no API-only mutations or custom pages.

The fixtures come from tlc_hr.seed.organization.run. These cases intentionally do
not claim to prove downstream co-leader approval routing or a combined chart.
"""
from lib import *  # noqa: F403


def open_form(s, slug, name):
    s.page.goto(f"{BASE}/desk/{slug}/{name}")
    s.page.wait_for_function("() => window.cur_frm && !cur_frm.is_new()")
    s.page.wait_for_load_state("networkidle")


def input_value(s, name):
    return s.page.locator(f'[data-fieldname="{name}"] input:visible').first.input_value()


def organization_desk(browser):
    s = Session(browser, "ORG", "hoa")
    try:
        login(s)
        with case(s, "ORG-01", "Administrative tree", "Open native Department tree", "Existing TLC departments",
                  "Native hierarchy is visible independently of Employee reporting"):
            s.page.goto(f"{BASE}/desk/department/view/tree")
            s.page.locator(".tree-node").first.wait_for(state="visible")
        with case(s, "ORG-02", "Independent co-leaders", "Open native reporting-line list", "Seeded Quang and Hoa",
                  "Two independent co-leader rows are listed; downstream routing is not exercised"):
            s.page.goto(f"{BASE}/desk/tlc-organization-reporting-line")
            s.page.locator(".list-row-container").nth(1).wait_for(state="visible")
        with case(s, "ORG-03", "Position and job", "Open seeded native Position form", "ORG-DEMO-SALES",
                  "Position has a department, job, grade and JD"):
            open_form(s, "tlc-organization-position", "ORG-DEMO-SALES")
            for field in ("department", "designation", "grade"):
                check(bool(input_value(s, field)), f"Missing {field}")
            check(bool(s.page.locator('[data-fieldname="job_description"]').inner_text().strip()), "Missing JD")
        with case(s, "ORG-04", "Worksite calendar references", "Open native Shift Location creation form", "Calendar and shift reference fields",
                  "Native worksite form exposes references; actual assignment remains HRMS Shift Assignment"):
            s.page.goto(f"{BASE}/desk/shift-location/new")
            s.page.locator('[data-fieldname="tlc_organization_holiday_list"] input:visible').wait_for()
            s.page.locator('[data-fieldname="tlc_organization_shift_type"] input:visible').wait_for()
        with case(s, "ORG-05", "Automatic position headcount", "Open headcount list > first seeded plan > recalculate", "Seeded sales position: capacity 2, one employee",
                  "Used 1, vacant 1, excess 0; values calculated through the native form"):
            s.page.goto(f"{BASE}/desk/tlc-organization-headcount")
            s.page.locator('.list-row-container .list-subject a').first.click()
            s.page.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'TLC Organization Headcount' && !cur_frm.is_new()")
            s.page.get_by_role("button", name=re.compile(r"^(Recalculate headcount|Tính lại định biên)$")).click()
            s.page.wait_for_function("() => cur_frm.doc.used === 1 && cur_frm.doc.vacant === 1 && cur_frm.doc.excess === 0")
        with case(s, "ORG-06", "Native primary reporting chart export", "Open Organizational Chart > Export", "Employee.reports_to, not TLC co-leader edges",
                  "Native chart downloads a PNG"):
            s.page.goto(f"{BASE}/desk/organizational-chart")
            s.page.locator('.node-card').first.wait_for(state="visible")
            with s.page.expect_download() as download:
                s.page.get_by_role("button", name=re.compile(r"^(Export|Xuất)$")).click()
            target = OUT / "shots" / "ORG-06-chart.png"
            download.value.save_as(str(target))
            check(target.stat().st_size > 0, "Empty chart export")
        with case(s, "ORG-07", "Effective organization change register", "Open native change list > New", "Effective date and source/target child table",
                  "Native draft exposes effective date and change lines; scheduler execution is covered separately"):
            s.page.goto(f"{BASE}/desk/tlc-organization-change")
            s.page.get_by_role("button", name=re.compile(r"^(Add TLC Organization Change|New|Mới|Thêm.*)$")).last.click()
            s.page.locator('[data-fieldname="effective_date"] input:visible').wait_for()
            s.page.locator('[data-fieldname="changes"] .grid-add-row').wait_for()
        with case(s, "ORG-08", "Multiple assignments without false warnings", "Open native assignment list", "Primary Sales and secondary HR for An",
                  "Multiple dated assignments remain separate records"):
            s.page.goto(f"{BASE}/desk/tlc-organization-assignment")
            s.page.locator(".list-row-container").nth(1).wait_for(state="visible")
    finally:
        s.close()


JOURNEYS = [organization_desk]
