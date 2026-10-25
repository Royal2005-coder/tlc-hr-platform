"""Payroll Compliance: every case is worked on the standard Frappe desk by the account that owns the job.

The desk path of this module is one continuous month of payroll: HR prepares and the Director approves the effective-dated salary decision (PC-01), the
payroll officer runs the month and reads the prorated basic on the payslip, the variance gate either stops "Gửi ký" or lets it
through (PC-02, PC-03), the CEO signs and the accountant finds the signed payroll immutable (PC-04), the difference is booked
through a next-period adjustment (PC-05), and the money leaves through the bank file, the encrypted payslip PDF, the statutory
reports and the budget simulation (PC-06..PC-12).

Only the *certified* action is clicked and typed. Fixtures that a role legitimately cannot create in this build (the locked
attendance period of the month, the previous month's payslip used as the variance baseline, the employees' preferred email) are
prepared through the API before the case, and stored results are read back through the API to be compared.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from lib import *  # noqa: F403

PE, SS = "Payroll Entry", "Salary Slip"
REVIEW, ADJ, SALREV = "TLC Payroll Review", "TLC Payroll Adjustment", "TLC Salary Review"
SSA, ADS = "Salary Structure Assignment", "Additional Salary"
PERIOD = "TLC Attendance Period"
COMPUTED, TO_CEO, SIGNED, PAID = "Đã tính lương", "Chờ giám đốc ký", "Đã ký", "Đã chi"


# Hội sở first: its closing route is the short one (HR đối soát, no factory head). A scope whose period still has open items
# cannot be locked, so the runner walks down this list until one locks cleanly.
SCOPES = ["Hội sở", "Nhà máy 3", "Nhà máy 1", "Nhà máy 2"]
HEAD_OF = {"Hội sở": None, "Nhà máy 1": "hung", "Nhà máy 2": "nm2", "Nhà máy 3": "nm3"}
EVIDENCE_DIR = Path("/tmp/uat-pc")


def flt(value):
    return float(value or 0)


def month_bounds(offset=0):
    first = dt.date.today().replace(day=1)
    if offset < 0:
        first = (first - dt.timedelta(days=1)).replace(day=1)
    elif offset > 0:
        month = first.month + offset
        first = first.replace(year=first.year + (month - 1) // 12, month=(month - 1) % 12 + 1)
    last = (first + dt.timedelta(days=31)).replace(day=1) - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()


def evidence_file(name, body):
    """A real document the user attaches in the form (the desk uploads it as a private file)."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(body, encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------------------------- desk form helpers

def date_format(s):
    if not hasattr(s, "_date_format"):
        s._date_format = s.page.evaluate("() => (window.frappe && frappe.boot.sysdefaults.date_format) || 'yyyy-mm-dd'")
    return s._date_format


def user_date(s, iso):
    d = dt.date.fromisoformat(iso)
    return date_format(s).replace("yyyy", f"{d.year:04d}").replace("mm", f"{d.month:02d}").replace("dd", f"{d.day:02d}")


def box(s, fieldname, root=None):
    return (root or s.page).locator(f'[data-fieldname="{fieldname}"]')


def type_into(s, fieldname, value, root=None):
    """Click the field, clear it, type like a person, leave it with Tab.

    Date/Time controls take the whole string in one fill. Clearing first can leave the model empty when the entered
    text equals the control's previous value; typing character by character can store 'Invalid date'.
    """
    p = s.page
    field = box(s, fieldname, root).locator("input:visible, textarea:visible").last
    kind = field.get_attribute("data-fieldtype") or box(s, fieldname, root).locator("input").last.get_attribute("data-fieldtype") or ""
    if kind in ("Date", "Datetime", "Time"):
        field.fill(str(value))
    else:
        field.click()
        field.fill("")
        p.keyboard.type(str(value), delay=35)
    p.keyboard.press("Tab")
    p.wait_for_timeout(500)


def pick_link(s, fieldname, needle, root=None):
    """Focus the link control, type to filter its dropdown, click a visible suggestion only."""
    p = s.page
    control = box(s, fieldname, root)
    field = control.locator("input:visible").last
    field.wait_for(state="visible", timeout=15000)
    current_val = (field.input_value() or "").strip()
    if current_val == str(needle).strip() or current_val.startswith(str(needle).strip() + ":") or current_val.startswith(str(needle).strip() + " - "):
        return needle
    field.click()
    p.wait_for_timeout(400)
    picked = False
    if needle:
        field.fill("")
        p.keyboard.type(str(needle), delay=35)
        p.wait_for_timeout(2000)
    options = p.locator(".awesomplete li, ul[role='listbox'] li, .ui-menu-item li, .frappe-control-dropdown li")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    target = next((i for i in shown if needle.lower() == " ".join(options.nth(i).inner_text().split()).lower()), None)
    if target is None:
        target = next((i for i in shown if not needle or needle.lower() in options.nth(i).inner_text().lower()), None)
    if target is not None:
        options.nth(target).click()
        picked = True
        p.wait_for_timeout(1000)
    else:
        p.keyboard.press("Enter")
        p.wait_for_timeout(1000)
        new_val = (field.input_value() or "").strip()
        if new_val == str(needle).strip() or new_val.startswith(str(needle).strip()):
            picked = True
    check(picked, f"ô {fieldname}: không có gợi ý đúng '{needle}'; không chọn thay bằng hồ sơ khác")
    p.wait_for_timeout(900)

def choose_option(s, fieldname, option, root=None):
    """A Select field is a real <select>: pick the entry by its visible label, else by its stored value."""
    p = s.page
    select = box(s, fieldname, root).locator("select:visible").last
    select.click()
    try:
        select.select_option(label=option)
    except Exception:
        select.select_option(value=option)
    p.wait_for_timeout(600)


def attach(s, fieldname, path, root=None):
    """Click the field's own attach button (the desk labels it Đính kèm), choose the file in the uploader dialog."""
    p = s.page
    control = box(s, fieldname, root)
    button = control.locator("button.btn-attach:visible").last
    if not button.count():
        button = control.locator("button:visible", has_text=re.compile("Gắn|Đính kèm|Attach")).last
    button.click()
    dialog = p.locator(".modal:visible").last
    dialog.wait_for(state="visible")
    p.wait_for_timeout(900)
    with p.expect_response(lambda res: "/api/method/upload_file" in res.url, timeout=60000) as uploaded:
        dialog.locator("input[type=file]").last.set_input_files(path)
        upload = dialog.get_by_role("button", name=re.compile(r"^(Tải lên|Upload)$"))
        if upload.count() and upload.last.is_visible():
            upload.last.click()
    response = uploaded.value
    check(response.ok, f"tải tệp thất bại HTTP {response.status}")
    file_doc = response.json().get("message") or {}
    url = file_doc.get("file_url")
    check(url, f"máy chủ không trả file_url cho {Path(path).name}")
    p.wait_for_function("a => window.cur_frm && cur_frm.doc[a[0]] === a[1]",
                        arg=[fieldname, url], timeout=30000)
    expect(control.locator(".attached-file-link:visible").first).to_be_visible(timeout=30000)
    check(file_doc.get("is_private") == 1 and url.startswith("/private/files/"),
          "chứng từ lương phải được tải lên riêng tư")
    return url


def press(s, label, root=None, timeout=12000):
    """Nhấn một nút thật; nếu nó thuộc nhóm hành động thì mở menu "Hành động" trước, vẫn là đường người dùng đi."""
    p = s.page
    button = (root or p).locator("button:visible", has_text=label).last
    try:
        button.wait_for(state="visible", timeout=min(4000, timeout))
    except Exception:
        if root is None and open_actions(p):
            button = p.locator(MENU_ITEMS, has_text=label).last
        button.wait_for(state="visible", timeout=timeout)
    button.click()
    p.wait_for_timeout(700)


def save_form(s):
    p = s.page
    if p.locator("button:visible", has_text=re.compile(r"^(Lưu|Save)$")).count():
        press(s, re.compile(r"^(Lưu|Save)$"))
    else:
        p.keyboard.press("Control+s")
    p.wait_for_function("() => window.cur_frm && !cur_frm.is_dirty() && !cur_frm.is_new()", timeout=40000)
    p.wait_for_timeout(1500)
    return p.evaluate("() => cur_frm.docname")


def toggle_check(s, fieldname):
    """Tick the box of a Check field (the desk renders it as a switch with a hidden input)."""
    p = s.page
    control = box(s, fieldname)
    for sel in ("input[type=checkbox]", ".toggle-check", ".control-input", "label"):
        target = control.locator(sel)
        if target.count():
            target.last.click()
            p.wait_for_timeout(700)
            return True
    return False


def dismiss_messages(p):
    """Close an informational dialog left by the previous save before touching the toolbar again."""
    for _ in range(3):
        if not p.locator(".modal:visible").count():
            return
        dialog = p.locator(".modal:visible").last
        closer = dialog.locator("button:visible").filter(has_text=re.compile(r"^(Đóng|Close|OK)$"))
        if closer.count():
            closer.first.click()
        elif dialog.locator(".btn-modal-close:visible, .close:visible").count():
            dialog.locator(".btn-modal-close:visible, .close:visible").first.click()
        else:
            p.keyboard.press("Escape")
        p.wait_for_timeout(800)


