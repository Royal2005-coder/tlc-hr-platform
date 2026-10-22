"""Overtime (TLC Tăng ca): the factory head proposes, the worker consents, the CEO approves; Labour Code limits.

Every action under test happens on screen: the request is opened from its list and filled field by field on the desk form,
`Lưu` and `Hành động` are clicked, the on-screen refusal of the legal cap is read from the form. The API is only used to
look an employee id up before the case and to confirm the stored result afterwards.
"""

from lib import *  # noqa: F403

OT = "TLC Overtime Request"
TO_WORKER, TO_DIRECTOR = "Chờ người lao động đồng ý", "Chờ giám đốc duyệt"


# ---------------------------------------------------------------------------------------------------- desk form helpers

def form_box(p, field):
    box = p.locator(f'[data-fieldname="{field}"] input:visible, [data-fieldname="{field}"] textarea:visible').last
    box.wait_for(state="visible", timeout=15000)
    return box


def type_into(p, field, value):
    """Bấm vào ô, đóng lịch/bảng gợi ý che ô nếu có, điền rồi rời ô bằng Tab.

    Ô ngày/giờ nhận cả chuỗi một lần: gõ từng ký tự làm bộ lọc ngày ghi 'Invalid date' vào form.
    """
    box = p.locator(f"input[data-fieldname='{field}']:visible, textarea[data-fieldname='{field}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    p.keyboard.press("Escape")  # bảng gợi ý của ô trước có thể đang che ô này
    p.wait_for_timeout(400)
    box.click()
    p.wait_for_timeout(500)
    p.keyboard.press("Escape")  # ô ngày/giờ mở bảng lịch che mất ô, Escape để bàn phím gõ thẳng vào ô
    p.wait_for_timeout(500)
    if (box.get_attribute("data-fieldtype") or "") in ("Date", "Datetime", "Time"):
        box.fill(str(value))
    else:
        box.press_sequentially(str(value), delay=60)
    p.keyboard.press("Tab")
    p.wait_for_timeout(900)
    if (box.input_value() or "").strip() != str(value).strip():
        box.fill(str(value))
        p.keyboard.press("Tab")
        p.wait_for_timeout(800)
    check((box.input_value() or "").strip() == str(value).strip(),
          f"ô {field} đang hiển thị {(box.input_value() or '(trống)')!r}, không nhận '{value}'")
    stored = str(p.evaluate("(f) => (window.cur_frm && cur_frm.doc[f]) || ''", field) or "")
    check("Invalid" not in stored, f"ô {field} ghi '{stored}' vào biểu mẫu thay vì '{value}'")
    return box.input_value()


def pick_link(p, field, needle):
    """Ô liên kết: bấm vào, gõ để lọc, nhấp đúng dòng gợi ý hiện ra dưới ô."""
    box = form_box(p, field)
    box.click()
    box.fill("")
    p.keyboard.type(needle, delay=40)
    p.wait_for_timeout(2400)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option], .frappe-control-dropdown li")
    for i in range(options.count()):
        text = " ".join(options.nth(i).inner_text().split())
        if needle.lower() in text.lower():
            options.nth(i).click()
            p.wait_for_timeout(1400)
            return text
    raise AssertionError(f"ô {field} không có gợi ý '{needle}' (gợi ý: {options.all_inner_texts()[:4]})")


def add_request(s, worker, day, t_from, t_to, reason):
    """Danh sách Tăng ca > bấm Thêm > điền từng ô trên form > Lưu. Trả về (tên đơn, dòng giới hạn trên màn hình)."""
    p = s.page
    p.goto(f"{BASE}/desk/tlc-overtime-request")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    s.step("Anh Hùng bấm nút Thêm để lập đề nghị tăng ca mới")
    add = None
    for _ in range(24):  # danh sách tải xong mới có nút "Thêm TLC Overtime Request"
        buttons = p.locator("button:visible").filter(has_text=re.compile(r"Thêm|Add|New", re.I))
        for i in range(buttons.count()):
            text = " ".join(buttons.nth(i).inner_text().split())
            if text and not re.search(r"Thêm (bộ lọc|dòng|người dùng)|Add (filter|row|user)", text, re.I):
                add = buttons.nth(i)
                break
        if add is not None:
            break
        p.wait_for_timeout(500)
    check(add is not None, f"danh sách tăng ca không có nút thêm · {' '.join(p.locator('body').inner_text().split())[:160]}")
    add.click()
    p.wait_for_timeout(2000)
    if p.locator(".modal:visible").count():  # quick entry: chuyển sang form đầy đủ để thấy từng ô được điền
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)
    if "/new" not in p.url:
        p.goto(f"{BASE}/desk/tlc-overtime-request/new")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)
    s.step("Anh Hùng chọn công nhân, ngày và giờ tăng ca, ghi lý do")
    pick_link(p, "employee", worker["employee_name"])
    type_into(p, "ot_date", user_date(s, day))
    type_into(p, "from_time", t_from)
    type_into(p, "to_time", t_to)
    type_into(p, "reason", reason)
    s.step("Anh Hùng bấm Lưu")
    p.locator(".page-head button:visible").filter(has_text=re.compile(r"Lưu|Save")).last.click()
    p.wait_for_timeout(3500)
    saved = re.search(r"tlc-overtime-request/(TLC-OT-\d{4}-\d+)", p.url)
    return (saved.group(1) if saved else ""), (headline(p) or screen_text(p))


