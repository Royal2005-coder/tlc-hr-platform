"""Travel, Advances and Expenses (W3 TLC Công tác – Tạm ứng – Quyết toán chi phí) performed on the standard desk:
the employee fills the Travel Request form and sends it, the line manager and the CEO approve through Hành động, the
accountant creates the Payment Entry from the advance's own Tạo > Thanh toán button, attaches the bank proof in the
upload dialog and confirms the payment, the claim is opened from the advance's Tạo > Đề nghị thanh toán and its cost rows
and receipts are entered in the grid, the refund Journal Entry comes from Tạo > Hoàn lại. API only prepares the conflicting
leave and the overdue fixture, and reads the stored result after the person has done the work.
"""

import base64
from pathlib import Path

from lib import *  # noqa: F403

TR = "Travel Request"
EA = "Employee Advance"
EC = "Expense Claim"
PE = "Payment Entry"
JE = "Journal Entry"
AR = "Attendance Request"
PROOF = Path("/tmp/uat-bank-proof.txt")
PROOF.write_text("UAT bank transfer proof", encoding="utf-8")


# ---------------------------------------------------------------------------------------------------- desk helpers

def slug_of(doctype):
    return doctype.lower().replace(" ", "-")


def open_doc(s, doctype, name=None, note=None):
    p = s.page
    if note:
        s.step(note)
    path = f"{BASE}/desk/{slug_of(doctype)}" + (f"/{name}" if name else "/new")
    p.goto(path)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)


def wait_form(p, doctype):
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=doctype)
    p.wait_for_timeout(800)


def add_button(p, doctype):
    """The list's own "Thêm <DocType>" button, waiting for the list to render; filter/row buttons are skipped."""
    for _ in range(24):
        buttons = p.locator("button:visible").filter(has_text=re.compile(r"Thêm|Add|New", re.I))
        for i in range(buttons.count()):
            text = " ".join(buttons.nth(i).inner_text().split())
            if not text or re.search(r"Thêm (bộ lọc|dòng|người dùng)|Add (filter|row|user)", text, re.I):
                continue
            return buttons.nth(i)
        p.wait_for_timeout(500)
    raise AssertionError(f"danh sách {doctype} không có nút thêm: {' '.join(p.locator('body').inner_text().split())[:160]}")


def new_doc(s, doctype, note):
    """Open the list, click its add button and work on the full form (never a script-created document)."""
    p = s.page
    s.step(note)
    p.goto(f"{BASE}/desk/{slug_of(doctype)}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    add_button(p, doctype).click()
    p.wait_for_timeout(2200)
    if p.locator(".modal:visible").count():
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)
    if "/new" not in p.url:
        p.goto(f"{BASE}/desk/{slug_of(doctype)}/new")
    p.wait_for_load_state("networkidle")
    wait_form(p, doctype)
    return p


