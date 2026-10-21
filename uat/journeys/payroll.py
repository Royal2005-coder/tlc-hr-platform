"""Payroll on the native desk: HR computes, CEO signs, accounting records payment; employees see their own slips."""

from lib import *  # noqa: F403
from urllib.parse import quote

PE = "Payroll Entry"
COMPUTED, TO_CEO, SIGNED, PAID = "Đã tính lương", "Chờ giám đốc ký", "Đã ký", "Đã chi"


def month_bounds(offset):
    first = dt.date.today().replace(day=1)
    if offset < 0:
        first = (first - dt.timedelta(days=1)).replace(day=1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()


def wait_slips(s, name, docstatus, minimum, timeout=240):
    for _ in range(timeout // 5):
        slips = api_get(s, "/api/resource/Salary Slip?limit_page_length=500&fields=" + json.dumps(["docstatus"]) + "&filters="
                        + json.dumps([["payroll_entry", "=", name]])).json().get("data", [])
        if len(slips) >= minimum and all(x["docstatus"] == docstatus for x in slips):
            return len(slips)
        s.page.wait_for_timeout(5000)
    raise AssertionError(f"phiếu lương chưa xong ({len(slips)})")


def new_entry(s, start, end):
    p = s.page
    company = api(s, "frappe.client.get_value", doctype="Employee", filters=json.dumps({"user_id": f"{s.account}@demo.example"}),
                  fieldname="company")["company"]
    bank = api_get(s, "/api/resource/Account?filters=" + json.dumps([["company", "=", company], ["account_number", "=", "1121"]])).json()["data"][0]["name"]
    p.goto(f"{BASE}/desk/payroll-entry")
    p.wait_for_load_state("networkidle")
    p.evaluate("([c, s, e, b]) => { frappe.new_doc('Payroll Entry', {company: c, posting_date: e, start_date: s, end_date: e, "
               "payroll_frequency: 'Monthly', payment_account: b}); }", [company, start, end, bank])
    p.wait_for_url(re.compile(r".*/payroll-entry/new.*"))
    p.wait_for_timeout(3000)
    p.keyboard.press("Control+s")
    p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Payroll Entry' && !cur_frm.is_new() && !cur_frm.is_dirty()",
                        timeout=30000)
    p.wait_for_load_state("networkidle")
    name = p.evaluate("cur_frm.doc.name")
    # HRMS owns response syncing, dirty state and persistence for this native action.
    p.get_by_role("button", name=re.compile(r"^(Get Employees|Lấy nhân viên)$")).click()
    p.wait_for_function("() => window.cur_frm && (cur_frm.doc.employees || []).length > 0 && !cur_frm.is_dirty()", timeout=60000)
    p.wait_for_load_state("networkidle")
    return name


def workflow(s, name, action):
    p = s.page
    p.goto(f"{BASE}/desk/payroll-entry/{name}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(3000)
    open_actions(p)
    p.locator(MENU_ITEMS).filter(has_text=action).first.click()
    p.wait_for_timeout(5000)
    return doc_state(s, PE, name)


def payroll_flow(browser):
    start, end = month_bounds(-1)
    s = Session(browser, "LG", "phuong")
    login(s)
    with case(s, "PR-01", "Chặn tính lương khi kỳ công tháng này chưa khoá", "Tạo bảng lương tháng hiện tại > Lấy nhân viên > Tính lương",
              "Tháng hiện tại", "Bị chặn: kỳ công chưa khoá, liệt kê phạm vi") as r:
        now_start, now_end = month_bounds(0)
        open_name = new_entry(s, now_start, now_end)
        open_actions(s.page)
        s.page.locator(MENU_ITEMS).filter(has_text="Tính lương").first.click()
        s.page.wait_for_timeout(4000)
        text = s.page.locator(".modal:visible, .msgprint").last.inner_text() if s.page.locator(".modal:visible").count() else ""
        state = doc_state(s, PE, open_name)
        check(state in ("Nháp", None) and "chưa khoá" in text, f"{state} {text[:200]}")
        r["actual"] = " ".join(text.split())[:220]
        s.page.keyboard.press("Escape")
    with case(s, "PR-02", "Tính lương tháng trước (kỳ công đã khoá)", "Bảng lương > Mới (tháng trước) > Lấy nhân viên > Hành động > Tính lương",
              f"{vn(start)} – {vn(end)}", "Phiếu lương nháp cho toàn công ty; tăng ca đã duyệt thành Tiền tăng ca + Phụ trội tăng ca") as r:
        REQ["pe"] = new_entry(s, start, end)
        people = len(api_get(s, f"/api/resource/{PE}/{REQ['pe']}").json()["data"]["employees"])
        state = workflow(s, REQ["pe"], "Tính lương")
        slips = wait_slips(s, REQ["pe"], 0, people)
        extra = api_get(s, "/api/resource/Additional Salary?limit_page_length=500&fields=" + json.dumps(["salary_component"]) + "&filters="
                        + json.dumps([["ref_docname", "=", REQ["pe"]]])).json()["data"]
        components = {x["salary_component"] for x in extra}
        check(state == COMPUTED and slips == people and {"Tiền tăng ca", "Phụ trội tăng ca"} <= components, f"{state} {slips}/{people} {components}")
        s.page.reload()
        s.page.wait_for_timeout(4000)
        r["actual"] = f"{REQ['pe']}: {state}; {slips} phiếu nháp; {len(extra)} khoản tăng ca · {headline(s.page)}"
    with case(s, "PR-03", "Gửi CEO ký", "Hành động > Gửi ký", REQ.get("pe", ""), TO_CEO) as r:
        state = workflow(s, REQ["pe"], "Gửi ký")
        check(state == TO_CEO, state)
        r["actual"] = state
    s.close()

    s = Session(browser, "LG", "thanh")
    login(s)
    with case(s, "PR-04", "CEO ký bảng lương từ workspace", "Thẻ Bảng lương chờ ký > mở > đọc dòng tổng > Hành động > Ký duyệt",
              REQ.get("pe", ""), "Thẻ đếm 1; dòng đầu có tổng thu nhập, thực lĩnh, thuế; sau khi ký mọi phiếu được ghi sổ") as r:
        waiting = card_value(s.page, "Bảng lương chờ ký")
        s.page.goto(f"{BASE}/desk/payroll-entry/{REQ['pe']}")
        s.page.wait_for_load_state("networkidle")
        s.page.wait_for_timeout(4000)
        text = headline(s.page)
        state = workflow(s, REQ["pe"], "Ký duyệt")
        slips = wait_slips(s, REQ["pe"], 1, 1)
        totals = api(s, "tlc_hr.interface.payroll.payroll_summary", name=REQ["pe"])
        check(totals["employer"] > 0, f"Thiếu đóng góp bảo hiểm doanh nghiệp: {totals['employer']}")
        check(waiting == 1 and "thực lĩnh" in text and state == SIGNED, f"{waiting} {state} {text[:120]}")
        r["actual"] = f"Thẻ {waiting}; {text[:200]} → {state}; {slips} phiếu đã ghi sổ"
    s.close()

    s = Session(browser, "LG", "chi")
    login(s)
    with case(s, "PR-05", "Kế toán xác nhận đã chi bằng chứng từ ngân hàng", "Mở bảng lương > nhập Số chứng từ, Ngày chi > Lưu > Hành động > Xác nhận đã chi",
              "VCB-UNC lương tháng trước", "Đã chi; bút toán ngân hàng mang số chứng từ") as r:
        p = s.page
        p.goto(f"{BASE}/desk/payroll-entry/{REQ['pe']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_function("d => window.cur_frm && cur_frm.doctype === 'Payroll Entry' && cur_frm.docname === d", arg=REQ["pe"])
        p.wait_for_timeout(2500)
        before = workflow_actions(p)
        reference = f"VCB-UNC-{start[:7]}-{dt.datetime.now():%H%M}"
        p.evaluate("async ([r, d]) => { await cur_frm.set_value('tlc_bank_reference', r); await cur_frm.set_value('tlc_paid_on', d); }",
                   [reference, dt.date.today().isoformat()])
        # The HRMS payroll form renders the primary save button inconsistently on submitted
        # entries; calling the form's own save keeps the real desk validation and permissions.
        p.evaluate("async () => { await cur_frm.save('Update'); }")
        p.wait_for_function("() => !cur_frm.is_dirty()")
        persisted = api_get(s, f"/api/resource/{PE}/{REQ['pe']}").json()["data"]
        check(persisted["tlc_bank_reference"] == reference and persisted["tlc_paid_on"] == dt.date.today().isoformat(),
              "Chứng từ ngân hàng chưa lưu vào bảng lương")
        state = workflow(s, REQ["pe"], "Xác nhận đã chi")
        entries = api_get(s, "/api/resource/Journal Entry?filters=" + json.dumps([["cheque_no", "=", reference], ["docstatus", "=", 1]])).json()["data"]
        check("Xác nhận đã chi" not in before and state == PAID and entries, f"{before} {state} {entries}")
        r["actual"] = f"Trước khi có chứng từ: không có Xác nhận đã chi; {state}; bút toán {entries[0]['name']} ({reference})"
    s.close()

    s = Session(browser, "LG", "binh")
    login(s)
    with case(s, "PR-06", "Công nhân xem phiếu lương trên app", "App > Lương > mở phiếu lương tháng trước", "Trần Văn Bình",
              "Phiếu lương có phụ cấp ăn trưa, BHXH, BHYT, BHTN, thực lĩnh") as r:
        p = s.page
        slips = api_get(s, "/api/resource/Salary Slip?fields=" + json.dumps(["name", "net_pay", "start_date"]) + "&filters="
                        + json.dumps([["payroll_entry", "=", REQ["pe"]]])).json()["data"]
        check(len(slips) == 1, str(slips))
        p.goto(f"{BASE}/hrms/salary-slips/{quote(slips[0]['name'], safe='')}")
        p.wait_for_load_state("networkidle")
        p.get_by_text(re.compile(r"^(Earnings & Deductions|Thu nhập & Khấu trừ)$")).click()
        p.get_by_text("Phụ cấp ăn trưa", exact=True).wait_for()
        text = p.locator("body").inner_text()
        check("ăn trưa" in text and "BHXH" in text, text[:300])
        r["actual"] = f"{slips[0]['name']}: thực lĩnh {slips[0]['net_pay']:,.0f}; app hiện phụ cấp ăn trưa, BHXH"
    s.close()

    s = Session(browser, "LG", "an")
    login(s)
    with case(s, "PR-07", "Nhân viên văn phòng chỉ thấy phiếu lương của mình", "API danh sách phiếu lương", "an@demo.example",
              "Chỉ phiếu của chính mình") as r:
        slips = api_get(s, "/api/resource/Salary Slip?limit_page_length=500&fields=" + json.dumps(["employee_name"])).json()["data"]
        check(slips and {x["employee_name"] for x in slips} == {"Nguyễn Hoài An"}, str(slips)[:200])
        r["actual"] = f"{len(slips)} phiếu, đều của Nguyễn Hoài An"
    s.close()

    s = Session(browser, "LG", "hung")
    login(s)
    with case(s, "PR-08", "Trưởng nhà máy không xem được lương công nhân", "API phiếu lương của Nhà máy 1", "hung@demo.example",
              "Không thấy phiếu lương của người khác") as r:
        slips = api_get(s, "/api/resource/Salary Slip?limit_page_length=500&fields=" + json.dumps(["employee_name"])).json().get("data", [])
        others = [x for x in slips if x["employee_name"] != "Đặng Văn Hùng"]
        check(not others, str(others)[:200])
        r["actual"] = f"{len(others)} phiếu của người khác"
    s.close()


JOURNEYS = [payroll_flow]