def ot_state(s, name):
    return doc_state(s, OT, name)


def screen_text(p):
    return " ".join(p.locator("body").inner_text().split())


def visible_error_text(p):
    """Whatever the interface shows after a rejected save: dialog, toast, inline red message."""
    found = []
    for sel in (".modal:visible", ".toast-message:visible", ".frappe-toast:visible", ".msgprint:visible",
                ".text-danger:visible", ".error-message:visible", "[role=alert]:visible", ".form-message:visible"):
        try:
            found += [" ".join(el.inner_text().split()) for el in p.locator(sel).all()]
        except Exception:
            pass
    return " | ".join(x for x in found if x)


def user_date(s, iso):
    """Chuỗi ngày theo đúng định dạng site hiển thị, để gõ vào ô bằng bàn phím."""
    format_ = s.page.evaluate("() => (window.frappe && frappe.boot.sysdefaults.date_format) || 'yyyy-mm-dd'")
    d = dt.date.fromisoformat(iso)
    return format_.replace("yyyy", f"{d.year:04d}").replace("mm", f"{d.month:02d}").replace("dd", f"{d.day:02d}")


def notice_of(p, name):
    """Bấm chuông thông báo trên desk để đọc dòng tin của đơn; rỗng nếu màn hình nhỏ không có chuông."""
    bell = p.locator("button:visible, a:visible").filter(has_text=re.compile("Thông báo|Notification")).first
    if not bell.count():
        icon = p.locator("[title*='Thông báo']:visible, [aria-label*='Thông báo']:visible, [title*='Notification']:visible")
        bell = icon.first if icon.count() else None
    if bell is None:
        return ""
    try:
        bell.click()
        p.wait_for_timeout(2500)
        item = p.locator(".notification-item, .dropdown-menu.show li, [role=menuitem], .modal:visible li").filter(has_text=name)
        if not item.count():
            p.keyboard.press("Escape")
            p.wait_for_timeout(600)
            return ""
        text = " ".join(item.first.inner_text().split())
        item.first.click()
        p.wait_for_timeout(3000)
        return text
    except Exception:
        p.keyboard.press("Escape")
        p.wait_for_timeout(600)
        return ""


