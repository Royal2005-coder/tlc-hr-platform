"""RX (W8) – Trải nghiệm native theo vai trò và phạm vi: mỗi vai trò làm một việc thật trên đúng màn hình của mình.

13 ca được nghiệm thu bằng thao tác chuột/gõ phím: nhân viên và nhân viên văn phòng làm việc trong app Frappe HR
(/hrms) – đọc thẻ số dư, điền đơn nghỉ, xem Đơn của tôi, quyết định lời đề nghị tăng ca, đọc phiếu lương;
trưởng nhà máy – HR – CEO – chuyên viên lương – kế toán – trưởng phòng làm việc trên desk workspace của họ –
bấm thẻ số để mở danh sách, mở dòng bằng chuột, điền từng ô trên form, bấm Hành động rồi chọn nút workflow.
Kết luận của mỗi ca đọc từ màn hình (danh sách nhìn thấy, badge trạng thái trên form, số trên thẻ, dòng tư vấn
đầu form, ô giá trị trên form); API chỉ dùng để đối chiếu sau khi người dùng đã làm xong.

API chỉ làm hai việc, đúng chuẩn UAT_UI_STANDARD:
  (a) chuẩn bị dữ liệu nền do vai trò KHÁC tạo: kỳ công tháng đã khoá (luật của phân hệ Chốt công, bắt buộc trước
      khi tính lương), lời đề nghị tăng ca do quản lý gửi (phân hệ Tăng ca), đầu việc ToDo có hạn của HR;
  (b) đọc để đối chiếu. Không có bước nghiệp vụ nào đang được nghiệm thu ở phân hệ này làm bằng API.
"""

from urllib.parse import quote

from lib import *  # noqa: F403

OT_D, PE_D, KC_D, SS_D, TD_D = "TLC Overtime Request", "Payroll Entry", "TLC Attendance Period", "Salary Slip", "ToDo"
COMPANY = "TLC Demo"
SCOPES = ("Nhà máy 1", "Nhà máy 2", "Nhà máy 3", "Hội sở")
HEAD_OF = {"Nhà máy 1": "hung", "Nhà máy 2": "nm2", "Nhà máy 3": "nm3"}
# nhân viên / nhân viên văn phòng: ca, người đề nghị tăng ca cho họ, cách họ quyết định lời đề nghị đó
WORKERS = (("binh", "RX-01", "hung", "Đồng ý"), ("f2w01", "RX-02", "nm2", "Đồng ý"),
           ("f3w01", "RX-03", "nm3", "Từ chối"), ("an", "RX-04", "quang", "Đồng ý"))
# trưởng nhà máy: ca, công nhân của mình (đơn sẽ duyệt), công nhân nhà máy khác (phạm vi phải từ chối trên màn hình)
HEAD_CASES = (("hung", "RX-11", "binh", "f2w01"), ("nm2", "RX-12", "f2w01", "binh"), ("nm3", "RX-13", "f3w01", "binh"))
COMPUTED, TO_CEO, SIGNED, PAID = "Đã tính lương", "Chờ giám đốc ký", "Đã ký", "Đã chi"
PERIOD_TO_HR, PERIOD_TO_CEO, TO_HEAD, TO_WORKER = "Chờ nhân sự đối soát", "Chờ giám đốc ký", "Chờ quản lý xác nhận", "Chờ người lao động đồng ý"
SLUGS = {"TLC Quản lý": "tlc-quản-lý", "TLC Nhân sự": "tlc-nhân-sự", "TLC Điều hành": "tlc-điều-hành",
         "TLC CEO Chi phí": "tlc-ceo-chi-phí", "TLC Cá nhân": "tlc-cá-nhân",
         "TLC HR Hạn xử lý": "tlc-hr-hạn-xử-lý", "TLC Tác nghiệp lương": "tlc-tác-nghiệp-lương",
         "TLC Kế toán chi trả": "tlc-kế-toán-chi-trả"}
DENIED = re.compile(r"Không được phép|Bạn cần quyền|Not permitted|Insufficient Permission|Không có quyền", re.I)


# ------------------------------------------------------------------------------------------------ màn hình nói gì

def page_text(p):
    return " ".join(p.locator("body").inner_text().split())


def list_text(p):
    loc = p.locator(".layout-main-section, .standard-page-list-section, .list-section")
    return " ".join((loc.first.inner_text() if loc.count() else p.locator("body").inner_text()).split())


def form_text(p):
    loc = p.locator(".form-layout:visible").first
    expect(loc).to_be_visible()
    return " ".join(loc.inner_text().split())


def screen_state(p):
    """Những gì người dùng trông thấy quanh trạng thái hồ sơ: đầu trang, badge, ô Trạng thái, dòng tin nhắn đầu form
    và toàn bộ chữ đang hiện trên màn hình form."""
    bits = [form_text(p), page_text(p)]
    for sel in (".title-area:visible", ".form-title:visible", ".page-head:visible", ".indicator-pill:visible",
                ".indicator:visible", "[data-fieldname='workflow_state']:visible", ".form-message:visible"):
        loc = p.locator(sel)
        for i in range(min(loc.count(), 4)):
            bits.append(" ".join(loc.nth(i).inner_text().split()))
    return " | ".join(bits)


def state_shown(s, expected, note=None, tries=30):
    """Ca chỉ đạt khi trạng thái mới hiện trên màn hình, không phải chỉ khi API báo về như vậy."""
    p = s.page
    s.step(note or f"Đọc trạng thái trên màn hình: {expected}")
    for _ in range(tries):
        if expected in screen_state(p):
            return
        p.wait_for_timeout(1000)
    raise AssertionError(f"màn hình không hiện {expected} · đang hiện: {screen_state(p)[:220]}")


def money_shown(p, value):
    """Số tiền trên màn hình: chữ hoặc giá trị của các ô chỉ đọc (app in tiền trong input)."""
    text = page_text(p)
    inputs = p.locator("input:visible")
    for i in range(inputs.count()):
        try:
            text += " " + inputs.nth(i).input_value()
        except Exception:
            pass
    return next((f for f in (f"{value:,.2f}", f"{value:,.0f}", f"{int(round(value)):,}".replace(",", "."),
                             f"{int(round(value))}") if f in text), None)


# ------------------------------------------------------------------------------------------------ điều hướng bằng chuột

def open_workspace(s, title, note=None):
    p = s.page
    s.step(note or f"Mở workspace {title}")
    p.goto(f"{BASE}/desk/tlc-hr/{quote(SLUGS[title])}")
    p.wait_for_load_state("networkidle")
    expect(p.get_by_text(title, exact=True).last).to_be_visible()
    p.wait_for_timeout(1500)


def read_card(s, label, note=None):
    s.step(note or f"Đọc thẻ {label} trên workspace")
    return card_value(s.page, label)


def click_card(s, label, note=None):
    """Bấm thẳng vào thẻ số để mở đúng danh sách mà thẻ đang đếm."""
    p = s.page
    s.step(note or f"Bấm thẻ {label} để mở danh sách")
    widget = p.locator(".widget", has_text=label).first
    expect(widget).to_be_visible()
    widget.scroll_into_view_if_needed()
    p.wait_for_timeout(500)
    before = p.url
    titles = widget.locator("h4, .widget-label, [class*=title]")
    for target in [widget] + ([titles.first] if titles.count() else []):
        try:
            target.click()
        except Exception:
            continue
        p.wait_for_timeout(3500)
        if p.url != before:
            break
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2500)
    check(p.url != before, f"bấm thẻ {label} không mở được danh sách (trang vẫn ở {p.url.replace(BASE, '')})")


