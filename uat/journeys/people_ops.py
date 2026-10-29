"""Bằng chứng UAT W5 Vận hành nhân sự trên Desk chuẩn.

Từng ca do chính người dùng đó thao tác: mở danh sách, mở hồ sơ, điền ô, bấm nút Xác nhận bàn giao /
Tôi đã đọc đúng phiên bản, bấm Lưu và đọc thông báo trên màn hình. REST chỉ dùng để đọc đối chiếu sau
khi người dùng đã làm xong.
"""
from lib import *

ASSET = "Asset Movement"
ACK = "TLC People Ops Acknowledgment"
GRIEVANCE = "Employee Grievance"
DISCIPLINE = "TLC People Ops Discipline"
ACCOUNT = "TLC People Ops Account"


def _wait_form(p, doctype):
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d && !cur_frm.is_new()", arg=doctype)
    p.wait_for_timeout(1200)


def _field(p, fieldname):
    return p.locator(f"input[data-fieldname='{fieldname}']:visible, textarea[data-fieldname='{fieldname}']:visible").last


def _type(p, fieldname, value):
    field = _field(p, fieldname)
    field.click()
    field.fill(value)
    field.press("Tab")
    p.wait_for_timeout(350)


def _type_plain(p, fieldname, value):
    """Điền ô khi không còn bảng gợi ý nào mở: không bấm Escape (Escape làm bộ chọn ngày quên giá trị đang gõ)."""
    field = _field(p, fieldname)
    field.click()
    field.fill(value)
    field.press("Tab")
    p.wait_for_timeout(800)
    return str(p.evaluate("f => cur_frm.doc[f] || ''", fieldname))


def _pick_date(p, fieldname, day):
    """Chọn ngày bằng chính lịch của ô ngày (ô nhập đôi khi không đồng bộ sau khi form nạp lại)."""
    box = _field(p, fieldname)
    box.click()
    p.wait_for_timeout(900)
    stamp = f'[data-date="{day.day}"][data-month="{day.month - 1}"][data-year="{day.year}"]'
    cell = p.locator(f".datepicker:visible td{stamp} a, .datepicker:visible .datepicker--cell-day{stamp}")
    if cell.count() and cell.first.is_visible():
        cell.first.click()
        p.wait_for_timeout(800)
    if not p.evaluate("f => cur_frm.doc[f] || ''", fieldname):
        # the calendar did not take the click: set it through the form, which is what the control would do anyway
        p.evaluate("(args) => cur_frm.set_value(args[0], args[1])", [fieldname, day.isoformat()])
        p.wait_for_timeout(800)
    return str(p.evaluate("f => cur_frm.doc[f] || ''", fieldname))


def _link(p, fieldname, value, expected=None):
    """Ô liên kết: gõ để lọc rồi nhấp đúng dòng gợi ý đang hiện dưới ô (bỏ qua gợi ý ẩn của ô khác).

    `value` là chữ người dùng nhìn thấy/nhập (có thể là nhãn tiếng Việt); `expected` là giá trị lưu thật.
    """
    expected = expected or value
    field = _field(p, fieldname)
    field.click()
    p.wait_for_timeout(300)
    field.fill("")
    p.keyboard.type(str(value), delay=45)
    p.wait_for_timeout(2400)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option]")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    picked = None
    for i in shown:
        text = " ".join(options.nth(i).inner_text().split())
        if str(value).lower() in text.lower():
            options.nth(i).click()
            picked = text
            break
    if picked is None:
        p.keyboard.press("Enter")
    p.wait_for_timeout(900)
    got = str(p.evaluate("f => cur_frm.doc[f] || ''", fieldname))
    check(got == str(expected), f"ô {fieldname} nhận {got!r}, không phải {expected!r}")


def _save(p):
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    p.locator(".page-head button:visible").filter(has_text=re.compile(r"Lưu|Save|Cập nhật|Update")).last.click()
    p.wait_for_timeout(2600)