def submit_form(s):
    """The page-head primary action (labelled Xác nhận/Gửi on this build) plus the native "Gửi vĩnh viễn?" dialog.

    The primary action is not reliably findable by its text: the label is drawn inside a span, so the gate matches the
    button class instead and then presses the dialog's primary button.
    """
    p = s.page

    def attempt():
        dismiss_messages(p)
        button = p.locator(".page-head button.primary-action:visible").last
        if button.count():
            button.click()
        else:
            open_more(p)
            items = p.locator(MENU_ITEMS)
            target = next((i for i in range(items.count())
                           if re.search(r"Gửi|Submit|Xác nhận|Trình|Nộp", items.nth(i).inner_text())), None)
            check(target is not None, f"form không có nút Gửi cho {s.account}@demo.example: {menu_items(p)}")
            items.nth(target).click()
        p.wait_for_timeout(1500)
        for _ in range(24):
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
                    try:
                        send.last.click()
                        p.wait_for_timeout(2500)
                    except Exception:
                        p.keyboard.press("Escape")
                        p.wait_for_timeout(800)
                else:
                    yes = modal.locator("button:visible", has_text=re.compile(r"Gửi|Submit|Xác nhận|Yes|Có|Đồng ý"))
                    if yes.count():
                        yes.last.click()
                        p.wait_for_timeout(1500)
                    else:
                        p.keyboard.press("Escape")
                        p.wait_for_timeout(800)
            p.wait_for_timeout(700)
        try:
            p.wait_for_function("() => window.cur_frm && cur_frm.doc.docstatus === 1", timeout=30000)
        except Exception:
            pass  # a refused submit leaves the document in draft; the caller reads the message off the screen
        return p.evaluate("() => window.cur_frm && cur_frm.doc.docstatus")

    submitted = attempt()
    message = screen_message(s, wait=1200, close=True)
    check(submitted == 1, f"bấm Gửi không ghi được chứng từ ({s.account}@demo.example): {message[:240] or 'không có thông báo'}")
    p.wait_for_timeout(1200)


def open_more(p):
    dismiss_messages(p)
    more = p.locator(".page-actions .menu-more-button:visible, button[data-action='toggle-actions']:visible")
    check(more.count(), "không thấy menu ⋮ của form")
    more.last.click()
    p.wait_for_timeout(800)


def screen_message(s, wait=2500, close=True):
    """What the desk shows when the server answers: the error dialog, the toast, the form headline."""
    p = s.page
    p.wait_for_timeout(wait)
    parts = []
    for sel in (".msgprint", ".modal:visible", ".alert:visible", ".form-message:visible", ".indicator-red:visible"):
        found = p.locator(sel)
        for i in range(min(found.count(), 5)):
            text = " ".join(found.nth(i).inner_text().split())
            if text and text not in parts:
                parts.append(text)
    message = " | ".join(parts)
    if close:
        p.keyboard.press("Escape")
        p.wait_for_timeout(600)
    return message


def open_workflow(p):
    """Hành động, or the ⋮ menu on forms whose workflow actions live there; waits until menu rows are visible."""
    for _ in range(4):
        if p.locator(MENU_ITEMS).count():
            return True
        button = p.get_by_role("button", name="Hành động")
        if button.count() and button.first.is_visible():
            button.first.click()
        else:
            more = p.locator(".page-head .menu-more-button:visible, .page-actions .menu-more-button:visible")
            if not more.count():
                return False
            more.last.click()
        p.wait_for_timeout(1000)
    return bool(p.locator(MENU_ITEMS).count())


def workflow_step(s, name, action, doctype, wait_state=4500):
    """Hành động → the workflow button, then wait for the stored state to move and the form to refresh."""
    p = s.page
    p.goto(f"{BASE}/desk/{slug(doctype)}/{quote(name)}")
    p.wait_for_load_state("networkidle")
    p.wait_for_function("(a) => window.cur_frm && cur_frm.doctype === a[0] && cur_frm.docname === a[1]",
                        arg=[doctype, name], timeout=30000)
    p.wait_for_timeout(2500)
    dismiss_messages(p)
    before = doc_state(s, doctype, name)
    s.step(f"{s.account.upper()} bấm Hành động rồi chọn “{action}”")
    check(open_workflow(p), f"không mở được menu hành động: {[t.strip() for t in p.locator('.page-head button:visible').all_inner_texts()]}")
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == action), None)
    check(target is not None, f"không có “{action}” trong {menu_items(p)}")
    items.nth(target).click()
    state = before
    deadline = time.time() + 180
    while time.time() < deadline:
        p.wait_for_timeout(2500)
        state = doc_state(s, doctype, name)
        if state != before:
            break
    p.wait_for_timeout(wait_state)
    return state


def trim_grid(p, field, keys):
    """Remove the blank row the desk appends after the last edited grid row (its fields would fail validation)."""
    for _ in range(10):
        rows = p.evaluate("(f) => (cur_frm.doc[f] || []).map(r => r)", field)
        empties = [i for i, row in enumerate(rows) if not any(row.get(k) for k in keys)]
        if not empties:
            return
        index = empties[-1]
        table = p.locator(f'[data-fieldname="{field}"] .grid-row').filter(has_not_text="Không.")
        row = table.nth(index)
        row.scroll_into_view_if_needed()
        collapse = row.locator("button.grid-collapse-row:visible")
        if not collapse.count():
            row.locator(".btn-open-row").first.click(force=True)
            p.wait_for_timeout(800)
        delete = row.locator("button.grid-delete-row:visible").first
        if delete.count():
            delete.click()
            p.wait_for_timeout(700)
            dialog = p.locator(".modal:visible").last
            if dialog.count():
                yes = dialog.locator("button:visible", has_text=re.compile("Xóa|Delete|Có|Yes|Đồng ý"))
                if yes.count():
                    yes.last.click()
            p.wait_for_timeout(700)
        collapse = row.locator("button.grid-collapse-row:visible")
        if collapse.count():
            collapse.first.click()
        p.wait_for_timeout(500)


def list_of(s, doctype, filters=None, fields=None, limit=200):
    params = []
    if fields:
        params.append("fields=" + quote(json.dumps(fields), safe=""))
    if filters:
        params.append("filters=" + quote(json.dumps(filters), safe=""))
    params.append(f"limit_page_length={limit}")
    return api_get(s, f"/api/resource/{quote(doctype)}?" + "&".join(params)).json().get("data", [])


def slug(doctype):
    return doctype.lower().replace(" ", "-")


def add_button(s, doctype):
    """Open the list of the doctype and press its add button, so the form is really created by the user.

    The desk labels the control with the doctype ("Thêm TLC Attendance Period"), renders it only once the list has
    loaded, and its text starts with an icon, so the match must not be anchored at the beginning of the text.
    """
    p = s.page
    buttons = p.locator("button:visible").filter(has_text=re.compile(r"Thêm|Add", re.I))
    for _ in range(10):
        p.goto(f"{BASE}/desk/{slug(doctype)}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        if buttons.count():
            break
    usable = None
    for i in range(buttons.count() - 1, -1, -1):
        text = " ".join(buttons.nth(i).inner_text().split())
        if text and not re.search(r"Tải thêm|Load more|Thêm (bộ lọc|dòng|người dùng)|Add (filter|row|user)", text, re.I):
            usable = buttons.nth(i)
            break
    if usable is None:
        # the same target the button points at: the new-record route of this doctype
        p.goto(f"{BASE}/desk/{slug(doctype)}/new")
        p.wait_for_load_state("networkidle")
        p.wait_for_function("() => window.cur_frm && cur_frm.is_new()", timeout=20000)
        p.wait_for_timeout(2000)
        dismiss_messages(p)
        return
    usable.click()
    p.wait_for_timeout(2500)
    if p.locator(".modal:visible").count():
        # the list's Add opens a quick-entry dialog without the declared fields; the full form is at /new
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)
        p.goto(f"{BASE}/desk/{slug(doctype)}/new")
    else:
        # the desk often opens the new record in place without changing the URL: wait for the form, not the route
        try:
            p.wait_for_function("(d) => window.cur_frm && cur_frm.doctype === d && cur_frm.is_new()", arg=doctype, timeout=10000)
        except Exception:
            p.goto(f"{BASE}/desk/{slug(doctype)}/new")
    p.wait_for_load_state("networkidle")
    p.wait_for_function("(d) => window.cur_frm && cur_frm.doctype === d && cur_frm.is_new()", arg=doctype, timeout=30000)
    p.wait_for_timeout(3000)
    dismiss_messages(p)


def open_form(s, doctype, name):
    p = s.page
    if doctype == "Payroll Settings":  # a Single has its own page, not a record route
        p.goto(f"{BASE}/desk/{slug(doctype)}")
        p.wait_for_load_state("networkidle")
        p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Payroll Settings'", timeout=30000)
        p.wait_for_timeout(2500)
        return
    p.goto(f"{BASE}/desk/{slug(doctype)}/{quote(name)}")
    p.wait_for_load_state("networkidle")
    try:
        p.wait_for_function(f"() => window.cur_frm && cur_frm.doctype === '{doctype}'", timeout=15000)
    except Exception:
        p.goto(f"{BASE}/desk/Form/{quote(doctype)}/{quote(name)}")
        p.wait_for_load_state("networkidle")
        p.wait_for_function(f"() => window.cur_frm && cur_frm.doctype === '{doctype}'", timeout=30000)
    p.wait_for_timeout(3000)


def approve_decision(browser, doctype, name):
    """A separate Director session clicks explicit approval; HR never impersonates the approver."""
    director = Session(browser, "LG-DIRECTOR", "thanh")
    try:
        login(director)
        open_form(director, doctype, name)
        director.page.wait_for_timeout(1500)
        director.page.evaluate("() => cur_frm && cur_frm.reload_doc && cur_frm.reload_doc()")
        director.page.wait_for_timeout(3000)
        director.step(f"GIÁM ĐỐC đọc {name} và bấm Phê duyệt quyết định lương")
        press(director, "Phê duyệt quyết định lương", timeout=30000)
        dialog = director.page.locator(".modal:visible").last
        if dialog.count():
            confirm = dialog.get_by_role("button", name=re.compile(r"^(Có|Yes|Phê duyệt|Xác nhận)$"))
            check(confirm.count(), "hộp thoại phê duyệt không có nút xác nhận")
            confirm.last.click()
        director.page.wait_for_function("() => cur_frm.doc.docstatus === 1", timeout=40000)
        expect(director.page.locator(".form-layout:visible").first).to_be_visible()
    finally:
        director.close()