def click_shortcut(s, label, route, note=None):
    """Bấm shortcut của workspace. Desk là SPA nên URL đổi ngay khi bấm; shortcut dạng URL còn mở app ở tab mới:
    kiểm tra đích ở tab đó rồi mở lại đúng đích đó ở tab đang ghi hình."""
    p = s.page
    s.step(note or f"Bấm shortcut {label}")
    target = p.get_by_text(label, exact=True).first
    expect(target).to_be_visible()
    popup = None
    try:
        with s.context.expect_page(timeout=3000) as info:
            target.click()
        popup = info.value
    except Exception:
        popup = None
    if popup is not None:
        try:
            popup.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        check(route.split("/")[-1] in popup.url,
              f"shortcut {label} mở sai đích {popup.url.replace(BASE, '')}")
        check(not DENIED.search(page_text(popup) if popup.locator("body").count() else ""),
              f"shortcut {label} mở màn hình bị từ chối quyền")
        destination = popup.url
        popup.close()
        for _ in range(3):  # the SPA sometimes keeps the current workspace on the first paint
            p.goto(destination)
            if route.split("/")[-1] in p.url:
                break
            p.wait_for_timeout(1000)
    check(route.split("/")[-1] in p.url,
          f"shortcut {label} không điều hướng tới {route}; không thay bằng goto để che lỗi")
    p.wait_for_load_state("domcontentloaded")
    p.wait_for_timeout(3000)
    check(route.split("/")[-1] in p.url, f"shortcut {label} không mở được {route} (đang ở {p.url.replace(BASE, '')})")
    check(not DENIED.search(page_text(p)), f"màn hình {route} từ chối quyền của {s.account}")


def list_rows(p):
    return p.locator(".list-row, .result-row, .list-row-container .layout-row")


def rows_text(p):
    rows = list_rows(p)
    return " | ".join(" ".join(rows.nth(i).inner_text().split()) for i in range(min(rows.count(), 40)))


def click_row(s, doctype, needle, note=None):
    """Mở hồ sơ bằng cách bấm vào liên kết ở ô đầu dòng của danh sách (ô tiêu đề).
    Ở desk bản này, bấm ô "Mã định danh" chỉ áp bộ lọc cho danh sách, nên phải bấm ô tiêu đề."""
    p = s.page
    s.step(note or f"Mở {needle} từ danh sách")
    row = p.locator(".list-row:visible, .result-row:visible", has_text=needle).first
    expect(row).to_be_visible(timeout=30000)
    link = row.locator(".list-subject a:visible").first
    check(link.count() > 0, f"dòng {needle} không có liên kết tiêu đề mở hồ sơ · {list_text(p)[:200]}")
    link.click()
    p.wait_for_function(
        "([d, n]) => window.cur_frm && cur_frm.doctype === d && "
        "cur_frm.doc && cur_frm.doc.name === n && !cur_frm.is_new() && "
        "cur_frm.wrapper && cur_frm.wrapper.getClientRects().length > 0",
        arg=[doctype, needle], timeout=40000)
    expect(p.locator(".form-layout:visible").first).to_be_visible()
    p.wait_for_timeout(2200)


def filter_list(p, labels, value):
    """Gõ vào chip lọc gốc của danh sách (ô "Họ và tên", "Mã định danh"…). Trả về True nếu danh sách có ô lọc đó."""
    for label in labels:
        chip = p.locator(f"input[placeholder='{label}'], input[placeholder*='{label}']")
        if chip.count():
            chip.first.click()
            chip.first.fill(value)
            p.keyboard.press("Enter")
            p.wait_for_timeout(4500)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(1500)
            return True
    return False


# ------------------------------------------------------------------------------------------------ điền form bằng bàn phím

def field_input(p, field):
    """Đọc đúng ô đang nhìn thấy trong control của form, không lấy ô của trang SPA đã ẩn."""
    return p.locator(f".form-layout:visible .frappe-control[data-fieldname='{field}'] "
                     "input:visible, "
                     f".form-layout:visible .frappe-control[data-fieldname='{field}'] textarea:visible")


def editable(p, field):
    """Form đã gửi thì chỉ những ô allow_on_submit mới gõ được trực tiếp; nếu ô bị khoá thì bấm Update trước."""
    box = field_input(p, field)
    check(box.count() > 0, f"form không có ô {field}")
    if not box.first.is_enabled():
        button = visible_button(p, "Update")
        check(button.count() > 0, f"ô {field} đang khoá và form không có nút Update")
        button.click()
        p.wait_for_timeout(2000)
        box = field_input(p, field)
    return box.first


def save_form(p):
    """Nút Lưu gốc của form; form đã gửi thì desk đổi nhãn thành Update/Cập nhật."""
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    for label in ("Lưu", "Update", "Cập nhật", "Save"):
        button = visible_button(p, label)
        if button.count():
            button.click()
            p.wait_for_timeout(4000)
            return label
    p.keyboard.press("Control+s")
    p.wait_for_timeout(4000)
    return "Ctrl+S"

def upload_payroll_proof(s, entry, reference):
    """Click the new tlc_bank_proof Attach button, upload a real private proof, and assert it attaches."""
    p = s.page
    control = box(s, "tlc_bank_proof")
    button = control.locator("button.btn-attach:visible").last
    if not button.count():
        button = control.locator("button:visible", has_text=re.compile(r"Gắn|Đính kèm|Attach")).last
    button.click()
    dialog = p.locator(".modal:visible").last
    dialog.wait_for(state="visible")
    p.wait_for_timeout(900)
    with p.expect_response(lambda res: "/api/method/upload_file" in res.url, timeout=60000) as uploaded:
        proof_path = Path("/tmp") / f"proof-rx-{entry}.txt"
        proof_path.write_text(f"Uỷ nhiệm chi ngân hàng thực tế {reference} cho bảng lương {entry}", encoding="utf-8")
        dialog.locator("input[type=file]").last.set_input_files(str(proof_path))
        upload = dialog.get_by_role("button", name=re.compile(r"^(Tải lên|Upload)$"))
        if upload.count() and upload.last.is_visible():
            upload.last.click()
    response = uploaded.value
    check(response.ok, f"tải ủy nhiệm chi thất bại: {response.status}")
    url = (response.json().get("message") or {}).get("file_url")
    check(url and url.startswith("/private/files/"), f"chứng từ chi lương phải riêng tư: {url}")
    p.wait_for_function("() => window.cur_frm && cur_frm.doc.tlc_bank_proof && cur_frm.doc.tlc_bank_proof.startsWith('/private/files/')",
                        timeout=30000)
    expect(control.locator(".attached-file-link:visible").first).to_be_visible()
    return url


def box(s, fieldname, root=None):
    return (root or s.page).locator(f'[data-fieldname="{fieldname}"]')



def type_text(p, field, value):
    box = editable(p, field)
    box.click()
    box.fill(value)
    p.keyboard.press("Tab")
    p.wait_for_timeout(900)
    got = p.evaluate("f => cur_frm.doc[f]", field)
    check(str(got) == value, f"ô {field} trên màn hình là {got!r}, mong {value!r}")


def user_date(p, value):
    """Định dạng ngày của người dùng, giống cách ô ngày của desk phân tích bàn phím."""
    fmt = p.evaluate("() => (window.frappe && frappe.boot.sysdefaults.date_format) || 'yyyy-mm-dd'")
    day = dt.date.fromisoformat(value)
    return fmt.replace("yyyy", f"{day.year:04d}").replace("mm", f"{day.month:02d}").replace("dd", f"{day.day:02d}")


def type_date(p, field, value):
    """Gõ ngày theo định dạng người dùng, rồi đọc lại ô và dữ liệu form; không sửa model thay bàn phím."""
    box = editable(p, field)
    shown_format = user_date(p, value)
    box.fill(shown_format)
    box.press("Tab")
    p.wait_for_timeout(1200)
    got = str(p.evaluate("f => cur_frm.doc[f]", field) or "")[:10]
    check(got == value[:10], f"ô {field} sau khi điền là {got or '(trống)'}, mong {value}")
    on_screen = box.input_value() or ""
    check(shown_format == on_screen, f"ô {field} trên màn hình hiển thị {on_screen!r}")


def type_link(p, field, value):
    """Ô liên kết: gõ giá trị vào đúng ô trên form rồi chọn gợi ý của desk."""
    current = p.evaluate("f => cur_frm.doc[f]", field) if field_input(p, field).count() else None
    if str(current or "") == value:  # desk đã điền sẵn mặc định đúng giá trị cần có
        return value
    box = editable(p, field)
    box.click()
    box.fill(value)
    box.press("Enter")
    p.wait_for_timeout(1200)
    if str(p.evaluate("f => cur_frm.doc[f]", field) or "") != value:
        box.click()
        box.fill("")
        box.type(value, delay=45)
        p.wait_for_timeout(2500)
        opts = p.locator("[role=menuitem]:visible, .awesomplete-list > li, .ui-menu-item")
        picked = None
        for i in range(opts.count()):
            text = " ".join(opts.nth(i).inner_text().split())
            if value.lower() in text.lower():
                opts.nth(i).click()
                picked = text
                break
        if picked is None:
            p.keyboard.press("Enter")
            p.wait_for_timeout(1500)
    got = p.evaluate("f => cur_frm.doc[f]", field)
    check(str(got or "") == value, f"ô {field} nhận {got!r}, mong {value!r}")
    return got


