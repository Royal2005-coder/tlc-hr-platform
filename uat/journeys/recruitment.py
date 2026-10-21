"""Native Desk recruitment journey; requires seed.recruitment.run on a fresh demo."""

from urllib.parse import quote

from lib import BASE, REQ, Session, case, check, dt, expect, login, open_actions, re, MENU_ITEMS


CLEARED = "recruitment.candidate@demo.example"
UNCLEARED = "recruitment.alias@demo.example"


def field(page, name):
    return page.locator(f'.frappe-control[data-fieldname="{name}"] input:visible, '
                        f'.frappe-control[data-fieldname="{name}"] select:visible').first


def value(page, name):
    control = page.locator(f'.frappe-control[data-fieldname="{name}"]')
    inputs = control.locator("input:visible, select:visible")
    return inputs.first.input_value() if inputs.count() else control.locator(".control-value").inner_text().strip()


def desk(s, doctype, name):
    slug = doctype.lower().replace(" ", "-")
    s.page.goto(f"{BASE}/desk/{slug}/{quote(name, safe='')}")
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_function("() => window.cur_frm && !cur_frm.is_new()")


def save(page):
    page.keyboard.press("Control+s")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)


def update(page):
    # A submitted document with allow_on_submit fields is changed through the Update action, not a draft save.
    page.evaluate("() => cur_frm.save('Update')")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)


def offer_form(s, applicant):
    p = s.page
    p.goto(f"{BASE}/desk/job-offer")
    p.wait_for_load_state("networkidle")
    # job_applicant is self-dependent in HRMS: it only shows once it has a value.
    p.evaluate("(a) => frappe.new_doc('Job Offer', {job_applicant: a})", applicant)
    p.wait_for_url(re.compile(r".*/job-offer/new-job-offer-.*"))
    p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Job Offer' && cur_frm.is_new()")
    expect(field(p, "job_applicant")).to_be_visible()
    p.wait_for_load_state("networkidle")
    field(p, "company").fill("TLC Demo")
    field(p, "company").press("Tab")
    field(p, "tlc_department").fill(REQ["recruitment_department"])
    field(p, "tlc_department").press("Tab")
    field(p, "offer_date").fill(dt.date.today().strftime("%d-%m-%Y"))
    field(p, "tlc_joining_date").fill((dt.date.today() + dt.timedelta(days=14)).strftime("%d-%m-%Y"))
    field(p, "tlc_salary").fill("25000000")


def action(s, name, label):
    desk(s, "Job Offer", name)
    open_actions(s.page)
    s.page.locator(MENU_ITEMS).filter(has_text=label).first.click()
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1200)


def recruitment_flow(browser):
    s = Session(browser, "TD", "lan")
    try:
        login(s)
        with case(s, "TD-01", "Canonical candidate preserves applications", "Open two native Job Applicant forms",
                  "Same normalized phone; different emails", "Same canonical candidate; separate application names"):
            desk(s, "Job Applicant", CLEARED)
            canonical = value(s.page, "tlc_candidate")
            opening = s.page.evaluate("() => cur_frm.doc.job_title")
            desk(s, "Job Applicant", UNCLEARED)
            check(bool(canonical) and value(s.page, "tlc_candidate") == canonical,
                  "Applications do not resolve to the same canonical candidate")
            desk(s, "Job Opening", opening)
            REQ["recruitment_department"] = field(s.page, "department").input_value()
            REQ["recruitment_opening"] = opening
        with case(s, "TD-02", "Offer final-round gate", "New native Job Offer > choose uncleared application > Save",
                  UNCLEARED, "Validation blocks offer before final round"):
            offer_form(s, UNCLEARED)
            save(s.page)
            expect(s.page.locator(".modal:visible, .msgprint").last).to_contain_text("vòng cuối")
            s.page.keyboard.press("Escape")
        with case(s, "TD-03", "Prepare offer for HR review", "Native Job Offer > cleared application > Save > Submit Offer",
                  CLEARED, "Draft persisted and sent to HR"):
            offer_form(s, CLEARED)
            save(s.page)
            check("new-job-offer" not in s.page.url, "Offer was not saved")
            name = s.page.url.rstrip("/").split("/")[-1]
            REQ["recruitment_offer"] = name
            action(s, name, "Submit Offer")
            expect(s.page.locator(".page-head")).to_contain_text("Recruitment HR Review")
    finally:
        s.close()
    s = Session(browser, "TD-HR", "hoa")
    try:
        login(s)
        with case(s, "TD-04", "HR reviews offer", "Job Offer > Review Offer", REQ["recruitment_offer"], "CEO review"):
            action(s, REQ["recruitment_offer"], "Review Offer")
            expect(s.page.locator(".page-head")).to_contain_text("Recruitment CEO Review")
    finally:
        s.close()
    s = Session(browser, "TD-CEO", "thanh")
    try:
        login(s)
        with case(s, "TD-05", "CEO approves compensation", "Job Offer > Approve Offer", REQ["recruitment_offer"], "Submitted approved offer"):
            action(s, REQ["recruitment_offer"], "Approve Offer")
            expect(s.page.locator(".page-head")).to_contain_text("Recruitment Approved")
    finally:
        s.close()
    s = Session(browser, "TD-ACCEPT", "lan")
    try:
        login(s)
        with case(s, "TD-06", "Approved salary is locked", "Open approved native Job Offer", REQ["recruitment_offer"], "Salary is not editable"):
            desk(s, "Job Offer", REQ["recruitment_offer"])
            check(s.page.locator('.frappe-control[data-fieldname="tlc_salary"] input:visible:not([readonly]):not([disabled])').count() == 0,
                  "Approved salary remains editable")
        with case(s, "TD-07", "Accepted offer consumes vacancy and opens onboarding", "Set Offer Stage Sent > Save; Status Accepted > Save; open native onboarding list",
                  REQ["recruitment_offer"], "Remaining headcount 1 and a native Employee Onboarding record"):
            field(s.page, "tlc_offer_stage").select_option("Sent")
            update(s.page)
            field(s.page, "status").select_option("Accepted")
            update(s.page)
            desk(s, "Job Opening", REQ["recruitment_opening"])
            # Read-only fields render formatted values, not necessarily inputs.
            expect(s.page.locator('.frappe-control[data-fieldname="tlc_remaining"] .control-value')).to_contain_text("1")
            s.page.goto(f"{BASE}/desk/employee-onboarding")
            s.page.wait_for_load_state("networkidle")
            s.page.get_by_text("Ứng viên tuyển dụng TLC Demo", exact=True).first.click()
            expect(field(s.page, "job_offer")).to_have_value(REQ["recruitment_offer"])
    finally:
        s.close()


JOURNEYS = [recruitment_flow]
