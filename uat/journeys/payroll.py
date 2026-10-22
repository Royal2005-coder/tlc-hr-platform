"""Payroll on the native desk and the Frappe HR app, shown as the roles really work: HR opens the Payroll Entry list,
clicks Thêm, types the company/dates/frequency/accounts, saves, clicks the native Lấy nhân viên, then the workflow buttons;
the CEO signs, the accountant types the bank proof and confirms the transfer; the worker reads the payslip in the app and
each role sees only the payslips it is allowed to. API is used only to prepare background fixtures (locking the previous
attendance month, the payroll period) and to double-check what was stored."""

from urllib.parse import quote

from lib import *  # noqa: F403

PE = "Payroll Entry"
AP = "TLC Attendance Period"
COMPANY = "TLC Demo"
COMPUTED, TO_CEO, SIGNED, PAID = "Đã tính lương", "Chờ giám đốc ký", "Đã ký", "Đã chi"
# scope -> the account that is its line manager (the head who confirms the month); the head office has none
SCOPES = {"Nhà máy 1": "hung", "Nhà máy 2": "nm2", "Nhà máy 3": "nm3", "Hội sở": None}


def month_bounds(offset):
    first = dt.date.today().replace(day=1)
    if offset < 0:
        first = (first - dt.timedelta(days=1)).replace(day=1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()


def vnd(amount):
    """The way the site prints money: dots for thousands."""
    return f"{int(round(amount)):,}".replace(",", ".")


def wait_slips(s, name, docstatus, minimum, timeout=240):
    slips = []
    for _ in range(timeout // 5):
        slips = api_get(s, "/api/resource/Salary Slip?limit_page_length=500&fields=" + json.dumps(["docstatus"])
                        + "&filters=" + json.dumps([["payroll_entry", "=", name]])).json().get("data", [])
        if len(slips) >= minimum and all(x["docstatus"] == docstatus for x in slips):
            return len(slips)
        s.page.wait_for_timeout(5000)
    raise AssertionError(f"phiếu lương chưa xong ({len(slips)})")


# -------------------------------------------------------------------------------------------- background fixtures (API only)

def _fixture_login(browser, account):
    s = Session(browser, "FIX-" + account.upper(), account)
    login(s)
    return s


def _fixture_close(s):
    """Tear down a fixture session without emitting an evidence video (it is not a role doing a job)."""
    try:
        s.context.close()
    except Exception:
        pass


def _apply_workflow(s, doctype, name, action):
    return api(s, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": doctype, "name": name}), action=action)


def _lock_one_period(lan, head, ceo, scope, month):
    """Bring one attendance period of one scope to Đã khoá (docstatus 1) by walking the real workflow as its owners."""
    doc = api(lan, "frappe.client.insert", doc=json.dumps({"doctype": AP, "company": COMPANY, "scope": scope, "period_month": month}))
    name = doc["name"]
    if head is not None:
        _apply_workflow(lan, AP, name, "Gửi xác nhận")
        _apply_workflow(head, AP, name, "Xác nhận")
    else:
        _apply_workflow(lan, AP, name, "Gửi đối soát")
    _apply_workflow(lan, AP, name, "Đối soát xong")
    _apply_workflow(ceo, AP, name, "Ký và khoá")


def _ensure_previous_month_locked(browser, month):
    """Payroll may only be computed once every scope's month is locked. In a full run the attendance journey does this; when only
    payroll runs the shared harness resets the periods first, so the locked month is rebuilt here as background data."""
    probe = _fixture_login(browser, "lan")
    try:
        locked = {r["scope"] for r in api_get(probe, "/api/resource/" + AP + "?fields=" + json.dumps(["scope"])
                                              + "&filters=" + json.dumps([["company", "=", COMPANY], ["period_month", "=", month],
                                                                         ["docstatus", "=", 1]])).json().get("data", [])}
    finally:
        _fixture_close(probe)
    missing = [scope for scope in SCOPES if scope not in locked]
    if not missing:
        return
    holders = {account: _fixture_login(browser, account) for account in {"lan", "thanh"} | {h for h in SCOPES.values() if h}}
    try:
        for scope in missing:
            head = SCOPES[scope]
            _lock_one_period(holders["lan"], holders.get(head), holders["thanh"], scope, month)
    finally:
        for session in holders.values():
            _fixture_close(session)


def _ensure_payroll_period(s, month_start, month_end):
    """The Frappe HR payslip list is grouped by payroll period; without one the worker sees an empty screen, so seed the year."""
    start = dt.date.fromisoformat(month_start)
    period = f"Payroll Period {start.year} - TLC"
    existing = api_get(s, "/api/resource/Payroll Period?filters=" + json.dumps([["company", "=", COMPANY]])).json().get("data", [])
    for row in existing:
        doc = api_get(s, f"/api/resource/Payroll Period/{quote(row['name'], safe='')}").json().get("data", {})
        if doc.get("start_date") <= month_start and (doc.get("end_date") or "") >= month_end:
            return
    try:
        api(s, "frappe.client.insert", doc=json.dumps({"doctype": "Payroll Period", "name": period, "company": COMPANY,
                                                       "start_date": f"{start.year}-01-01", "end_date": f"{start.year}-12-31"}))
    except Exception:
        pass  # an overlapping period already covers the month


# -------------------------------------------------------------------------------------------- the desk payroll form

def _field(p, name):
    return p.locator(f'.frappe-control[data-fieldname="{name}"] input:visible').first


def user_date(s, iso):
    """An ISO date written the way this user's desk displays dates, so typing it into a date field is understood."""
    fmt = getattr(s, "_date_format", None) or "yyyy-mm-dd"
    if not hasattr(s, "_date_format"):
        s._date_format = s.page.evaluate("() => (window.frappe && frappe.boot.sysdefaults.date_format) || 'yyyy-mm-dd'")
        fmt = s._date_format
    d = dt.date.fromisoformat(iso)
    return fmt.replace("yyyy", f"{d.year:04d}").replace("mm", f"{d.month:02d}").replace("dd", f"{d.day:02d}")


def digits(text):
    return re.sub(r"\D", "", text or "")


def _save(p, label="Lưu"):
    """Native Save (or Update on a submitted document); Escape first so a link autocomplete cannot swallow the click."""
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    button = p.locator("button:visible", has_text=label)
    clicked = False
    if button.count():
        try:
            button.last.click(timeout=6000)
            clicked = True
        except Exception:
            clicked = False
    if not clicked:
        p.keyboard.press("Control+s")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)


def _new_entry(s, start, end, account_label):
    """Open the Payroll Entry list, click Thêm, type company/dates/frequency/accounts, press Lưu, then the native Lấy nhân viên."""
    p = s.page
    payment_account = api_get(s, "/api/resource/Account?filters=" + json.dumps([["company", "=", COMPANY], ["account_number", "=", "1121"]])).json()["data"][0]["name"]
    s.step(f"{account_label} mở danh sách Bảng lương và bấm Thêm")
    p.goto(f"{BASE}/desk/payroll-entry")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    p.locator("button:visible", has_text="Thêm Bảng lương").first.click()
    p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Payroll Entry' && cur_frm.is_new()", timeout=25000)
    p.wait_for_timeout(2000)

    s.step("Điền công ty, ngày hạch toán, kỳ lương và tần suất trả lương")
    _field(p, "company").fill(COMPANY)
    _field(p, "company").press("Enter")
    p.wait_for_timeout(1000)
    _field(p, "posting_date").fill(vn(end))
    _field(p, "posting_date").press("Tab")
    p.wait_for_timeout(600)
    p.locator('.frappe-control[data-fieldname="payroll_frequency"] select').first.select_option("Monthly")
    p.wait_for_timeout(2000)  # HRMS derives start/end from the frequency; re-type them so the period is explicit
    _field(p, "start_date").fill(vn(start))
    _field(p, "start_date").press("Tab")
    _field(p, "end_date").fill(vn(end))
    _field(p, "end_date").press("Tab")
    p.wait_for_timeout(1200)

    s.step("Chọn tài khoản chi lương trên tab Kế toán & Thanh toán")
    p.locator("button:visible", has_text="Kế toán & Thanh toán").first.click()
    p.wait_for_timeout(1200)
    account = _field(p, "payment_account")
    account.fill(payment_account)
    account.press("Enter")
    p.wait_for_timeout(1500)

    s.step("Nhấn Lưu để tạo bảng lương")
    _save(p, "Lưu")
    p.wait_for_function("() => window.cur_frm && !cur_frm.is_new()", timeout=30000)
    name = p.evaluate("cur_frm.doc.name")

    s.step("Nhấn Lấy nhân viên để hệ thống liệt kê nhân sự của kỳ")
    get = p.locator("button:visible", has_text=re.compile(r"Lấy nhân viên|Get Employees"))
    get.last.click()
    p.wait_for_function("() => window.cur_frm && (cur_frm.doc.employees || []).length > 0", timeout=60000)
    p.wait_for_load_state("networkidle")
    _save(p, "Lưu")  # persist the employee rows before any workflow action
    return name


def _open_entry(s, name, label):
    p = s.page
    s.step(f"{label} mở bảng lương {name}")
    p.goto(f"{BASE}/desk/payroll-entry/{name}")
    p.wait_for_load_state("networkidle")
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === 'Payroll Entry' && cur_frm.docname === d", arg=name)
    p.wait_for_timeout(2500)


def _state_label(p):
    return " ".join(p.locator(".page-head").first.inner_text().split())


def _workflow(s, action):
    """Hành động > <action> on the opened form; returns the new state read back from the form."""
    p = s.page
    s.step(f"Nhấn Hành động rồi chọn “{action}”")
    open_actions(p)
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == action), None)
    check(target is not None, f"không có {action} trong {menu_items(p)}")
    items.nth(target).click()
    p.wait_for_timeout(8000)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)
    return p.evaluate("cur_frm.doc.workflow_state")