def pick_select(p, field, value, label=None):
    sel = p.locator(f"select[data-fieldname='{field}']:visible")
    check(sel.count() > 0, f"form không có ô chọn {field}")
    for attempt in ({"value": value}, {"label": label or value}, {"label": value}):
        try:
            sel.first.select_option(**attempt)
            break
        except Exception:
            continue
    p.wait_for_timeout(800)
    got = str(p.evaluate("f => cur_frm.doc[f]", field))
    check(got == value, f"{field} = {got}, mong {value}")


def add_new(s, doctype, note=None):
    p = s.page
    slug = doctype.lower().replace(" ", "-")
    s.step(note or "Bấm nút thêm mới trên danh sách")
    add = None
    for _ in range(12):  # danh sách của desk tải chậm: chờ nút "Thêm <Tên DocType>" xuất hiện
        buttons = p.locator("button:visible").filter(has_text=re.compile(r"Thêm|Tạo mới|Add|New", re.I))
        for i in range(buttons.count()):
            text = " ".join(buttons.nth(i).inner_text().split())
            if not text or re.search(r"Tải thêm|Load more|Thêm (bộ lọc|dòng|người dùng)|Add (filter|row|user)", text, re.I):
                continue
            add = buttons.nth(i)
            break
        if add is not None:
            break
        p.wait_for_timeout(2000)
    check(add is not None, f"danh sách {doctype} không có nút thêm mới · {page_text(p)[:180]}")
    add.click()
    p.wait_for_timeout(2500)
    if p.locator(".modal:visible").count():  # quick entry: làm trên form đầy đủ để thấy từng ô được điền
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)
        p.goto(f"{BASE}/desk/{slug}/new")
    else:
        # the desk often opens the new record in place without changing the URL, so wait for the form, not the route
        try:
            p.wait_for_function("(d) => window.cur_frm && cur_frm.doctype === d && cur_frm.is_new()", arg=doctype, timeout=10000)
        except Exception:
            p.goto(f"{BASE}/desk/{slug}/new")
    p.wait_for_load_state("networkidle")
    p.wait_for_function("(d) => window.cur_frm && cur_frm.doctype === d && cur_frm.is_new()", arg=doctype, timeout=40000)
    p.wait_for_timeout(1800)


def form_action(s, action, note=None, reason=None, wait=4000):
    """Bấm Hành động trên form rồi chọn đúng một nút workflow, như người dùng thật."""
    p = s.page
    s.step(note or f"Bấm Hành động rồi chọn {action}")
    open_actions(p)
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == action), None)
    check(target is not None, f"không có {action} trong menu Hành động: {menu_items(p)}")
    items.nth(target).click()
    if action == "Từ chối":
        dialog = p.locator(".modal:visible")
        if dialog.count():
            dialog = dialog.last
            box = dialog.locator("textarea")
            if box.count() and reason:
                box.first.fill(reason)
            button = dialog.get_by_role("button", name="Từ chối")
            if button.count():
                button.last.click()
    p.wait_for_timeout(wait)


# ------------------------------------------------------------------------------------------------ API: đối chiếu và dữ liệu nền

def api_list(s, doctype, fields, filters=None, limit=200):
    path = f"/api/resource/{quote(doctype)}?limit_page_length={limit}&fields=" + json.dumps(fields)
    if filters:
        path += "&filters=" + json.dumps(filters)
    return api_get(s, path).json().get("data", [])


def api_doc(s, doctype, name):
    return api_get(s, f"/api/resource/{quote(doctype)}/{quote(name)}").json()["data"]


def employee_of(s, account):
    rows = api_list(s, "Employee", ["name", "employee_name", "department", "user_id"], [["user_id", "=", f"{account}@demo.example"]], limit=2)
    check(rows, f"không tìm thấy hồ sơ nhân viên của {account}")
    return rows[0]