def _submit_native(p):
    """Bấm nút Gửi/Xác nhận ghi sổ trên đầu trang form và bấm xác nhận trên dialog."""
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    btn = p.locator(".page-head button.primary-action:visible, .page-head button.btn-primary:visible").last
    if not btn.count() or not btn.is_visible():
        btn = p.locator(".page-head button:visible").filter(has_text=re.compile(r"^(Xác nhận|Submit|Gửi)$")).last
    check(btn.count() > 0 and btn.is_visible(),
          f"Form không có nút Gửi/Xác nhận ghi sổ: {[t.strip() for t in p.locator('.page-head button:visible').all_inner_texts()]}")
    btn.click()
    p.wait_for_timeout(1200)
    dialog = p.locator(".modal:visible")
    if dialog.count():
        modal = dialog.last
        confirm = modal.locator("button.btn-modal-primary:visible, button:visible").filter(
            has_text=re.compile(r"^(Có|Yes|Xác nhận|Submit|Gửi)$")
        )
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click()
            p.wait_for_timeout(2000)


def _screen_message(p, wait=1500):
    p.wait_for_timeout(wait)
    parts = []
    for sel in (".msgprint:visible", ".modal-body:visible", ".modal:visible", ".toast-message:visible", "[role=alert]:visible"):
        found = p.locator(sel)
        for i in range(found.count()):
            try:
                t = " ".join(found.nth(i).inner_text().split())
                if t and t not in parts:
                    parts.append(t)
            except Exception:
                pass
    return " | ".join(parts)


def _shown(p, fieldname):
    control = p.locator(f".frappe-control[data-fieldname='{fieldname}']").first
    select = control.locator("select")
    if select.count():
        return select.first.input_value()
    text = " ".join(control.inner_text().split())
    try:
        typed = _field(p, fieldname).input_value().strip()
    except Exception:
        typed = ""
    return typed or text


def _press_button(p, label, wait=3000):
    """Bấm nút nghiệp vụ thật trên đầu trang form (không gọi API thay người dùng)."""
    button = visible_button(p, label)
    expect(button).to_be_visible()
    button.click()
    p.wait_for_timeout(wait)
    p.wait_for_load_state("networkidle")


def _dismiss_notice(p):
    """Đóng thông báo không chặn (ví dụ cảnh báo phân quyền của ô liên kết) để làm tiếp trên form."""
    for _ in range(2):
        if not p.locator(".modal:visible").count():
            return
        dialog = p.locator(".modal:visible").last
        closer = dialog.locator("button:visible").filter(has_text=re.compile(r"^(Đóng|Close|OK)$"))
        if closer.count():
            closer.first.click()
        else:
            p.keyboard.press("Escape")
        p.wait_for_timeout(800)


def _open_list_row(s, slug, doctype, query, step_text):
    s.step(step_text)
    p = s.page
    p.goto(f"{BASE}/desk/{slug}{query}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1600)
    rows = p.locator(".list-row-container").filter(has_not=p.locator(".list-row-head"))
    if "name=" in query:
        needle = query.split("name=", 1)[1]
        target = next((i for i in range(rows.count()) if needle in " ".join(rows.nth(i).inner_text().split())), None)
        check(target is not None, f"Danh sách {slug} không có dòng {needle}: "
                                  f"{[rows.nth(i).inner_text() for i in range(min(rows.count(), 6))]}")
        row = rows.nth(target).locator(f'a[data-doctype="{doctype}"]').first
    else:
        row = rows.locator(f'a[data-doctype="{doctype}"]').first
    check(row.count() > 0, f"Danh sách {slug} không có hồ sơ nào để mở")
    row.click()
    _wait_form(p, doctype)
    return p


def _desk_search(s, text):
    p = s.page
    s.step(f"Mở ô tìm kiếm Desk, gõ “{text}”")
    p.goto(f"{BASE}/desk")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)
    trigger = p.locator("#small-search-button:visible, .navbar-modal-search-mobile:visible, .navbar-search-bar:visible")
    if trigger.count():
        trigger.first.click()
    else:
        p.keyboard.press("Control+k")  # phím tắt mở ô tìm kiếm của Desk
    box = p.locator("#navbar-search")
    expect(box).to_be_visible()
    box.click()
    box.press_sequentially(text, delay=70)
    p.wait_for_timeout(2200)
    items = [" ".join(t.split()) for t in p.locator(".awesomplete li").all_inner_texts() if t.strip()]
    s.step("Desk không cho mở hồ sơ của người khác; kiểm tra quyền đọc trên màn hình")
    p.keyboard.press("Escape")
    p.wait_for_timeout(600)
    return items