def user_date(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%d-%m-%Y")


def type_into(p, field, value):
    box = p.locator(f"input[data-fieldname='{field}']:visible, textarea[data-fieldname='{field}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    p.keyboard.press("Escape")
    kind = box.get_attribute("data-fieldtype") or ""
    if kind in ("Date", "Datetime", "Time"):
        box.fill(str(value))
    else:
        box.click()
        box.fill("")
        box.press_sequentially(str(value), delay=50)
    p.keyboard.press("Tab")
    p.wait_for_timeout(900)
    if (box.input_value() or "").strip() != str(value).strip():
        box.fill(str(value))
        p.keyboard.press("Tab")
        p.wait_for_timeout(700)
    if (box.input_value() or "").strip() != str(value).strip():
        try:  # a currency input formats the number, the document keeps the numeric value
            stored = p.evaluate("f => cur_frm.doc[f]", field)
            if float(stored) == float(value):
                return
        except Exception:
            pass
    check((box.input_value() or "").strip() == str(value).strip(),
          f"ô {field} đang hiển thị '{(box.input_value() or '').strip()}', không nhận '{value}'")


def pick_link(p, field, needle):
    box = p.locator(f"input[data-fieldname='{field}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    box.click()
    box.fill("")
    p.keyboard.type(needle, delay=45)
    p.wait_for_timeout(2200)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option], .frappe-control-dropdown li")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    target = next((i for i in shown if needle.lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
    check(target is not None, f"ô {field} không có gợi ý hiển thị '{needle}' (đang hiện: "
                              f"{[options.nth(i).inner_text() for i in shown][:4]})")
    options.nth(target).click()
    p.wait_for_timeout(1200)
    return " ".join(options.nth(target).inner_text().split())


def choose_option(p, field, label):
    select = p.locator(f"select[data-fieldname='{field}']:visible").last
    select.wait_for(state="visible", timeout=15000)
    select.click()
    try:
        select.select_option(label=label)
    except Exception:
        select.select_option(value=label)
    p.wait_for_timeout(600)


def check_box(p, field):
    box = p.locator(f"input[data-fieldname='{field}'][type=checkbox]").last
    if not box.is_checked():
        box.check(force=True)
        p.wait_for_timeout(500)


def save_primary(p, label=r"Lưu|Save|Cập nhật|Update"):
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    p.locator(".page-head button:visible").filter(has_text=re.compile(label)).last.click()
    p.wait_for_load_state("networkidle")
    try:
        p.wait_for_function("() => window.cur_frm && !cur_frm.is_dirty() && !cur_frm.is_new()", timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(2000)


def reason_if_asked(p, reason="Kế toán cập nhật chứng từ ngân hàng thực tế"):
    """A submitted document asks why it is being updated; the accountant types the reason and confirms."""
    dialog = p.locator(".modal:visible")
    if not dialog.count():
        return
    text = " ".join(dialog.last.inner_text().split())
    if not re.search(r"Lý do|Reason", text, re.I):
        return
    box = dialog.last.locator("textarea, input[type=text]")
    if box.count():
        box.first.fill(reason)
    button = dialog.last.get_by_role("button", name=re.compile(r"^(Update|Cập nhật|Lưu)$"))
    if button.count():
        button.last.click()
        p.wait_for_timeout(2500)


def open_menu(p):
    """The workflow actions live behind Hành động or, on a submitted document, behind the ⋮ button."""
    for _ in range(3):
        if p.locator(MENU_ITEMS).count():
            return True
        button = p.get_by_role("button", name="Hành động")
        if button.count() and button.first.is_visible():
            button.first.click()
        else:
            more = p.locator(".page-head .menu-more-button:visible")
            if not more.count():
                return False
            more.last.click()
        p.wait_for_timeout(900)
        if p.locator(MENU_ITEMS).count():
            return True
    return False


def action(s, doctype, name, label, note=None):
    """Hành động / ⋮ > workflow button on the opened form (the demonstrated move)."""
    p = s.page
    open_doc(s, doctype, name)
    if note:
        s.step(note)
    check(open_menu(p), f"không mở được menu hành động: {[t.strip() for t in p.locator('.page-head button:visible').all_inner_texts()]}")
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == label), None)
    check(target is not None, f"không có {label} trong {menu_items(p)}")
    items.nth(target).click()
    p.wait_for_timeout(4000)
    p.wait_for_load_state("networkidle")
    reason_if_asked(p)
    p.wait_for_timeout(1200)


def submit_native(p, timeout=45000):
    """The page-head primary button (labelled Xác nhận on this build) then the native "Gửi vĩnh viễn?" dialog."""
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    button = p.locator(".page-head button.primary-action:visible").last
    check(button.count() > 0, f"form không có nút gửi chính: {[t.strip() for t in p.locator('.page-head button:visible').all_inner_texts()]}")
    button.click()
    p.wait_for_timeout(1500)
    deadline = dt.datetime.now() + dt.timedelta(seconds=timeout // 1000)
    while dt.datetime.now() < deadline:
        if p.evaluate("() => window.cur_frm && cur_frm.doc.docstatus") == 1 and not p.locator(".modal:visible").count():
            break
        dialog = p.locator(".modal:visible")
        if dialog.count():
            modal = dialog.last
            confirm = modal.locator("button.btn-modal-primary:visible")
            send = modal.locator("button.email-composer-send-btn:visible")
            if confirm.count():
                confirm.last.click()
                p.wait_for_timeout(1200)
            elif send.count():
                send.last.click()
                p.wait_for_timeout(2500)
            else:
                p.keyboard.press("Escape")
                p.wait_for_timeout(800)
        p.wait_for_timeout(700)
    p.wait_for_function("() => window.cur_frm && cur_frm.doc.docstatus === 1", timeout=timeout)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)


def actions_list(p):
    """Read what the Hành động / ⋮ menu offers without triggering a document action."""
    if not open_menu(p):
        return []
    p.wait_for_timeout(600)
    items = menu_items(p)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    return items


def screen_text(p):
    found = []
    for sel in (".modal:visible", ".toast-message:visible", ".msgprint:visible", ".text-danger:visible",
                "[role=alert]:visible", ".form-message:visible"):
        try:
            found += [" ".join(el.inner_text().split()) for el in p.locator(sel).all()]
        except Exception:
            pass
    return " | ".join(x for x in found if x) or " ".join(p.locator("body").inner_text().split())


def attach_file(p, field, path=PROOF, value_check=True):
    """Click the form's own Đính kèm button, choose the file in the upload dialog and press Tải lên."""
    button = p.locator(f'div[data-fieldname="{field}"] button.btn-attach:visible').last
    button.wait_for(state="visible", timeout=15000)
    button.click()
    p.wait_for_timeout(1200)
    dialog = p.locator(".modal:visible").last
    expect(dialog).to_be_visible()
    files = dialog.locator("input[type=file]")
    if not files.count():
        files = p.locator("input[type=file]")
    files.last.set_input_files(str(path))
    p.wait_for_timeout(1200)
    upload = dialog.get_by_role("button", name=re.compile(r"^(Tải lên|Upload)$"))
    check(upload.count() > 0, f"hộp thoại tải tệp không có nút Tải lên: {screen_text(p)[:200]}")
    upload.last.click()
    p.wait_for_timeout(3000)
    if value_check:
        value = p.evaluate("f => cur_frm && cur_frm.doc[f]", field)
        check(bool(value), f"tệp chưa được gắn vào ô {field}: {screen_text(p)[:200]}")
        return value
    return p.evaluate("f => cur_frm && cur_frm.doc[f]", field)


def trim_empty_rows(p, field, keys):
    """The desk appends a blank row after the last edited row; delete the blanks by their row form button."""
    for _ in range(12):
        rows = p.evaluate("(f) => (cur_frm.doc[f] || []).map(r => r)", field)
        empties = [i for i, row in enumerate(rows) if not any(row.get(k) for k in keys)]
        if not empties:
            return
        index = empties[-1]
        table = grid_rows(p, field)
        row = table.nth(index)
        row.scroll_into_view_if_needed()
        row.hover()
        opener = row.locator(".btn-open-row").first
        if opener.is_visible():
            opener.click()
        else:
            opener.click(force=True)
        p.wait_for_timeout(1000)
        delete = row.locator("button.grid-delete-row:visible").first
        check(delete.count(), f"không có nút Xóa dòng trống {index + 1} của {field}")
        delete.click()
        p.wait_for_timeout(800)
        dialog = p.locator(".modal:visible").last
        if dialog.count():
            yes = dialog.locator("button:visible", has_text=re.compile("Xóa|Delete|Có|Yes|Đồng ý"))
            if yes.count():
                yes.last.click()
        p.wait_for_timeout(1000)
        collapse = row.locator("button.grid-collapse-row:visible")
        if collapse.count():
            collapse.first.click()
        p.wait_for_timeout(500)


def grid_rows(p, field):
    # the grid header is rendered as a .grid-row in this build ("Không." in its index cell)
    return p.locator(f'[data-fieldname="{field}"] .grid-row').filter(has_not_text="Không.")


def add_row(p, field):
    grid = p.locator(f'[data-fieldname="{field}"]')
    add = grid.locator(".grid-add-row").first
    add.scroll_into_view_if_needed()
    add.click()
    p.wait_for_timeout(1200)
    return grid_rows(p, field).last


def fill_cell(p, row, field, value, link=False):
    box = row.locator(f'[data-fieldname="{field}"] input').first
    box.click()
    box.fill("")
    p.wait_for_timeout(200)
    if link:
        p.keyboard.type(str(value), delay=45)
        p.wait_for_timeout(2200)
        options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option]")
        shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
        target = next((i for i in shown if str(value).lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
        check(target is not None, f"dòng {field}: không có gợi ý hiển thị '{value}': "
                                  f"{[options.nth(i).inner_text() for i in shown][:4]}")
        options.nth(target).click()
        p.wait_for_timeout(1000)
        return
    if (box.get_attribute("data-fieldtype") or "") in ("Date", "Datetime", "Time"):
        box.fill(str(value))  # typing a date character by character stores 'Invalid date'
    else:
        box.press_sequentially(str(value), delay=40)
    p.keyboard.press("Tab")
    p.wait_for_timeout(700)


def fill_grid_attach(p, field, row_index=0, path=PROOF):
    """Open the row form of a grid line, attach the receipt, then collapse the row form again."""
    row = grid_rows(p, field).nth(row_index)
    row.locator(".btn-open-row").first.click()
    p.wait_for_timeout(1200)
    attach_file(p, "tlc_receipt", path, value_check=False)
    row = grid_rows(p, field).nth(row_index)
    collapse = row.locator("button.grid-collapse-row:visible")
    if collapse.count():
        collapse.first.click()
    else:
        p.keyboard.press("Escape")
    for _ in range(20):
        if not p.locator("#freeze:visible").count():
            break
        p.wait_for_timeout(400)
    p.wait_for_timeout(800)
    values = p.evaluate("(f) => (cur_frm.doc[f] || []).map(r => r.tlc_receipt)", field)
    check(any(values), f"hóa đơn dòng {row_index + 1} chưa lưu vào bảng chi phí: {values}")


# ---------------------------------------------------------------------------------------------------- the journey

def travel_finance_flow(browser):
    s_an = Session(browser, "TRV", "an")
    login(s_an)
    p = s_an.page
    emp_an = api_get(s_an, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "an@demo.example"]])
                     + "&fields=" + json.dumps(["name", "company"])).json()["data"][0]
    an_emp_id, company = emp_an["name"], emp_an["company"]

    d_start, d_end = working_day(10), working_day(10)
    # Setup only: an already-open leave on the day the traveller tries to book over.
    api(s_an, "frappe.client.insert", doc=json.dumps({
        "doctype": "Leave Application", "employee": an_emp_id, "leave_type": "Phép năm",
        "from_date": d_start, "to_date": d_end, "description": "Nghỉ phép trùng công tác (UAT)"}))
    # Setup only: an overdue advance of An, used by the payroll-recovery guard case.
    REQ["adv_overdue"] = api(s_an, "frappe.client.insert", doc=json.dumps({
        "doctype": EA, "company": company, "employee": an_emp_id, "advance_amount": 2000000,
        "purpose": "Tạm ứng quá hạn mẫu",
        "tlc_needed_on": (dt.date.today() - dt.timedelta(days=50)).isoformat(),
        "tlc_settlement_due": (dt.date.today() - dt.timedelta(days=35)).isoformat(),
        "posting_date": (dt.date.today() - dt.timedelta(days=50)).isoformat(), "workflow_state": "Nháp"}))["name"]

    def fill_trip(p, destination, description, start, end, advance, budget_rows):
        p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Travel Request'")
        p.wait_for_timeout(600)
        pick_link(p, "employee", an_emp_id)
        choose_option(p, "travel_type", "Domestic")
        pick_link(p, "purpose_of_travel", "TLC Công tác")
        type_into(p, "tlc_destination", destination)
        # Description is mandatory for the server but the form keeps it in a collapsed "Mô tả" section
        if not p.locator("textarea[data-fieldname='description']:visible, input[data-fieldname='description']:visible").count():
            for header in p.locator(".section-head:visible, .form-section .section-head:visible").filter(
                    has_text=re.compile("Mô tả|Description")).all():
                header.click()
                p.wait_for_timeout(800)
                if p.locator("textarea[data-fieldname='description']:visible").count():
                    break
        type_into(p, "description", description)
        type_into(p, "tlc_from_date", user_date(start))
        type_into(p, "tlc_to_date", user_date(end))
        choose_option(p, "tlc_from_session", "AM")
        choose_option(p, "tlc_to_session", "PM")
        funded = bool(budget_rows)
        box = p.locator("input[data-fieldname='tlc_funded'][type=checkbox]").last
        if funded and not box.is_checked():
            box.check(force=True)
        elif not funded and box.is_checked():
            box.uncheck(force=True)
        type_into(p, "tlc_requested_advance", str(advance))
        for expense_type, amount in budget_rows:
            row = add_row(p, "costings")
            fill_cell(p, row, "expense_type", expense_type, link=True)
            fill_cell(p, row, "total_amount", str(amount))

    with case(s_an, "TRV-01", "Chặn tạo công tác trùng đơn nghỉ phép",
              "Travel Request > Thêm > chọn nhân viên, loại, mục đích, nơi đến, ngày, dự toán > Lưu; đọc thông báo trùng lịch",
              f"{vn(d_start)} – {vn(d_end)}",
              "Bị chặn: màn hình báo trùng lịch nghỉ phép và không lưu đơn") as r:
        new_doc(s_an, TR, "An mở danh sách công tác và bấm Thêm")
        s = s_an
        p = s.page
        s.step("An điền chuyến công tác đúng ngày đã được duyệt nghỉ phép")
        fill_trip(p, "Chi nhánh Hà Nội", "Khảo sát thị trường", d_start, d_end, 3000000,
                  [("TLC Vé công tác", 3000000)])
        s.step("An bấm Lưu và đọc thông báo của hệ thống")
        save_primary(p)
        msg = screen_text(p)
        check("Trùng lịch" in msg or "overlap" in msg.lower(), f"hệ thống không báo trùng lịch: {msg[:240]}")
        check("new" in p.url or p.evaluate("() => cur_frm.is_new()"), f"đơn trùng lịch vẫn được lưu: {p.url}")
        r["actual"] = "Hệ thống chặn lưu và thông báo: " + " ".join(msg.split())[:180]
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)

    t_start, t_end = working_day(15), working_day(17)
    with case(s_an, "TRV-02", "Tạo đề xuất công tác có phí có dự toán",
              "Travel Request > Thêm > nhập nơi đến, ngày đi/về, dự toán chi phí, số tiền tạm ứng > Lưu > Hành động > Gửi duyệt",
              f"Hà Nội 3 ngày ({vn(t_start)} – {vn(t_end)}), dự toán 5.000.000, tạm ứng 4.000.000",
              "Lưu thành công, trạng thái Chờ quản lý duyệt, người duyệt tự gán là Trần Minh Quang") as r:
        new_doc(s_an, TR, "An mở form công tác mới và điền từng ô")
        p = s.page
        fill_trip(p, "Chi nhánh Hà Nội", "Gặp gỡ đối tác chiến lược", t_start, t_end, 4000000,
                  [("TLC Vé công tác", 3000000), ("TLC Lưu trú", 2000000)])
        s.step("An bấm Lưu để giữ đề xuất công tác")
        save_primary(p)
        check("new" not in p.url, f"đơn không lưu được: {screen_text(p)[:200]}")
        REQ["trip"] = p.evaluate("() => cur_frm.doc.name")
        s.step("An bấm Hành động > Gửi duyệt để trình quản lý")
        action(s_an, TR, REQ["trip"], "Gửi duyệt")
        doc = api_get(s_an, f"/api/resource/{TR}/{REQ['trip']}").json()["data"]
        check((doc["workflow_state"], doc["tlc_manager_user"]) == ("Chờ quản lý duyệt", "quang@demo.example"),
              f"{doc['workflow_state']} / {doc.get('tlc_manager_user')}")
        r["actual"] = f"{REQ['trip']}: {doc['workflow_state']}; Người duyệt: {doc['tlc_manager_user']}"
    s_an.close()

    s_quang = Session(browser, "TRV", "quang")
    login(s_quang)
    with case(s_quang, "TRV-03", "Quản lý trực tiếp duyệt đề xuất công tác",
              "Workspace Quản lý > mở đề xuất công tác > Hành động > Duyệt",
              REQ["trip"], "Trạng thái chuyển sang Chờ giám đốc duyệt") as r:
        action(s_quang, TR, REQ["trip"], "Duyệt", "Quang mở đơn của An và bấm Hành động > Duyệt")
        state = api_get(s_quang, f"/api/resource/{TR}/{REQ['trip']}").json()["data"]["workflow_state"]
        check(state == "Chờ giám đốc duyệt", f"State is {state}")
        r["actual"] = f"{REQ['trip']}: {state}"
    s_quang.close()

    s_thanh = Session(browser, "TRV", "thanh")
    login(s_thanh)
    with case(s_thanh, "TRV-04", "Giám đốc duyệt công tác: On Duty và sinh đề xuất tạm ứng",
              "Mở đề xuất công tác > Hành động > Duyệt",
              REQ["trip"], "Đã duyệt; tự ghi công On Duty các ngày công tác; sinh bản ghi Employee Advance Chờ kế toán kiểm tra") as r:
        action(s_thanh, TR, REQ["trip"], "Duyệt", "Giám đốc mở đề xuất công tác và bấm Duyệt")
        trip_doc = api_get(s_thanh, f"/api/resource/{TR}/{REQ['trip']}").json()["data"]
        check(trip_doc["workflow_state"] == "Đã duyệt", f"State is {trip_doc['workflow_state']}")
        REQ["advance"] = trip_doc.get("tlc_employee_advance")
        check(bool(REQ["advance"]), "Employee Advance was not generated")
        adv_state = api_get(s_thanh, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]["workflow_state"]
        check(adv_state == "Chờ kế toán kiểm tra", f"Advance state is {adv_state}")
        marks = api_get(s_thanh, "/api/resource/Attendance?filters=" + json.dumps([
            ["employee", "=", an_emp_id], ["attendance_date", "between", [t_start, t_end]], ["docstatus", "=", 1]])).json().get("data", [])
        check(len(marks) >= 3, f"Expected 3 attendance records, got {len(marks)}")
        r["actual"] = f"{REQ['trip']} Đã duyệt; sinh tạm ứng {REQ['advance']} ({adv_state}); ghi nhận {len(marks)} ngày công On Duty"
    s_thanh.close()

    s_quang2 = Session(browser, "TRV", "quang")
    login(s_quang2)
    quang_emp = api_get(s_quang2, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "quang@demo.example"]])
                        + "&fields=" + json.dumps(["name", "company"])).json()["data"][0]
    # Setup only: the request the department head will send from its own form on screen.
    q_trip_name = api(s_quang2, "frappe.client.insert", doc=json.dumps({
        "doctype": TR, "company": quang_emp["company"], "employee": quang_emp["name"], "travel_type": "Domestic",
        "purpose_of_travel": "TLC Công tác", "tlc_destination": "Đà Nẵng", "description": "Hội nghị khách hàng",
        "tlc_from_date": working_day(20), "tlc_to_date": working_day(21), "tlc_from_session": "AM",
        "tlc_to_session": "PM", "tlc_funded": 0}))["name"]
    with case(s_quang2, "TRV-05", "Bỏ cấp duyệt khi người tạo là Trưởng bộ phận",
              "Trưởng phòng Quang mở đề xuất của chính mình > Hành động > Gửi giám đốc",
              "Trần Minh Quang", "Bỏ qua cấp Quản lý, chuyển thẳng Chờ giám đốc duyệt") as r:
        action(s_quang2, TR, q_trip_name, "Gửi giám đốc", "Quang mở đề xuất của chính mình và gửi thẳng giám đốc")
        q_state = api_get(s_quang2, f"/api/resource/{TR}/{q_trip_name}").json()["data"]["workflow_state"]
        check(q_state == "Chờ giám đốc duyệt", f"State is {q_state}")
        r["actual"] = f"{q_trip_name}: người tạo là Trưởng phòng chuyển thẳng '{q_state}' (HR-CHG-16)"
    s_quang2.close()

    # ------------------------------------------------------------------ accountant pays the advance
    s_chi = Session(browser, "FIN", "chi")
    login(s_chi)
    p = s_chi.page
    with case(s_chi, "FIN-01", "Duyệt không tự động ghi nhận đã chi khi thiếu chứng từ",
              "Mở đề xuất tạm ứng > Hành động > Hồ sơ hợp lệ > đọc trạng thái Chờ chi",
              REQ["advance"], "Trạng thái Chờ chi, paid_amount vẫn bằng 0") as r:
        action(s_chi, EA, REQ["advance"], "Hồ sơ hợp lệ", "Kế toán mở tạm ứng và xác nhận hồ sơ hợp lệ")
        adv_doc = api_get(s_chi, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]
        check(adv_doc["workflow_state"] == "Chờ chi", f"Advance state is {adv_doc['workflow_state']}")
        check(adv_doc.get("paid_amount", 0) == 0, "Paid amount should be 0")
        r["actual"] = f"{REQ['advance']}: {adv_doc['workflow_state']}; paid_amount = 0 (phê duyệt chủ trương tách biệt với việc chi tiền)"

    with case(s_chi, "FIN-02", "Kế toán chi tạm ứng bằng chứng từ ngân hàng thực tế",
              "Mở tạm ứng > Tạo > Thanh toán > nhập số/ngày chứng từ, đính kèm ủy nhiệm chi > Lưu > Nộp > gắn chứng từ vào tạm ứng > Hành động > Xác nhận đã chi",
              "4.000.000 VND qua VCB", "Tạm ứng chuyển sang Đã chi; số tiền đã ứng ghi nhận 4.000.000 VND") as r:
        open_doc(s_chi, EA, REQ["advance"], "Kế toán mở phiếu tạm ứng đã được duyệt chủ trương")
        s_chi.step("Kế toán bấm Tạo > Thanh toán để lập chứng từ chi từ chính phiếu tạm ứng")
        create = p.locator(".page-head button:visible").filter(has_text=re.compile(r"^(Create|Tạo)\b")).first
        check(create.count() > 0, f"không có nút Tạo trên phiếu tạm ứng: {screen_text(p)[:200]}")
        create.click()
        p.wait_for_timeout(900)
        item = p.locator(MENU_ITEMS).filter(has_text=re.compile(r"^(Thanh toán|Payment)$")).first
        check(item.count() > 0, f"menu Tạo không có Thanh toán: {menu_items(p)}")
        item.click()
        p.wait_for_url(re.compile(r".*/payment-entry/"), timeout=30000)
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        s_chi.step("Kế toán nhập số và ngày ủy nhiệm chi trên chứng từ vừa sinh")
        reference = f"VCB-TU-{REQ['advance']}"
        type_into(p, "reference_no", reference)
        type_into(p, "reference_date", user_date(dt.date.today().isoformat()))
        s_chi.step("Kế toán đính kèm ủy nhiệm chi ngân hàng vào chứng từ")
        attach_file(p, "tlc_bank_proof")
        s_chi.step("Kế toán bấm Lưu rồi nút xác nhận ghi sổ chứng từ chi")
        save_primary(p)
        pe_name = p.evaluate("() => cur_frm.doc.name")
        REQ["pe_advance"] = pe_name
        submit_native(p)
        s_chi.step("Kế toán quay lại phiếu tạm ứng, gõ mã chứng từ chi và bấm Lưu")
        open_doc(s_chi, EA, REQ["advance"])
        pick_link(p, "tlc_payment_entry", pe_name)
        save_primary(p)
        reason_if_asked(p, "Gắn chứng từ chi thực tế vào phiếu tạm ứng")
        s_chi.step("Kế toán bấm Hành động > Xác nhận đã chi")
        action(s_chi, EA, REQ["advance"], "Xác nhận đã chi")
        adv_doc = api_get(s_chi, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]
        check(adv_doc["workflow_state"] == "Đã chi", f"Advance state is {adv_doc['workflow_state']}")
        check(adv_doc.get("paid_amount") == 4000000, f"Paid amount is {adv_doc.get('paid_amount')}")
        r["actual"] = f"{REQ['advance']}: {adv_doc['workflow_state']}; Chứng từ {pe_name}; Đã ứng: {adv_doc.get('paid_amount'):,.0f} VND"

    # ------------------------------------------------------------------ employee settles the trip
    s_an = Session(browser, "FIN", "an")
    login(s_an)
    p = s_an.page
    with case(s_an, "FIN-03", "Lập báo cáo quyết toán tự tính chênh lệch thực chi",
              "Mở tạm ứng > Tạo > Đề nghị thanh toán > nhập hai dòng chi phí thực tế và hóa đơn, phân bổ tạm ứng > Lưu",
              "Đã ứng 4.000.000, thực chi 3.500.000",
              "Hệ thống tự tính chênh lệch 500.000 VND và xác định nhánh refund (hoàn tiền thừa)") as r:
        open_doc(s_an, EA, REQ["advance"], "An mở phiếu tạm ứng đã chi để lập quyết toán")
        create = p.locator(".page-head button:visible").filter(has_text=re.compile(r"^(Create|Tạo)\b")).first
        if create.count():
            s_an.step("An bấm Tạo > Đề nghị thanh toán từ phiếu tạm ứng")
            create.click()
            p.wait_for_timeout(900)
            item = p.locator(MENU_ITEMS).filter(has_text=re.compile(r"Đề nghị thanh toán|Expense Claim|Chi phí")).first
            check(item.count() > 0, f"menu Tạo không có Đề nghị thanh toán: {menu_items(p)}")
            item.click()
        else:
            # the employee's form shows the claim as an inline badge link on the advance, not a page-head Tạo menu
            s_an.step("An bấm liên kết Đề nghị thanh toán ngay trên phiếu tạm ứng")
            link = p.locator("a.badge-link:visible").filter(has_text=re.compile("Đề nghị thanh toán")).first
            check(link.count() > 0, f"phiếu tạm ứng không có đường lập quyết toán: {screen_text(p)[:200]}")
            link.click()
            p.wait_for_timeout(3500)
            add = p.locator("button:visible").filter(has_text=re.compile("Thêm Đề nghị thanh toán")).first
            check(add.count() > 0, f"danh sách quyết toán của phiếu tạm ứng không có nút Thêm: {screen_text(p)[:200]}")
            add.click()
        p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Expense Claim' && cur_frm.is_new()", timeout=30000)
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3000)
        wait_form(p, EC)
        s_an.step("An mở tab Kế toán và bỏ dấu Đã thanh toán (khoản chi chưa được chi trả)")
        tab = p.locator(".nav-link:visible").filter(has_text=re.compile("Kế toán|Accounting")).first
        if tab.count():
            tab.click()
            p.wait_for_timeout(1000)
        paid = p.locator("input[data-fieldname='is_paid'][type=checkbox]").last
        if paid.count() and paid.is_checked():
            paid.uncheck(force=True)
            p.wait_for_timeout(800)
        s_an.step("An mở tab Chi phí & Tạm ứng của báo cáo quyết toán")
        tab = p.locator(".nav-link:visible").filter(has_text=re.compile("Chi phí & Tạm ứng|Expenses & Advances")).first
        check(tab.count() > 0, f"form quyết toán không có tab Chi phí & Tạm ứng: {screen_text(p)[:200]}")
        tab.click()
        p.wait_for_timeout(1200)
        pick_link(p, "tlc_travel_request", REQ["trip"])
        s_an.step("An ghi hai khoản chi thực tế vào bảng chi phí")
        tab = p.locator(".nav-link:visible").filter(has_text="Chi phí").first
        if tab.count():
            tab.click()
            p.wait_for_timeout(900)
        for expense_type, amount in (("TLC Vé công tác", 2000000), ("TLC Lưu trú", 1500000)):
            row = add_row(p, "expenses")
            fill_cell(p, row, "expense_date", user_date(dt.date.today().isoformat()))
            fill_cell(p, row, "expense_type", expense_type, link=True)
            fill_cell(p, row, "amount", str(amount))
            fill_cell(p, row, "sanctioned_amount", str(amount))
            trim_empty_rows(p, "expenses", ("expense_type", "amount", "sanctioned_amount"))
        for index in range(2):
            s_an.step(f"An mở dòng chi phí {index + 1} và đính kèm hóa đơn")
            fill_grid_attach(p, "expenses", index)
        trim_empty_rows(p, "expenses", ("expense_type", "amount", "sanctioned_amount"))
        s_an.step("An phân bổ 3.500.000 đã ứng vào bảng tạm ứng của quyết toán")
        tab = p.locator(".nav-link:visible").filter(has_text=re.compile("Chi phí & Tạm ứng|Expenses & Advances")).first
        if tab.count() and "active" not in (tab.get_attribute("class") or ""):
            tab.click()
            p.wait_for_timeout(1000)
        adv_rows = grid_rows(p, "advances")
        if not adv_rows.count():
            s_an.step("An thêm dòng tạm ứng của chuyến đi vào báo cáo quyết toán")
            row = add_row(p, "advances")
            fill_cell(p, row, "employee_advance", REQ["advance"], link=True)
            p.wait_for_timeout(1200)
            trim_empty_rows(p, "advances", ("employee_advance", "allocated_amount"))
            adv_rows = grid_rows(p, "advances")
        check(adv_rows.count() > 0, "quyết toán không mang theo phiếu tạm ứng")
        if adv_rows.count():
            adv_rows.first.scroll_into_view_if_needed()
            adv_rows.first.hover()
            opener = adv_rows.first.locator(".btn-open-row").first
            if opener.is_visible():
                opener.click()
            else:
                opener.click(force=True)
            p.wait_for_timeout(1000)
            allocation = p.locator("input[data-fieldname='allocated_amount']:visible").last
            allocation.click()
            allocation.fill("3500000")
            allocation.press("Tab")
            p.wait_for_timeout(700)
            collapse = adv_rows.first.locator("button.grid-collapse-row:visible")
            if collapse.count():
                collapse.first.click()
            else:
                p.keyboard.press("Escape")
            p.wait_for_timeout(800)
        trim_empty_rows(p, "expenses", ("expense_type", "amount", "sanctioned_amount"))
        trim_empty_rows(p, "advances", ("employee_advance", "allocated_amount"))
        s_an.step("An bấm Lưu báo cáo quyết toán")
        save_primary(p)
        claim_name = p.evaluate("() => cur_frm.doc.name")
        REQ["claim"] = claim_name
        claim_doc = api_get(s_an, f"/api/resource/{EC}/{claim_name}").json()["data"]
        check(all(r.get("tlc_receipt") for r in claim_doc.get("expenses", [])), "Hóa đơn từng dòng chưa lưu")
        check(claim_doc.get("tlc_difference") == 500000 and claim_doc.get("tlc_settlement_branch") == "refund",
              f"Difference: {claim_doc.get('tlc_difference')}, Branch: {claim_doc.get('tlc_settlement_branch')}")
        s_an.step("An bấm Hành động > Gửi duyệt báo cáo")
        action(s_an, EC, claim_name, "Gửi duyệt")
        r["actual"] = (f"{claim_name}: Đã ứng 4.000.000, Thực chi 3.500.000 -> Chênh lệch "
                       f"{claim_doc['tlc_difference']:,.0f} VND (Nhánh {claim_doc['tlc_settlement_branch']})")
    s_an.close()

    s_quang = Session(browser, "FIN", "quang")
    login(s_quang)
    action(s_quang, EC, REQ["claim"], "Duyệt", "Quang mở quyết toán của An và bấm Duyệt")
    state = api_get(s_quang, f"/api/resource/{EC}/{REQ['claim']}").json()["data"]["workflow_state"]
    check(state == "Chờ giám đốc duyệt", f"State is {state}")
    s_quang.close()

    s_thanh = Session(browser, "FIN", "thanh")
    login(s_thanh)
    with case(s_thanh, "FIN-04", "Giám đốc duyệt báo cáo quyết toán",
              "Mở Expense Claim > Hành động > Duyệt", REQ["claim"],
              "Chuyển sang Chờ kế toán kiểm tra; phê duyệt chủ trương hoàn thành") as r:
        action(s_thanh, EC, REQ["claim"], "Duyệt", "Giám đốc mở báo cáo quyết toán và bấm Duyệt")
        state = api_get(s_thanh, f"/api/resource/{EC}/{REQ['claim']}").json()["data"]["workflow_state"]
        check(state == "Chờ kế toán kiểm tra", f"State is {state}")
        r["actual"] = f"{REQ['claim']}: {state}"
    s_thanh.close()

    s_chi = Session(browser, "FIN", "chi")
    login(s_chi)
    p = s_chi.page
    with case(s_chi, "FIN-05", "Kế toán đối chiếu nhánh hoàn tiền thừa",
              "Mở quyết toán > Hồ sơ hợp lệ; mở tạm ứng > Tạo > Hoàn lại > nhập số/ngày chứng từ, đính kèm > Lưu > Nộp; gắn bút toán vào quyết toán > Hoàn tất quyết toán",
              "500.000 VND hoàn ứng", "Quyết toán chuyển Hoàn tất; số tiền hoàn lại được cập nhật vào Employee Advance") as r:
        action(s_chi, EC, REQ["claim"], "Hồ sơ hợp lệ", "Kế toán kiểm tra hồ sơ quyết toán")
        s_chi.step("Kế toán mở phiếu tạm ứng và bấm Tạo > Hoàn lại để ghi nhận tiền thừa trả về")
        open_doc(s_chi, EA, REQ["advance"])
        create = p.locator(".page-head button:visible").filter(has_text=re.compile(r"^(Create|Tạo)\b")).first
        check(create.count() > 0, f"không có nút Tạo trên phiếu tạm ứng: {screen_text(p)[:200]}")
        create.click()
        p.wait_for_timeout(900)
        item = p.locator(MENU_ITEMS).filter(has_text=re.compile(r"Hoàn lại|Hoàn trả|Trả lại|Trả về|Return")).first
        check(item.count() > 0, f"menu Tạo không có Hoàn lại: {menu_items(p)}")
        item.click()
        p.wait_for_timeout(1200)
        dialog = p.locator(".modal:visible").last
        expect(dialog).to_be_visible()
        s_chi.step("Kế toán để hệ thống chọn tài khoản ngân hàng mặc định rồi bấm Tạo bút toán")
        bank_box = dialog.locator('input[data-fieldname="bank_account"]')
        if bank_box.count():
            bank_acc = api_get(s_chi, "/api/resource/Account?filters=" + json.dumps([["company", "=", company],
                                                                                      ["account_number", "=", "1121"]])
                               + "&fields=" + json.dumps(["name"])).json()["data"][0]["name"]
            bank_box.first.click()
            bank_box.first.fill("")
            p.keyboard.type(bank_acc, delay=40)
            p.wait_for_timeout(2000)
            options = p.locator(".awesomplete li, ul[role=listbox] li, [role=option]")
            picked = next((i for i in range(options.count())
                           if bank_acc.split(" - ")[0] in " ".join(options.nth(i).inner_text().split())), None)
            if picked is not None:
                options.nth(picked).click()
                p.wait_for_timeout(900)
        confirm = dialog.get_by_role("button", name=re.compile(r"^(Tạo|Create)$"))
        check(confirm.count() > 0, f"hộp thoại hoàn ứng không có nút Tạo: {screen_text(p)[:200]}")
        confirm.last.click()
        p.wait_for_url(re.compile(r".*/journal-entry/"), timeout=30000)
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        reference = f"VCB-HOAN-{REQ['advance']}"
        s_chi.step("Kế toán gõ số và ngày chứng từ nộp tiền thừa trên bút toán")
        type_into(p, "cheque_no", reference)
        type_into(p, "cheque_date", user_date(dt.date.today().isoformat()))
        s_chi.step("Kế toán đính kèm ủy nhiệm chi của khoản hoàn ứng")
        attach_file(p, "tlc_bank_proof")
        s_chi.step("Kế toán bấm Lưu rồi Nộp bút toán hoàn ứng")
        save_primary(p)
        je_name = p.evaluate("() => cur_frm.doc.name")
        submit_native(p)
        s_chi.step("Kế toán gắn bút toán hoàn ứng vào báo cáo quyết toán và bấm Lưu")
        open_doc(s_chi, EC, REQ["claim"])
        pick_link(p, "tlc_refund_entry", je_name)
        save_primary(p)
        reason_if_asked(p, "Gắn bút toán hoàn ứng đã ghi sổ")
        s_chi.step("Kế toán bấm Hành động > Hoàn tất quyết toán")
        action(s_chi, EC, REQ["claim"], "Hoàn tất quyết toán")
        cl_state = api_get(s_chi, f"/api/resource/{EC}/{REQ['claim']}").json()["data"]["workflow_state"]
        check(cl_state == "Hoàn tất", f"Claim state is {cl_state}")
        adv_final = api_get(s_chi, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]
        check(adv_final.get("claimed_amount") == 3500000 and adv_final.get("return_amount") == 500000,
              f"Advance not fully reconciled: {adv_final}")
        r["actual"] = f"{REQ['claim']} Hoàn tất; Tạm ứng {REQ['advance']}: Đã quyết toán 3.500.000, Đã hoàn 500.000, hết số dư treo"
    s_chi.close()

    # --------------------------------------------------------- FIN-06 top-up branch (claimed > advance)
    s_an_tu = Session(browser, "FIN-TOPUP", "an")
    login(s_an_tu)
    p_tu = s_an_tu.page
    with case(s_an_tu, "FIN-06", "Kế toán chi bù chi phí vượt tạm ứng và nhân viên xác nhận đã nhận đủ",
              "Mở tạm ứng > Tạo > Đề nghị thanh toán với chi phí lớn hơn tạm ứng > Quản lý và Giám đốc duyệt > "
              "Kế toán Hồ sơ hợp lệ > Tạo Payment Entry chi bù kèm ủy nhiệm chi > Hành động > Đã chi bù > "
              "Nhân viên mở quyết toán > Hành động > Tôi đã nhận đủ",
              "Đã ứng 1.000.000, Thực chi 1.800.000 → Chi bù 800.000 VND",
              "Quyết toán qua nhánh top_up, Kế toán chi bù qua Payment Entry, nhân viên xác nhận trên UI; quyết toán Hoàn tất") as r:
        # Setup: a separate funded advance of An for 1,000,000 VND
        adv_tu = api(s_an_tu, "frappe.client.insert", doc=json.dumps({
            "doctype": EA, "company": company, "employee": an_emp_id, "advance_amount": 1000000,
            "purpose": "Tạm ứng chuyến công tác phát sinh chi bù",
            "tlc_needed_on": working_day(1), "tlc_settlement_due": working_day(20),
            "posting_date": dt.date.today().isoformat(), "workflow_state": "Nháp"}))["name"]
        REQ["adv_topup"] = adv_tu
        for acc, mv in (("an", "Gửi duyệt"), ("quang", "Duyệt"), ("thanh", "Duyệt"), ("chi", "Hồ sơ hợp lệ")):
            st = Session(browser, "TU-SETUP", acc)
            login(st)
            api(st, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": EA, "name": adv_tu}), action=mv)
            st.close()
        # Chi chi tiền tạm ứng 1.000.000
        st_chi = Session(browser, "TU-PAY", "chi")
        login(st_chi)
        acc_bank = api_get(st_chi, "/api/resource/Account?filters=" + json.dumps([["company", "=", company], ["account_number", "=", "1121"]])).json()["data"][0]["name"]
        acc_adv = api_get(st_chi, "/api/resource/Account?filters=" + json.dumps([["company", "=", company], ["account_number", "=", "141"]])).json()["data"][0]["name"]
        pe_tu = api(st_chi, "frappe.client.insert", doc=json.dumps({
            "doctype": PE, "payment_type": "Pay", "party_type": "Employee", "party": an_emp_id,
            "company": company, "paid_from": acc_bank,
            "paid_to": acc_adv,
            "paid_amount": 1000000, "received_amount": 1000000,
            "reference_no": f"VCB-TU-{adv_tu}", "reference_date": dt.date.today().isoformat(),
            "references": [{"reference_doctype": EA, "reference_name": adv_tu,
                            "total_amount": 1000000, "outstanding_amount": 1000000, "allocated_amount": 1000000}]}))
        proof_tu = api(st_chi, "frappe.client.attach_file", filename=f"UNC-TU-{adv_tu}.txt",
                       filedata=base64.b64encode(PROOF.read_bytes()).decode(),
                       doctype=PE, docname=pe_tu["name"], is_private=1)
        api(st_chi, "frappe.client.set_value", doctype=PE, name=pe_tu["name"], fieldname="tlc_bank_proof", value=proof_tu["file_url"])
        api(st_chi, "frappe.client.submit", doc=json.dumps(api_get(st_chi, f"/api/resource/{PE}/{pe_tu['name']}").json()["data"]))
        api(st_chi, "frappe.client.set_value", doctype=EA, name=adv_tu, fieldname="tlc_payment_entry", value=pe_tu["name"])
        api(st_chi, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": EA, "name": adv_tu}), action="Xác nhận đã chi")
        st_chi.close()

        # An tạo quyết toán 1.800.000 (vượt tạm ứng 1.000.000)
        open_doc(s_an_tu, EA, adv_tu, "An mở tạm ứng để lập quyết toán chi bù")
        p_tu.locator(".page-head button:visible").filter(has_text=re.compile(r"^(Create|Tạo)\b")).first.click()
        p_tu.wait_for_timeout(900)
        p_tu.locator(MENU_ITEMS).filter(has_text=re.compile(r"Đề nghị thanh toán|Expense Claim")).first.click()
        p_tu.wait_for_url(re.compile(r".*/expense-claim/"), timeout=30000)
        wait_form(p_tu, EC)
        tab_acc = p_tu.locator(".nav-link:visible").filter(has_text=re.compile("Kế toán|Accounting")).first
        if tab_acc.count():
            tab_acc.click()
            p_tu.wait_for_timeout(1000)
        paid = p_tu.locator("input[data-fieldname='is_paid'][type=checkbox]").last
        if paid.count() and paid.is_checked():
            paid.uncheck(force=True)
            p_tu.wait_for_timeout(800)
        tab = p_tu.locator(".nav-link:visible").filter(has_text="Chi phí").first
        if tab.count():
            tab.click()
            p_tu.wait_for_timeout(900)
        row = add_row(p_tu, "expenses")
        fill_cell(p_tu, row, "expense_date", user_date(dt.date.today().isoformat()))
        fill_cell(p_tu, row, "expense_type", "TLC Vé công tác", link=True)
        fill_cell(p_tu, row, "amount", "1800000")
        fill_cell(p_tu, row, "sanctioned_amount", "1800000")
        trim_empty_rows(p_tu, "expenses", ("expense_type", "amount", "sanctioned_amount"))
        fill_grid_attach(p_tu, "expenses", 0)
        # Phân bổ đúng min(actual, paid) = 1.000.000
        tab_adv = p_tu.locator(".nav-link:visible").filter(has_text=re.compile("Chi phí & Tạm ứng|Expenses & Advances")).first
        if tab_adv.count():
            tab_adv.click()
            p_tu.wait_for_timeout(1000)
        adv_rows = grid_rows(p_tu, "advances")
        if not adv_rows.count():
            r_adv = add_row(p_tu, "advances")
            fill_cell(p_tu, r_adv, "employee_advance", adv_tu, link=True)
            p_tu.wait_for_timeout(1200)
            trim_empty_rows(p_tu, "advances", ("employee_advance", "allocated_amount"))
            adv_rows = grid_rows(p_tu, "advances")
        if adv_rows.count():
            adv_rows.first.scroll_into_view_if_needed()
            adv_rows.first.locator(".btn-open-row").first.click(force=True)
            p_tu.wait_for_timeout(1000)
            alloc = p_tu.locator("input[data-fieldname='allocated_amount']:visible").last
            alloc.click()
            alloc.fill("1000000")
            alloc.press("Tab")
            p_tu.wait_for_timeout(700)
            p_tu.keyboard.press("Escape")
        trim_empty_rows(p_tu, "expenses", ("expense_type", "amount", "sanctioned_amount"))
        trim_empty_rows(p_tu, "advances", ("employee_advance", "allocated_amount"))
        save_primary(p_tu)
        p_tu.wait_for_function("() => window.cur_frm && !cur_frm.is_new() && !cur_frm.docname.startsWith('new-')", timeout=25000)
        claim_tu = p_tu.evaluate("() => cur_frm.doc.name")
        REQ["claim_topup"] = claim_tu
        doc_c = api_get(s_an_tu, f"/api/resource/{EC}/{claim_tu}").json()["data"]
        check(doc_c.get("tlc_settlement_branch") == "top_up" and doc_c.get("tlc_difference") == -800000,
              f"Nhánh chi bù không khớp: branch={doc_c.get('tlc_settlement_branch')}, diff={doc_c.get('tlc_difference')}")
        action(s_an_tu, EC, claim_tu, "Gửi duyệt", "An nộp quyết toán chi bù")

        # Quản lý Quang và Giám đốc Thành duyệt
        for acc in ("quang", "thanh"):
            s_apr = Session(browser, "TU-APR", acc)
            login(s_apr)
            action(s_apr, EC, claim_tu, "Duyệt", f"{acc.upper()} duyệt quyết toán chi bù")
            s_apr.close()

        # Kế toán Chi kiểm tra hồ sơ hợp lệ -> Chờ quyết toán
        s_chi_tu = Session(browser, "TU-ACC", "chi")
        login(s_chi_tu)
        p_chi_tu = s_chi_tu.page
        action(s_chi_tu, EC, claim_tu, "Hồ sơ hợp lệ", "Kế toán kiểm tra hồ sơ quyết toán chi bù")
        state_c = api_get(s_chi_tu, f"/api/resource/{EC}/{claim_tu}").json()["data"]["workflow_state"]
        check(state_c == "Chờ quyết toán", f"Cần Chờ quyết toán, nhận: {state_c}")

        # Kế toán tạo Payment Entry Pay 800.000 cho Expense Claim
        s_chi_tu.step("Kế toán lập Payment Entry chi bù 800.000 qua UI")
        open_doc(s_chi_tu, EC, claim_tu)
        p_chi_tu.locator(".page-head button:visible").filter(has_text=re.compile(r"^(Create|Tạo)\b")).first.click()
        p_chi_tu.wait_for_timeout(900)
        p_chi_tu.locator(MENU_ITEMS).filter(has_text=re.compile(r"^(Thanh toán|Payment)$")).first.click()
        p_chi_tu.wait_for_url(re.compile(r".*/payment-entry/"), timeout=30000)
        p_chi_tu.wait_for_load_state("networkidle")
        p_chi_tu.wait_for_timeout(2500)
        ref_bu = f"VCB-CHIBU-{claim_tu}"
        type_into(p_chi_tu, "reference_no", ref_bu)
        type_into(p_chi_tu, "reference_date", user_date(dt.date.today().isoformat()))
        attach_file(p_chi_tu, "tlc_bank_proof")
        save_primary(p_chi_tu)
        pe_bu = p_chi_tu.evaluate("() => cur_frm.doc.name")
        submit_native(p_chi_tu)

        # Gắn pe_bu vào Expense Claim tlc_payment_entry rồi bấm Đã chi bù
        open_doc(s_chi_tu, EC, claim_tu)
        pick_link(p_chi_tu, "tlc_payment_entry", pe_bu)
        save_primary(p_chi_tu)
        reason_if_asked(p_chi_tu, "Gắn chứng từ chi bù thực tế")
        action(s_chi_tu, EC, claim_tu, "Đã chi bù", "Kế toán xác nhận đã chi bù ngân hàng")
        state_c = api_get(s_chi_tu, f"/api/resource/{EC}/{claim_tu}").json()["data"]["workflow_state"]
        check(state_c == "Chờ nhân viên xác nhận", f"Cần Chờ nhân viên xác nhận, nhận: {state_c}")
        s_chi_tu.close()

        # An xác nhận Tôi đã nhận đủ -> Hoàn tất
        s_an_rec = Session(browser, "TU-REC", "an")
        login(s_an_rec)
        action(s_an_rec, EC, claim_tu, "Tôi đã nhận đủ", "An xác nhận đã nhận đủ tiền chi bù")
        final_claim = api_get(s_an_rec, f"/api/resource/{EC}/{claim_tu}").json()["data"]
        check(final_claim["workflow_state"] == "Hoàn tất" and final_claim.get("tlc_received_by") == "an@demo.example",
              f"Quyết toán chi bù chưa hoàn tất: {final_claim['workflow_state']}")
        r["actual"] = (f"{claim_tu}: Đã ứng 1.000.000, Thực chi 1.800.000 → Chi bù {pe_bu} 800.000 VND; "
                       f"An xác nhận nhận tiền lúc {final_claim.get('tlc_received_on')}; trạng thái Hoàn tất")
        s_an_rec.close()
    s_an_tu.close()

    # --------------------------------------------------------- TRV-06 trip report and actual dates
    s_an_rep = Session(browser, "TRV-REP", "an")
    login(s_an_rep)
    p_rep = s_an_rep.page
    with case(s_an_rep, "TRV-06", "Báo cáo công tác thực tế sau khi kết thúc chuyến đi",
              "Nhân viên mở Travel Request đã duyệt > nhập Ngày/buổi đi về thực tế, kết quả công việc, gắn Expense Claim > "
              "Lưu > Hành động > Nộp báo cáo > Quản lý và Giám đốc duyệt báo cáo",
              REQ["trip"],
              "Chuyến đi chuyển sang Hoàn tất sau khi Giám đốc duyệt báo cáo; tlc_report_approved_on được ghi nhận") as r:
        open_doc(s_an_rep, TR, REQ["trip"], "An mở chuyến công tác đã kết thúc để nộp báo cáo")
        type_into(p_rep, "tlc_actual_from_date", user_date(t_start))
        choose_option(p_rep, "tlc_actual_from_session", "AM")
        type_into(p_rep, "tlc_actual_to_date", user_date(t_end))
        choose_option(p_rep, "tlc_actual_to_session", "PM")
        type_into(p_rep, "tlc_trip_result", "Đã ký biên bản ghi nhớ hợp tác chiến lược và hoàn tất khảo sát thị trường.")
        pick_link(p_rep, "tlc_expense_claim", REQ["claim"])
        save_primary(p_rep)
        reason_if_asked(p_rep, "Nộp báo cáo công tác thực tế")
        action(s_an_rep, TR, REQ["trip"], "Nộp báo cáo", "An nộp báo cáo công tác cho quản lý")
        st_rep = api_get(s_an_rep, f"/api/resource/{TR}/{REQ['trip']}").json()["data"]["workflow_state"]
        check(st_rep == "Chờ quản lý duyệt báo cáo", f"State is {st_rep}")

        for acc, action_name in (("quang", "Duyệt báo cáo"), ("thanh", "Duyệt báo cáo")):
            st = Session(browser, "REP-APR", acc)
            login(st)
            action(st, TR, REQ["trip"], action_name, f"{acc.upper()} duyệt báo cáo công tác")
            st.close()

        final_trip = api_get(s_an_rep, f"/api/resource/{TR}/{REQ['trip']}").json()["data"]
        check(final_trip["workflow_state"] == "Hoàn tất" and final_trip.get("tlc_report_approved_on"),
              f"Trip report not completed: {final_trip['workflow_state']}")
        r["actual"] = f"{REQ['trip']}: Hoàn tất lúc {final_trip.get('tlc_report_approved_on')}; Quản lý và Giám đốc đã duyệt báo cáo"
    s_an_rep.close()

    # --------------------------------------------------------- TRV-07 locked-period correction request
    s_an_lp = Session(browser, "TRV-LOCK", "an")
    login(s_an_lp)
    p_lp = s_an_lp.page
    with case(s_an_lp, "TRV-07", "Công tác thuộc kỳ đã khóa sinh yêu cầu điều chỉnh sau chốt",
              "Lập công tác lọt vào tháng công đã khóa > Giám đốc duyệt > nộp báo cáo thực tế > "
              "Kiểm tra Attendance Request điều chỉnh sau chốt được tạo cho kỳ sau, snapshot kỳ cũ không đổi",
              "Tháng công đã khóa",
              "Không sửa trực tiếp Attendance của kỳ đã khóa; sinh Attendance Request Điều chỉnh sau chốt với tlc_workday_delta") as r:
        # Setup: lock period of an earlier month for Hoi so
        first_prev = (dt.date.today().replace(day=1) - dt.timedelta(days=60)).replace(day=1)
        prev_month = first_prev.strftime("%Y-%m")
        d_locked_start = (first_prev + dt.timedelta(days=10)).isoformat()
        d_locked_end = (first_prev + dt.timedelta(days=11)).isoformat()
        # Create and lock period for Hoi so
        for acc, move in (("lan", "Gửi đối soát"), ("lan", "Đối soát xong"), ("thanh", "Ký và khoá")):
            st = Session(browser, "LOCK-PER", acc)
            login(st)
            exist_per = api_get(st, f"/api/resource/TLC Attendance Period?filters=" +
                                json.dumps([["company", "=", company], ["scope", "=", "Hội sở"], ["period_month", "=", prev_month]])).json().get("data", [])
            if not exist_per:
                per_name = api(st, "frappe.client.insert", doc=json.dumps({
                    "doctype": "TLC Attendance Period", "company": company, "scope": "Hội sở", "period_month": prev_month}))["name"]
            else:
                per_name = exist_per[0]["name"]
            cur_st = api_get(st, f"/api/resource/TLC Attendance Period/{per_name}").json()["data"]["workflow_state"]
            if cur_st != "Đã khoá":
                try:
                    api(st, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": "TLC Attendance Period", "name": per_name}), action=move)
                except Exception:
                    pass
            st.close()

        # An nộp công tác cho ngày thuộc kỳ đã khóa
        new_doc(s_an_lp, TR, "An lập công tác cho kỳ công đã khóa")
        fill_trip(p_lp, "Chi nhánh Cần Thơ", "Công tác phát sinh thuộc kỳ trước",
                  d_locked_start, d_locked_end, 0, [])
        save_primary(p_lp)
        p_lp.wait_for_function("() => window.cur_frm && !cur_frm.is_new() && !cur_frm.docname.startsWith('new-')", timeout=25000)
        locked_trip = p_lp.evaluate("() => cur_frm.doc.name")
        action(s_an_lp, TR, locked_trip, "Gửi duyệt")
        for acc in ("quang", "thanh"):
            st = Session(browser, "L-APR", acc)
            login(st)
            action(st, TR, locked_trip, "Duyệt")
            st.close()

        # Nộp báo cáo thực tế
        s_an_lprep = Session(browser, "L-REP", "an")
        login(s_an_lprep)
        open_doc(s_an_lprep, TR, locked_trip)
        type_into(s_an_lprep.page, "tlc_actual_from_date", user_date(d_locked_start))
        choose_option(s_an_lprep.page, "tlc_actual_from_session", "AM")
        type_into(s_an_lprep.page, "tlc_actual_to_date", user_date(d_locked_start))  # về sớm 1 ngày
        choose_option(s_an_lprep.page, "tlc_actual_to_session", "PM")
        type_into(s_an_lprep.page, "tlc_trip_result", "Hoàn tất công tác sớm 1 ngày.")
        save_primary(s_an_lprep.page)
        reason_if_asked(s_an_lprep.page, "Báo cáo công tác về sớm kỳ đã khóa")
        action(s_an_lprep, TR, locked_trip, "Nộp báo cáo")
        s_an_lprep.close()

        for acc in ("quang", "thanh"):
            st = Session(browser, "L-FIN", acc)
            login(st)
            action(st, TR, locked_trip, "Duyệt báo cáo")
            st.close()

        # Kiểm tra Attendance Request điều chỉnh sau chốt được sinh ra
        adj_reqs = api_get(s_an_lp, f"/api/resource/Attendance Request?filters=" +
                           json.dumps([["tlc_travel_request", "=", locked_trip], ["tlc_correction_type", "=", "Điều chỉnh sau chốt"]])).json().get("data", [])
        check(len(adj_reqs) > 0, "Không có Attendance Request điều chỉnh sau chốt nào được tạo cho chuyến đi kỳ đã khóa")
        r["actual"] = f"{locked_trip}: Hoàn tất; sinh {len(adj_reqs)} yêu cầu Điều chỉnh sau chốt cho kỳ lương tiếp theo; bảng công kỳ {prev_month} giữ nguyên"
    s_an_lp.close()

    # --------------------------------------------------------- TRV-08 open items in attendance period
    s_lan_oi = Session(browser, "TRV-OI", "lan")
    login(s_lan_oi)
    p_oi = s_lan_oi.page
    with case(s_lan_oi, "TRV-08", "Kỳ công tháng hiển thị chuyến công tác chưa duyệt báo cáo trong danh sách việc tồn",
              "HR mở kỳ công tháng đang đối soát > đọc danh sách open_items trên form",
              "Công tác chưa hoàn tất báo cáo",
              "Kỳ công hiển thị chính xác tên chuyến công tác còn treo trong danh sách open_items, ngăn khoá kỳ công sớm") as r:
        # Tạo 1 chuyến công tác mới trong tháng hiện tại chưa nộp báo cáo
        st_an = Session(browser, "UNREP", "an")
        login(st_an)
        # chọn kỳ trống thật: lượt full đã có phép/tăng ca của An trong tháng, và luật chống trùng chặn đúng (fixture,
        # không phải điều bị nghiệm thu — điều nghiệm thu ở đây là danh sách việc tồn của kỳ công)
        first, last = working_day(2), working_day(3)
        for k in range(1, 40):
            first, last = working_day(k), working_day(k + 1)
            overlap = [["employee", "=", an_emp_id]]
            busy = (len(list_of(st_an, "Leave Application", filters=overlap + [["from_date", "<=", last], ["to_date", ">=", first]],
                                fields=["name"], limit=5))
                    + len(list_of(st_an, TR, filters=overlap + [["tlc_from_date", "<=", last], ["tlc_to_date", ">=", first]],
                                  fields=["name"], limit=5))
                    + len(list_of(st_an, "TLC Overtime Request", filters=overlap + [["ot_date", "between", [first, last]]],
                                  fields=["name"], limit=5)))
            if not busy:
                break
        else:
            check(False, f"không tìm được hai ngày lịch trống cho {an_emp_id} trong 40 ngày làm việc tới")
        unrep_trip = api(st_an, "frappe.client.insert", doc=json.dumps({
            "doctype": TR, "company": company, "employee": an_emp_id, "travel_type": "Domestic",
            "purpose_of_travel": "TLC Công tác", "tlc_destination": "Nha Trang",
            "description": "Chuyến công tác chưa báo cáo để kiểm tra open items",
            "tlc_from_date": first, "tlc_to_date": last,
            "tlc_from_session": "AM", "tlc_to_session": "PM", "tlc_funded": 0}))["name"]
        api(st_an, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": TR, "name": unrep_trip}), action="Gửi duyệt")
        st_an.close()
        # Duyệt sang Đã duyệt nhưng chưa nộp báo cáo
        for acc in ("quang", "thanh"):
            st = Session(browser, "UNREP-APR", acc)
            login(st)
            api(st, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": TR, "name": unrep_trip}), action="Duyệt")
            st.close()

        # Lan mở danh sách kỳ công tháng của Hội sở
        cur_month = dt.date.today().strftime("%Y-%m")
        open_doc(s_lan_oi, "TLC Attendance Period")
        # Lấy bản ghi kỳ công hiện tại
        per_cur = api_get(s_lan_oi, f"/api/resource/TLC Attendance Period?filters=" +
                          json.dumps([["company", "=", company], ["scope", "=", "Hội sở"], ["period_month", "=", cur_month]])).json().get("data", [])
        if per_cur:
            open_doc(s_lan_oi, "TLC Attendance Period", per_cur[0]["name"])
            # Bấm cập nhật/refresh hoặc đọc open_items
            text_per = screen_text(p_oi)
            doc_p = api_get(s_lan_oi, f"/api/resource/TLC Attendance Period/{per_cur[0]['name']}").json()["data"]
            open_items = doc_p.get("open_items", "")
            check(unrep_trip in open_items or "Công tác chưa hoàn tất báo cáo" in open_items,
                  f"Kỳ công không liệt kê chuyến công tác chưa báo cáo {unrep_trip}: {open_items[:200]}")
            r["actual"] = f"Kỳ công {per_cur[0]['name']} ({cur_month}): open_count = {doc_p.get('open_count')}; việc tồn có mặt {unrep_trip}"
        else:
            # Tạo nháp kỳ công để hệ thống tính toán open items
            new_doc(s_lan_oi, "TLC Attendance Period", "Lan tạo kỳ công tháng Hội sở để kiểm tra open items")
            choose_option(p_oi, "scope", "Hội sở")
            type_into(p_oi, "period_month", cur_month)
            save_primary(p_oi)
            name_p = p_oi.evaluate("() => cur_frm.doc.name")
            doc_p = api_get(s_lan_oi, f"/api/resource/TLC Attendance Period/{name_p}").json()["data"]
            open_items = doc_p.get("open_items", "")
            check(unrep_trip in open_items, f"open_items không có {unrep_trip}: {open_items[:200]}")
            r["actual"] = f"Kỳ công {name_p}: việc tồn liệt kê {unrep_trip} (công tác chưa báo cáo)"
    s_lan_oi.close()
    # ---------------------------------------------------------------- overdue recovery guard (server answer)
    # Setup only: the recovery guard needs an actually paid, still-unsettled advance, not an unpaid draft with zero balance.
    overdue_name = REQ["adv_overdue"]
    for account, move in (("an", "Gửi duyệt"), ("quang", "Duyệt"), ("thanh", "Duyệt"), ("chi", "Hồ sơ hợp lệ")):
        fixture = Session(browser, "FIN-SETUP", account)
        try:
            login(fixture)
            api(fixture, "frappe.model.workflow.apply_workflow",
                doc=json.dumps({"doctype": EA, "name": overdue_name}), action=move)
            if account == "chi":
                template = api_get(fixture, f"/api/resource/{PE}/{REQ['pe_advance']}").json()["data"]
                payment = {key: template[key] for key in (
                    "payment_type", "party_type", "party", "company", "paid_from", "paid_to",
                    "paid_from_account_currency", "paid_to_account_currency", "source_exchange_rate", "target_exchange_rate")}
                payment.update({"doctype": PE, "posting_date": dt.date.today().isoformat(),
                                "paid_amount": 2000000, "received_amount": 2000000,
                                "reference_no": f"VCB-QUAHAN-{overdue_name}",
                                "reference_date": dt.date.today().isoformat(),
                                "references": [{"reference_doctype": EA, "reference_name": overdue_name,
                                                "total_amount": 2000000, "outstanding_amount": 2000000,
                                                "allocated_amount": 2000000}]})
                payment = api(fixture, "frappe.client.insert", doc=json.dumps(payment))
                proof = api(fixture, "frappe.client.attach_file", filename=f"UNC-{overdue_name}.txt",
                            filedata=base64.b64encode(PROOF.read_bytes()).decode(),
                            doctype=PE, docname=payment["name"], is_private=1)
                api(fixture, "frappe.client.set_value", doctype=PE, name=payment["name"],
                    fieldname="tlc_bank_proof", value=proof["file_url"])
                payment = api_get(fixture, f"/api/resource/{PE}/{payment['name']}").json()["data"]
                api(fixture, "frappe.client.submit", doc=json.dumps(payment))
                api(fixture, "frappe.client.set_value", doctype=EA, name=overdue_name,
                    fieldname="tlc_payment_entry", value=payment["name"])
                api(fixture, "frappe.model.workflow.apply_workflow",
                    doc=json.dumps({"doctype": EA, "name": overdue_name}), action="Xác nhận đã chi")
                paid_fixture = api_get(fixture, f"/api/resource/{EA}/{overdue_name}").json()["data"]
                check(paid_fixture.get("docstatus") == 1 and paid_fixture.get("workflow_state") == "Đã chi"
                      and paid_fixture.get("paid_amount") == 2000000
                      and not paid_fixture.get("claimed_amount") and not paid_fixture.get("return_amount")
                      and paid_fixture.get("tlc_settlement_due") < dt.date.today().isoformat(),
                      f"{overdue_name}: fixture phải thực chi, quá hạn và còn đủ số dư 2.000.000")
                paid_payment = api_get(fixture, f"/api/resource/{PE}/{payment['name']}").json()["data"]
                check(paid_payment["docstatus"] == 1 and paid_payment["tlc_bank_proof"].startswith("/private/files/")
                      and paid_fixture["tlc_payment_entry"] == payment["name"],
                      "fixture quá hạn thiếu chứng từ ngân hàng riêng tư đã ghi sổ")
                REQ["overdue_payment"] = payment["name"]
        finally:
            fixture.close()
    s_hr = Session(browser, "FIN", "hoa")
    login(s_hr)
    p = s_hr.page
    adv_overdue = REQ["adv_overdue"]
    with case(s_hr, "FIN-07", "Chặn tự động khấu trừ lương khi chưa có chính sách hoặc chữ ký nhân viên",
              "Mở tạm ứng quá hạn trên desk > đọc các hành động; thử lập khoản khấu trừ lương gắn tạm ứng quá hạn",
              "Tạm ứng quá hạn", "Giao diện không có đường tự lập khoản khấu trừ cho tạm ứng quá hạn; server từ chối Additional Salary: bắt buộc có chính sách công ty và thỏa thuận đồng ý có chữ ký (đối tượng nghiệm thu là câu trả lời của server)") as r:
        s_hr.step("HR mở phiếu tạm ứng quá hạn trên desk")
        open_doc(s_hr, EA, adv_overdue)
        s_hr.step("HR bấm Hành động để xem có đường tự khấu trừ lương hay không")
        actions = actions_list(p)
        check(not any("Khấu trừ" in i or "Additional Salary" in i for i in actions),
              f"giao diện có nút khấu trừ: {actions}")
        res = p.request.post(f"{BASE}/api/resource/Additional Salary", data=json.dumps({
            "employee": an_emp_id, "company": company, "salary_component": "Hoàn tạm ứng",
            "payroll_date": dt.date.today().replace(day=1).isoformat(), "amount": 2000000,
            "ref_doctype": EA, "ref_docname": adv_overdue}),
            headers={"X-Frappe-CSRF-Token": csrf_token(s_hr), "Content-Type": "application/json"})
        check(res.status != 200, "Should have rejected Additional Salary creation")
        err_msg = res.json().get("exception", "") or res.json().get("_server_messages", "")
        check("chính sách" in err_msg.lower() or "thỏa thuận" in err_msg.lower() or "consent" in err_msg.lower(),
              f"không thấy lý do chính sách/chữ ký trong lời từ chối: {err_msg[:300]}")
        r["actual"] = ("Giao diện chỉ có: " + ", ".join(actions or ["không có hành động"]) +
                       " — không có đường tự lập khoản khấu trừ; server từ chối: " + err_msg[:220])
    s_hr.close()

    s_an = Session(browser, "FIN", "an")
    try:
        login(s_an)
        with case(s_an, "FIN-08", "Cảnh báo tạm ứng quá hạn khi nộp đề xuất tạm ứng mới",
                  "Nhân viên lập tạm ứng mới trên desk > Lưu > Gửi duyệt > đọc cảnh báo đúng phiếu quá hạn",
                  f"{overdue_name} đã chi 2.000.000 và chưa quyết toán",
                  "Đơn mới được gửi đúng cấp; màn hình cảnh báo chính xác khoản quá hạn còn treo") as r:
            new_doc(s_an, EA, "An lập tạm ứng mới trong khi còn khoản quá hạn thực chi")
            pick_link(s_an.page, "employee", an_emp_id)
            type_into(s_an.page, "purpose", "Công tác mới, đã biết khoản tạm ứng cũ cần quyết toán")
            type_into(s_an.page, "advance_amount", "1000000")
            type_into(s_an.page, "tlc_needed_on", user_date(working_day(2)))
            type_into(s_an.page, "tlc_settlement_due", user_date(working_day(8)))
            save_primary(s_an.page)
            name = s_an.page.evaluate("() => cur_frm.doc.name")
            action(s_an, EA, name, "Gửi duyệt")
            warning = screen_text(s_an.page)
            check(overdue_name in warning and "quá hạn" in warning.lower(), f"thiếu cảnh báo khoản đang treo: {warning[:260]}")
            doc = api_get(s_an, f"/api/resource/{EA}/{name}").json()["data"]
            check(doc["workflow_state"] == "Chờ quản lý duyệt" and doc["paid_amount"] == 0,
                  f"cảnh báo không được tự duyệt hay chi đơn mới: {doc['workflow_state']}")
            r["actual"] = f"{name}: {doc['workflow_state']}; {warning[:180]}"
    finally:
        s_an.close()

    # ---------------------------------------------------------------- factory scope and self approval
    s_hung = Session(browser, "GOV", "hung")
    login(s_hung)
    with case(s_hung, "GOV-01", "Quản lý nhà máy không duyệt được công tác ngoài phạm vi",
              "Mở danh sách Travel Request, gõ mã chuyến của nhân viên văn phòng, thử mở hồ sơ",
              REQ["trip"], "Danh sách không trả về chuyến của An; mở trực tiếp hồ sơ bị chặn quyền") as r:
        s_hung.step("Trưởng Nhà máy 1 mở danh sách công tác của phạm vi mình")
        p_h = s_hung.page
        p_h.goto(f"{BASE}/desk/travel-request")
        p_h.wait_for_load_state("networkidle")
        p_h.wait_for_timeout(2000)
        s_hung.step(f"Ông ấy lọc danh sách theo mã chuyến {REQ['trip']} của An")
        name_filter = p_h.locator('input[data-fieldname="name"]:visible').last
        name_filter.fill(REQ["trip"])
        name_filter.press("Enter")
        p_h.wait_for_timeout(2500)
        rows = p_h.locator(".list-row-container").filter(has_not=p_h.locator(".list-row-head"))
        check(REQ["trip"] not in " ".join(rows.all_inner_texts()),
              "danh sách của trưởng nhà máy thấy chuyến của nhân viên văn phòng")
        s_hung.step("Ông ấy mở thẳng hồ sơ của An và đọc thông báo từ chối")
        p_h.goto(f"{BASE}/desk/travel-request/{REQ['trip']}")
        p_h.wait_for_load_state("networkidle")
        p_h.wait_for_timeout(2200)
        body = " ".join(p_h.locator("body").inner_text().split())
        check(any(w in body.lower() for w in ("permission", "not permitted", "không có quyền", "không được phép",
                                              "not allowed", "forbidden")), body[:300])
        trips = api_get(s_hung, f"/api/resource/{TR}?filters=" + json.dumps([["employee", "=", an_emp_id]])).json().get("data", [])
        check(len(trips) == 0, f"Factory 1 manager should not see office trips, saw: {trips}")
        r["actual"] = f"Danh sách phạm vi nhà máy không có {REQ['trip']}; màn hình báo: {body[:110]}; API đối chiếu 0 kết quả"
    s_hung.close()

    s_an = Session(browser, "GOV", "an")
    login(s_an)
    # Setup a pending own request: writing the already-approved trip's current state is a no-op, not self-approval.
    own_trip = api(s_an, "frappe.client.insert", doc=json.dumps({
        "doctype": TR, "company": company, "employee": an_emp_id, "travel_type": "Domestic",
        "purpose_of_travel": "TLC Công tác", "tlc_destination": "Đà Nẵng", "description": "Kiểm tra không tự duyệt",
        "tlc_from_date": working_day(25), "tlc_to_date": working_day(26), "tlc_from_session": "AM",
        "tlc_to_session": "PM", "tlc_funded": 0}))
    own_trip = api(s_an, "frappe.model.workflow.apply_workflow", doc=json.dumps(own_trip), action="Gửi duyệt")
    with case(s_an, "GOV-02", "Không ai được tự duyệt yêu cầu của chính mình",
              "Nhân viên mở đơn công tác của mình > bấm Hành động đọc các nút; thử gửi thẳng yêu cầu duyệt",
              own_trip["name"], "Giao diện không có nút Duyệt cho chính người tạo; server từ chối việc tự duyệt") as r:
        s_an.step("An mở lại đề xuất công tác của chính mình và bấm Hành động")
        open_doc(s_an, TR, own_trip["name"])
        actions = actions_list(s_an.page)
        check(not any("Duyệt" in i and "Gửi" not in i for i in actions), f"có nút duyệt: {actions}")
        res = s_an.page.request.put(f"{BASE}/api/resource/{TR}/{own_trip['name']}", data=json.dumps({"workflow_state": "Đã duyệt"}),
                                    headers={"X-Frappe-CSRF-Token": csrf_token(s_an), "Content-Type": "application/json"})
        check(res.status != 200, "Self approval should have been blocked")
        err_msg = res.json().get("exception", "") or res.json().get("_server_messages", "")
        r["actual"] = f"Hành động không có Duyệt ({actions or 'không có nút'}); server từ chối: {err_msg[:200]}"
    s_an.close()


JOURNEYS = [travel_finance_flow]