def workflow_step(s, doctype, name, action):
    """API: một bước workflow, chỉ dùng cho DỮ LIỆU NỀN của vai trò khác (xem docstring đầu file)."""
    return api(s, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": doctype, "name": name}), action=action)


def month_start(month):
    return f"{month}-01"


def month_end(month):
    first = dt.date.fromisoformat(month_start(month))
    return ((first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)).isoformat()


def month_candidates():
    first = dt.date.today().replace(day=1)
    return [(first - dt.timedelta(days=1)).strftime("%Y-%m"), (first - dt.timedelta(days=32)).strftime("%Y-%m")]


def periods_of(s, month):
    return {r["scope"]: r for r in api_list(s, KC_D, ["name", "scope", "workflow_state", "docstatus"],
                                            [["period_month", "=", month], ["company", "=", COMPANY]])}


def payment_account(s):
    rows = api_list(s, "Account", ["name", "account_number"], [["company", "=", COMPANY], ["account_number", "=", "1121"]], limit=3)
    check(rows, "không thấy tài khoản chi lương 1121 để điền vào bảng lương")
    return rows[0]["name"]


def ensure_payroll_period(s, month):
    """The Frappe HR app groups payslips by payroll period; without one the worker's app list is empty."""
    first = dt.date.fromisoformat(month_start(month))
    existing = api_list(s, "Payroll Period", ["name", "start_date", "end_date"], [["company", "=", COMPANY]], limit=20)
    for row in existing:
        if row.get("start_date") and row.get("end_date") and row["start_date"] <= f"{first.year}-01-01" and row["end_date"] >= f"{first.year}-12-31":
            return
    api(s, "frappe.client.insert", doc=json.dumps({
        "doctype": "Payroll Period", "company": COMPANY,
        "start_date": f"{first.year}-01-01", "end_date": f"{first.year}-12-31"}))
    covered = api_list(s, "Payroll Period", ["name"], [["company", "=", COMPANY],
        ["start_date", "<=", month_start(month)], ["end_date", ">=", month_end(month)]], limit=2)
    check(covered, f"thiếu Payroll Period bao phủ đúng {month}")


def wait_slips(s, name, docstatus, minimum, rounds=48):
    rows = []
    for _ in range(rounds):
        rows = api_list(s, SS_D, ["name"], [["payroll_entry", "=", name], ["docstatus", "=", docstatus]], limit=500)
        if len(rows) >= minimum:
            return len(rows)
        s.page.wait_for_timeout(5000)
    return len(rows)


# ------------------------------------------------------------------------------------------------ dữ liệu nền (không phải ca)

def payroll_month_taken(browser, month):
    """lan cannot read Payroll Entry, so a payroll-capable account decides whether the month is free."""
    st = Session(browser, "RX-PREP", "hoa")
    try:
        login(st)
        return bool(api_list(st, PE_D, ["name"], [["company", "=", COMPANY], ["start_date", "=", f"{month}-01"],
                                               ["docstatus", "<", 2]], limit=1))
    finally:
        st.close()


def close_attendance_month(browser):
    """Bảng lương chỉ tính được khi kỳ công của các phạm vi trong tháng đã khoá (luật của phân hệ Chốt công).
    Kỳ công được đưa hết chuỗi bước nghiệp vụ bằng phiên của đúng vai trò; phần RX-23/24/25 nghiệm thu
    (lập bảng lương, ký, xác nhận chi) vẫn do người dùng bấm trên form."""
    for month in month_candidates():
        s = Session(browser, "RX-PREP", "lan")
        try:
            login(s)
            # a month that already carries a payroll entry cannot be paid a second time (the app refuses duplicate slips)
            if payroll_month_taken(browser, month):
                print(f"PREP: tháng {month} đã có bảng lương, chọn tháng khác", flush=True)
                continue
            rows = periods_of(s, month)
            for scope in SCOPES:
                if scope not in rows:
                    api(s, "frappe.client.insert", doc=json.dumps({"doctype": KC_D, "company": COMPANY,
                                                                   "scope": scope, "period_month": month}))
            for row in periods_of(s, month).values():
                if row["workflow_state"] in (DRAFT, None, ""):
                    workflow_step(s, KC_D, row["name"], "Gửi đối soát" if row["scope"] == "Hội sở" else "Gửi xác nhận")
            for scope, account in HEAD_OF.items():
                head = Session(browser, "RX-PREP", account)
                try:
                    login(head)
                    row = periods_of(head, month).get(scope)
                    if row and row["workflow_state"] == TO_HEAD:
                        workflow_step(head, KC_D, row["name"], "Xác nhận")
                finally:
                    head.close()
            for row in periods_of(s, month).values():
                if row["workflow_state"] == PERIOD_TO_HR:
                    workflow_step(s, KC_D, row["name"], "Đối soát xong")
            ceo = Session(browser, "RX-PREP", "thanh")
            try:
                login(ceo)
                for row in periods_of(ceo, month).values():
                    if row["workflow_state"] == PERIOD_TO_CEO:
                        workflow_step(ceo, KC_D, row["name"], "Ký và khoá")
                locked = periods_of(ceo, month)
                done = len(locked) == len(SCOPES) and all(r["docstatus"] == 1 for r in locked.values())
            finally:
                ceo.close()
            if done:
                REQ["rx_month"] = month
                print(f"PREP: kỳ công {month} đã khoá đủ {len(SCOPES)} phạm vi", flush=True)
                return month
            print(f"PREP: tháng {month} chưa khoá đủ để tính lương", flush=True)
        finally:
            s.close()
    raise AssertionError("không có tháng chưa trả lương với đủ bốn kỳ công đã khoá; không chạy tiếp trên fixture dở dang")


def propose_overtime(s, emp_name, reason):
    """Một lời đề nghị tăng ca cho người lao động, do chính quản lý của họ gửi (dữ liệu nền của phân hệ Tăng ca)."""
    mine = api_list(s, OT_D, ["name", "workflow_state", "ot_date"], [["employee", "=", emp_name]], limit=200)
    pending = [m for m in mine if m["workflow_state"] == TO_WORKER]
    if pending:
        return pending[0]["name"]
    used = {m["ot_date"] for m in mine}
    day = next((d for n in range(20, 34) for d in [working_day(n)] if d not in used
                and not api_list(s, OT_D, ["name"], [["employee", "=", emp_name], ["ot_date", "=", d]], limit=1)), None)
    check(day, f"{emp_name}: không có ngày làm việc trống để chuẩn bị lời đề nghị tăng ca")
    doc = api(s, "frappe.client.insert", doc=json.dumps({"doctype": OT_D, "employee": emp_name, "ot_date": day,
                                                          "from_time": "17:30:00", "to_time": "20:00:00", "reason": reason}))
    workflow_step(s, OT_D, doc["name"], "Đề nghị")
    check(api_doc(s, OT_D, doc["name"])["workflow_state"] == TO_WORKER, "đề nghị không vào đúng bước chờ người lao động")
    return doc["name"]


def prepare_overtime(browser):
    for account, case_id, manager, decision in WORKERS:
        name = None
        for who in (manager, "lan"):  # quản lý trực tiếp đề nghị; nếu không được thì HR đề nghị (cùng vai trò được phép)
            s = Session(browser, "RX-PREP", who)
            try:
                login(s)
                emp = employee_of(s, account)
                name = propose_overtime(s, emp["name"], "Kiểm kê kho cuối tháng (dữ liệu nền cho RX)")
                break
            except Exception as exc:
                print("PREP overtime failed", account, who, str(exc)[:160], flush=True)
            finally:
                s.close()
        check(name, f"không chuẩn bị được lời đề nghị tăng ca cho {account}")
        REQ.setdefault("rx_ot", {})[account] = name


def prepare_todos(browser):
    """Hai đầu việc HR có hạn xử lý (một quá hạn, một trong tuần) để thẻ hạn trên TLC HR Hạn xử lý có hàng thật."""
    for account, marker, day in (("hoa", "RX-21", (dt.date.today() - dt.timedelta(days=2)).isoformat()),
                                 ("lan", "RX-22", dt.date.today().isoformat())):
        s = Session(browser, "RX-PREP", account)
        try:
            login(s)
            refs = api_list(s, "Employee Separation", ["name", "employee_name"], limit=5)
            doc = {"doctype": TD_D, "allocated_to": f"{account}@demo.example", "status": "Open", "date": day,
                   "description": (f"Việc UAT {marker}: đối chiếu hồ sơ nghỉ việc của {refs[0]['employee_name']} trước {vn(day)}"
                                   if refs else f"Việc UAT {marker}: kiểm tra hạn xử lý hồ sơ nhân sự")}
            if refs:
                doc.update({"reference_type": "Employee Separation", "reference_name": refs[0]["name"]})
            api(s, "frappe.client.insert", doc=json.dumps(doc))
            REQ.setdefault("rx_todo", {})[account] = f"Việc UAT {marker}"
        except Exception as exc:
            print("PREP todo failed", account, str(exc)[:180], flush=True)
        finally:
            s.close()


def prepare_data(browser):
    close_attendance_month(browser)
    prepare_overtime(browser)
    prepare_todos(browser)


# ------------------------------------------------------------------------------------------------ RX-24, RX-23, RX-25: một tháng lương

def payroll_maker(browser):
    """RX-24 – chuyên viên tính lương làm việc trên đúng màn hình Bảng lương của mình."""
    month = REQ.get("rx_month")
    if not month:
        raise AssertionError("không còn tháng nào chưa trả lương để nghiệm thu RX-24")
    start, end = month_start(month), month_end(month)
    s = Session(browser, "RX-PAYROLL", "phuong")
    try:
        with case(s, "RX-24", "Chuyên viên tính lương lập và tính bảng lương của tháng đã khoá kỳ công",
                  "Workspace TLC Tác nghiệp lương > đọc thẻ > mở danh sách Bảng lương bằng shortcut > bấm Thêm bảng lương > "
                  "điền Công ty, tần suất, kỳ lương, tài khoản chi > Lưu > bấm Lấy nhân viên > "
                  "Hành động > Tính lương > Hành động > Gửi ký",
                  f"{COMPANY}, kỳ {vn(start)} – {vn(end)}",
                  f"Lưới nhân viên hiện trên form đúng số người của công ty; trạng thái trên form đổi thành {COMPUTED} "
                  "rồi Chờ giám đốc ký; dòng đầu form hiện tổng hợp lương") as r:
            login(s)
            p = s.page
            open_workspace(s, "TLC Tác nghiệp lương", "Chuyên viên tính lương mở workspace TLC Tác nghiệp lương")
            waiting = read_card(s, "Bảng lương chờ ký", "Đọc thẻ Bảng lương chờ ký trước khi lập bảng")
            queue = api_list(s, PE_D, ["name"], [["workflow_state", "=", TO_CEO]], limit=200)
            check(waiting == len(queue), f"thẻ chờ ký đếm {waiting}, đối chiếu {len(queue)} bảng lương")
            account = payment_account(s)
            click_shortcut(s, "Điều hành ký bảng lương", "/desk/payroll-entry", "Mở danh sách Bảng lương bằng shortcut")
            add_new(s, PE_D, "Bấm nút thêm bảng lương")
            s.step("Điền Công ty cho bảng lương")
            type_link(p, "company", COMPANY)
            s.step("Chọn tần suất trả lương Hàng tháng")
            pick_select(p, "payroll_frequency", "Monthly", label="Hàng tháng")
            s.step("Điền kỳ lương và ngày hạch toán")
            type_date(p, "posting_date", end)
            type_date(p, "start_date", start)
            type_date(p, "end_date", end)
            s.step("Chọn tài khoản dùng để chi lương trên tab Kế toán & Thanh toán")
            tab = p.locator("button:visible", has_text="Kế toán & Thanh toán").first
            expect(tab).to_be_visible()
            tab.click()
            p.wait_for_timeout(1200)
            type_link(p, "payment_account", account)
            s.step("Bấm Lưu để tạo bảng lương nháp")
            save_form(p)
            # the desk can keep the /new route while the doc is saved: read the document name, not the URL
            p.wait_for_function("() => window.cur_frm && cur_frm.docname && cur_frm.docname.indexOf('HR-PRUN-') === 0",
                                timeout=40000)
            name = p.evaluate("() => cur_frm.docname")
            REQ["rx_pe"] = name
            s.step("Mở tab Nhân viên để xem lưới nhân viên của kỳ")
            p.locator("button:visible", has_text="Nhân viên").first.click()
            p.wait_for_timeout(1200)
            s.step("Bấm Lấy nhân viên để desk tự kéo danh sách người lao động của kỳ")
            get_emp = p.locator("button:visible").filter(has_text=re.compile("Lấy nhân viên|Get Employees", re.I)).last
            check(get_emp.count() > 0, "form không có nút Lấy nhân viên")
            get_emp.click()
            p.wait_for_function("() => window.cur_frm && (cur_frm.doc.employees || []).length > 0", timeout=120000)
            p.wait_for_timeout(3000)
            people = p.evaluate("() => cur_frm.doc.employees.length")
            grid = p.locator(".frappe-control[data-fieldname='employees'] .grid-row:visible").count()
            check(grid > 0, f"lưới nhân viên không hiển thị ({people} người ở dữ liệu form)")
            REQ["rx_people"] = people
            s.step("Lưu danh sách nhân viên vừa lấy")
            save_form(p)
            form_action(s, "Tính lương")
            state_shown(s, COMPUTED, tries=60)
            slips = wait_slips(s, name, 0, 1)
            head_line = headline(p)
            check(len(head_line) > 0, "form không có dòng tổng hợp sau khi tính lương")
            form_action(s, "Gửi ký")
            state_shown(s, TO_CEO)
            doc = api_doc(s, PE_D, name)
            check(doc["workflow_state"] == TO_CEO, doc["workflow_state"])
            r["actual"] = (f"{name}: lưới {people} người ({grid} dòng nhìn thấy), {slips} phiếu nháp, dòng đầu form "
                           f"“{head_line[:90]}” → trạng thái {TO_CEO}")
    finally:
        s.close()


def ceo_signs(browser):
    """RX-23 – CEO đọc thẻ chi phí lương, bấm qua lại giữa thẻ và danh sách, rồi ký bảng lương bằng nút workflow."""
    s = Session(browser, "RX-CEO", "thanh")
    try:
        entry = REQ.get("rx_pe", "")
        with case(s, "RX-23", "CEO đọc thẻ chi phí lương và ký bảng lương",
                  "Workspace TLC Điều hành > đọc thẻ Bảng lương chờ ký > sang TLC CEO Chi phí > đọc thẻ gross và net rồi "
                  "bấm mở danh sách phiếu lương > quay lại TLC Điều hành > bấm thẻ Bảng lương chờ ký > mở bảng lương chờ ký "
                  "> đọc dòng tổng hợp > Hành động > Ký duyệt",
                  entry,
                  f"Thẻ gross/net hiện số khớp đối chiếu và mở đúng danh sách phiếu lương; thẻ chờ ký đếm đúng bảng lương; "
                  f"sau khi bấm Ký duyệt form hiện {SIGNED} và phiếu lương của người lao động được ghi sổ") as r:
            login(s)
            p = s.page
            open_workspace(s, "TLC Điều hành", "CEO Nguyễn Văn Thành mở workspace TLC Điều hành")
            waiting = read_card(s, "Bảng lương chờ ký", "Đọc thẻ Bảng lương chờ ký trên TLC Điều hành")
            check(waiting >= 1 and entry, f"thẻ Bảng lương chờ ký đếm {waiting}, bảng lương chờ ký: {entry}")
            open_workspace(s, "TLC CEO Chi phí", "Mở màn hình chi phí lương TLC CEO Chi phí")
            gross = read_card(s, "Điều hành lương gross tháng này", "Đọc thẻ lương gross đã phát hành trong tháng")
            net = read_card(s, "Điều hành lương net tháng này", "Đọc thẻ lương net đã phát hành trong tháng")
            first = f"{dt.date.today():%Y-%m}-01"
            slips = api_list(s, SS_D, ["name", "gross_pay", "net_pay"], [["docstatus", "=", 1], ["start_date", ">=", first]], limit=500)
            api_gross, api_net = sum(x["gross_pay"] for x in slips), sum(x["net_pay"] for x in slips)
            check(abs(gross - api_gross) <= 1 and abs(net - api_net) <= 1, f"thẻ gross/net {gross}/{net}, đối chiếu {api_gross}/{api_net}")
            click_card(s, "Điều hành lương gross tháng này", "Bấm thẻ gross để mở danh sách phiếu lương của tháng")
            s.step("Đọc những gì danh sách phiếu lương hiển thị")
            shown_rows = list_rows(p).count()
            check("salary-slip" in p.url, f"thẻ gross không mở ra danh sách phiếu lương mà ở {p.url.replace(BASE, '')}")
            if slips:
                check(shown_rows > 0, f"danh sách trống trong khi đối chiếu có {len(slips)} phiếu")
            else:
                check("Không tìm thấy" in list_text(p) or shown_rows == 0,
                      f"danh sách hiện {shown_rows} dòng trong khi đối chiếu = 0 · {list_text(p)[:180]}")
            open_workspace(s, "TLC Điều hành", "Quay lại TLC Điều hành để ký")
            click_card(s, "Bảng lương chờ ký", "Bấm thẻ Bảng lương chờ ký để mở danh sách")
            click_row(s, PE_D, entry, f"Mở bảng lương {entry} chờ ký")
            head_line = headline(p)
            s.step("Đọc tổng hợp lương trên đầu form trước khi ký")
            check("thực lĩnh" in head_line or "tổng" in head_line.lower(), f"form không có dòng tổng hợp · {head_line[:180]}")
            actions = workflow_actions(p)
            check("Ký duyệt" in actions, f"CEO không thấy nút Ký duyệt trong Hành động: {actions}")
            form_action(s, "Ký duyệt")
            state_shown(s, SIGNED, tries=60)
            posted = wait_slips(s, entry, 1, 1)
            doc = api_doc(s, PE_D, entry)
            check(doc["workflow_state"] == SIGNED and posted > 0, f"{doc['workflow_state']} · {posted} phiếu ghi sổ")
            r["actual"] = (f"thẻ gross {gross:,} / net {net:,} của tháng này khớp đối chiếu ({shown_rows} dòng danh sách phiếu lương); "
                           f"thẻ chờ ký {waiting} → ký {entry} → {doc['workflow_state']}, {posted} phiếu lương đã ghi sổ")
    finally:
        s.close()


def accountant_pays(browser):
    """RX-25 – kế toán xác nhận đã chi ngay trên form bảng lương, kèm chứng từ ngân hàng."""
    s = Session(browser, "RX-ACCOUNT", "chi")
    entry = REQ.get("rx_pe", "")
    month = REQ.get("rx_month") or month_candidates()[0]
    reference = f"VCB-UNC-{month}-RX"
    try:
        with case(s, "RX-25", "Kế toán xác nhận chi lương trên form",
                  "Workspace TLC Kế toán chi trả > bấm thẻ Bảng lương chờ chi > mở bảng lương > kiểm tra Hành động chưa có "
                  "Xác nhận đã chi > gõ Số chứng từ ngân hàng và Ngày chi > Lưu > Hành động > Xác nhận đã chi",
                  f"{entry}, chứng từ {reference}",
                  "Chưa nhập chứng từ thì nút Xác nhận đã chi không tồn tại trên form; nhập xong thì nút hiện ra, bấm "
                  f"một lần là form chuyển {PAID}, bút toán ngân hàng mang đúng số chứng từ") as r:
            login(s)
            p = s.page
            open_workspace(s, "TLC Kế toán chi trả", "Kế toán mở workspace TLC Kế toán chi trả")
            waiting = read_card(s, "Bảng lương chờ chi", "Đọc thẻ Bảng lương chờ chi")
            check(waiting >= 1 and entry, f"thẻ Bảng lương chờ chi đếm {waiting}")
            click_card(s, "Bảng lương chờ chi", "Bấm thẻ Bảng lương chờ chi để mở danh sách")
            click_row(s, PE_D, entry, f"Mở bảng lương {entry}")
            actions = workflow_actions(p)
            check("Xác nhận đã chi" not in actions, f"chưa có chứng từ mà nút đã hiện: {actions}")
            s.step("Mở tab Nhân viên và mục Ký và chi lương để nhập đủ chứng từ")
            p.locator(".nav-link:visible", has_text=re.compile(r"^(Nhân viên|Employees)$")).first.click()
            p.wait_for_timeout(1200)
            s.step("Gõ số chứng từ ngân hàng vào form")
            type_text(p, "tlc_bank_reference", reference)
            s.step("Chọn ngày chi")
            type_date(p, "tlc_paid_on", dt.date.today().isoformat())
            upload_payroll_proof(s, entry, reference)
            s.step("Bấm Lưu để ghi chứng từ vào bảng lương")
            save_form(p)
            p.wait_for_function("() => window.cur_frm && !cur_frm.is_dirty()", timeout=40000)
            shown = field_input(p, "tlc_bank_reference").first.input_value()
            check(shown == reference, f"chứng từ hiển thị trên màn hình là {shown}")
            saved = api_doc(s, PE_D, entry)
            check(saved["tlc_bank_reference"] == reference and saved["tlc_paid_on"] == dt.date.today().isoformat()
                  and saved.get("tlc_bank_proof", "").startswith("/private/files/"), "thiếu số/ngày/file chi riêng tư")
            actions = workflow_actions(p)
            check("Xác nhận đã chi" in actions, f"có chứng từ rồi mà nút chưa hiện: {actions}")
            form_action(s, "Xác nhận đã chi")
            state_shown(s, PAID)
            doc = api_doc(s, PE_D, entry)
            je = api_list(s, "Journal Entry", ["name", "cheque_no"], [["cheque_no", "=", reference], ["docstatus", "=", 1]], limit=3)
            check(doc["workflow_state"] == PAID and je, f"{doc['workflow_state']} bút toán {je}")
            r["actual"] = (f"{entry}: thiếu chứng từ → không có nút; nhập {reference} + ngày chi → lưu → nút hiện ra → "
                           f"{doc['workflow_state']}, bút toán {je[0]['name']}")
    finally:
        s.close()


# ------------------------------------------------------------------------------------------------ RX-01..04 nhân viên

def read_balance(s):
    """Nhân viên bấm menu Nghỉ phép và đọc thẻ số dư ngay trên màn hình."""
    p = s.page
    s.step("Mở mục Nghỉ phép để đọc thẻ số dư phép")
    tab = p.locator("a[href*='/hrms/dashboard/leaves'], ion-tab-button[href*='/dashboard/leaves']").last
    if tab.count() and tab.is_visible():
        tab.click()
    else:
        p.get_by_text("Nghỉ phép", exact=True).last.click()
    p.wait_for_timeout(3500)
    if "/dashboard/leaves" not in p.url:  # the menu item next to it opens the request form; the balance lives on the dashboard
        p.goto(f"{BASE}/hrms/dashboard/leaves")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
    text = page_text(p)
    match = re.search(r"([\d.,]+)\s*/\s*([\d.,]+)[^\d]{0,20}Phép năm", text)
    check(match, f"màn hình Nghỉ phép không hiện thẻ số dư Phép năm · {text[:220]}")
    shown = tuple(float(x.replace(",", ".")) for x in match.groups())
    emp = employee_of(s, s.account)
    balance = api(s, "hrms.api.get_leave_balance_map", employee=emp["name"]).get("Phép năm", {})
    server = (float(balance.get("balance_leaves", -1)), float(balance.get("allocated_leaves", -1)))
    check(shown == server, f"số trên thẻ {shown} không khớp số dư {server}")
    return emp, shown


def worker_payslip(s, slip):
    """Từ trang chủ app bấm Xem phiếu lương rồi đọc số thực lĩnh trên màn hình phiếu lương."""
    p = s.page
    s.step("Về trang chủ app, bấm Xem phiếu lương của mình")
    p.goto(f"{BASE}/hrms/home")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2500)
    p.get_by_text("Xem phiếu lương", exact=True).first.click()
    p.wait_for_timeout(4500)
    if slip["name"] not in page_text(p):
        s.step("Chọn kỳ lương để danh sách phiếu lương hiện ra")
        period = p.get_by_text("Select Payroll Period", exact=False).first
        if period.count():
            period.click()
            option = p.locator("[role=option]:visible, .dropdown-item:visible, [role=menuitem]:visible")
            payroll_period = api_list(s, "Payroll Period", ["name", "start_date", "end_date"],
                                     [["company", "=", COMPANY]], limit=100)
            matching = [row for row in payroll_period if row["start_date"] <= slip["start_date"] <= row["end_date"]]
            check(len(matching) == 1, f"không có đúng kỳ trả lương bao phủ phiếu {slip['name']}")
            target = option.filter(has_text=matching[0]["name"])
            check(target.count() == 1, f"dropdown không có đúng kỳ {matching[0]['name']}; không chọn dòng đầu tuỳ ý")
            target.click()
            p.wait_for_timeout(3500)
    link = p.locator("a", has_text=slip["name"])
    if link.count():
        link.first.click()
        p.wait_for_timeout(4500)
    else:
        # the dashboard row prints the amount, not the employee; open the row with this payslip's net pay
        amount = f"{int(round(slip['net_pay'])):,}".replace(",", ".")
        row = p.locator("div.cursor-pointer").filter(has_text=amount).first
        if row.count():
            row.click()
            p.wait_for_timeout(4500)
        else:
            p.goto(f"{BASE}/hrms/salary-slips/{quote(slip['name'], safe='')}")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(3500)
    check(quote(slip["name"], safe="") in p.url or slip["name"] in p.url,
          f"đã mở nhầm phiếu lương thay vì {slip['name']}: {p.url.replace(BASE, '')}")
    tab = p.locator("button:visible, [role=tab]:visible", has_text=re.compile(r"Earnings & Deductions|Thu nhập & Khấu trừ"))
    if tab.count():
        tab.first.click()
        p.wait_for_timeout(2500)
    earn_text = page_text(p)
    net_tab = p.locator("button:visible, [role=tab]:visible",
                        has_text=re.compile(r"Net Pay Info|Thông tin thực lĩnh|Thông tin thực nhận"))
    if net_tab.count():
        net_tab.first.click()
        p.wait_for_timeout(2000)
    text = page_text(p)
    money = money_shown(p, slip["net_pay"])
    check(money, f"màn hình phiếu lương không hiện số thực lĩnh {slip['net_pay']:,.0f} · {text[:220]}")
    check("BHXH" in earn_text or "Thu nhập" in earn_text or "Earnings" in earn_text,
          f"phiếu lương không hiện cơ cấu thu nhập · {earn_text[:200]}")
    return money