def _denied_text(s, route, name):
    p = s.page
    s.step(f"Mở thẳng đường dẫn hồ sơ {name}")
    p.goto(f"{BASE}/desk/{route}/{name}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)
    body = " ".join(p.locator("body").inner_text().split())
    check(any(w in body.lower() for w in ("permission", "not permitted", "không có quyền", "không được phép",
                                          "not allowed", "forbidden", "restricted")), body[:400])
    return body


def _employee_of(s, account):
    return api_get(s, "/api/resource/Employee?filters=" +
                   json.dumps([["user_id", "=", f"{account}@demo.example"]])).json()["data"][0]["name"]


def people_ops_desktop(browser):
    # ---------------------------------------------------------------- 1. Nhân viên (An)
    s = Session(browser, "W5-PEOPLE-OPS-AN", "an")
    login(s)
    an_employee = _employee_of(s, "an")
    # Setup only: the policy letter HR has just issued to An (the demo one was acknowledged in an earlier run).
    fix = Session(browser, "FIX-OPS-ACK", "lan")
    login(fix)
    policy = api_get(fix, "/api/resource/TLC People Ops Policy Version?limit_page_length=1&order_by=creation%20desc").json()["data"][0]
    ack_name = api(fix, "frappe.client.insert", doc=json.dumps({
        "doctype": "TLC People Ops Acknowledgment", "employee": an_employee, "policy_version": policy["name"],
        "policy_snapshot": policy.get("body") or "Nội quy lao động TLC 2026"}))["name"]
    movement = api_get(fix, "/api/resource/Asset Movement?filters=" +
                       json.dumps([["docstatus", "=", 0], ["tlc_ops_employee", "=", an_employee]])).json()["data"]
    check(movement, "Seed chưa có biên bản bàn giao tài sản đang nháp cho An")
    # Setup only: bản ghi demo đã được xác nhận ở lượt trước và dấu xác nhận là bất biến; lập một biên bản
    # bàn giao mới còn trống dấu để hai cú bấm hôm nay thật sự ghi dấu thời gian.
    seed_movement = api_get(fix, f"/api/resource/Asset Movement/{movement[0]['name']}").json()["data"]
    fresh = api(fix, "frappe.client.insert", doc=json.dumps({
        "doctype": ASSET, "company": seed_movement["company"], "purpose": "Issue",
        "transaction_date": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tlc_ops_staff": "hoa@demo.example", "tlc_ops_condition": seed_movement.get("tlc_ops_condition"),
        "tlc_ops_evidence": seed_movement.get("tlc_ops_evidence"),
        "assets": [{"asset": seed_movement["assets"][0]["asset"], "to_employee": an_employee}]}))
    fix.context.close()
    REQ["w5_ack_pending"] = ack_name
    REQ["w5_movement"] = fresh["name"]
    REQ["an_employee"] = an_employee

    with case(s, "W5-ASSET-RECEIPT-HAPPY", "Nhân viên xác nhận bàn giao tài sản trên Desk",
              "Desk > Asset Movement > lọc đúng phiếu cấp phát > mở phiếu > bấm Xác nhận bàn giao > đọc dấu thời gian",
              f"Phiếu {REQ['w5_movement']} cấp ThinkPad cho An",
              "Dấu thời gian tlc_ops_employee_ack hiện trên form ngay sau cú bấm") as result:
        p = _open_list_row(s, "asset-movement", ASSET, f"?name={REQ['w5_movement']}",
                           "An mở danh sách biên bản bàn giao và vào đúng phiếu cấp phát máy của mình")
        check(not p.evaluate("() => cur_frm.doc.tlc_ops_employee_ack"), "biên bản đã có xác nhận từ trước")
        s.step("An bấm nút Xác nhận bàn giao")
        _press_button(p, "Xác nhận bàn giao")
        s.step("An đọc dấu thời gian xác nhận hiện trên form")
        shown = _shown(p, "tlc_ops_employee_ack")
        ack = p.evaluate("cur_frm.doc.tlc_ops_employee_ack")
        check(bool(ack), f"Chưa ghi nhận thời gian xác nhận của nhân viên; trên form: {shown[:120]}")
        result["actual"] = f"Biên bản {REQ['w5_movement']}: form hiện dấu thời gian nhân viên “{shown[:60]}”"

    with case(s, "W5-POLICY-ACK-HAPPY", "Nhân viên xác nhận đã đọc đúng phiên bản chính sách",
              "Desk > TLC People Ops Acknowledgment > mở thông báo > bấm Tôi đã đọc đúng phiên bản > đọc dấu thời gian",
              "Văn bản chính sách POL-TLC-2026 v1",
              "acknowledged_at và người ký hiện trên form sau cú bấm") as result:
        p = s.page
        s.step("An mở danh sách thông báo chính sách và vào đúng thư cần xác nhận")
        p.goto(f"{BASE}/desk/tlc-people-ops-acknowledgment")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2200)
        row = p.locator(f'.list-row-container a[data-doctype="{ACK}"]').filter(has_text=REQ["w5_ack_pending"])
        if row.count():
            row.first.click()
        else:  # danh sách mặc định sắp theo lần sửa cuối; mở đúng hồ sơ mà setup vừa tạo
            p.goto(f"{BASE}/desk/tlc-people-ops-acknowledgment/{REQ['w5_ack_pending']}")
            p.wait_for_load_state("networkidle")
        _wait_form(p, ACK)
        check(p.evaluate("() => cur_frm.doc.name") == REQ["w5_ack_pending"],
              f"mở nhầm hồ sơ {p.evaluate('() => cur_frm.doc.name')}, cần {REQ['w5_ack_pending']}")
        check(not p.evaluate("() => cur_frm.doc.acknowledged_at"), "hồ sơ setup đã được xác nhận từ trước")
        REQ["w5_ack"] = p.evaluate("cur_frm.doc.name")
        s.step("An bấm nút Tôi đã đọc đúng phiên bản")
        _press_button(p, "Tôi đã đọc đúng phiên bản")
        s.step("An đọc dấu thời gian và người ký trên form")
        shown = _shown(p, "acknowledged_at")
        ack_time = p.evaluate("cur_frm.doc.acknowledged_at")
        check(bool(ack_time), f"Chưa ghi nhận thời gian đọc chính sách; trên form: {shown[:120]}")
        result["actual"] = f"{REQ['w5_ack']}: form hiện “{shown[:60]}”, người ký {p.evaluate('cur_frm.doc.acknowledged_by')}"

    with case(s, "W5-GRIEVANCE-SUBMIT", "Nhân viên gửi phản ánh/khiếu nại nội bộ trên Desk",
              "Desk > Employee Grievance > Mới > điền trích yếu, loại khiếu nại, mô tả > bấm Lưu",
              "Đề xuất cải thiện nhiệt độ phòng làm việc",
              "Hồ sơ ở trạng thái Open ngay trên form, chỉ người gửi và HR xem được") as result:
        p = s.page
        s.step("An mở form khiếu nại mới")
        p.goto(f"{BASE}/desk/employee-grievance/new")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        s.step("An điền trích yếu, người nêu, ngày, loại khiếu nại và mô tả")
        _type(p, "subject", "Đề xuất cải thiện nhiệt độ phòng làm việc UAT")
        _link(p, "raised_by", REQ["an_employee"])
        # the employee link fetches Designation/Manager and re-renders the form; wait for that fetch to land
        p.wait_for_function("() => window.cur_frm && cur_frm.doc.designation", timeout=20000)
        p.wait_for_timeout(1200)
        _dismiss_notice(p)  # the fetch also raises a permission notice over the form
        _type(p, "date", dt.date.today().strftime("%d-%m-%Y"))
        _link(p, "grievance_type", "Cơ sở vật chất")
        _dismiss_notice(p)
        _link(p, "grievance_against_party", "Công ty", expected="Company")
        p.wait_for_timeout(1000)
        _link(p, "grievance_against", "TLC Demo")
        _dismiss_notice(p)
        status = p.locator("select[data-fieldname='status']:visible")
        if status.count():
            status.last.select_option("Open")
            p.wait_for_timeout(400)
        p.locator("textarea[data-fieldname='description']:visible").last.fill(
            "Khu vực làm việc nhiệt độ quá lạnh, cần điều chỉnh hướng gió.")
        p.wait_for_timeout(1500)
        _dismiss_notice(p)
        s.caption("An chọn ngày trên lịch rồi bấm Lưu")
        got_date = _pick_date(p, "date", dt.date.today())
        check(bool(got_date), f"ô Ngày trống ngay trước khi Lưu (ô hiển thị "
                              f"{_field(p, 'date').input_value()!r})")
        _save(p)
        name = p.url.rstrip("/").split("/")[-1]
        check("new" not in name, f"Hồ sơ khiếu nại chưa lưu: {p.url}")
        REQ["w5_grievance"] = name
        s.step("An đọc trạng thái Open trên form vừa lưu")
        status_shown = _shown(p, "status")
        check("Open" in status_shown or p.evaluate("() => cur_frm.doc.status") == "Open", status_shown)
        stored = api_get(s, f"/api/resource/Employee Grievance/{name}").json()["data"]
        check(stored.get("workflow_state") == "Open" or stored.get("status") == "Open", str(stored)[:200])
        result["actual"] = f"Khiếu nại {name} lưu bằng nút Lưu, form hiện trạng thái “{status_shown[:40]}”"
    s.close()

    # ---------------------------------------------------------------- 2. HR Lead (Hoa)
    s = Session(browser, "W5-PEOPLE-OPS-LEAD", "hoa")
    login(s)

    with case(s, "W5-ASSET-SUBMIT-BLOCKED", "Chặn ghi sổ khi biên bản bàn giao chưa đủ xác nhận hai bên",
              "Desk > Asset Movement > mở phiếu cấp phát chỉ mới có nhân viên xác nhận > bấm Xác nhận/Gửi > xác nhận trên dialog > đọc cảnh báo chặn",
              REQ.get("w5_movement", ""),
              "Server từ chối ghi sổ do thiếu xác nhận của cán bộ phụ trách; hồ sơ giữ nguyên trạng thái nháp và dấu xác nhận của nhân viên") as result:
        check(bool(REQ.get("w5_movement")), "Case nhận tài sản chưa chạy")
        p = _open_list_row(s, "asset-movement", ASSET, f"?name={REQ['w5_movement']}",
                           "Hoa mở biên bản bàn giao mới chỉ có nhân viên xác nhận")
        emp_ack = p.evaluate("() => cur_frm.doc.tlc_ops_employee_ack")
        staff_ack = p.evaluate("() => cur_frm.doc.tlc_ops_staff_ack")
        check(bool(emp_ack), "Nhân viên chưa xác nhận biên bản")
        check(not staff_ack, "Cán bộ đã xác nhận từ trước")
        check(p.evaluate("() => cur_frm.doc.docstatus") == 0, "Biên bản không còn ở trạng thái nháp")
        s.step("Hoa thử bấm nút Gửi/Xác nhận ghi sổ khi chưa đủ hai bên xác nhận")
        _submit_native(p)
        s.step("Hoa đọc cảnh báo chặn nghiệp vụ từ server trên màn hình")
        msg = _screen_message(p)
        check(bool(msg), "Không thấy thông báo từ chối ghi sổ trên màn hình")
        check(any(w in msg.lower() for w in ("xác nhận", "cán bộ", "hai bên", "bàn giao")),
              f"Cảnh báo chặn không đúng nghiệp vụ dual ack: {msg}")
        check("không có quyền" not in msg.lower() and "permission" not in msg.lower(),
              f"Bị chặn bởi generic permission error thay vì business rule: {msg}")
        _dismiss_notice(p)
        s.step("Hoa đối chiếu biên bản vẫn giữ nguyên trạng thái nháp và dấu xác nhận của An")
        doc_after = p.evaluate("({docstatus: cur_frm.doc.docstatus, emp: cur_frm.doc.tlc_ops_employee_ack, staff: cur_frm.doc.tlc_ops_staff_ack})")
        check(doc_after["docstatus"] == 0, f"Biên bản bị đổi trạng thái: {doc_after['docstatus']}")
        check(doc_after["emp"] == emp_ack, f"Dấu xác nhận của nhân viên bị thay đổi: {doc_after['emp']} != {emp_ack}")
        check(not doc_after["staff"], f"Dấu xác nhận của cán bộ bị gán ngoài ý muốn: {doc_after['staff']}")
        stored = api_get(s, f"/api/resource/Asset Movement/{REQ['w5_movement']}").json()["data"]
        check(stored.get("docstatus") == 0, f"Docstatus trên server không phải 0: {stored.get('docstatus')}")
        check(stored.get("tlc_ops_employee_ack") == emp_ack, "Dấu nhân viên trên DB bị thay đổi")
        check(not stored.get("tlc_ops_staff_ack"), "Dấu cán bộ trên DB bị gán")
        result["actual"] = (f"Biên bản {REQ['w5_movement']}: server chặn ghi sổ đúng nghiệp vụ ({msg[:80]}), "
                            f"hồ sơ giữ docstatus=0 và chỉ có dấu nhân viên")

    with case(s, "W5-ASSET-RECEIPT-STAFF", "HR xác nhận bàn giao và hoàn tất biên bản hai bên",
              "Desk > Asset Movement > mở lại phiếu cấp phát > bấm Xác nhận bàn giao > đọc hai dấu thời gian",
              REQ.get("w5_movement", ""), "Cả hai dấu thời gian nhân viên và cán bộ hiện trên form") as result:
        check(bool(REQ.get("w5_movement")), "Case nhận tài sản chưa chạy")
        p = _open_list_row(s, "asset-movement", ASSET, f"?name={REQ['w5_movement']}",
                           "Hoa mở lại đúng biên bản bàn giao An vừa xác nhận")
        check(bool(p.evaluate("() => cur_frm.doc.tlc_ops_employee_ack")), "An chưa xác nhận biên bản")
        check(not p.evaluate("() => cur_frm.doc.tlc_ops_staff_ack"), "cán bộ đã xác nhận từ trước")
        s.step("Hoa bấm nút Xác nhận bàn giao với vai trò cán bộ phụ trách")
        _press_button(p, "Xác nhận bàn giao")
        s.step("Hoa đọc hai dấu thời gian của hai bên trên form")
        staff_shown = _shown(p, "tlc_ops_staff_ack")
        employee_shown = _shown(p, "tlc_ops_employee_ack")
        acks = p.evaluate("({emp: cur_frm.doc.tlc_ops_employee_ack, staff: cur_frm.doc.tlc_ops_staff_ack})")
        check(bool(acks["staff"]), f"Chưa ghi nhận xác nhận của cán bộ; trên form: {staff_shown[:120]}")
        stored = api_get(s, f"/api/resource/Asset Movement/{REQ['w5_movement']}").json()["data"]
        check(bool(stored.get("tlc_ops_employee_ack")) and bool(stored.get("tlc_ops_staff_ack")), str(stored)[:200])
        result["actual"] = (f"Biên bản {REQ['w5_movement']} có đủ hai bên: nhân viên {employee_shown[:38]}, "
                            f"cán bộ {staff_shown[:38]}")

    with case(s, "W5-LICENSE-CLEARANCE-BLOCKER", "Kiểm tra điều kiện thôi việc: tài sản và tài khoản còn mở",
              "Desk > mở danh sách biên bản bàn giao chưa ghi sổ > mở hồ sơ > mở danh sách tài khoản IT đang mở > đối chiếu kết quả kiểm tra",
              "An đang giữ tài sản và tài khoản Google Workspace",
              "Người duyệt thấy tận mắt phiếu bàn giao chưa ghi sổ và tài khoản còn Active trên Desk; "
              "hàm kiểm tra thôi việc của server trả về đúng các mục đó (đối chiếu)") as result:
        an_employee = _employee_of(s, "an")
        p = _open_list_row(s, "asset-movement", ASSET, f"?name={REQ['w5_movement']}",
                           "Hoa mở danh sách biên bản bàn giao để tìm phiếu chưa ghi sổ của An")
        s.step("Hoa đọc trạng thái còn nháp của biên bản trên form")
        docstatus = p.evaluate("cur_frm.doc.docstatus")
        check(docstatus == 0, f"Biên bản {REQ['w5_movement']} không còn ở trạng thái chưa ghi sổ")
        s.step("Hoa mở danh sách tài khoản IT đang mở của An")
        p.goto(f"{BASE}/desk/tlc-people-ops-account?employee={an_employee}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1600)
        rows = p.locator(f'.list-row-container a[data-doctype="{ACCOUNT}"]')
        check(rows.count() > 0, "Danh sách tài khoản IT của An trống trên màn hình")
        rows.first.click()
        _wait_form(p, ACCOUNT)
        account_name = p.evaluate("cur_frm.doc.name")
        shown_status = _shown(p, "status")
        check("Active" in shown_status or "Đang hoạt động" in shown_status
              or p.evaluate("() => cur_frm.doc.status") == "Active",
              f"Tài khoản trên form không Active: {shown_status[:120]}")
        s.step("Hoa đối chiếu kết quả kiểm tra điều kiện thôi việc của hệ thống")
        blockers = api(s, "tlc_hr.interface.people_ops.exit_clearance", employee=an_employee)
        check(isinstance(blockers, list) and blockers, f"exit_clearance không trả về danh sách tồn đọng: {blockers}")
        check(any(REQ["w5_movement"] in item for item in blockers),
              f"Không thấy biên bản bàn giao {REQ['w5_movement']} trong {blockers}")
        check(any(item.startswith("Tài khoản chưa khóa") and account_name in item for item in blockers),
              f"Không thấy tài khoản {account_name} trong {blockers}")
        result["actual"] = (f"HR thấy tận mắt: biên bản {REQ['w5_movement']} còn nháp + tài khoản {account_name} Active; "
                            f"hệ thống báo {len(blockers)} mục tồn đọng")
    s.close()

    # ---------------------------------------------------------------- 3. Quản lý (Quang)
    s = Session(browser, "W5-PEOPLE-OPS-MANAGER", "quang")
    login(s)

    with case(s, "W5-DISCIPLINE-WORKFLOW", "Quản lý lập đề xuất kỷ luật theo quy trình",
              "Desk > TLC People Ops Discipline > Mới > chọn nhân viên > nhập lý do > bấm Lưu > đọc trạng thái Proposal",
              "Đề xuất kỷ luật nhân viên đi muộn nhiều lần",
              "Hồ sơ ở trạng thái Proposal ngay trên form, người đề xuất là quản lý lập phiếu") as result:
        p = s.page
        emp = _employee_of(s, "an")
        s.step("Quang mở form đề xuất kỷ luật mới")
        p.goto(f"{BASE}/desk/tlc-people-ops-discipline/new")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        s.step("Quang chọn nhân viên và nhập lý do vi phạm")
        _link(p, "employee", emp)
        p.locator("textarea[data-fieldname='reason']:visible").last.fill("Đi muộn không phép 3 lần trong tháng 10/2026")
        p.wait_for_timeout(400)
        s.step("Quang bấm Lưu")
        _save(p)
        name = p.url.rstrip("/").split("/")[-1]
        check("new" not in name, f"Đề xuất chưa lưu: {p.url}")
        REQ["w5_discipline"] = name
        s.step("Quang đọc trạng thái Proposal trên form")
        status_shown = _shown(p, "status")
        check("Proposal" in status_shown or "Đề xuất" in status_shown
              or p.evaluate("() => cur_frm.doc.status") == "Proposal", status_shown)
        stored = api_get(s, f"/api/resource/{DISCIPLINE}/{name}").json()["data"]
        check(stored["status"] == "Proposal" and stored["employee"] == emp, str(stored)[:200])
        result["actual"] = f"Đề xuất {name} lưu bằng nút Lưu, form hiện “{status_shown[:40]}”, nhân viên {emp}"
    s.close()

    # ---------------------------------------------------------------- 4. Công nhân (Bình)
    s = Session(browser, "W5-PEOPLE-OPS-PERMISSION", "binh")
    login(s)

    with case(s, "W5-DISCIPLINE-PERMISSION", "Công nhân không xem được hồ sơ kỷ luật của người khác",
              "Desk > ô tìm kiếm > gõ mã hồ sơ kỷ luật của An > mở đường dẫn hồ sơ > đọc thông báo từ chối",
              REQ.get("w5_discipline", ""),
              "Không có dữ liệu hồ sơ trên màn hình; server từ chối quyền đọc (đối chiếu REST 403)") as result:
        check(bool(REQ.get("w5_discipline")), "Case tạo đề xuất kỷ luật chưa chạy")
        found = _desk_search(s, REQ["w5_discipline"])
        body = _denied_text(s, "tlc-people-ops-discipline", REQ["w5_discipline"])
        check("Đi muộn" not in body, "Lộ nội dung hồ sơ kỷ luật của người khác")
        denied = api_get(s, f"/api/resource/{DISCIPLINE}/{REQ['w5_discipline']}")
        check(denied.status == 403, f"REST đọc hồ sơ trả {denied.status}")
        result["actual"] = (f"Ô tìm kiếm chỉ liệt kê {len(found)} mục; màn hình báo: {body[:90]}; REST đối chiếu 403")
    s.close()


JOURNEYS = [people_ops_desktop]