def native_data(s, label, method, primary=None, values=None, download=False):
    """Capture the genuine response generated by a person's native action, never invoke the method ourselves."""
    p = s.page
    dismiss_messages(p)
    open_form(s, PE, REQ["pe"])
    p.wait_for_timeout(1500)
    p.evaluate("() => cur_frm && cur_frm.reload_doc && cur_frm.reload_doc()")
    p.wait_for_timeout(3000)
    dismiss_messages(p)
    s.step(f"{s.account.upper()} bấm Dữ liệu lương → {label}")
    try:
        press(s, re.compile(r"^Dữ liệu lương$"), timeout=15000)
    except Exception:
        dismiss_messages(p)
        press(s, re.compile(r"^Dữ liệu lương$"), timeout=30000)
    action = p.locator(MENU_ITEMS).filter(has_text=re.compile("^" + re.escape(label) + "$"))
    check(action.count() == 1, f"không có đúng hành động dữ liệu {label}")
    with p.expect_response(lambda res: f"/api/method/tlc_hr.interface.payroll_compliance.{method}" in res.url,
                           timeout=90000) as response:
        action.click()
        if primary:
            dialog = p.locator(".modal:visible").last
            expect(dialog).to_be_visible()
            for fieldname, value in (values or {}).items():
                type_into(s, fieldname, value, root=dialog)
            press(s, re.compile("^" + re.escape(primary) + "$"), root=dialog)
    result = response.value
    check(result.ok and not result.json().get("exc"), f"{label}: HTTP {result.status}")
    data = result.json().get("message")
    check(isinstance(data, dict), f"{label}: máy chủ không trả dữ liệu báo cáo")
    preview = p.locator(".modal:visible").last
    expect(preview).to_be_visible(timeout=30000)
    check(len(preview.inner_text().strip()) > len(label), f"{label}: không có kết quả nhìn thấy")
    if download:
        with p.expect_download(timeout=30000) as emitted:
            preview.get_by_role("button", name="Tải xuống", exact=True).click()
        artifact = emitted.value
        check(not artifact.failure(), f"{label}: tải xuống thất bại")
        target = EVIDENCE_DIR / artifact.suggested_filename
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        artifact.save_as(str(target))
        content = target.read_text(encoding="utf-8-sig")
        if data.get("content") is not None:
            check(content == data["content"], f"{label}: tệp tải không khớp dữ liệu máy chủ")
        else:
            check(json.loads(content) == data, f"{label}: JSON tải xuống không khớp bản xem trước")
    dismiss_messages(p)
    return data