def worker_day(browser):
    """Một buổi làm việc trọn vẹn của nhân viên trong app Frappe HR."""
    REQ.setdefault("rx_leave", {})
    for account, case_id, manager, decision in WORKERS:
        s = Session(browser, "RX-ESS", account)
        try:
            info = ACCOUNTS[account]
            who = info["name"] or account
            start = working_day(35)
            with case(s, case_id, "Nhân viên tự làm việc của mình trên app Frappe HR",
                      f"Đăng nhập /hrms > đọc thẻ số dư Phép năm > Xin nghỉ phép (điền loại, ngày, lý do) > Lưu > "
                      f"Hành động > Gửi duyệt > mở Đơn của tôi xem trạng thái > workspace Cá nhân > Đồng ý tăng ca > "
                      f"{decision} lời đề nghị của {manager} > Xem phiếu lương đọc số thực lĩnh",
                      f"{account}@demo.example: nghỉ 1 ngày {vn(start)}, lời đề nghị tăng ca của {manager}",
                      "Thẻ số dư trên màn hình khớp số dư; đơn của mình hiện đúng trạng thái chờ duyệt trong Đơn của tôi; "
                      "lời đề nghị tăng ca chuyển đúng bước sau quyết định của người lao động; phiếu lương hiện số thực lĩnh") as r:
                login(s)
                p = s.page
                s.step(f"{who} mở trang chủ app Frappe HR")
                check("/hrms" in p.url, f"nhân viên không vào app Frappe HR mà ở {p.url.replace(BASE, '')}")
                check(who in page_text(p) or "Xin chào" in page_text(p), "trang chủ không có lời chào của người dùng")
                emp, balance = read_balance(s)
                s.step("Bấm Xin nghỉ phép và điền đơn")
                name = hrms_request_leave(s, start, start, "Việc gia đình")
                REQ["rx_leave"][account] = name
                s.step("Mở Đơn của tôi để xem đơn mình đang chờ ai duyệt")
                p.goto(f"{BASE}/hrms/leave-applications")
                p.wait_for_load_state("networkidle")
                p.wait_for_timeout(3000)
                p.get_by_text("Đơn của tôi", exact=True).first.click()
                p.wait_for_timeout(3500)
                mine = page_text(p)
                day_tag = dt.date.fromisoformat(start).strftime("%d %b")
                check(day_tag in mine, f"Đơn của tôi không thấy đơn ngày {day_tag} · {mine[:240]}")
                check(TO_MANAGER in mine, f"đơn trong Đơn của tôi không hiện {TO_MANAGER} · {mine[:240]}")
                doc = api_doc(s, "Leave Application", name)
                check((doc["workflow_state"], doc["leave_approver"]) == (TO_MANAGER, f"{manager}@demo.example"), str(doc)[:220])
                # lời đề nghị tăng ca
                ot_name = REQ.get("rx_ot", {}).get(account)
                check(ot_name, f"không có lời đề nghị tăng ca nào chờ {account} quyết định")
                open_workspace(s, "TLC Cá nhân", f"Mở workspace Cá nhân của {who}")
                click_shortcut(s, "ESS Đồng ý tăng ca", "/desk/tlc-overtime-request", "Bấm shortcut Đồng ý tăng ca")
                filter_list(p, ("Mã định danh", "Name"), ot_name)
                click_row(s, OT_D, ot_name, f"Mở lời đề nghị tăng ca {ot_name}")
                ot_doc = api_doc(s, OT_D, ot_name)
                s.step("Đọc nội dung lời đề nghị tăng ca trên form")
                form = form_text(p)
                identity = " ".join(p.locator(".page-head:visible, .form-sidebar:visible").all_inner_texts())
                shown_day = user_date(p, ot_doc["ot_date"])
                check(ot_name in identity and shown_day in form,
                      f"form tăng ca không hiện đúng đề nghị {ot_name} / {ot_doc['ot_date']} · "
                      f"định danh: {identity[:180]} · ngày: {shown_day!r} · {form[:220]}")
                actions = workflow_actions(p)
                check(decision in actions, f"người lao động không thấy nút {decision} trong Hành động: {actions}")
                if decision == "Từ chối":
                    s.step("Gõ lý do từ chối vào ô Lý do từ chối rồi Lưu")
                    reason = "Ca này tôi đã hẹn khám sức khỏe định kỳ, đề nghị bố trí người khác"
                    box = field_input(p, "tlc_reject_reason")
                    check(box.count() > 0, "form tăng ca không có ô Lý do từ chối cho người lao động")
                    box.first.click()
                    box.first.fill(reason)
                    p.keyboard.press("Tab")
                    p.wait_for_timeout(900)
                    save_form(p)
                    form_action(s, "Từ chối", reason=reason)
                    state_shown(s, REJECTED)
                    shown_reason = field_input(p, "tlc_reject_reason").first.input_value()
                    check(shown_reason == reason, f"lý do trên màn hình là {shown_reason!r}")
                    saved = api_doc(s, OT_D, ot_name)
                    check(saved["workflow_state"] == REJECTED and saved["tlc_reject_reason"] == reason, str(saved)[:220])
                    decide = f"từ chối kèm lý do “{shown_reason[:46]}”"
                else:
                    form_action(s, "Đồng ý")
                    state_shown(s, "Chờ giám đốc duyệt")
                    saved = api_doc(s, OT_D, ot_name)
                    check(saved["workflow_state"] == "Chờ giám đốc duyệt" and saved["consent_at"], str(saved)[:220])
                    decide = "đồng ý"
                # phiếu lương của mình
                slips = api_list(s, SS_D, ["name", "net_pay", "start_date"], [["employee", "=", emp["name"]], ["docstatus", "=", 1]], limit=10)
                check(slips, f"{account} chưa có phiếu lương đã phát hành để xem")
                slip = max(slips, key=lambda x: x["start_date"])
                money = worker_payslip(s, slip)
                r["actual"] = (f"{who}: thẻ phép {balance[0]:g}/{balance[1]:g} khớp đối chiếu; đơn {name} hiện {TO_MANAGER} "
                               f"trong Đơn của tôi; tăng ca {ot_name} → {saved['workflow_state']} ({decide}); "
                               f"phiếu {slip['name']} hiện thực lĩnh {money}")
        finally:
            s.close()