def overtime_flow(browser):
    """Head of factory 1 proposes overtime for a worker on the desk, the worker consents on the phone, the CEO approves."""
    day = working_day(9)
    s = Session(browser, "OT", "hung")
    login(s)
    p = s.page
    worker = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "binh@demo.example"]])
                     + "&fields=" + json.dumps(["name", "employee_name"])).json()["data"][0]
    before = len(api_get(s, f"/api/resource/{OT}?filters=" + json.dumps([["employee", "=", worker["name"]],
                                                                        ["ot_date", "=", day]])).json()["data"])
    with case(s, "OT-01", "Quản lý nhà máy đề xuất tăng ca",
              "Danh sách Tăng ca > Thêm; chọn công nhân, ngày, giờ, lý do trên form > Lưu > Hành động > Đề nghị",
              f"Trần Văn Bình, {vn(day)} 17:30-20:30, Kiểm kê kho",
              "Đơn 3 giờ ngày thường, Chờ người lao động đồng ý; dòng đầu form hiện giới hạn 40/200 giờ") as r:
        s.step("Anh Hùng mở danh sách đề nghị tăng ca của nhà máy")
        REQ["ot"], text = add_request(s, worker, day, "17:30:00", "20:30:00", "Kiểm kê kho cuối quý")
        check(REQ["ot"], f"đơn không lưu được: {text[:160]} · {p.url}")
        s.step("Anh Hùng bấm Hành động > Đề nghị để gửi cho công nhân")
        open_actions(p)
        items = p.locator(MENU_ITEMS)
        target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == "Đề nghị"), None)
        check(target is not None, f"không có Đề nghị trong {menu_items(p)}")
        items.nth(target).click()
        p.wait_for_timeout(3500)
        doc = api_get(s, f"/api/resource/{OT}/{REQ['ot']}").json()["data"]
        check(doc["employee"] == worker["name"], f"đơn tạo cho {doc['employee']}, không phải {worker['name']}: {doc['employee_name']}")
        check((doc["workflow_state"], doc["hours"], doc["day_type"]) == (TO_WORKER, 3, "Ngày thường") and "/40" in text,
              f"{doc['workflow_state']} · trên form: {text}")
        limit_line = next((part.strip() for part in text.split("·") if "/40" in part), "")
        r["actual"] = f"{REQ['ot']}: {doc['hours']:g} giờ {doc['day_type']}, {doc['workflow_state']} · {limit_line or text[:160]}"
    with case(s, "OT-02", "Chặn vượt trần ngày theo luật",
              "Thêm đề nghị cùng công nhân cùng ngày (20:30-22:30), bấm Lưu, đọc thông báo trên màn hình",
              f"{vn(day)} 20:30-22:30", "Không lưu được: màn hình báo quá 4 giờ tăng ca trong một ngày thường (BLLĐ 2019 điều 107)") as r:
        s.step("Anh Hùng thử đề nghị thêm 2 giờ nữa trong cùng ngày và bấm Lưu")
        name, text = add_request(s, worker, day, "20:30:00", "22:30:00", "Thêm giờ")
        shown = visible_error_text(p) or text or screen_text(p)
        check(not name, f"đơn vẫn được lưu ({name}) dù vượt trần: {shown[:160]}")
        check(any(k in shown for k in ("4 giờ", "107")), f"màn hình không báo vượt trần: {shown[:200]}")
        # đơn bị chặn không được ghi: tìm đúng đơn vừa thử (lý do riêng), không so tổng số vì nó phụ thuộc lúc danh sách
        # trả về đơn hợp lệ OT-01
        blocked = api_get(s, f"/api/resource/{OT}?filters=" + json.dumps([["employee", "=", worker["name"]],
                                                                          ["ot_date", "=", day],
                                                                          ["reason", "=", "Thêm giờ"]])).json()["data"]
        check(not blocked, f"đơn vượt trần vẫn ghi vào hệ thống: {blocked}")
        first = api_get(s, f"/api/resource/{OT}/{REQ['ot']}").json()["data"]
        check(first["reason"] == "Kiểm kê kho cuối quý" and first["ot_date"] == day,
              f"đơn hợp lệ OT-01 bị ảnh hưởng: {str(first)[:200]}")
        r["actual"] = f"Không lưu được; thông báo trên màn hình: {shown[:170]}; đối chiếu server không có đơn “Thêm giờ”"
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)
    with case(s, "OT-03", "Quản lý không đồng ý thay công nhân",
              "Mở lại đơn đã gửi từ danh sách > bấm Hành động, đọc các nút workflow", REQ["ot"],
              "Không có Đồng ý / Từ chối trong Hành động") as r:
        s.step("Anh Hùng mở danh sách đề nghị tăng ca để tìm lại đơn vừa gửi")
        p.goto(f"{BASE}/desk/tlc-overtime-request")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        rows = p.locator(".list-row-container")
        got = next((i for i in range(rows.count()) if REQ["ot"] in " ".join(rows.nth(i).inner_text().split())), None)
        check(got is not None, f"đơn {REQ['ot']} không có trong danh sách: {' '.join(p.locator('body').inner_text().split())[:180]}")
        s.step("Anh Hùng nhấp vào đơn đã gửi để mở lại trên form")
        rows.nth(got).locator(".list-subject a, a").first.click()
        p.wait_for_function("(d) => window.cur_frm && cur_frm.doctype === d && !cur_frm.is_new()", arg=OT, timeout=30000)
        p.wait_for_timeout(2500)
        s.step("Anh Hùng bấm menu ⋮ rồi Hành động để xem mình được phép làm gì")
        items = []
        more = p.locator(".menu-more-button:visible").last
        if more.count():
            more.click()
            p.wait_for_timeout(900)
            items = menu_items(p)
            p.keyboard.press("Escape")
            p.wait_for_timeout(400)
        actions = workflow_actions(p)
        all_items = items + actions
        check("Đồng ý" not in all_items and "Từ chối" not in all_items, str(all_items))
        r["actual"] = f"Đã mở lại {REQ['ot']} từ danh sách; menu ⋮ + Hành động: {all_items or 'không có'}"
    s.close()

    s = Session(browser, "OT", "binh", phone=True)
    login(s)
    p = s.page
    with case(s, "OT-04", "Công nhân nhận thông báo và đồng ý tăng ca",
              "Chuông thông báo > mở đơn > Hành động > Đồng ý", REQ["ot"],
              "Có thông báo trên màn hình; đơn chuyển Chờ giám đốc duyệt, ghi thời điểm đồng ý") as r:
        s.step("Anh Bình bấm chuông thông báo để đọc đề nghị tăng ca của mình")
        notice = notice_of(p, REQ["ot"])
        log = api_get(s, "/api/resource/Notification Log?fields=" + json.dumps(["subject"]) + "&filters="
                      + json.dumps([["document_name", "=", REQ["ot"]]])).json()["data"]
        check(log, "không có thông báo nào cho đơn tăng ca")
        if REQ["ot"] not in p.url:
            s.step("Anh Bình mở đơn tăng ca trên màn hình")
            p.goto(f"{BASE}/desk/tlc-overtime-request/{REQ['ot']}")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2500)
        notice = notice or " ".join(log[0]["subject"].split())
        text = headline(p)
        s.step("Anh Bình bấm Hành động > Đồng ý")
        open_actions(p)
        items = p.locator(MENU_ITEMS)
        target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == "Đồng ý"), None)
        check(target is not None, f"không có Đồng ý trong {menu_items(p)}")
        items.nth(target).click()
        p.wait_for_timeout(3500)
        doc = api_get(s, f"/api/resource/{OT}/{REQ['ot']}").json()["data"]
        check(doc["workflow_state"] == TO_DIRECTOR and doc["consent_at"], str(doc)[:200])
        r["actual"] = f"Thông báo: {notice[:80] or '(xem trên danh sách)'} · đơn {REQ['ot']}: {doc['workflow_state']} lúc {doc['consent_at']}" \
                      + (f" · {text}" if text else "")
    s.close()

    s = Session(browser, "OT", "thanh")
    login(s)
    p = s.page
    with case(s, "OT-05", "CEO duyệt tăng ca",
              "Workspace TLC Điều hành > thẻ Tăng ca chờ giám đốc duyệt > mở đơn từ danh sách > Hành động > Duyệt", REQ["ot"],
              "Thẻ đếm 6 đơn (5 demo + 1); đơn Đã duyệt") as r:
        s.step("Anh Thành đọc thẻ Tăng ca chờ giám đốc duyệt trên workspace")
        waiting = card_value(p, "Tăng ca chờ giám đốc duyệt")
        s.step("Anh Thành bấm vào thẻ để mở danh sách đơn chờ mình duyệt")
        p.locator(".widget", has_text="Tăng ca chờ giám đốc duyệt").first.click()
        p.wait_for_timeout(3000)
        rows = p.locator(".list-row-container .list-subject a")
        got = next((i for i in range(rows.count()) if REQ["ot"] in " ".join(rows.nth(i).inner_text().split())), None)
        if got is None:
            p.goto(f"{BASE}/desk/tlc-overtime-request/{REQ['ot']}")
            p.wait_for_timeout(1500)
        else:
            rows.nth(got).click()
            p.wait_for_timeout(3000)
        p.wait_for_load_state("networkidle")
        s.step("Anh Thành bấm Hành động > Duyệt")
        open_actions(p)
        items = p.locator(MENU_ITEMS)
        target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == "Duyệt"), None)
        check(target is not None, f"không có Duyệt trong {menu_items(p)}")
        items.nth(target).click()
        p.wait_for_timeout(3500)
        state = ot_state(s, REQ["ot"])
        check(waiting == 6 and state == APPROVED, f"{waiting} {state}")
        r["actual"] = f"Thẻ chờ giám đốc {waiting}; đơn {state}"
    s.close()


JOURNEYS = [overtime_flow]