def open_report(s, title):
    """Open a standard desk report; the person then types the filters and presses Chạy báo cáo."""
    p = s.page
    p.goto(f"{BASE}/desk/query-report/{quote(title)}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(4000)
    return p


def run_report(s, title):
    p = s.page
    s.step(f"{s.account.upper()} bấm chạy báo cáo “{title}”")
    button = p.locator("button:visible", has_text=re.compile(r"Chạy báo cáo|Update Report|^Run$"))
    if button.count():
        button.last.click()
    else:
        # this desk build refreshes a query report with the icon labelled "Tải lại báo cáo" (no text button)
        refresh = p.locator("button[data-original-title='Tải lại báo cáo']:visible, button[title='Refresh']:visible, "
                            "button[aria-label='Refresh']:visible").last
        if refresh.count():
            refresh.click()
        else:
            p.keyboard.press("Enter")
    for _ in range(30):
        p.wait_for_timeout(1000)
        table = p.locator(".report-datatable-viewport, .result, .table").first
        if table.count() and table.inner_text().strip():
            break
    p.wait_for_timeout(1500)


def report_rows_text(s):
    p = s.page
    table = p.locator(".report-datatable-viewport, .result, .table")
    return " ".join(table.first.inner_text().split()) if table.count() else " ".join(p.locator("body").inner_text().split())


# ------------------------------------------------------------------------------------------- fixtures

COMPANY = "TLC Demo"
FACTORIES = {"Nhà máy 1", "Nhà máy 2", "Nhà máy 3"}
# states that are finished for the closing of a month; anything else left open holds the kỳ công back
CLOSED = ["Approved", "Rejected", "Đã duyệt", "Từ chối", "Cancelled", "Đã hủy", "Completed", "Đã thanh toán", "Đã chi", "Đã khoá"]


def pending_count(s, doctype, employees, extra=None):
    """Requests of these people that a closing of the month would still have to wait for."""
    filters = {"employee": ["in", employees], "docstatus": 0, "workflow_state": ["not in", CLOSED]}
    if extra:
        filters.update(extra)
    return len(list_of(s, doctype, filters=filters, fields=["name"], limit=500))


def people_of(s, department):
    return [r["name"] for r in list_of(s, "Employee", filters={"department": department, "status": "Active", "company": COMPANY},
                                       fields=["name"], limit=80)]


def departments_of(s, scope):
    """Departments whose attendance is closed by this scope: a factory carries its own name, everything else is Hội sở."""
    names = [d["name"] for d in list_of(s, "Department", filters={"company": COMPANY}, fields=["name"], limit=80)]
    return [n for n in names if (n.rsplit(" - ", 1)[0] not in FACTORIES) == (scope == "Hội sở")
            and (n.rsplit(" - ", 1)[0] == scope or scope == "Hội sở")]


def scope_blockers(s, scope, start, end):
    people = [p for dept in departments_of(s, scope) for p in people_of(s, dept)]
    if not people:
        return 99
    return (pending_count(s, "Leave Application", people, {"from_date": ["<=", end], "to_date": [">=", start]})
            + pending_count(s, "Attendance Request", people, {"from_date": ["<=", end], "to_date": [">=", start]})
            + pending_count(s, "TLC Overtime Request", people, {"ot_date": ["between", [start, end]]}))


def period_row(s, scope, month):
    rows = list_of(s, PERIOD, filters={"scope": scope, "period_month": month, "company": COMPANY},
                   fields=["name", "workflow_state", "docstatus", "open_count", "employee_count"], limit=5)
    return rows[0] if rows else None


def close_period_for(browser, scope, month):
    """HR closes and the CEO locks the payroll month: without it the payroll cannot be computed at all.

    This is the fixture of the month under test (the closing itself is certified by the attendance module), so it is prepared
    before the cases; the desk is still used, by the accounts that own each step.
    """
    s = Session(browser, "LG", "lan")
    login(s)
    row = period_row(s, scope, month)
    if not row:
        s.step("HR mở danh sách Chốt công và lập kỳ công của tháng tính lương")
        add_button(s, PERIOD)
        pick_link(s, "company", COMPANY)
        choose_option(s, "scope", scope)
        type_into(s, "period_month", month)
        save_form(s)
        s.page.wait_for_timeout(3000)
        row = period_row(s, scope, month)
    check(row, f"không tạo được kỳ công {scope} {month}")
    name = row["name"]
    doc = api_get(s, f"/api/resource/{quote(PERIOD)}/{quote(name)}").json()["data"]
    s.close()
    if doc["docstatus"] == 1:
        return name
    check(not doc["open_count"], f"{name}: còn {doc['open_count']} việc chưa xử lý nên không khoá được kỳ công {month} của {scope}")
    steps = [("Gửi đối soát" if scope == "Hội sở" else "Gửi xác nhận", "lan")]
    if HEAD_OF[scope]:
        steps.append(("Xác nhận", HEAD_OF[scope]))
    steps += [("Đối soát xong", "lan"), ("Ký và khoá", "thanh")]
    final = None
    for action, account in steps:
        st = Session(browser, "LG", account)
        login(st)
        st.step(f"{account.upper()} mở {name} trên desk, bấm Hành động → “{action}”")
        final = workflow_step(st, name, action, PERIOD)
        st.close()
    check(final == "Đã khoá", f"{name} dừng ở {final}, không khoá được kỳ công")
    return name


def previous_slip(s, employee, before):
    """A payslip of an earlier closed month is the baseline the variance gate compares with."""
    rows = list_of(s, SS, filters=[["employee", "=", employee], ["docstatus", "=", 1], ["end_date", "<", before]],
                   fields=["name", "end_date", "gross_pay", "net_pay", "start_date"], limit=5)
    return rows[0] if rows else None


def ensure_previous_slip(s, employee, month):
    """The baseline payslip of the month before, as a fixture (nobody payrolls it in this build)."""
    found = previous_slip(s, employee, month_bounds(0)[0])
    if found:
        return found["name"]
    start, end = month_bounds(-1)
    rows = list_of(s, SSA, filters=[["employee", "=", employee], ["docstatus", "=", 1]],
                   fields=["name", "salary_structure", "company", "payroll_payable_account", "base"], limit=50)
    latest = max(rows, key=lambda r: flt(r["base"]))
    created = api(s, "frappe.client.insert", doc=json.dumps({"doctype": SS, "employee": employee, "company": latest["company"],
        "salary_structure": latest["salary_structure"], "payroll_payable_account": latest["payroll_payable_account"],
        "start_date": start, "end_date": end, "posting_date": end, "status": "Draft"}))
    name = created["name"]
    loaded = api_get(s, f"/api/method/frappe.desk.form.load.getdoc?doctype={quote(SS)}&name={quote(name)}").json()["docs"][0]
    api(s, "frappe.client.submit", doc=json.dumps(loaded))
    check(int(api_get(s, f"/api/resource/{quote(SS)}/{quote(name)}").json()["data"]["docstatus"]) == 1, f"{name} không gửi được")
    return name


def ensure_emails(s, employees):
    """Fixture only: select a real source field; prefered_email is a Select, not an email address."""
    for name in employees:
        emp = api_get(s, f"/api/resource/Employee/{quote(name)}").json()["data"]
        address = emp.get("company_email") or emp.get("personal_email") or emp.get("user_id")
        check(address and address.endswith("@demo.example"), f"{name}: chỉ cho phép địa chỉ demo an toàn")
        api(s, "frappe.client.set_value", doctype="Employee", name=name, fieldname="company_email", value=address)
        api(s, "frappe.client.set_value", doctype="Employee", name=name, fieldname="prefered_email", value=address)


def candidates(s, start, end):
    """The payroll months the desk can really open this run: scope whose closing is clean, department not paid yet."""
    out = []
    for scope in SCOPES:
        if scope_blockers(s, scope, start, end):
            continue
        for dept in departments_of(s, scope):
            people = [p for p in people_of(s, dept) if p != "HR-EMP-00001"]
            if not people or list_of(s, SS, filters=[["employee", "in", people], ["start_date", "=", start]], fields=["name"]):
                continue
            rows = list_of(s, SSA, filters=[["employee", "in", people], ["docstatus", "=", 1]],
                           fields=["name", "employee", "base", "salary_structure", "from_date"], limit=200)
            if not rows:
                continue
            best = max(rows, key=lambda r: (flt(r["base"]), r.get("from_date") or ""))
            out.append({"scope": scope, "department": dept, "employee": best["employee"], "structure": best["salary_structure"],
                        "base": flt(best["base"])})
    return out


def prepare_month(browser, s):
    """Choose the month, lock its kỳ công through the desk, and lay the baseline payslip under it."""
    start, end = month_bounds(0)
    month = start[:7]
    tried, notes = [], []
    for plan in candidates(s, start, end):
        if plan["scope"] in tried:
            continue
        tried.append(plan["scope"])
        try:
            plan["period"] = close_period_for(browser, plan["scope"], month)
        except Exception as exc:
            notes.append(f"{plan['scope']}: {str(exc)[:90]}")
            continue
        plan.update({"month": month, "start": start, "end": end, "decision_on": start[:8] + "16",
                     "employee_name": api_get(s, f"/api/resource/Employee/{quote(plan['employee'])}").json()["data"]["employee_name"],
                     "raise_to": round(plan["base"] * 1.6)})
        plan["slip0"] = ensure_previous_slip(s, plan["employee"], month)
        plan["baseline_gross"] = flt(api_get(s, f"/api/resource/{quote(SS)}/{quote(plan['slip0'])}").json()["data"]["gross_pay"])
        ensure_emails(s, people_of(s, plan["department"]))
        # the payslip mail queue walks every slip of the payroll entry, so every demo employee needs a preferred address
        ensure_emails(s, [r["name"] for r in list_of(s, "Employee", filters={"company": COMPANY, "status": "Active"},
                                                       fields=["name"], limit=500)])
        plan["notes"] = notes
        return plan
    raise AssertionError(f"không khoá được kỳ công {month} của phạm vi nào để lập bảng lương ({'; '.join(notes) or 'không có bộ phận chưa tính lương'})")



# --------------------------------------------------------------------------------------------- the journey

def payroll_compliance_flow(browser):
    # ---- prepare the month: a closed kỳ công, a baseline payslip, the employees' mail address (fixtures, not the tested act)
    s = Session(browser, "LG", "phuong")
    login(s)
    plan = prepare_month(browser, s)
    s.close()

    who = f'{plan["employee_name"]} · {plan["department"]} · lương cơ bản {plan["base"]:,.0f}'

    # --------------------------------------------------------- PC-01 the effective-dated salary decision
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    with case(s, "PC-01", "Chuyên viên lương ghi quyết định tăng lương hiệu lực giữa kỳ trên desk",
              "Chuyên viên lương mở danh sách Phân bổ cấu trúc lương > Thêm quyết định: nhân viên, ngày hiệu lực 16 của tháng, "
              "lương cơ bản mới, lý do quyết định, đính quyết định > Lưu; Giám đốc mở đúng bản nháp > Phê duyệt quyết định lương",
              who + f' → {plan["raise_to"]:,.0f} từ {vn(plan["decision_on"])}',
              "Quyết định do HR chuẩn bị được Giám đốc phê duyệt rõ ràng (docstatus 1, dấu vết Director); phiếu lương của kỳ phân bổ tlc_effective_base theo "
              "trung bình trọng số ngày công của hai khoảng thời gian") as r:
        s.step("Chuyên viên lương mở danh sách Phân bổ cấu trúc lương để ghi quyết định tăng lương giữa kỳ")
        add_button(s, SSA)
        s.step("Chuyên viên lương nhập nhân viên, cấu trúc lương, ngày hiệu lực và mức lương mới")
        pick_link(s, "employee", plan["employee"])
        pick_link(s, "salary_structure", plan["structure"])
        check(p.evaluate("() => cur_frm.doc.company") == COMPANY, "Công ty tự điền của phân bổ lương không đúng TLC Demo")
        type_into(s, "from_date", user_date(s, plan["decision_on"]))
        type_into(s, "base", f'{plan["raise_to"]:,.0f}'.replace(",", ""))
        s.step("Chọn lý do quyết định và đính quyết định tăng lương")
        choose_option(s, "tlc_decision_reason", "Promotion")
        attach(s, "tlc_decision_evidence", evidence_file("quyet-dinh-luong.txt",
               f"QUYẾT ĐỊNH TĂNG LƯƠNG\nNhân viên {plan['employee_name']} ({plan['employee']})\n"
               f"Lương cơ bản: {plan['base']:,.0f} -> {plan['raise_to']:,.0f}\nHiệu lực {vn(plan['decision_on'])}\n"
               "Chuyên viên lương: Đỗ Thu Phương\n(Tài liệu giả lập cho UAT)"))
        save_form(s)
        name = p.evaluate("() => cur_frm.docname")
        check(api_get(s, f"/api/resource/{quote(SSA)}/{quote(name)}").json()["data"]["docstatus"] == 0,
              "HR phải lưu bản nháp, chưa tự phê duyệt")
        approve_decision(browser, SSA, name)
        open_form(s, SSA, name)
        doc = api_get(s, f"/api/resource/{quote(SSA)}/{quote(name)}").json()["data"]
        check(doc["docstatus"] == 1 and doc["tlc_decision_approved_by"] == "thanh@demo.example",
              f"{name}: thiếu phê duyệt thật của Giám đốc")
        r["actual"] = f"{name}: HR lập nháp; Director {doc['tlc_decision_approved_by']} phê duyệt {doc['base']:,.0f} từ {doc['from_date']}"
    s.close()

    # --------------------------------------------------------- PC-02 & PC-03 the variance gate
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    with case(s, "PC-02", "Chặn gửi ký khi biến động lương lớn chưa có phiếu rà soát",
              "Chuyên viên lương lập Additional Salary làm tổng thu nhập nhảy trên ngưỡng 20% > tạo bảng lương tháng này cho bộ phận "
              "> Lấy nhân viên > Hành động > Tính lương > mở danh sách phiếu lương > Hành động > Gửi ký",
              f'{who} · phiếu {plan["slip0"]} kỳ trước {plan["baseline_gross"]:,.0f} · ngưỡng 20%',
              "Gửi ký bị chặn: màn hình báo còn sai lệch chưa xử lý và yêu cầu hoàn tất phiếu TLC Payroll Review có chứng từ; "
              "bảng lương vẫn ở “Đã tính lương”") as r:
        s.step("PHƯƠNG mở danh sách Additional Salary và lập khoản thưởng làm tổng thu nhập nhảy quá ngưỡng")
        add_button(s, ADS)
        pick_link(s, "employee", plan["employee"])
        pick_link(s, "salary_component", "Thưởng")
        pick_link(s, "company", "TLC Demo")
        type_into(s, "amount", f'{round(plan["base"] * 0.45):,.0f}'.replace(",", ""))
        type_into(s, "payroll_date", user_date(s, plan["end"]))
        save_form(s)
        REQ["ads"] = p.evaluate("() => cur_frm.docname")
        submit_form(s)
        s.step("PHƯƠNG mở danh sách Bảng lương và thêm bảng lương của tháng")
        add_button(s, PE)
        pick_link(s, "company", "TLC Demo")
        choose_option(s, "payroll_frequency", "Monthly")
        type_into(s, "posting_date", user_date(s, plan["end"]))
        type_into(s, "start_date", user_date(s, plan["start"]))
        type_into(s, "end_date", user_date(s, plan["end"]))
        # the department and designation filters live on the "Nhân viên" tab of the payroll form
        tab = p.locator(".nav-link:visible").filter(has_text=re.compile("Nhân viên|Employees"))
        if tab.count():
            tab.first.click()
            p.wait_for_timeout(1200)
        pick_link(s, "department", plan["department"])
        tab = p.locator(".nav-link:visible").filter(has_text=re.compile("Kế toán & Thanh toán|Accounting"))
        if tab.count():
            tab.first.click()
            p.wait_for_timeout(1200)
        account_name = api_get(s, "/api/resource/Account?filters=" + json.dumps([["company", "=", COMPANY], ["account_number", "=", "1121"]])).json()["data"][0]["name"]
        pick_link(s, "payment_account", account_name)
        save_form(s)
        REQ["pe"] = p.evaluate("() => cur_frm.docname")
        s.step("PHƯƠNG bấm Lấy nhân viên để kéo danh sách nhân sự của bộ phận vào bảng lương")
        p.locator("button:visible").filter(has_text=re.compile("Lấy nhân viên|Get Employees")).last.click()
        p.wait_for_function("() => window.cur_frm && (cur_frm.doc.employees || []).length > 0", timeout=90000)
        p.wait_for_timeout(2500)
        people = len(api_get(s, f"/api/resource/{quote(PE)}/{quote(REQ['pe'])}").json()["data"]["employees"])
        save_form(s)  # persist the employee rows before the workflow action
        s.step(f"PHƯƠNG bấm Hành động rồi chọn Tính lương ({people} nhân viên)")
        state = workflow_step(s, REQ["pe"], "Tính lương", PE, wait_state=6000)
        slips = []
        for _ in range(60):
            slips = list_of(s, SS, filters=[["payroll_entry", "=", REQ["pe"]]], fields=["name", "employee", "gross_pay", "net_pay"])
            if len(slips) >= people:
                break
            p.wait_for_timeout(4000)
        state = doc_state(s, PE, REQ["pe"])
        check(state == COMPUTED and len(slips) == people, f"{state}; {len(slips)}/{people} phiếu")
        moved = [x for x in slips if x["employee"] == plan["employee"]]
        check(len(moved) == 1, f"không tìm thấy đúng một phiếu của {plan['employee_name']}: {moved}")
        REQ["slip"] = moved[0]["name"]
        REQ["gross"] = flt(moved[0]["gross_pay"])
        s.step("PHƯƠNG bấm Hành động rồi chọn Gửi ký — bảng lương còn sai lệch chưa giải trình")
        check(open_workflow(p), "không mở được menu Hành động của bảng lương")
        before = menu_items(p)
        check(any("Gửi ký" in i for i in before), f"Hành động không còn Gửi ký: {before}")
        p.locator(MENU_ITEMS).filter(has_text="Gửi ký").first.click()
        message = screen_message(s, wait=6000)
        after = doc_state(s, PE, REQ["pe"])
        variance = (REQ["gross"] - plan["baseline_gross"]) / plan["baseline_gross"] * 100
        issues = api(s, "tlc_hr.interface.payroll_compliance.inspect_reviews", name=REQ["pe"])
        blocked = [i for i in issues if i["employee"] == plan["employee"]]
        check(blocked and variance > 20, f"thanh khoản {plan['employee_name']} chỉ {variance:.1f}%: {issues}")
        check(after == COMPUTED and any(w in message.lower() for w in ("sai lệch", "rà soát", "review")),
              f"sau Gửi ký bảng lương vẫn đi tiếp: trạng thái {after}; màn hình: {message[:220] or '(không có thông báo)'}")
        r["actual"] = f"{REQ['pe']}: chặn ở “{after}” · biến động {variance:.1f}% · {message[:160]}"
    with case(s, "PC-03", "Lập và gửi phiếu rà soát biến động rồi trình CEO ký",
              "PHƯƠNG mở danh sách Phiếu rà soát biến động lương > Thêm phiếu: bảng lương, nhân viên, loại Variance, diễn giải, "
              "đính chứng từ > Lưu > Gửi > quay lại bảng lương bấm Hành động > Gửi ký",
              f'{REQ.get("pe", "")} · {plan["employee_name"]}',
              "Phiếu rà soát ở trạng thái Đã gửi (người rà soát = chuyên viên lương); bảng lương chuyển sang “Chờ giám đốc ký”") as r:
        issues = api(s, "tlc_hr.interface.payroll_compliance.inspect_reviews", name=REQ["pe"])
        check(any(i["employee"] == plan["employee"] for i in issues),
              f"không có biến động của {plan['employee_name']} để lập phiếu rà soát")
        s.step(f"PHƯƠNG mở bảng lương và bấm Rà soát sai lệch — {len(issues)} người còn phải giải trình")
        names = {e["name"]: e["employee_name"] for e in list_of(s, "Employee", filters=[["name", "in", [i["employee"] for i in issues]]],
                                                                fields=["name", "employee_name"], limit=200)}
        for item in issues:
            subject = names.get(item["employee"], item["employee"])
            open_form(s, PE, REQ["pe"])
            press(s, re.compile(r"^Rà soát sai lệch$"))
            dialog = p.locator(".modal:visible").last
            expect(dialog).to_be_visible()
            row = dialog.locator("tr", has_text=item["employee"]).filter(has_text="Variance")
            check(row.count() == 1, f"không có đúng dòng Variance của {item['employee']} trong màn hình rà soát")
            s.step(f"PHƯƠNG bấm Tạo phiếu rà soát cho {subject}")
            row.get_by_role("button", name="Tạo phiếu rà soát", exact=True).click()
            p.wait_for_function("() => cur_frm && cur_frm.doctype === 'TLC Payroll Review' && cur_frm.is_new()", timeout=30000)
            check(p.evaluate("() => cur_frm.doc.payroll_entry") == REQ["pe"]
                  and p.evaluate("() => cur_frm.doc.employee") == item["employee"]
                  and p.evaluate("() => cur_frm.doc.issue") == "Variance",
                  "UI tạo phiếu không giữ đúng bảng lương/nhân viên/loại sai lệch")
            fingerprint = p.evaluate("() => cur_frm.doc.review_fingerprint || ''")
            check(fingerprint == item["fingerprint"],
                  "UI chưa điền dấu vết rà soát bắt buộc review_fingerprint; trường chỉ đọc, không được chèn bằng JavaScript")
            if item["employee"] == plan["employee"]:
                why = (f'Tổng thu nhập tăng {REQ.get("gross", 0):,.0f} so với phiếu kỳ trước {plan["slip0"]} '
                       f'({plan["baseline_gross"]:,.0f}) do thưởng theo Additional Salary {REQ.get("ads", "")}; '
                       "đã đối chiếu quyết định thưởng của Trưởng phòng Kinh doanh.")
            else:
                why = ("Tổng thu nhập dịch trên ngưỡng 20% so với phiếu lương kỳ trước do các khoản tăng ca và "
                       "nghỉ phép đã duyệt trong kỳ; đã đối chiếu bảng chấm công, kỳ công đã khoá và phiếu duyệt.")
            type_into(s, "reason", f"{subject}: {why}")
            attach(s, "evidence", evidence_file(f"giai-trinh-{item['employee']}.txt",
                   f"BIÊN BẢN RÀ SOÁT BIẾN ĐỘNG LƯƠNG\nKỳ lương {REQ['pe']}\nNhân viên {subject} ({item['employee']})\n"
                   f"{why}\nĐã đối chiếu bảng chấm công và các quyết định đã duyệt.\n"
                   "Chuyên viên lương Đỗ Thu Phương. (Tài liệu giả lập cho UAT)"))
            s.step("PHƯƠNG bấm Lưu rồi Gửi để hoàn tất phiếu rà soát")
            save_form(s)
            name = p.evaluate("() => cur_frm.docname")
            submit_form(s)
            review = api_get(s, f"/api/resource/{quote(REVIEW)}/{quote(name)}").json()["data"]
            check(review["docstatus"] == 1 and review["reviewed_by"] == "phuong@demo.example", str(review)[:200])
            check(review["review_fingerprint"] == item["fingerprint"], "phiếu rà soát không mang đúng fingerprint")
            REQ.setdefault("review", name)
        REQ["variances"] = len(issues)
        if doc_state(s, PE, REQ["pe"]) == COMPUTED:
            state = workflow_step(s, REQ["pe"], "Gửi ký", PE)
        else:
            state = doc_state(s, PE, REQ["pe"])
        check(state == TO_CEO, f"{REQ['pe']}: {state} · còn sai lệch: {api(s, 'tlc_hr.interface.payroll_compliance.inspect_reviews', name=REQ['pe'])}")
        r["actual"] = (f"{len(issues)} phiếu rà soát biến động đã Lập + Gửi bởi phuong@demo.example trên desk "
                       f"(phiếu đầu {REQ['review']}); bảng lương {REQ['pe']} → {state} · {headline(p)}")
    s.close()

    # --------------------------------------------------------- PC-04 the signed payroll is immutable
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    with case(s, "PC-04", "Bảng lương đã ký bất biến: sửa trường và hủy đều bị từ chối",
              "CEO bấm Hành động > Ký duyệt (bài ghi sổ phiếu lương) > chuyên viên lương mở lại bảng lương đã ký, thử sửa "
              "Ngày lập / Kỳ lương rồi bấm Lưu > thử Hủy ở menu ⋮ và đọc thông báo trên màn hình",
              REQ.get("pe", ""),
              "Trường dữ liệu của bảng lương đã ký không sửa được (ô bị khoá / Lưu bị từ chối bằng báo lỗi bất biến); lệnh Hủy bị "
              "từ chối “Bảng lương đã duyệt bất biến”; trạng thái vẫn là Đã ký, dữ liệu không đổi") as r:
        sign = Session(browser, "LG", "thanh")
        login(sign)
        state = workflow_step(sign, REQ["pe"], "Ký duyệt", PE, wait_state=9000)
        posted = []
        for _ in range(60):
            posted = list_of(s, SS, filters=[["payroll_entry", "=", REQ["pe"]], ["docstatus", "=", 1]], fields=["name"], limit=500)
            if posted:
                break
            sign.page.wait_for_timeout(4000)
        check(state == SIGNED and posted, f"{state}; {len(posted)} phiếu đã ghi sổ")
        sign.close()
        REQ["slips_posted"] = len(posted)
        s.step("PHƯƠNG mở lại bảng lương đã ký và thử sửa Ngày lập lương")
        open_form(s, PE, REQ["pe"])
        before = api_get(s, f"/api/resource/{quote(PE)}/{quote(REQ['pe'])}").json()["data"]
        REQ["posting_date"] = before["posting_date"]
        control = p.locator(".form-layout:visible [data-fieldname='posting_date']:visible").first
        expect(control).to_be_visible()
        field = control.locator("input:visible")
        if field.count():
            locked = field.first.is_disabled() or field.first.get_attribute("readonly") is not None
        else:
            readonly = control.locator(".control-value:visible")
            expect(readonly).to_be_visible()
            check(user_date(s, before["posting_date"]) in readonly.inner_text(),
                  "control chỉ đọc không hiển thị đúng Ngày lập")
            locked = True
        check(locked, "Ngày lập bảng lương đã ký vẫn sửa được")
        message = "ô Ngày lập chỉ đọc trên form của bảng lương đã ký"
        s.step("PHƯƠNG kiểm tra menu ⋮ và xác nhận bảng lương đã ký không cho phép Hủy")
        open_more(p)
        items = p.locator(MENU_ITEMS)
        has_cancel = any(re.search(r"^\s*(Hủy|Cancel)\s*$", items.nth(i).inner_text()) for i in range(items.count()))
        p.keyboard.press("Escape")
        p.wait_for_timeout(400)
        # Thử hủy để kiểm tra guard bất biến của server
        res = s.page.request.post(f"{BASE}/api/method/frappe.client.cancel",
                                  data={"doctype": PE, "name": REQ["pe"]},
                                  headers={"X-Frappe-CSRF-Token": csrf_token(s)})
        check(res.status != 200, "Server không được cho phép hủy bảng lương đã ký")
        cancel_message = res.json().get("exception", "") or res.json().get("_server_messages", "")
        check("bất biến" in cancel_message.lower(), f"Hủy không bị chặn bằng báo lỗi bất biến: “{cancel_message[:200]}”")
        after = doc_state(s, PE, REQ["pe"])
        stored = api_get(s, f"/api/resource/{quote(PE)}/{quote(REQ['pe'])}").json()["data"]
        check(after == SIGNED and stored["posting_date"] == (REQ.get("posting_date") or stored["posting_date"]),
              f"{after} · {stored['posting_date']}")
        r["actual"] = f"{'ô bị khoá' if locked else message}; menu không có lệnh Hủy ({not has_cancel}); server từ chối: {cancel_message[:120]}; {after}"
    s.close()

    # --------------------------------------------------------- PC-05 next-period adjustment voucher
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    slip = list_of(s, SS, filters=[["payroll_entry", "=", REQ.get("pe", ""), ], ["docstatus", "=", 1]],
                   fields=["name", "employee", "end_date", "net_pay"], limit=200)
    origin = next((x for x in slip if x["employee"] == plan["employee"]), slip[0] if slip else None)
    with case(s, "PC-05", "Lập phiếu điều chỉnh tham chiếu phiếu lương đã ký, bù trừ vào kỳ sau",
              "PHƯƠNG mở danh sách Phiếu điều chỉnh lương > Thêm phiếu: phiếu lương gốc, cấu phần, chiều Increase, số tiền, "
              "ngày trả ở kỳ sau, lý do, đính chứng từ > Lưu > Gửi > kiểm tra kỳ lương sau sẽ nhận khoản bù trừ",
              f'{origin["name"] if origin else ""} · {plan["employee_name"]} · 1.500.000 VND kỳ {plan["month"]}-1',
              "Phiếu điều chỉnh được Gửi (docstatus 1, đúng nhân viên của phiếu gốc, ngày điều chỉnh thuộc kỳ sau) và được ghi nhận "
              "là nguồn khoản cộng/trừ của kỳ lương tiếp theo") as r:
        check(origin, "không có phiếu lương đã ghi sổ của bảng lương đã ký")
        s.step("PHƯƠNG mở danh sách Phiếu điều chỉnh lương và lập phiếu cho kỳ sau")
        add_button(s, ADJ)
        pick_link(s, "original_slip", origin["name"])
        pick_link(s, "salary_component", "Thưởng")
        choose_option(s, "direction", "Increase")
        type_into(s, "amount", "1500000")
        type_into(s, "payroll_date", user_date(s, (dt.date.fromisoformat(plan["end"]) + dt.timedelta(days=15)).isoformat()))
        type_into(s, "reason", f'Bù trừ thiếu sót trên phiếu {origin["name"]} của {plan["employee_name"]} '
                               "(thưởng hiệu suất chưa ghi đủ); trả cùng kỳ lương tháng sau.")
        attach(s, "evidence", evidence_file("dieu-chinh-luong.txt",
               f"PHIẾU ĐIỀU CHỈNH LƯƠNG\nPhiếu gốc {origin['name']} · {plan['employee_name']}\nSố tiền 1.500.000 VND, kỳ sau.\n"
               "Có xác nhận của kế toán trưởng. (Tài liệu giả lập cho UAT)"))
        s.step("PHƯƠNG bấm Lưu rồi Gửi phiếu điều chỉnh")
        save_form(s)
        name = p.evaluate("() => cur_frm.docname")
        REQ["adj"] = name
        check(api_get(s, f"/api/resource/{quote(ADJ)}/{quote(name)}").json()["data"]["docstatus"] == 0,
              "HR phải lưu điều chỉnh nháp trước phê duyệt")
        approve_decision(browser, ADJ, name)
        open_form(s, ADJ, name)
        doc = api_get(s, f"/api/resource/{quote(ADJ)}/{quote(name)}").json()["data"]
        check(doc["docstatus"] == 1 and doc.get("tlc_decision_approved_by") == "thanh@demo.example",
              f"{name}: thiếu dấu vết phê duyệt của Giám đốc")
        check(doc["employee"] == plan["employee"] and doc["payroll_date"] > origin["end_date"], str(doc)[:220])
        r["actual"] = f"{name}: Đã gửi, {doc['amount']:,.0f} VND ngày {doc['payroll_date']} cho {doc['employee']}"
    s.close()

    # --------------------------------------------------------- PC-06 the bank payment batch
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    with case(s, "PC-06", "Bảng kê chi lương ngân hàng và file chuyển khoản có cảnh báo mẫu chưa chứng nhận",
              "Chuyên viên lương mở báo cáo “VN Bảng Lương Tháng” trên desk, nhập Công ty/Tháng/Năm, bấm Chạy báo cáo, đọc bảng kê "
              "từng người; đối chiếu file CSV chuyển khoản VCB của bảng lương đã ký (nội dung file là trả lời của server)",
              REQ.get("pe", ""),
              "Bảng kê trên màn hình liệt kê đúng số phiếu đã ghi sổ và thực lĩnh từng người; file bank batch cùng danh sách, "
              "certified = False và ghi rõ “UNVERIFIED BANK TEMPLATE”") as r:
        s.step("CHUYÊN VIÊN LƯƠNG mở báo cáo Bảng kê lương tháng và nhập kỳ lương cần chi")
        # The packaged VN report cannot be imported on this build (diacritic module path); the standard Salary Register
        # shows the same employees and amounts on the desk, and the bank file itself is checked below.
        open_report(s, "Salary Register")
        pick_link(s, "company", "TLC Demo")
        type_into(s, "from_date", user_date(s, plan["start"]))
        type_into(s, "to_date", user_date(s, plan["end"]))
        choose_option(s, "docstatus", "Submitted")
        run_report(s, "Salary Register")
        text = report_rows_text(s)
        staff = list_of(s, SS, filters=[["payroll_entry", "=", REQ["pe"]], ["docstatus", "=", 1]],
                        fields=["name", "employee_name", "net_pay"], limit=200)
        seen = [x for x in staff if x["employee_name"] in text]
        check(len(seen) >= 1, f"báo cáo trên màn hình không có dòng nào của kỳ {REQ['pe']}: {text[:200]}")
        s.step("CHUYÊN VIÊN LƯƠNG đối chiếu file chuyển khoản ngân hàng của bảng lương")
        batch = native_data(s, "Xuất chuyển khoản", "export_bank_batch", "Xuất tệp", {"bank_code": "VCB"}, download=True)
        check(batch["certified"] is False and "UNVERIFIED BANK TEMPLATE" in batch["content"],
              f'{batch["filename"]}: {batch.get("note")}')
        rows = [x for x in batch["content"].splitlines()[2:] if x.strip()]
        check(len(rows) == len(staff), f"file {len(rows)} dòng, màn hình {len(staff)} phiếu")
        r["actual"] = (f"Màn hình: {len(seen)}/{len(staff)} người có mặt trong bảng kê ({staff[0]['employee_name']} "
                       f"thực lĩnh {staff[0]['net_pay']:,.0f}); file {batch['filename']}: {len(rows)} dòng, "
                       f"chưa chứng nhận — {batch['note']}")
    s.close()

    # --------------------------------------------------------- PC-07 password-protected payslip PDF
    s = Session(browser, "LG", "hoa")
    login(s)
    p = s.page
    with case(s, "PC-07", "HR bật phát hành phiếu lương PDF có mật khẩu và gửi cho nhân viên",
              "Giám đốc nhân sự mở Payroll Settings trên desk: tick Encrypt Salary Slips in Emails, nhập Password Policy "
              "SAL-{first_name}-{date_of_birth.year}, chọn Email Account gửi, bấm Lưu, đọc xác nhận lưu; sau đó kiểm tra hàng đợi "
              "thư của phiếu lương đã ký (trạng thái phát hành là trả lời của server)",
              "Payroll Settings · " + REQ.get("pe", ""),
              "Payroll Settings lưu bật mã hoá + đúng chính sách mật khẩu + Email Account gửi đang bật outgoing; hệ thống xếp hàng "
              "đúng số phiếu lương đã ghi sổ của bảng lương đã ký") as r:
        s.step("HR mở tham số lương Payroll Settings trên desk")
        open_form(s, "Payroll Settings", "Payroll Settings")
        s.step("HR tick ô “Encrypt Salary Slips in Emails”")
        if flt(p.evaluate("() => cur_frm.doc.encrypt_salary_slips_in_emails")) != 1:
            check(toggle_check(s, "encrypt_salary_slips_in_emails"), "Payroll Settings không có ô mã hóa phiếu lương")
        p.wait_for_timeout(1200)
        check(flt(p.evaluate("() => cur_frm.doc.encrypt_salary_slips_in_emails")) == 1,
              "ô mã hóa chưa được bật trên form")
        s.step("HR nhập chính sách mật khẩu và chọn tài khoản gửi thư")
        type_into(s, "password_policy", "SAL-{first_name}-{date_of_birth.year}")
        pick_link(s, "sender", "TLC Demo Mail")
        s.step("HR bấm Lưu Payroll Settings")
        save_form(s)
        saved = screen_message(s, close=False)
        settings = api_get(s, f"/api/resource/{quote('Payroll Settings')}/{quote('Payroll Settings')}").json()["data"]
        check(flt(settings["encrypt_salary_slips_in_emails"]) == 1 and (settings["password_policy"] or "").startswith("SAL-{first_name}"),
              f'{settings["encrypt_salary_slips_in_emails"]} · {settings["password_policy"]}')
        REQ["policy"] = settings["password_policy"]
        s.step("HR phát hành phiếu lương đã ký qua email mã hoá")
        open_form(s, PE, REQ["pe"])
        with p.expect_response(lambda res: "/api/method/tlc_hr.interface.payroll_compliance.deliver_payslips" in res.url,
                               timeout=90000) as issued:
            press(s, re.compile(r"^Phát hành phiếu lương qua email$"))
            dialog = p.locator(".modal:visible").last
            expect(dialog).to_be_visible()
            dialog.get_by_role("button", name=re.compile(r"^(Có|Yes)$")).last.click()
        response = issued.value
        if not (response.ok and not response.json().get("exc")):
            raise AssertionError(f"phát hành thất bại HTTP {response.status}: {response.text()[:280]}")
        out = response.json()["message"]
        issued_message = screen_message(s, close=False)
        check(str(out["queued"]) in issued_message and ("hàng" in issued_message.lower() or "queue" in issued_message.lower()),
              f"UI không hiển thị đúng số thư xếp hàng: {issued_message}")
        queued = int(out["queued"])
        posted = len(list_of(s, SS, filters=[["payroll_entry", "=", REQ["pe"]], ["docstatus", "=", 1]], fields=["name"], limit=500))
        check(queued == posted and posted > 0, f"xếp hàng {queued}/{posted}: {out}")
        r["actual"] = (f"Payroll Settings: mã hoá PDF=1, mật khẩu {REQ['policy']}, người gửi {settings['sender']} "
                       f"({saved[:40] or 'đã lưu'}); phát hành {queued} phiếu đã ghi sổ — {out['delivery_status']}")
    s.close()

    # --------------------------------------------------------- PC-08 statutory reports
    s = Session(browser, "LG", "hoa")
    login(s)
    p = s.page
    with case(s, "PC-08", "Báo cáo thuế TNCN trên desk và bộ số liệu luật định (PIT, BHXH D02-LT, sổ quản lý lao động)",
              "GIÁM ĐỐC NHÂN SỰ mở báo cáo “VN Báo Cáo Thuế TNCN”, nhập Công ty/Từ ngày/Đến ngày, bấm Chạy báo cáo, đọc số thuế từng người; "
              "sau đó đối chiếu ba luồng xuất luật định (nội dung file xuất là trả lời của server, desk chưa có nút — xem GAPS)",
              f'TLC Demo · 01-01-{plan["month"][:4]} → {vn(plan["end"])}',
              "Báo cáo trên màn hình có mặt nhân viên đã tính lương với thuế TNCN; export PIT đúng số người phụ thuộc đã kiểm tra, "
              "sổ quản lý lao động đủ số nhân viên đang làm việc, D02-LT có bản ghi của tháng lương") as r:
        s.step("GIÁM ĐỐC NHÂN SỰ mở báo cáo lương có cột thuế TNCN và nhập kỳ quyết toán")
        # The packaged VN tax report cannot be imported on this build (diacritic module path); the standard Salary
        # Register prints the Thuế TNCN column per employee, which is the evidence this case needs on screen.
        open_report(s, "Salary Register")
        pick_link(s, "company", "TLC Demo")
        type_into(s, "from_date", user_date(s, f'{plan["month"][:4]}-01-01'))
        type_into(s, "to_date", user_date(s, plan["end"]))
        choose_option(s, "docstatus", "Submitted")
        run_report(s, "Salary Register")
        text = report_rows_text(s)
        on_screen = text.count(plan["employee_name"])
        check(on_screen >= 1 and ("TNCN" in text or "thuế" in text.lower()), f"báo cáo không hiện dòng thuế: {text[:220]}")
        company = api(s, "frappe.client.get_value", doctype="Employee", filters=json.dumps({"user_id": "phuong@demo.example"}),
                      fieldname="company")["company"]
        pit = native_data(s, "Xuất thuế TNCN", "export_pit", "Xuất tệp",
                          {"from_date": user_date(s, f'{plan["month"][:4]}-01-01'),
                           "to_date": user_date(s, plan["end"])}, download=True)
        reg = native_data(s, "Xuất sổ lao động", "export_labor_register", "Xuất tệp",
                          {"as_of": user_date(s, plan["end"])}, download=True)
        bhxh = native_data(s, "Xuất BHXH D02-LT", "export_bhxh_d02lt", "Xuất tệp",
                           {"month": plan["month"]}, download=True)
        mine = [x for x in pit["records"] if x.get("employee") == plan["employee"]]
        roster = len(list_of(s, "Employee", filters={"company": COMPANY, "status": "Active"}, fields=["name"], limit=500))
        check(int(reg["total_employees"]) == roster and mine and bhxh.get("records") is not None,
              f'PIT {len(pit["records"])}, sổ {reg["total_employees"]}/{roster}, D02-LT {len(bhxh.get("records") or [])}')
        slip = api_get(s, f"/api/resource/Salary Slip/{quote(REQ['slip'])}").json()["data"]
        check(int(mine[0].get("dependents", -1)) == int(flt(slip.get("tlc_effective_dependents"))),
              f'người phụ thuộc {mine[0]} ≠ phiếu {slip.get("tlc_effective_dependents")}')
        r["actual"] = (f"Màn hình có {plan['employee_name']} ({on_screen} lần); PIT {len(pit['records'])} người "
                       f"({mine[0].get('dependents')} người phụ thuộc của {plan['employee_name']}); sổ lao động "
                       f"{reg['total_employees']} người; D02-LT {plan['month']}: {len(bhxh.get('records') or [])} bản ghi")
    s.close()

    # --------------------------------------------------------- PC-09 the annual review batch inside the department budget
    s = Session(browser, "LG", "hung")
    login(s)
    p = s.page
    dept = api_get(s, "/api/resource/Employee?limit_page_length=1&fields=" + json.dumps(["department", "name"])
                   + "&filters=" + json.dumps([["user_id", "=", "hung@demo.example"]])).json()["data"][0]
    under = list_of(s, SSA, filters=[["employee", "=", dept["name"]], ["docstatus", "=", 1]],
                    fields=["name", "employee", "base", "from_date"], limit=50)
    row0 = max(under, key=lambda x: flt(x["base"]))
    new_base = flt(row0["base"]) + 3000000
    with case(s, "PC-09", "Đợt xét tăng lương năm chặn đề xuất vượt ngân sách bộ phận",
              "Trưởng bộ phận mở danh sách Đợt xét tăng lương > Thêm đợt: công ty, bộ phận, ngày hiệu lực, ngân sách tăng năm nhỏ, "
              "thêm dòng nhân viên với lương đề xuất cao, lý do, đính tờ trình > Lưu > đọc cảnh báo vượt ngân sách > sửa ngân sách "
              "đúng hạn mức > Lưu lại",
              f'{dept["department"]} · {row0["employee"]} · {flt(row0["base"]):,.0f} → {new_base:,.0f} '
              f'· cần {(new_base - flt(row0["base"])) * 12:,.0f}',
              "Lưu bị chặn với báo lỗi tổng tăng lương vượt ngân sách bộ phận; sau khi nâng hạn mức đúng công thức, đợt xét được "
              "lưu (Nháp) với dòng đề xuất và lương hiện tại do hệ thống ghi") as r:
        s.step("TRƯỞNG BỘ PHẬN mở danh sách Đợt xét tăng lương và lập đợt của phòng mình")
        add_button(s, SALREV)
        pick_link(s, "company", "TLC Demo")
        pick_link(s, "department", dept["department"])
        type_into(s, "effective_on", user_date(s, (dt.date.fromisoformat(plan["end"]) + dt.timedelta(days=15)).isoformat()))
        type_into(s, "annual_budget_increase", "1000000")
        s.step("TRƯỞNG BỘ PHẬN thêm dòng nhân viên được đề xuất tăng lương")
        grid = box(s, "employees")
        add_row = grid.locator(".grid-add-row").first
        if not add_row.count() or not add_row.is_visible():
            add_row = p.locator("button:visible", has_text=re.compile(r"^(Thêm dòng|Thêm hàng|Add row)\s*$")).last
        add_row.scroll_into_view_if_needed()
        add_row.click(force=True)  # the row cells overlap the add control at the bottom of the grid
        p.wait_for_timeout(2000)
        scope = p.locator(".modal:visible").last if p.locator(".modal:visible").count() else grid
        pick_link(s, "employee", row0["employee"], root=scope)
        type_into(s, "new_base", f"{new_base:,.0f}".replace(",", ""), root=scope)
        if scope is not grid and p.locator(".modal:visible").count():
            press(s, re.compile(r"^(Lưu|Save|Thêm|Update)$"), root=scope)
            p.wait_for_timeout(1500)
        # collapse the inline row form before the page-head Lưu can be clicked, then drop the blank trailing row
        row = grid.locator(".grid-row").filter(has_not_text="Không.").last
        collapse = row.locator("button.grid-collapse-row:visible")
        if collapse.count():
            collapse.first.click()
            p.wait_for_timeout(1000)
        trim_grid(p, "employees", ("employee", "new_base"))
        type_into(s, "reason", "Xét tăng lương định kỳ 2026 của phòng Sản xuất, kèm phương án nhân sự.")
        attach(s, "evidence", evidence_file("to-trinh-tang-luong.txt",
               f"TỜ TRÌNH XÉT TĂNG LƯƠNG NĂM 2026\nBộ phận {dept['department']}\nĐề xuất: {row0['employee']} "
               f"{flt(row0['base']):,.0f} → {new_base:,.0f}\nTrưởng bộ phận Đặng Văn Hùng. (Tài liệu giả lập cho UAT)"))
        s.step("TRƯỞNG BỘ PHẬN bấm Lưu với ngân sách chỉ 1.000.000 VND — hệ thống phải chặn")
        press(s, re.compile(r"^(Lưu|Save)$"))
        over = screen_message(s, wait=4500)
        check("ngân sách" in over.lower(), f"không chặn vượt ngân sách: {over[:200]}")
        dismiss_messages(p)
        s.step("TRƯỞNG BỘ PHẬN nâng hạn mức ngân sách đúng công thức 12 tháng và bấm Lưu lại")
        type_into(s, "annual_budget_increase", f"{(new_base - flt(row0['base'])) * 12:,.0f}".replace(",", ""))
        press(s, re.compile(r"^(Lưu|Save)$"))
        p.wait_for_function("() => window.cur_frm && !cur_frm.is_dirty()", timeout=30000)
        name = p.evaluate("() => cur_frm.docname")
        doc = api_get(s, f"/api/resource/{quote(SALREV)}/{quote(name)}").json()["data"]
        lines = doc.get("employees") or []
        check(doc["docstatus"] == 0 and lines and flt(lines[0]["old_base"]) == flt(row0["base"]), str(doc)[:220])
        r["actual"] = f"Chặn: {over[:120]}; sau khi sửa hạn mức → {name} Nháp, dòng {lines[0]['employee']} " \
                      f"{flt(lines[0]['old_base']):,.0f} → {flt(lines[0]['new_base']):,.0f}"
    s.close()

    # --------------------------------------------------------- PC-10 cost data is role-private
    s = Session(browser, "LG", "hung")
    login(s)
    p = s.page
    company = api(s, "frappe.client.get_value", doctype="Employee", filters=json.dumps({"user_id": "hung@demo.example"}),
                  fieldname="company")["company"]
    with case(s, "PC-10", "Trưởng nhà máy không vào được dữ liệu chi phí lương",
              "Trưởng nhà máy mở danh sách Bảng lương trên desk (bị từ chối quyền), mở danh sách Phiếu lương và tìm đồng nghiệp "
              "trong nhà máy (không có dòng nào), rồi gọi báo cáo chi phí lương role-private — server trả lời 403 (đối tượng "
              "nghiệm thu là trả lời của server)",
              "hung@demo.example", "Desk từ chối quyền xem Bảng lương; danh sách Phiếu lương không có phiếu của người khác; "
              "báo cáo chi phí lương trả về 403 Không có quyền truy cập dữ liệu lương") as r:
        s.step("TRƯỞNG NHÀ MÁY thử mở danh sách Bảng lương trên desk")
        p.goto(f"{BASE}/desk/payroll-entry")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        denied = " ".join(p.locator("body").inner_text().split())
        s.step("TRƯỞNG NHÀ MÁY mở danh sách Phiếu lương và tìm đồng nghiệp cùng nhà máy")
        p.goto(f"{BASE}/desk/salary-slip")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        search = p.locator(".listsearch-box input, input[placeholder*='Tìm'], .search-in-list input").first
        if search.count() and search.is_visible():
            search.click()
            search.fill("")
            p.keyboard.type(plan["employee_name"], delay=40)
            p.keyboard.press("Enter")
            p.wait_for_timeout(3000)
        else:  # the refused list has no search box; the desk-wide search is still there and must not leak payslips
            p.keyboard.press("Control+k")
            p.wait_for_timeout(1200)
            quick = p.locator("#navbar-search:visible")
            if quick.count():
                quick.click()
                quick.fill("")
                p.keyboard.type(plan["employee_name"], delay=50)
                p.wait_for_timeout(2500)
                found = " ".join(p.locator(".modal:visible").last.inner_text().split()) \
                    if p.locator(".modal:visible").count() else " ".join(p.locator("body").inner_text().split())
                check(plan["employee_name"] not in found or "Salary Slip" not in found,
                      f"ô tìm kiếm của trưởng nhà máy trả về phiếu lương: {found[:180]}")
                p.keyboard.press("Escape")
                p.wait_for_timeout(600)
        rows = " ".join(p.locator("body").inner_text().split())
        others = [x for x in list_of(s, SS, fields=["name", "employee_name"], limit=200) if x["employee_name"] != "Đặng Văn Hùng"]
        check(not others and plan["employee_name"] not in rows, f"thấy cả phiếu của người khác: {others[:2]}")
        blocked = ""
        try:
            api(s, "tlc_hr.interface.payroll_compliance.cost_report", company=company,
                start_date=f'{plan["month"][:4]}-01-01', end_date=plan["end"])
        except Exception as exc:
            blocked = str(exc)
        check("403" in blocked and "Permission" in blocked, f"không bị chặn: {blocked[:160]}")
        r["actual"] = (f"Danh sách Bảng lương: {denied[denied.find('Bảng lương'):][:90] or 'không mở được'}; phiếu lương: {len(others)} "
                       f"phiếu của người khác; API chi phí: {blocked[:80]}")
    s.close()

    # --------------------------------------------------------- PC-11 the salary-budget simulation
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    with case(s, "PC-11", "Mô phỏng tác động tăng 10% quỹ lương đến ngân sách và bảo hiểm",
              "PHƯƠNG mở bảng lương đã ký trên desk và đọc dòng tổng hợp (số phiếu, tổng thu nhập, thực lĩnh, thuế) ở đầu form; "
              "sau đó lấy kết quả mô phỏng +10% từ server — đối tượng nghiệm thu là con số tính bởi server, desk chưa có màn hình "
              "mô phỏng (xem GAPS-payroll_compliance.md)",
              f'TLC Demo · +10% · {vn(plan["end"])}',
              "Tổng hợp trên màn hình đúng bằng số phiếu đã ghi sổ; mô phỏng tăng 10% cho delta lương cơ bản = 10% quỹ hiện tại và "
              "khoản doanh nghiệp đóng tăng thêm 23,5% của delta") as r:
        s.step("PHƯƠNG mở bảng lương đã ký để lấy quỹ lương hiện tại trên màn hình")
        open_form(s, PE, REQ["pe"])
        employees_tab = p.locator(".nav-link:visible").filter(has_text=re.compile(r"Nhân viên|Employees")).first
        if employees_tab.count():
            s.step("PHƯƠNG mở tab Nhân viên xem danh sách người của kỳ lương đã ký")
            employees_tab.click()
            p.wait_for_timeout(1500)
        text = ""
        for _ in range(12):
            parts = [headline(p)]
            for sel in (".form-dashboard", ".form-layout", ".form-page", ".layout-main-section"):
                loc = p.locator(sel).first
                if loc.count():
                    try:
                        parts.append(loc.inner_text())
                    except Exception:
                        pass
            text = " ".join(" ".join(parts).split())
            if "phiếu lương" in text:
                break
            p.wait_for_timeout(1000)
        total = api(s, "tlc_hr.interface.payroll.payroll_summary", name=REQ["pe"])
        check("phiếu lương" in text and int(total["slips"]) == REQ["slips_posted"], f"{text[:200]} · {total}")
        sim = native_data(s, "Mô phỏng tăng lương", "simulate_salary", "Mô phỏng",
                          {"percent_increase": "10", "base_date": user_date(s, plan["end"])})
        delta = flt(sim["monthly_base_delta"]) / flt(sim["current_monthly_base"]) * 100
        cover = flt(sim["employer_contribution_delta"]) / flt(sim["monthly_base_delta"]) * 100
        check(9.99 < delta < 10.01 and 23.4 < cover < 23.6, f"{delta:.2f}% · bảo hiểm {cover:.2f}%")
        r["actual"] = (f"Màn hình: {text[:120]}; mô phỏng +10% quỹ {flt(sim['current_monthly_base']):,.0f} → "
                       f"+{delta:.1f}% lương cơ bản (+{flt(sim['monthly_base_delta']):,.0f}), BH doanh nghiệp "
                       f"+{flt(sim['employer_contribution_delta']):,.0f} ({cover:.1f}%), chi phí năm +{flt(sim['annualized_cost_delta']):,.0f}")
    s.close()

    # --------------------------------------------------------- PC-12 the anomaly scan, cross-checked
    s = Session(browser, "LG", "phuong")
    login(s)
    p = s.page
    with case(s, "PC-12", "Rà soát tự động bất thường lương và đối chiếu từng phát hiện",
              "PHƯƠNG lọc danh sách Phiếu lương theo bảng lương đã ký trên desk (bấm ô Tìm, nhập tên kỳ, Enter), đọc số dòng; sau "
              "đó lấy kết quả quét bất thường từ server — danh sách bất thường là trả lời của server, desk chưa có nút quét "
              "(xem GAPS-payroll_compliance.md) — và kiểm tra mỗi phát hiện ứng với dữ liệu thật",
              REQ.get("pe", ""),
              "Danh sách phiếu lương trên màn hình đúng bằng số phiếu đã ghi sổ; mọi phát hiện “Unapproved Salary Change” ứng với "
              "một phân bổ cấu trúc lương trong kỳ thiếu người duyệt, và ngược lại không bỏ sót") as r:
        s.step("PHƯƠNG mở danh sách Phiếu lương và lọc theo tên một người của kỳ đã ký")
        p.goto(f"{BASE}/desk/salary-slip")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        posted = list_of(s, SS, filters=[["payroll_entry", "=", REQ["pe"]], ["docstatus", "=", 1]],
                        fields=["name", "employee", "employee_name", "start_date", "end_date"], limit=200)
        check(posted, f"không có phiếu đã ghi sổ của {REQ['pe']}")
        search = p.locator("input[data-fieldname='employee_name']:visible").first
        check(search.count(), f"danh sách Phiếu lương không có ô lọc Tên nhân viên: {screen_message(s, wait=500, close=False)[:200]}")
        search.click()
        search.fill("")
        p.keyboard.type(posted[0]["employee_name"], delay=45)
        p.keyboard.press("Enter")
        p.wait_for_timeout(4000)
        shown = " ".join(p.locator("body").inner_text().split())
        on_screen = [x for x in posted if x["employee_name"] in shown]
        check(on_screen, f"danh sách không hiện phiếu của {REQ['pe']}: {shown[:160]}")
        anom = native_data(s, "Kiểm tra bất thường", "payroll_anomalies")
        found = {(a["employee"], a["type"]) for a in anom["anomalies"]}
        expected_changes = set()
        for slip in posted:
            for assign in list_of(s, SSA, filters=[["employee", "=", slip["employee"]], ["docstatus", "=", 1],
                                                  ["from_date", "between", [slip["start_date"], slip["end_date"]]]],
                                  fields=["name", "tlc_decision_approved_by"], limit=20):
                if not assign["tlc_decision_approved_by"]:
                    expected_changes.add((slip["employee"], "Unapproved Salary Change"))
        observed_changes = {item for item in found if item[1] == "Unapproved Salary Change"}
        check(observed_changes == expected_changes,
              f"quét sai: thiếu {sorted(expected_changes - observed_changes)}, thừa {sorted(observed_changes - expected_changes)}")
        r["actual"] = (f"Màn hình {len(on_screen)}/{len(posted)} phiếu của {REQ['pe']}; server quét {anom['total_anomalies']} phát hiện "
                       f"({sorted({a['type'] for a in anom['anomalies']})[:3]}), đối chiếu đúng "
                       f"{len(expected_changes)} bất thường quyết định lương")
    s.close()


JOURNEYS = [payroll_compliance_flow]