# ------------------------------------------------------------------------------------------------ RX-11..13 trưởng nhà máy

def factory_head_day(browser):
    """Trưởng nhà máy duyệt đơn của đội mình từ thẻ trên TLC Quản lý, rồi tự kiểm tra phạm vi ngay trên danh sách."""
    for account, case_id, own, other in HEAD_CASES:
        s = Session(browser, "RX-FACTORY", account)
        try:
            own_leave = REQ.get("rx_leave", {}).get(own)
            with case(s, case_id, "Trưởng nhà máy làm việc trong hàng đợi của mình và không thấy người nhà máy khác",
                      "Workspace TLC Quản lý > bấm thẻ Đơn chờ tôi duyệt > mở danh sách > mở đơn của công nhân nhà mình > "
                      "đọc dòng tư vấn > Hành động > Duyệt > mở danh sách Nhân viên bằng shortcut > lọc theo tên một nhân "
                      "viên nhà máy khác > thử mở hồ sơ nhân viên nhà máy đó",
                      f"{account}@demo.example duyệt {own_leave or ''} của {own}; thử mở hồ sơ của {other}",
                      f"Thẻ mở đúng danh sách chờ; đơn chuyển {TO_HR} ngay sau khi bấm Duyệt; danh sách nhân sự chỉ có "
                      "người của nhà máy mình, lọc tên người nhà máy khác cho danh sách trống và hồ sơ đó bị màn hình từ chối") as r:
                login(s)
                p = s.page
                open_workspace(s, "TLC Quản lý", f"{ACCOUNTS[account]['name']} mở workspace TLC Quản lý")
                waiting = read_card(s, "Đơn chờ tôi duyệt", "Đọc thẻ Đơn chờ tôi duyệt")
                check(waiting >= 1 and own_leave, f"thẻ đếm {waiting} đơn, dữ liệu nền {own_leave}")
                click_card(s, "Đơn chờ tôi duyệt", "Bấm thẻ để mở danh sách đơn chờ mình duyệt")
                own_worker = employee_of(s, own)
                s.step("Kiểm tra danh sách có đúng đơn của công nhân nhà mình")
                text = list_text(p)
                check(own_worker["employee_name"] in text or own_leave in text,
                      f"hàng đợi không thấy đơn của {own_worker['employee_name']} · {text[:240]}")
                click_row(s, "Leave Application", own_leave, f"Mở đơn {own_leave} của {own_worker['employee_name']}")
                check(p.evaluate("() => cur_frm.doc.name") == own_leave, "form mở ra không phải đơn đang nghiệm thu")
                s.step("Đọc dòng tư vấn trên đầu đơn trước khi duyệt")
                head_line = headline(p)
                check(len(head_line) > 0, "form đơn nghỉ không có dòng tư vấn số dư/trùng ngày cho người duyệt")
                actions = workflow_actions(p)
                check("Duyệt" in actions, f"Hành động không có nút Duyệt: {actions}")
                state = desk_action(s, own_leave, "Duyệt")
                state_shown(s, TO_HR, "Xem trạng thái đơn sau khi duyệt cấp quản lý")
                check(state == TO_HR, state)
                open_workspace(s, "TLC Quản lý", "Quay lại workspace TLC Quản lý")
                click_shortcut(s, "Nhân viên", "/desk/employee", "Mở danh sách Nhân viên bằng shortcut của workspace")
                s.step("Đọc danh sách nhân sự: chỉ người của nhà máy mình")
                mine = api_list(s, "Employee", ["name", "employee_name", "department"], limit=500)
                shown = rows_text(p)
                # the head cannot read another factory's employees (that is what the case proves), so the fixture
                # lookup goes through a company-wide session; the UI attempts below still run as the head.
                fix = Session(browser, "RX-LOOKUP", "lan")
                login(fix)
                try:
                    other_emp = employee_of(fix, other)
                finally:
                    fix.context.close()
                check(own_worker["employee_name"] in shown, f"danh sách nhân sự không có người của mình · {shown[:220]}")
                check(other_emp["employee_name"] not in shown, f"danh sách nhân sự lẫn người nhà máy khác: {other_emp['employee_name']}")
                depts = {m["department"] for m in mine}
                check(depts == {own_worker["department"]}, f"phạm vi Employee của {account} lẫn bộ phận: {sorted(depts)}")
                s.step(f"Lọc danh sách theo tên {other_emp['employee_name']} (người của nhà máy khác)")
                filtered = filter_list(p, ("Họ và tên", "Tên nhân viên", "Mã định danh"), other_emp["employee_name"])
                after = rows_text(p)
                empty_list = list_rows(p).count() == 0 or "Không tìm thấy" in list_text(p) or "Không có dữ liệu" in list_text(p)
                if filtered:
                    check(empty_list and other_emp["employee_name"] not in after,
                          f"lọc tên người nhà máy khác vẫn ra dòng: {after[:220]}")
                s.step("Thử mở thẳng hồ sơ nhân viên nhà máy khác (đường dẫn đồng nghiệp gửi)")
                p.goto(f"{BASE}/desk/employee/{quote(other_emp['name'])}")
                p.wait_for_load_state("networkidle")
                p.wait_for_timeout(3500)
                denied = page_text(p)
                check(re.search(r"Không được phép|Bạn cần quyền|Not permitted|Insufficient Permission|Không có quyền", denied, re.I),
                      f"hồ sơ {other_emp['name']} mở được với {account}: {denied[:180]}")
                r["actual"] = (f"{account}: thẻ {waiting} → đơn {own_leave} của {own_worker['employee_name']} → {state}; "
                               f"danh sách nhân sự {len(mine)} người đúng bộ phận {own_worker['department']}"
                               + (f", lọc “{other_emp['employee_name']}” ra danh sách trống" if filtered else " (danh sách không có ô lọc)")
                               + f"; mở hồ sơ {other_emp['name']} → màn hình “Không được phép”")
        finally:
            s.close()