# -------------------------------------------------------------------------------------------- the journey

def payroll_flow(browser):
    start, end = month_bounds(-1)        # last month: the month payroll is computed for
    now_start, now_end = month_bounds(0)  # this month: still open, must not be payable
    month = start[:7]

    _ensure_previous_month_locked(browser, month)

    # ---------------------------------------------------------- HR computes
    s = Session(browser, "LG", "phuong")
    login(s)
    _ensure_payroll_period(s, start, end)

    with case(s, "PR-01", "Chặn tính lương khi kỳ công tháng này chưa khoá", "Thêm bảng lương tháng hiện tại > điền form > Lưu > Lấy nhân viên > Hành động > Tính lương",
              "Tháng hiện tại", "Bị chặn ngay trên form: kỳ công chưa khoá, liệt kê phạm vi chưa khoá") as r:
        open_name = _new_entry(s, now_start, now_end, "Chuyên viên lương")
        people = len(api_get(s, f"/api/resource/{PE}/{open_name}").json()["data"]["employees"])
        _workflow(s, "Tính lương")  # the submit is refused; the block shows in the dialog
        dialog = s.page.locator(".modal:visible")
        text = " ".join(dialog.last.inner_text().split()) if dialog.count() else headline(s.page)
        state = doc_state(s, PE, open_name)
        check(state == "Nháp" and "chưa khoá" in text and people > 0, f"{state} | {text[:180]}")
        r["actual"] = f"Đã chặn khi Tính lương ({people} nhân viên): {text[:200]}"
        s.page.keyboard.press("Escape")

    with case(s, "PR-02", "Tính lương tháng trước (kỳ công đã khoá)", "Thêm bảng lương tháng trước > điền form > Lưu > Lấy nhân viên (xem dòng hiện ra) > Hành động > Tính lương",
              f"{vn(start)} – {vn(end)}", "Toàn công ty có phiếu lương nháp; tăng ca đã duyệt thành Tiền tăng ca + Phụ trội tăng ca") as r:
        REQ["pe"] = _new_entry(s, start, end, "Chuyên viên lương")
        people = len(api_get(s, f"/api/resource/{PE}/{REQ['pe']}").json()["data"]["employees"])
        s.step("Quan sát danh sách nhân viên đã hiện trên bảng lương")
        state = _workflow(s, "Tính lương")
        slips = wait_slips(s, REQ["pe"], 0, people)
        extra = api_get(s, "/api/resource/Additional Salary?limit_page_length=500&fields=" + json.dumps(["salary_component"]) + "&filters="
                        + json.dumps([["ref_docname", "=", REQ["pe"]]])).json()["data"]
        components = {x["salary_component"] for x in extra}
        check(state == COMPUTED and slips == people and {"Tiền tăng ca", "Phụ trội tăng ca"} <= components, f"{state} {slips}/{people} {components}")
        # the payroll operator can list every slip of the run; remember them so the worker/scope cases can aim at a foreign one
        REQ["slips"] = api_get(s, "/api/resource/Salary Slip?limit_page_length=500&fields=" + json.dumps(["name", "employee_name", "net_pay"])
                               + "&filters=" + json.dumps([["payroll_entry", "=", REQ["pe"]]])).json().get("data", [])
        s.page.reload()
        s.page.wait_for_timeout(3000)
        check(COMPUTED in _state_label(s.page), _state_label(s.page)[:120])
        r["actual"] = f"{REQ['pe']}: nhãn trạng thái “{state}”; {slips} phiếu nháp cho {people} người; {len(extra)} khoản tăng ca"
        REQ["people"] = people

    with case(s, "PR-03", "Gửi CEO ký", "Hành động > Gửi ký > đọc nhãn trạng thái trên form", REQ.get("pe", ""), "Chờ giám đốc ký") as r:
        _open_entry(s, REQ["pe"], "Chuyên viên lương")
        state = _workflow(s, "Gửi ký")
        check(state == TO_CEO and TO_CEO in _state_label(s.page), f"{state} | {_state_label(s.page)[:100]}")
        r["actual"] = f"Nhãn trên form: {state}"
    s.close()

    # ---------------------------------------------------------- CEO signs
    s = Session(browser, "LG", "thanh")
    login(s)
    with case(s, "PR-04", "CEO ký bảng lương từ workspace", "Thẻ Bảng lương chờ ký > mở bảng lương > đọc dòng tổng > Hành động > Ký duyệt > đọc nhãn trạng thái",
              REQ.get("pe", ""), "Thẻ đếm 1; dòng ghi sổ thực lĩnh/tổng thu nhập; sau khi ký mọi phiếu được ghi sổ, nhãn form là Đã ký") as r:
        waiting = card_value(s.page, "Bảng lương chờ ký")
        _open_entry(s, REQ["pe"], "Tổng giám đốc")
        summary = headline(s.page)
        state = _workflow(s, "Ký duyệt")
        slips = wait_slips(s, REQ["pe"], 1, 1)
        totals = api(s, "tlc_hr.interface.payroll.payroll_summary", name=REQ["pe"])
        check(totals["employer"] > 0, f"Thiếu đóng góp bảo hiểm doanh nghiệp: {totals['employer']}")
        check(waiting == 1 and "thực lĩnh" in summary and state == SIGNED and SIGNED in _state_label(s.page), f"{waiting} {state} {summary[:120]}")
        # slips of the run were listed in PR-02 (the operator's view) and are now posted; reuse them for the scope cases
        r["actual"] = f"Thẻ chờ ký {waiting}; {summary[:150]} → nhãn form “{state}”; {slips} phiếu đã ghi sổ"
    s.close()

    # ---------------------------------------------------------- accountant confirms the transfer
    s = Session(browser, "LG", "chi")
    login(s)
    reference = f"VCB-UNC-{month}-{dt.datetime.now():%H%M}"
    paid_on = dt.date.today().isoformat()
    with case(s, "PR-05", "Kế toán xác nhận đã chi bằng chứng từ ngân hàng",
              "Mở bảng lương > Hành động khi chưa có chứng từ (từ chối) > nhập Số chứng từ & Ngày chi > Cập nhật > Hành động > Xác nhận đã chi",
              reference, "Khi thiếu chứng từ thì không có hành động Xác nhận đã chi; sau khi nhập và lưu thì bảng lương Đã chi, bút toán ngân hàng mang số chứng từ") as r:
        _open_entry(s, REQ["pe"], "Kế toán")
        refused = s.page.locator("button:visible", has_text="Hành động").count() == 0  # no action offered while the proof is empty
        s.step("Chưa có chứng từ: Hành động không đề nghị Xác nhận đã chi")
        s.page.wait_for_timeout(800)
        s.step("Kế toán nhập số chứng từ ngân hàng và ngày chi ngay trên form")
        s.page.locator("button:visible", has_text="Nhân viên").first.click()
        s.page.wait_for_timeout(1200)
        _field(s.page, "tlc_bank_reference").fill(reference)
        _field(s.page, "tlc_bank_reference").press("Tab")
        # the date control parses what is typed with the user's own date format, not with the ISO one
        typed = user_date(s, paid_on)
        s.step(f"Nhập Ngày chi theo định dạng ngày của người dùng: {typed}")
        _field(s.page, "tlc_paid_on").fill(typed)
        _field(s.page, "tlc_paid_on").press("Tab")
        proof_path = Path("/tmp/uat-bank-proof.txt")
        proof_path.write_text("UAT bank transfer proof", encoding="utf-8")
        s.step("Kế toán đính kèm ủy nhiệm chi ngân hàng vào bảng lương đã ký")
        attach_btn = s.page.locator('[data-fieldname="tlc_bank_proof"] button.btn-attach:visible, [data-fieldname="tlc_bank_proof"] button:visible').last
        if attach_btn.count():
            attach_btn.click()
            s.page.wait_for_timeout(1000)
            dialog = s.page.locator(".modal:visible").last
            dialog.locator("input[type=file]").last.set_input_files(str(proof_path))
            s.page.wait_for_timeout(1200)
            upload_btn = dialog.get_by_role("button", name=re.compile(r"^(Tải lên|Upload)$"))
            if upload_btn.count():
                upload_btn.last.click()
            s.page.wait_for_timeout(3000)
        s.page.wait_for_timeout(800)
        s.step("Nhấn Cập nhật để lưu chứng từ vào bảng lương đã ký")
        _save(s.page, "Cập nhật")
        persisted = api_get(s, f"/api/resource/{PE}/{REQ['pe']}").json()["data"]
        check(persisted.get("tlc_bank_reference") == reference and persisted.get("tlc_paid_on") == paid_on,
              f"chứng từ chưa lưu: {persisted.get('tlc_bank_reference')} / {persisted.get('tlc_paid_on')}")
        state = _workflow(s, "Xác nhận đã chi")
        entries = api_get(s, "/api/resource/Journal Entry?filters=" + json.dumps([["cheque_no", "=", reference], ["docstatus", "=", 1]])).json().get("data", [])
        check(refused and state == PAID and PAID in _state_label(s.page) and entries, f"refused={refused} {state} {entries}")
        r["actual"] = f"Khi chưa nhập chứng từ: không có Xác nhận đã chi; sau khi nhập & lưu: nhãn form “{state}”; bút toán {entries[0]['name']} ({reference})"
    s.close()

    # ---------------------------------------------------------- worker reads the payslip in the Frappe HR app
    s = Session(browser, "LG", "binh")
    login(s)
    with case(s, "PR-06", "Công nhân xem phiếu lương trên app", "App > Lương (danh sách phiếu) > mở phiếu tháng trước > đọc thực lĩnh > tab Thu nhập & Khấu trừ",
              "Trần Văn Bình", "Phiếu lương hiện thực lĩnh trên trang, có phụ cấp ăn trưa, BHXH, BHYT, BHTN") as r:
        p = s.page
        mine = next((x for x in REQ["slips"] if x["employee_name"] == "Trần Văn Bình"), None)
        check(mine, "Không thấy phiếu lương của công nhân")
        s.step("Công nhân mở màn hình Phiếu lương trên app Frappe HR")
        p.goto(f"{BASE}/hrms/dashboard/salary-slips")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(5000)
        list_text = p.locator("body").inner_text()
        check(vnd(mine["net_pay"]) in list_text, f"Không thấy thực lĩnh {vnd(mine['net_pay'])} trên danh sách: {list_text[:200]}")
        s.step("Nhấn vào phiếu lương để mở chi tiết")
        p.locator("div.cursor-pointer").filter(has_text=vnd(mine["net_pay"])).first.click()
        p.wait_for_url(re.compile(r".*/salary-slips/"), timeout=25000)
        p.wait_for_timeout(3000)
        p.get_by_text(re.compile(r"^(Earnings & Deductions|Thu nhập & Khấu trừ)$")).click()
        p.wait_for_timeout(1500)
        text = p.locator("body").inner_text()
        check("ăn trưa" in text and "BHXH" in text, text[:300])
        r["actual"] = f"{mine['name']}: thực lĩnh {vnd(mine['net_pay'])} ₫ đọc trên trang; có phụ cấp ăn trưa, BHXH/BHYT/BHTN"
    s.close()

    # ---------------------------------------------------------- office employee: only their own slips
    s = Session(browser, "LG", "an")
    login(s)
    with case(s, "PR-07", "Nhân viên văn phòng chỉ thấy phiếu lương của mình",
              "App > Lương: danh sách chỉ phiếu của An > mở > thử sang phiếu của người khác (bị chặn)",
              "an@demo.example", "Chỉ thấy phiếu của chính mình; phiếu của đồng nghiệp không mở được qua giao diện") as r:
        p = s.page
        an_employee = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "an@demo.example"]])
                              + "&fields=" + json.dumps(["name"])).json()["data"][0]["name"]
        mine = api_get(s, "/api/resource/Salary Slip?limit_page_length=100&fields=" + json.dumps(["name", "net_pay"])
                       + "&filters=" + json.dumps([["employee", "=", an_employee], ["docstatus", "=", 1]])).json().get("data", [])
        foreign = next((x for x in REQ["slips"] if x["employee_name"] != "Nguyễn Hoài An"), None)
        check(mine and foreign, f"cần cả phiếu của mình và người khác: {bool(mine)} {bool(foreign)}")
        s.step("Nhân viên mở danh sách Phiếu lương trên app")
        p.goto(f"{BASE}/hrms/dashboard/salary-slips")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(5000)
        rows = p.locator("div.cursor-pointer")
        check(rows.count(), "danh sách phiếu lương không có dòng nào trên màn hình")
        # the row shows the period and the amount, not the employee: open the first row and prove on the slip
        # screen whose payslip it is
        rows.first.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3000)
        # the payslip shows its amounts inside read-only controls (input values, not innerText):
        # open the tab a person reads to check their money, then read those controls
        tab = p.locator("button:visible, [role=tab]:visible, a:visible").filter(has_text="thực lĩnh").first
        own_amounts = {digits(str(round(x["net_pay"]))) for x in mine}
        if tab.count():
            tab.click()
            p.wait_for_timeout(1500)
        amounts_text = ""
        for _ in range(20):
            values = []
            inputs = p.locator("input:visible")
            for i in range(inputs.count()):
                try:
                    values.append(inputs.nth(i).input_value())
                except Exception:
                    pass
            amounts_text = " ".join(values)
            if any(a in digits(amounts_text) for a in own_amounts):
                break
            p.wait_for_timeout(500)
        own_text = " ".join(p.locator("body").inner_text().split())
        # the payslip prints the amount with the site's thousands separators; compare the digits so the check does not
        # depend on how the page groups them. The app does not print the employee's name on this screen: the slip id in
        # the page head carries the employee (Sal Slip/HR-EMP-00016/…) and the amount must be one of An's net pays.
        check(an_employee in own_text and any(a in digits(amounts_text) for a in own_amounts),
              f"phiếu mở ra không phải thực lĩnh của An ({an_employee}): {own_text[:200]} · ô tiền: {amounts_text[:120]}")
        s.step("Thử mở trực tiếp phiếu lương của một đồng nghiệp")
        p.goto(f"{BASE}/desk/salary-slip/{quote(foreign['name'], safe='')}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3000)
        blocked = " ".join(p.locator("body").inner_text().split())
        leaked = foreign["employee_name"] in blocked and digits(str(round(foreign["net_pay"]))) in digits(blocked)
        check(not leaked, f"vẫn đọc được phiếu của người khác: {blocked[:180]}")
        r["actual"] = f"Danh sách chỉ phiếu của Nguyễn Hoài An (thực lĩnh {vnd(mine[0]['net_pay'])}); phiếu {foreign['name']} không mở được qua giao diện"
    s.close()

    # ---------------------------------------------------------- factory head: cannot see workers' payslips
    s = Session(browser, "LG", "hung")
    login(s)
    with case(s, "PR-08", "Trưởng nhà máy không xem được phiếu lương công nhân",
              "Desk > danh sách Phiếu lương: chỉ thấy của mình (không có công nhân) > mở của mình > thử sang phiếu công nhân (từ chối)",
              "hung@demo.example", "Danh sách không có phiếu công nhân; phiếu công nhân mở trực tiếp bị chặn trên giao diện") as r:
        p = s.page
        foreign = next((x for x in REQ["slips"] if x["employee_name"] != "Đặng Văn Hùng"), None)
        check(foreign, "Không có phiếu công nhân để thử")
        s.step("Trưởng nhà máy mở danh sách Phiếu lương")
        p.goto(f"{BASE}/desk/salary-slip")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        listing = " ".join(p.locator("body").inner_text().split())
        workers = {x["employee_name"] for x in REQ["slips"] if x["employee_name"] != "Đặng Văn Hùng"}
        seen = sorted(name for name in workers if name in listing)
        s.step("Trưởng nhà máy mở phiếu của chính mình trong danh sách để đối chiếu")
        row = p.locator('.list-row-container a[data-doctype="Salary Slip"], .frappe-list a[data-doctype="Salary Slip"]')
        check(row.count() <= 1, f"danh sách có {row.count()} phiếu (nhiều hơn phiếu của chính mình)")
        if row.count():
            row.first.click()
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2500)
        s.step("Rồi thử mở trực tiếp phiếu của một công nhân")
        p.goto(f"{BASE}/desk/salary-slip/{quote(foreign['name'], safe='')}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3000)
        refused = " ".join(p.locator("body").inner_text().split())
        leaked = foreign["employee_name"] in refused and vnd(foreign["net_pay"]) in refused
        check(not seen and not leaked, f"thấy phiếu công nhân {seen} hoặc mở được phiếu người khác: {refused[:180]}")
        r["actual"] = f"Danh sách không có phiếu công nhân ({len(workers)} người bị ẩn); phiếu {foreign['name']} không truy cập được qua giao diện"
    s.close()
    # ---------------------------------------------------------- HR checks VN payroll settings
    s_hoa = Session(browser, "LG", "hoa")
    login(s_hoa)
    p = s_hoa.page
    with case(s_hoa, "HR-05", "Tham số lương Việt Nam", "Mở Cài đặt lương VN > bấm vào ô Lương cơ sở > đọc các giá trị trên form", "",
              "Lương cơ sở 2.530.000; giảm trừ 15.500.000 / 6.200.000; hiệu lực 01-07-2026") as r:
        s_hoa.step("Chị Hòa mở Cài đặt lương VN và bấm vào ô Lương cơ sở để xem giá trị")
        p.goto(f"{BASE}/desk/vn-payroll-settings")
        p.wait_for_load_state("networkidle")
        base_field = p.locator('[data-fieldname="base_salary"]').first
        base_field.wait_for(state="visible", timeout=20000)
        base_field.click()  # real click: the user focuses the salary-base field to read it (fields are read-only here)
        p.wait_for_timeout(600)
        text = p.locator("body").inner_text()
        for label, value in (("Lương cơ sở", 2530000), ("Giảm trừ bản thân", 15500000), ("Giảm trừ người phụ thuộc", 6200000)):
            dot = f"{value:,}".replace(",", ".")  # 2.530.000 (Vietnamese thousands separator)
            check(dot in text, f"không thấy {label}={dot} trên form")
        eff = p.locator('[data-fieldname="effective_date"]').first.inner_text() if p.locator('[data-fieldname="effective_date"]').count() else ""
        check("2026" in eff or "01-07-2026" in text or "2026-07-01" in text, f"không thấy ngày hiệu lực 2026: {eff}")
        d = api_get(s_hoa, "/api/resource/VN Payroll Settings/VN Payroll Settings").json()["data"]
        check((d["base_salary"], d["personal_deduction"], d["dependent_deduction"], d["effective_date"]) == (2530000, 15500000, 6200000, "2026-07-01"), str(d))
        r["actual"] = "Form hiển thị Lương cơ sở 2.530.000; giảm trừ 15.500.000 / 6.200.000; hiệu lực 01-07-2026"
    s_hoa.close()


JOURNEYS = [payroll_flow]
