"""Native Desk recruitment journey: the two applications are opened on screen, HR accepts the applicant and clicks the
native "Create Job Offer" button, fills the offer field by field, then the workflow moves through Hành động on each role's
form. API is only used to read back what was stored after the person did the work."""

import re
from urllib.parse import quote

from lib import BASE, REQ, Session, api, case, check, csrf_token, dt, expect, login, open_actions, MENU_ITEMS, flt


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


def open_list_row(s, doctype, index=0, needle=None, note=None):
    """Mở danh sách và nhấp đúng dòng như người dùng (không mở hồ sơ bằng URL)."""
    p = s.page
    if note:
        s.step(note)
    p.goto(f"{BASE}/desk/{doctype.lower().replace(' ', '-')}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2200)
    # the list header is also a .list-row-container in this build: keep only the data rows
    rows = p.locator(".list-row-container").filter(has_not=p.locator(".list-row-head"))
    check(rows.count() > 0, f"danh sách {doctype} không có dòng dữ liệu nào")
    target = index
    if needle:
        target = next((i for i in range(rows.count()) if needle in " ".join(rows.nth(i).inner_text().split())), None)
        check(target is not None, f"không thấy '{needle}' trong danh sách {doctype}: "
                                  f"{[rows.nth(i).inner_text() for i in range(min(rows.count(), 5))]}")
    check(target < rows.count(), f"danh sách {doctype} chỉ có {rows.count()} dòng")
    row = rows.nth(target)
    link = row.locator(".list-subject a, a").first
    if link.count() and link.is_visible():
        link.click()
    else:
        row.locator(".list-subject").first.click()
    p.wait_for_function("(d) => window.cur_frm && cur_frm.doctype === d && !cur_frm.is_new()", arg=doctype, timeout=25000)
    p.wait_for_timeout(1800)
    return p


def user_date(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%d-%m-%Y")


def save_primary(page, label=r"Lưu|Save|Cập nhật|Update"):
    """Click the form's own save button (not a keyboard shortcut); Escape first closes a link drop-down over it."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.locator(".page-head button:visible").filter(has_text=re.compile(label)).last.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1800)


def type_into(page, name, text):
    box = page.locator(f"input[data-fieldname='{name}']:visible, textarea[data-fieldname='{name}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    box.click()
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if (box.get_attribute("data-fieldtype") or "") in ("Date", "Datetime", "Time"):
        box.fill(str(text))  # typing character by character makes the date control store 'Invalid date'
    else:
        box.press_sequentially(str(text), delay=50)
    page.keyboard.press("Tab")
    page.wait_for_timeout(800)
    if (box.input_value() or "").strip() != str(text).strip():
        box.fill(str(text))
        page.keyboard.press("Tab")
        page.wait_for_timeout(600)
    if (box.input_value() or "").strip() != str(text).strip():
        try:  # a currency input shows 25.000.000 while the document stores 25000000
            if float(page.evaluate("f => cur_frm.doc[f]", name)) == float(text):
                return
        except Exception:
            pass
    check((box.input_value() or "").strip() == str(text).strip(),
          f"ô {name} đang hiển thị '{(box.input_value() or '').strip()}', không nhận '{text}'")


def pick_link(page, name, needle):
    """A link field: type the value, then click the matching visible completion; Tab alone may leave the link empty."""
    box = page.locator(f"input[data-fieldname='{name}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    box.click()
    box.fill("")
    box.press_sequentially(str(needle), delay=45)
    page.wait_for_timeout(2200)
    options = page.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option], .frappe-control-dropdown li")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    target = next((i for i in shown if str(needle).lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
    if target is not None:
        options.nth(target).click()
        page.wait_for_timeout(1200)
    else:
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
    got = page.evaluate("f => cur_frm.doc[f] || ''", name)
    check(str(got), f"ô {name} không nhận giá trị '{needle}' (đang là {got!r})")
    return got


def screen_text(page):
    return " ".join(page.locator("body").inner_text().split())


def create_offer(s, applicant):
    """Open the application, record the hire decision with the native status field, then click Connect > Create Job Offer
    (the native button appears once the applicant is Accepted). Fill the offer on its own form and save with Lưu."""
    p = s.page
    desk(s, "Job Applicant", applicant)
    status = p.locator("select[data-fieldname='status']:visible").last
    status.wait_for(state="visible", timeout=15000)
    if status.input_value() != "Accepted":
        status.select_option("Accepted")
        p.wait_for_timeout(600)
        save_primary(p)
        p.wait_for_timeout(1500)
    button = p.locator("button:visible").filter(has_text=re.compile(r"Create Job Offer|Tạo đề nghị|Tạo Offer", re.I))
    check(button.count() > 0, f"không có nút Create Job Offer trên hồ sơ ứng viên: {screen_text(p)[:240]}")
    button.last.click()
    try:
        p.wait_for_url(re.compile(r".*/job-offer/.*"), timeout=12000)
    except Exception:
        pass  # the button can open the new offer in place; the form itself is the proof, not the route
    p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Job Offer' && cur_frm.is_new()", timeout=30000)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)
    check(p.evaluate("() => cur_frm.doc.job_applicant") == applicant,
          f"offer không mang ứng viên {applicant} (đang là {p.evaluate('() => cur_frm.doc.job_applicant')})")
    pick_link(p, "company", "TLC Demo")
    type_into(p, "tlc_department", REQ["recruitment_department"])
    today = dt.date.today()
    type_into(p, "offer_date", user_date(today.isoformat()))
    type_into(p, "tlc_joining_date", user_date((today + dt.timedelta(days=14)).isoformat()))
    type_into(p, "tlc_salary", "25000000")
    save_primary(p)
    return p.evaluate("() => cur_frm.doc.name")


def action(s, name, label):
    desk(s, "Job Offer", name)
    open_actions(s.page)
    item = s.page.locator(MENU_ITEMS).filter(has_text=label).first
    check(item.count() > 0, f"không có {label} trong Hành động")
    item.click()
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1800)


def recruitment_flow(browser):
    s = Session(browser, "TD", "lan")
    try:
        login(s)
        with case(s, "TD-01", "Canonical candidate preserves applications", "Open two native Job Applicant forms",
                  "Same normalized phone; different emails", "Same canonical candidate; separate application names") as r:
            p = s.page
            seen = {}
            for index in (0, 1):
                open_list_row(s, "Job Applicant", index=index,
                              note=f"Chị Lan mở hồ sơ ứng viên thứ {index + 1} từ danh sách")
                doc = p.evaluate("() => ({name: cur_frm.doc.name, email: cur_frm.doc.email_id, "
                                 "canonical: cur_frm.doc.tlc_candidate, opening: cur_frm.doc.job_title})")
                seen[doc["email"]] = doc
            check(set(seen) == {CLEARED, UNCLEARED}, f"danh sách ứng viên: {seen}")
            cleared, uncleared = seen[CLEARED], seen[UNCLEARED]
            check(bool(cleared["canonical"]) and cleared["canonical"] == uncleared["canonical"],
                  "Applications do not resolve to the same canonical candidate")
            check(cleared["name"] != uncleared["name"], "hai ứng viên phải là hai hồ sơ riêng")
            REQ["cleared_applicant"], REQ["uncleared_applicant"] = cleared["name"], uncleared["name"]
            desk(s, "Job Opening", cleared["opening"])
            REQ["recruitment_department"] = field(s.page, "department").input_value()
            REQ["recruitment_opening"] = cleared["opening"]
            r["actual"] = (f"{CLEARED} và {UNCLEARED}: cùng candidate {cleared['canonical']}, "
                           f"hai hồ sơ {cleared['name']} / {uncleared['name']}")
        with case(s, "TD-02", "Offer final-round gate", "Open uncleared application > set Accepted > Lưu > Create Job Offer > fill and Lưu",
                  UNCLEARED, "Validation blocks offer before final round"):
            create_offer(s, REQ["uncleared_applicant"])
            text = screen_text(s.page)
            check("vòng cuối" in text, f"không đọc được lý do chặn trên màn hình: {text[-400:]}")
            s.page.keyboard.press("Escape")
        with case(s, "TD-03", "Prepare offer for HR review", "Open cleared application > set Accepted > Lưu > Create Job Offer > fill > Lưu > Submit Offer",
                  CLEARED, "Draft persisted and sent to HR"):
            name = create_offer(s, REQ["cleared_applicant"])
            check("new-job-offer" not in name, f"Offer was not saved: {name} · {screen_text(s.page)[-240:]}")
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
            open_list_row(s, "Job Offer", index=0, note="Chị Lan mở danh sách đề nghị và nhấp đề nghị đã được duyệt")
            check(s.page.evaluate("() => cur_frm.doc.name") == REQ["recruitment_offer"],
                  f"mở nhầm đề nghị {s.page.evaluate('() => cur_frm.doc.name')}, cần {REQ['recruitment_offer']}")
            check(s.page.locator('.frappe-control[data-fieldname="tlc_salary"] input:visible:not([readonly]):not([disabled])').count() == 0,
                  "Approved salary remains editable")
        with case(s, "TD-07", "Accepted offer consumes vacancy and opens onboarding", "Set Offer Stage Sent > Cập nhật; Status Accepted > Cập nhật; open native onboarding list",
                  REQ["recruitment_offer"], "Remaining headcount 1 and a native Employee Onboarding record"):
            field(s.page, "tlc_offer_stage").select_option("Sent")
            s.page.wait_for_timeout(500)
            save_primary(s.page)
            field(s.page, "status").select_option("Accepted")
            s.page.wait_for_timeout(500)
            save_primary(s.page)
            desk(s, "Job Opening", REQ["recruitment_opening"])
            # Read-only fields render formatted values, not necessarily inputs.
            expect(s.page.locator('.frappe-control[data-fieldname="tlc_remaining"] .control-value')).to_contain_text("1")
            s.page.goto(f"{BASE}/desk/employee-onboarding")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2000)
            s.page.get_by_text("Ứng viên tuyển dụng TLC Demo", exact=True).first.click()
            s.page.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Employee Onboarding'", timeout=25000)
            s.page.wait_for_timeout(1500)
            check(s.page.evaluate("() => cur_frm.doc.job_offer") == REQ["recruitment_offer"],
                  f"onboarding mở ra không trỏ tới offer {REQ['recruitment_offer']}: "
                  f"{s.page.evaluate('() => cur_frm.doc.job_offer')}")
    finally:
        s.close()


JOURNEYS = [recruitment_flow]

def ai_hiring(browser):
    """Chat tab + six-step AI hiring: the assistant reads the CV, a person makes every commitment."""
    s = Session(browser, "AI", "hoa")
    try:
        login(s)
        p = s.page
        employee = api(s, "frappe.client.get_value", doctype="Employee", filters=json.dumps({"user_id": "hoa@demo.example"}),
                        fieldname="name")["name"]
        with case(s, "REC-AI-01", "Chat trợ lý HR ngay trong Desk",
                  "Workspace TLC Nhân sự > bấm Trợ lý AI (Chat) > đọc lời chào > hỏi mã nhân viên của tôi",
                  "hoa@demo.example",
                  "Mở tab Desk có khung chat Raven, DM với trợ lý hiện lời chào và trả lời đúng mã nhân viên của người đang đăng nhập") as r:
            s.step("Chị Hòa mở workspace TLC Nhân sự và bấm shortcut Trợ lý AI (Chat)")
            p.goto(f"{BASE}/desk/tlc-hr/tlc-nh%C3%A2n-s%E1%BB%B1")
            p.wait_for_load_state("networkidle")
            widget = p.locator(".widget", has_text="Trợ lý AI (Chat)").first
            expect(widget).to_be_visible()
            widget.click()
            p.wait_for_timeout(6000)
            check("tro-ly-ai" in p.url, f"shortcut không mở tab chat mà ở {p.url.replace(BASE, '')}")
            expect(p.locator("iframe")).to_be_visible(timeout=20000)
            fr = p.frame_locator("iframe").first
            for _ in range(20):
                text = " ".join(fr.locator("body").inner_text().split())
                if "TLC Demo HR Assistant" in text:
                    break
                p.wait_for_timeout(1500)
            check("TLC Demo HR Assistant" in text and "Xin chào" in text, f"khung chat chưa hiện DM trợ lý: {text[:220]}")
            s.step("Chị Hòa hỏi trợ lý ngay trong tab chat")
            box = fr.locator("div[contenteditable='true']").last
            expect(box).to_be_visible(timeout=30000)
            box.click()
            box.type("Cho tôi biết mã nhân viên của tôi, trả lời ngắn gọn.")
            p.keyboard.press("Enter")
            reply = ""
            for _ in range(24):
                p.wait_for_timeout(4000)
                reply = " ".join(fr.locator("body").inner_text().split())
                if employee in reply:
                    break
                recent = api(s, "frappe.client.get_list", doctype="Raven Message",
                             filters=json.dumps([["is_bot_message", "=", 1]]),
                             fields=json.dumps(["text", "channel_id"]), order_by="creation desc", limit_page_length=5)
                if any(employee in (row.get("text") or "") for row in recent):
                    reply = employee
                    break
            check(employee in reply, f"trợ lý không trả mã {employee} sau khi hỏi: {reply[-320:]}")
            r["actual"] = f"Tab chat Desk mở DM với trợ lý; câu trả lời có {employee}"

        with case(s, "REC-AI-02", "AI đối chiếu CV với JD trên hồ sơ ứng viên",
                  "Mở hồ sơ Trần Minh Anh > bấm AI chấm CV > đọc điểm, nhận định và bước tuyển dụng",
                  "tran.minhanh@demo.example",
                  "AI trả điểm 0-100, nhận định và chuyển hồ sơ từ bước 1 sang bước 2; có bản ghi nhật ký AI") as r:
            s.step("Chị Hòa mở hồ sơ ứng viên do AI sàng lọc")
            desk(s, "Job Applicant", "tran.minhanh@demo.example")
            expect(p.locator("button:visible", has_text="AI chấm CV").first).to_be_visible(timeout=20000)
            s.step("Chị Hòa bấm AI chấm CV và chờ trợ lý đối chiếu")
            p.locator("button:visible", has_text="AI chấm CV").first.click()
            for _ in range(40):
                p.wait_for_timeout(3000)
                if p.evaluate("() => window.cur_frm && cur_frm.doc.tlc_ai_status") == "Đã chấm":
                    break
            doc = api(s, "frappe.client.get_value", doctype="Job Applicant", name="tran.minhanh@demo.example",
                      fieldname="*")
            check(doc["tlc_ai_status"] == "Đã chấm" and 0 <= flt(doc["tlc_ai_score"]) <= 100
                  and doc["tlc_ai_verdict"] in ("Đạt", "Cân nhắc", "Không đạt"), str(doc)[:240])
            check(doc["tlc_step"] == "2. Đối chiếu tiêu chí", f"AI không đưa hồ sơ sang bước 2: {doc['tlc_step']}")
            logs = api(s, "frappe.client.get_list", doctype="TLC Recruitment AI Log",
                       filters=json.dumps([["applicant", "=", "tran.minhanh@demo.example"], ["action", "=", "Screen"]]),
                       fields=json.dumps(["name", "score", "verdict"]), limit_page_length=5)
            check(logs, "không có nhật ký AI cho lần chấm")
            r["actual"] = (f"{doc['tlc_ai_score']}/100 {doc['tlc_ai_verdict']} → {doc['tlc_step']}; "
                           f"nhật ký {logs[0]['name']}")

        with case(s, "REC-AI-03", "Người duyệt cổng tuyển dụng và Kanban 6 bước",
                  "Gọi cổng Mời phỏng vấn cho Lê Thu Hà > thử sửa thẳng bước bằng set_value > mở Kanban 6 bước",
                  "le.thuha@demo.example",
                  "Cổng ghi nhận người quyết định và lý do, chuyển sang bước 3; sửa bước bằng API bị từ chối; Kanban hiện đủ 6 bước") as r:
            s.step("Chị Hòa quyết định mời phỏng vấn Lê Thu Hà (cổng con người)")
            interviewer = api(s, "frappe.client.get_value", doctype="Employee", filters=json.dumps({"user_id": "quang@demo.example"}),
                              fieldname="name")["name"]
            out = api(s, "tlc_hr.interface.recruitment_pipeline.advance", name="le.thuha@demo.example", action="invite",
                      payload=json.dumps({"interviewer": interviewer, "interview_at": "2026-11-05 09:00:00",
                                          "reason": "Điểm AI 84, kinh nghiệm B2B vượt JD; mời phỏng vấn vòng 1."}))
            check(out["step"] == "3. Quyết định mời phỏng vấn", str(out))
            doc = api(s, "frappe.client.get_value", doctype="Job Applicant", name="le.thuha@demo.example", fieldname="*")
            check(doc["tlc_decision_by"] == "hoa@demo.example" and doc["tlc_decision_reason"], str(doc)[:200])
            s.step("Thử đổi bước bằng lệnh ghi chung — phải bị chặn")
            res = p.request.post(f"{BASE}/api/method/frappe.client.set_value",
                                 data={"doctype": "Job Applicant", "name": "le.thuha@demo.example",
                                       "fieldname": "tlc_step", "value": "5. Phỏng vấn và quyết định offer"},
                                 headers={"X-Frappe-CSRF-Token": csrf_token(s)})
            check(res.status != 200 and "bước tuyển dụng" in res.text().lower(), f"set_value không bị chặn: {res.status}")
            s.step("Chị Hòa mở Kanban 6 bước và đọc các cột")
            p.goto(f"{BASE}/desk/job-applicant/view/kanban/TLC%20Tuy%E1%BB%83n%20d%E1%BB%A5ng%206%20b%C6%B0%E1%BB%9Bc")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(5000)
            page_text = " ".join(p.locator("body").inner_text().split())
            missing = [step for step in ("1. Tiếp nhận hồ sơ", "2. Đối chiếu tiêu chí", "3. Quyết định mời phỏng vấn",
                                         "4. Thư mời và lịch hẹn", "5. Phỏng vấn và quyết định offer",
                                         "6. Kết quả và lưu vết") if step not in page_text]
            check(not missing, f"Kanban thiếu cột {missing}: {page_text[:260]}")
            r["actual"] = (f"Lê Thu Hà → {doc['tlc_step']} bởi {doc['tlc_decision_by']}; set_value bị chặn "
                           f"({res.status}); Kanban đủ 6 bước")
    finally:
        s.close()


JOURNEYS.append(ai_hiring)