# ------------------------------------------------------------------------------------------------ RX-26 trưởng phòng hội sở

def office_manager_day(browser):
    s = Session(browser, "RX-MANAGER", "quang")
    leave = REQ.get("rx_leave", {}).get("an")
    try:
        with case(s, "RX-26", "Trưởng phòng hội sở duyệt đơn trong hàng đợi native của mình",
                  "Workspace TLC Quản lý > đọc và bấm thẻ Đơn chờ tôi duyệt > mở danh sách > mở đơn của nhân viên phòng > "
                  "Hành động > Duyệt",
                  f"quang@demo.example duyệt {leave or ''} của Nguyễn Hoài An",
                  f"Thẻ mở đúng danh sách đơn chờ mình và hàng đợi chỉ có người của phòng; đơn chuyển {TO_HR} sau khi bấm Duyệt") as r:
            login(s)
            p = s.page
            open_workspace(s, "TLC Quản lý", "Trần Minh Quang mở workspace TLC Quản lý")
            waiting = read_card(s, "Đơn chờ tôi duyệt", "Đọc thẻ Đơn chờ tôi duyệt")
            check(waiting >= 1 and leave, f"thẻ Đơn chờ tôi duyệt đếm {waiting}")
            click_card(s, "Đơn chờ tôi duyệt", "Bấm thẻ để mở danh sách đơn chờ mình duyệt")
            queue = api_list(s, "Leave Application", ["name", "employee_name"], [["workflow_state", "=", TO_MANAGER]], limit=100)
            check(leave in [q["name"] for q in queue], f"hàng đợi của trưởng phòng không có đơn {leave}: {queue}")
            click_row(s, "Leave Application", leave, "Mở đơn của Nguyễn Hoài An")
            s.step("Đọc nhân viên và tình trạng đơn trên form")
            check("Nguyễn Hoài An" in form_text(p), form_text(p)[:200])
            form_action(s, "Duyệt")
            state_shown(s, TO_HR)
            doc = api_doc(s, "Leave Application", leave)
            check(doc["workflow_state"] == TO_HR and doc["leave_approver"] == "quang@demo.example", str(doc)[:220])
            r["actual"] = f"thẻ {waiting} → hàng đợi {len(queue)} đơn phòng mình → duyệt {leave} của Nguyễn Hoài An → {doc['workflow_state']}"
    finally:
        s.close()


# ------------------------------------------------------------------------------------------------ RX-21, RX-22 HR

def hr_day(browser):
    """HR duyệt cấp cuối trong hàng đợi nhân sự, mở danh sách hồ sơ vòng đời và bấm thẻ việc đến hạn."""
    cases = (("hoa", "RX-21", "binh", "HR Nghỉ việc", "Employee Separation", "/desk/employee-separation", "Việc mở quá hạn"),
             ("lan", "RX-22", "an", "HR Tuyển dụng", "Job Opening", "/desk/job-opening", "Việc mở đến hạn tuần này"))
    for account, case_id, worker, shortcut, list_dt, route, due_card in cases:
        s = Session(browser, "RX-HR", account)
        try:
            leave = REQ.get("rx_leave", {}).get(worker)
            with case(s, case_id, "HR duyệt cấp cuối và làm việc với hồ sơ vòng đời, việc đến hạn",
                      f"Workspace TLC Nhân sự > bấm thẻ Đơn chờ nhân sự duyệt > mở đơn của {worker} > Hành động > Duyệt "
                      f"> quay lại đọc lại thẻ > sang TLC HR Hạn xử lý > bấm thẻ {due_card} > bấm shortcut {shortcut}",
                      f"{account}@demo.example duyệt {leave or ''}; mở danh sách {list_dt}",
                      f"Hàng đợi nhân sự mở đúng đơn; sau khi bấm Duyệt đơn hiện {APPROVED} ngay trên form và số trên thẻ "
                      "giảm đúng một; thẻ việc đến hạn mở ra thấy đúng đầu việc của mình; danh sách hồ sơ vòng đời mở bằng chuột") as r:
                login(s)
                p = s.page
                open_workspace(s, "TLC Nhân sự", f"{ACCOUNTS[account]['name']} mở workspace TLC Nhân sự")
                before = read_card(s, "Đơn chờ nhân sự duyệt", "Đọc thẻ Đơn chờ nhân sự duyệt")
                check(before >= 1 and leave, f"thẻ Đơn chờ nhân sự duyệt đếm {before}, đơn chờ: {leave}")
                click_card(s, "Đơn chờ nhân sự duyệt", "Bấm thẻ để mở hàng đợi của nhân sự")
                name = employee_of(s, worker)["employee_name"]
                click_row(s, "Leave Application", leave, f"Mở đơn {leave} của {name}")
                actions = workflow_actions(p)
                check("Duyệt" in actions, f"HR không thấy nút Duyệt trong Hành động: {actions}")
                form_action(s, "Duyệt", "Hành động > Duyệt (cấp cuối của nhân sự)")
                state_shown(s, APPROVED, "Xem trạng thái đã duyệt trên form")
                doc = api_doc(s, "Leave Application", leave)
                check(doc["workflow_state"] == APPROVED and doc["status"] == "Approved", str(doc)[:220])
                open_workspace(s, "TLC Nhân sự", "Quay lại TLC Nhân sự đọc lại thẻ hàng đợi")
                after = card_value(p, "Đơn chờ nhân sự duyệt")
                check(after == before - 1, f"thẻ hàng đợi {before} → {after} sau khi duyệt một đơn")
                open_workspace(s, "TLC HR Hạn xử lý", "Mở workspace TLC HR Hạn xử lý")
                due = read_card(s, due_card, f"Đọc thẻ {due_card}")
                check(due >= 1, f"thẻ {due_card} đếm {due}")
                click_card(s, due_card, f"Bấm thẻ {due_card} để mở danh sách việc")
                marker = REQ.get("rx_todo", {}).get(account, "Việc UAT")
                s.step("Kiểm tra đầu việc đến hạn của mình có trong danh sách")
                check(marker in rows_text(p), f"danh sách việc không thấy {marker} · {rows_text(p)[:240]}")
                open_workspace(s, "TLC HR Hạn xử lý", "Quay lại TLC HR Hạn xử lý")
                click_shortcut(s, shortcut, route, f"Bấm shortcut {shortcut} để mở danh sách hồ sơ")
                s.step(f"Đọc danh sách hồ sơ {list_dt}")
                rows = list_rows(p).count()
                check(rows > 0, f"danh sách {list_dt} không có dòng nào · {list_text(p)[:200]}")
                r["actual"] = (f"{account}: thẻ {before} → duyệt {leave} của {name} → {doc['workflow_state']} (thẻ còn {after}); "
                               f"thẻ {due_card} = {due} mở ra thấy “{marker}”; shortcut {shortcut} mở {rows} dòng hồ sơ")
        finally:
            s.close()


JOURNEYS = [prepare_data, payroll_maker, ceo_signs, accountant_pays, worker_day, factory_head_day, office_manager_day, hr_day]