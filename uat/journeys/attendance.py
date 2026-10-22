"""Attendance: GPS check-in at the work site, corrections, and the monthly closing (TLC Chốt công) of the three factories and the
head office: HR sends, each factory head confirms only their factory, HR reconciles, the CEO signs and locks; after the lock a
direct change is refused and HR goes through a post-lock adjustment.

Every action under test is done on the screen the role really works on: the period is created by clicking `Thêm` and typing
into the form, the workflow moves happen through `Hành động`, and the lock is demonstrated by opening the attendance of the
locked month, trying to change it and reading the refusal the interface shows. The API only prepares data and re-reads the
stored result afterwards.
"""

from lib import *  # noqa: F403

KC, AR = "TLC Attendance Period", "Attendance Request"
SITES = {"Nhà máy 1": (10.850632, 106.772010), "Nhà máy 2": (10.980410, 106.651871), "Nhà máy 3": (10.957413, 106.842687)}
HOME = (10.762622, 106.660172)  # a worker's home in the city, kilometres away from every site
TO_HEAD, PERIOD_TO_HR, TO_CEO, LOCKED = "Chờ quản lý xác nhận", "Chờ nhân sự đối soát", "Chờ giám đốc ký", "Đã khoá"
SCOPES = ["Nhà máy 1", "Nhà máy 2", "Nhà máy 3", "Hội sở"]
HEADS = {"Nhà máy 1": "hung", "Nhà máy 2": "nm2", "Nhà máy 3": "nm3"}


# ---------------------------------------------------------------------------------------------------- desk form helpers

def user_date(s, iso):
    """Ngày viết theo đúng định dạng site đang hiển thị, để gõ vào ô bằng bàn phím."""
    format_ = s.page.evaluate("() => (window.frappe && frappe.boot.sysdefaults.date_format) || 'yyyy-mm-dd'")
    d = dt.date.fromisoformat(iso)
    return format_.replace("yyyy", f"{d.year:04d}").replace("mm", f"{d.month:02d}").replace("dd", f"{d.day:02d}")


def field_box(p, field):
    box = p.locator(f"input[data-fieldname='{field}']:visible, textarea[data-fieldname='{field}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    return box


def type_into(p, field, value):
    """Bấm vào ô, đóng bảng lịch đang che ô, điền rồi rời ô bằng Tab.

    Ô ngày nhận cả chuỗi một lần (bàn phím gõ từng ký tự làm bộ lọc ngày hiểu sai và ghi 'Invalid date'
    vào form dù ô vẫn hiện đúng chữ); ô chữ thường vẫn được gõ từng ký tự như người dùng.
    """
    box = field_box(p, field)
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    box.click()
    p.wait_for_timeout(500)
    p.keyboard.press("Escape")
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
          f"ô {field} đang hiển thị '{box.input_value() or '(trống)'}', không nhận '{value}'")
    stored = str(p.evaluate("(f) => (window.cur_frm && cur_frm.doc[f]) || ''", field) or "")
    check("Invalid" not in stored, f"ô {field} ghi '{stored}' vào biểu mẫu thay vì '{value}'")


def pick_link(p, field, needle):
    """Ô liên kết: bấm vào, gõ để lọc, nhấp đúng dòng gợi ý hiện ra dưới ô."""
    box = field_box(p, field)
    box.click()
    box.fill("")
    p.keyboard.type(needle, delay=45)
    p.wait_for_timeout(2400)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option], .frappe-control-dropdown li")
    for i in range(options.count()):
        text = " ".join(options.nth(i).inner_text().split())
        if needle.lower() in text.lower():
            options.nth(i).click()
            p.wait_for_timeout(1300)
            return text
    raise AssertionError(f"ô {field} không có gợi ý '{needle}' (gợi ý: {options.all_inner_texts()[:4]})")


def choose_option(s, field, label):
    """Chọn một phương án trong ô Select bằng chính chiếc select trên màn hình.

    `label` có thể ghi "nhãn tiếng Việt|English value" cho ô mà giao diện có thể dịch hoặc không.
    """
    p = s.page
    select = p.locator(f"select[data-fieldname='{field}']:visible").last
    select.wait_for(state="visible", timeout=15000)
    select.click()
    for candidate in [label] + [part.strip() for part in str(label).split("|") if part.strip()]:
        try:
            select.select_option(label=candidate)
            p.wait_for_timeout(700)
            return
        except Exception:
            try:
                select.select_option(value=candidate)
                p.wait_for_timeout(700)
                return
            except Exception:
                continue
    raise AssertionError(f"ô {field} không có phương án '{label}': {select.locator('option').all_inner_texts()}")


def press_save(s, note="Bấm Lưu"):
    """Nhấp nút Lưu của biểu mẫu (không dùng phím tắt), trả về dòng chữ màn hình đang hiện."""
    s.step(note)
    p = s.page
    p.locator(".page-head button:visible").filter(has_text=re.compile(r"Lưu|Save")).last.click()
    p.wait_for_timeout(4000)
    return visible_message_text(p)


def visible_message_text(p):
    """Dòng chữ từ chối / cảnh báo người dùng vừa nhìn thấy: hộp thoại, toast, dòng đỏ trên form."""
    found = []
    for sel in (".modal:visible", ".toast-message:visible", ".msgprint:visible", ".text-danger:visible",
                "[role=alert]:visible", ".form-message:visible"):
        try:
            found += [" ".join(el.inner_text().split()) for el in p.locator(sel).all()]
        except Exception:
            pass
    return " | ".join(x for x in found if x)


def dismiss_confirm(p):
    """Xác nhận hộp thoại 'hủy tài liệu' bằng đúng nút đồng ý trên màn hình (không bấm Hủy)."""
    if not p.locator(".modal:visible").count():
        return False
    dialog = p.locator(".modal:visible").last
    for label in ("Có", "Yes", "Đồng ý", "Xác nhận", "OK", "Hủy bỏ", "Hủy"):
        button = dialog.get_by_role("button", name=re.compile(rf"^{label}$"))
        if button.count() and button.last.is_visible():
            button.last.click()
            p.wait_for_timeout(1800)
            return True
    fallback = dialog.locator(".btn-modal-primary:visible")
    if fallback.count():
        fallback.first.click()
        p.wait_for_timeout(1800)
    return True


def dismiss_dialog(p):
    """Đóng hộp thoại thông báo để màn hình sẵn sàng cho bước kế tiếp."""
    if p.locator(".modal:visible").count():
        dialog = p.locator(".modal:visible").last
        closer = dialog.locator("button:visible").filter(has_text=re.compile(r"^(Đóng|Close|OK)$"))
        if closer.count():
            closer.first.click()
        else:
            p.keyboard.press("Escape")
        p.wait_for_timeout(1000)


def press_cancel(p):
    """Lệnh Hủy của bản ghi đã ghi sổ: nằm trong menu ⋮, một số bản desk còn để nút Hủy ở đầu trang."""
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    more = p.locator(".menu-more-button:visible, .page-actions button[data-action='toggle-actions']:visible")
    if more.count():
        more.last.click()
        p.wait_for_timeout(900)
        items = p.locator(MENU_ITEMS)
        target = next((i for i in range(items.count())
                       if re.match(r"^\s*(Hủy|Cancel)\s*$", " ".join(items.nth(i).inner_text().split()))), None)
        if target is not None:
            items.nth(target).click()
            p.wait_for_timeout(1500)
            return True
        p.keyboard.press("Escape")
        p.wait_for_timeout(500)
    cancel = p.locator("button:visible").filter(has_text=re.compile(r"^Hủy\b"))
    if cancel.count():
        cancel.first.click()
        p.wait_for_timeout(1500)
        return True
    return False


def add_button(p, slug):
    """Nút "Thêm <DocType>" của danh sách, chờ danh sách tải xong; bỏ qua nút thêm bộ lọc/dòng của lưới."""
    for _ in range(24):
        buttons = p.locator("button:visible").filter(has_text=re.compile(r"Thêm|Add|New", re.I))
        for i in range(buttons.count()):
            text = " ".join(buttons.nth(i).inner_text().split())
            if not text or re.search(r"Thêm (bộ lọc|dòng|người dùng)|Add (filter|row|user)", text, re.I):
                continue
            return buttons.nth(i)
        p.wait_for_timeout(500)
    raise AssertionError(f"danh sách {slug} không có nút thêm: {' '.join(p.locator('body').inner_text().split())[:150]}")


def open_new_form(s, slug, note):
    """Mở danh sách, bấm nút Thêm, làm trên biểu mẫu đầy đủ (không tạo bản ghi bằng script)."""
    p = s.page
    goto_list(s, slug)
    s.step(note)
    add_button(p, slug).click()
    p.wait_for_timeout(2200)
    if p.locator(".modal:visible").count():  # quick entry: chuyển sang form đầy đủ để nhìn thấy từng ô được điền
        p.keyboard.press("Escape")
        p.wait_for_timeout(800)
    if "/new" not in p.url:
        p.goto(f"{BASE}/desk/{slug}/new")
        leave_unsaved(p)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)


def goto_list(s, slug):
    """Mở danh sách; nếu desk hỏi 'rời khỏi trang đang sửa' thì trả lời đúng nút trên hộp thoại."""
    p = s.page
    p.keyboard.press("Escape")
    p.goto(f"{BASE}/desk/{slug}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    leave_unsaved(p)
    p.wait_for_load_state("networkidle")


def leave_unsaved(p):
    if not p.locator(".modal:visible").count():
        return
    dialog = p.locator(".modal:visible").last
    away = dialog.locator("button:visible").filter(has_text=re.compile(r"Rời|Leave|Discard|Bỏ|OK|Đóng", re.I))
    if away.count():
        away.first.click()
        p.wait_for_timeout(1500)


def open_from_card(s, card, needle, slug):
    """Bấm thẻ trên workspace để mở danh sách, rồi nhấp đúng dòng cần làm."""
    p = s.page
    s.step(f"Bấm thẻ '{card}' để mở danh sách")
    widget = p.locator(".widget", has_text=card).first
    widget.wait_for(state="visible", timeout=20000)
    widget.click()
    p.wait_for_timeout(3200)
    if not p.locator(".list-row-container").count():  # thẻ mở bằng tab khác: quay lại danh sách trên tab đang ghi hình
        p.goto(f"{BASE}/desk/{slug}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
    rows = p.locator(".list-row-container")
    seen = [row_text_of(rows, i) for i in range(rows.count())]
    target = next((i for i, text in enumerate(seen) if needle in text), None)
    check(target is not None, f"không thấy dòng '{needle}' trong danh sách mở ra: {seen[:6]}")
    link = rows.nth(target).locator(".list-subject a, a").first
    link.click()
    p.wait_for_function("() => window.cur_frm && !cur_frm.is_new()", timeout=25000)
    p.wait_for_timeout(2200)


def row_text_of(rows, i):
    try:
        return " ".join(rows.nth(i).inner_text().split())
    except Exception:
        return ""


def last_month():
    first = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    return first.strftime("%Y-%m")


def past_working_day(n):
    day, found = dt.date.today(), 0
    while found < n:
        day -= dt.timedelta(days=1)
        if day.weekday() < 5:
            found += 1
    return day.isoformat()


def checkin_worker():
    """A worker whose shift is open now: the peak shift of factory 3 (06:00-23:00 window), else the night shift of factory 1."""
    return ("f3w01", "Nhà máy 3") if 6 <= dt.datetime.now().hour < 23 else ("binh", "Nhà máy 1")


def checkin_count(s):
    return len(api_get(s, "/api/resource/Employee Checkin?limit_page_length=1000").json().get("data", []))


def press_checkin(p):
    p.goto(f"{BASE}/hrms/home")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    p.locator("button:visible", has_text=re.compile("Vào ca|Ra ca")).first.click()
    p.wait_for_timeout(2500)  # the panel reads the position
    p.locator("button:visible", has_text=re.compile("Xác nhận|Confirm")).last.click()
    p.wait_for_timeout(3000)
    return p.locator("body").inner_text()


def gps_checkin(browser):
    account, site = checkin_worker()
    s = Session(browser, "CC", account, geolocation=HOME)
    login(s)
    p = s.page
    with case(s, "AT-01", "Chấm công ngoài phạm vi nhà máy bị từ chối", "App > Vào ca khi đang ở nhà (cách nhà máy vài km) > Xác nhận",
              f"{account}@demo.example, vị trí {HOME}", f"Không ghi nhận; báo phải ở trong bán kính của {site}") as r:
        before = checkin_count(s)
        s.step(f"Bạn bấm Vào ca khi đang ở nhà, cách {site} vài km")
        text = press_checkin(p)
        after = checkin_count(s)
        check(after == before, f"{before} -> {after}: {text[-300:]}")
        r["actual"] = f"Không có lượt chấm công mới ({after}); thông báo lỗi trên app"
    s.context.set_geolocation({"latitude": SITES[site][0] + 0.0003, "longitude": SITES[site][1] - 0.0002})
    with case(s, "AT-02", "Chấm công GPS tại cổng nhà máy", "App > Vào ca tại nhà máy > Xác nhận", f"{account}@demo.example tại {site}",
              "Ghi nhận lượt chấm công với toạ độ, gắn ca đang mở") as r:
        before = checkin_count(s)
        s.step(f"Bạn di chuyển đến cổng {site} rồi bấm Vào ca > Xác nhận")
        press_checkin(p)
        logs = api_get(s, "/api/resource/Employee Checkin?fields=" + json.dumps(["name", "log_type", "time", "shift", "latitude"])
                       + "&order_by=creation%20desc&limit_page_length=1").json()["data"]
        check(checkin_count(s) == before + 1 and logs and logs[0]["shift"], str(logs))
        r["actual"] = f"{logs[0]['name']}: {logs[0]['log_type']} lúc {logs[0]['time']}, ca {logs[0]['shift']}, vĩ độ {logs[0]['latitude']:.5f}"
    s.close()


WORKERS = (["binh", "tai"] + [f"nightw{i:02d}" for i in range(1, 9)] + [f"dayw{i:02d}" for i in range(1, 5)]
           + [f"f2w{i:02d}" for i in range(1, 7)] + [f"f3w{i:02d}" for i in range(1, 7)])


def forgotten_day(browser):
    """A factory worker marked absent on a past day of this month (the check-out never reached the system) and that day.
    Looked up as HR through the API, outside the recording."""
    context = browser.new_context()
    context.request.post(f"{BASE}/api/method/login", data={"usr": "lan@demo.example", "pwd": PASSWORD})
    first = dt.date.today().replace(day=1).isoformat()
    users = [f"{w}@demo.example" for w in WORKERS]
    people = context.request.get(f"{BASE}/api/resource/Employee?limit_page_length=100&fields=" + json.dumps(["name", "user_id"])
                                 + "&filters=" + json.dumps([["user_id", "in", users]])).json()["data"]
    user_of = {e["name"]: e["user_id"] for e in people}
    absent = context.request.get(f"{BASE}/api/resource/Attendance?limit_page_length=100&order_by=attendance_date%20desc&fields="
                                 + json.dumps(["employee", "attendance_date"]) + "&filters="
                                 + json.dumps([["employee", "in", list(user_of)], ["status", "in", ["Absent", "Half Day"]],
                                               ["docstatus", "=", 1], ["attendance_date", ">=", first]])).json()["data"]
    context.close()
    check(absent, "không có công nhân nào vắng trong tháng để giải trình")
    return user_of[absent[0]["employee"]].split("@")[0], absent[0]["attendance_date"]


def correction(browser):
    account, day = forgotten_day(browser)
    s = Session(browser, "GT", account)
    login(s)
    p = s.page
    with case(s, "AT-03", "Công nhân giải trình quên chấm ra trên app", "App > Yêu cầu chấm công > ngày, loại Quên chấm ra, giải thích > Lưu > Gửi duyệt",
              f"{account}@demo.example, {vn(day)} (đang bị tính vắng), Quên chấm ra", "Đơn Chờ quản lý duyệt, người duyệt là trưởng nhà máy / tổ trưởng của người đó") as r:
        s.step("Bạn mở Yêu cầu chấm công trên app và điền ngày bị tính vắng")
        p.goto(f"{BASE}/hrms/attendance-requests/new")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        dates = p.locator("input[type=date]")
        dates.nth(0).fill(day)
        dates.nth(1).fill(day)
        p.get_by_text("Chọn Lý do").click()
        p.get_by_text(re.compile("Đang làm việc|On Duty", re.I)).last.click()
        p.get_by_text("Chọn Loại điều chỉnh").click()
        p.get_by_text("Quên chấm ra", exact=True).last.click()
        p.locator("textarea").first.fill("Hết ca quên bấm Ra ca, có tổ trưởng xác nhận")
        p.wait_for_timeout(1000)
        visible_button(p, "Lưu").click()
        p.wait_for_url(re.compile(r".*/attendance-requests/HR-ARQ-[\d-]+"), timeout=30000)
        REQ["ar"] = re.search(r"HR-ARQ-[\d-]+", p.url).group(0)
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        visible_button(p, "Hành động").click()
        p.wait_for_timeout(800)
        p.get_by_role("button", name="Gửi duyệt").last.click()
        p.wait_for_timeout(2500)
        doc = api_get(s, f"/api/resource/{AR}/{REQ['ar']}").json()["data"]
        check(doc["workflow_state"] == TO_MANAGER and doc["tlc_approver"], str(doc)[:200])
        REQ["ar_approver"] = doc["tlc_approver"].split("@")[0]
        r["actual"] = f"{REQ['ar']}: {doc['workflow_state']}, duyệt bởi {doc['tlc_approver']}"
    s.close()
    for account, case_id, title, target in ((REQ.get("ar_approver", "hung"), "AT-04", "Quản lý trực tiếp duyệt giải trình", TO_HR),
                                             ("lan", "AT-05", "HR duyệt giải trình, công được ghi", APPROVED)):
        s = Session(browser, "GT", account)
        login(s)
        with case(s, case_id, title, "Mở đơn > Hành động > Duyệt", REQ.get("ar", ""), target) as r:
            s.page.goto(f"{BASE}/desk/attendance-request/{REQ['ar']}")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            desk_action(s, REQ["ar"], "Duyệt", doctype=AR)
            state = doc_state(s, AR, REQ["ar"])
            check(state == target, state)
            r["actual"] = state
            if target == APPROVED:
                att = api_get(s, "/api/resource/Attendance?filters=" + json.dumps([["attendance_request", "=", REQ["ar"]]])
                              + "&fields=" + json.dumps(["name", "status"])).json()["data"]
                check(att and att[0]["status"] == "Present", str(att))
                r["actual"] = f"{state}; bảng công {att[0]['name']}: {att[0]['status']}"
        s.close()


def open_period(s, name):
    s.page.goto(f"{BASE}/desk/tlc-attendance-period/{name}")
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(2500)


def act_on_open_form(s, action, reason=None):
    """Bấm Hành động trên biểu mẫu đang mở rồi chọn đúng nút nghiệp vụ."""
    p = s.page
    s.step(f"Bấm Hành động rồi chọn '{action}'")
    open_actions(p)
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == action), None)
    check(target is not None, f"không có {action} trong {menu_items(p)}")
    items.nth(target).click()
    if reason:
        dialog = p.locator(".modal:visible").last
        expect(dialog).to_be_visible()
        dialog.locator("textarea").first.fill(reason)
        dialog.get_by_role("button", name=action).last.click()
    p.wait_for_timeout(3500)


def period_action(s, name, action, reason=None, card=None):
    if card:
        open_from_card(s, card, name, "tlc-attendance-period")
    else:
        open_period(s, name)
    act_on_open_form(s, action, reason)
    return doc_state(s, KC, name)


def period_closing(browser):
    month = last_month()
    REQ["kc"] = {}
    s = Session(browser, "KC", "lan")
    login(s)
    p = s.page
    with case(s, "PD-01", "HR lập kỳ công tháng trước cho 3 nhà máy và hội sở",
              "Chốt công > bấm Thêm > chọn phạm vi, gõ tháng > Lưu; đọc bảng tổng hợp trên form",
              f"Tháng {month}; Nhà máy 1, 2, 3, Hội sở", "4 kỳ công Nháp, có bảng công từng người, không còn việc chưa xử lý") as r:
        out = []
        for scope in SCOPES:
            open_new_form(s, "tlc-attendance-period", f"Chị Lan mở danh sách kỳ công và bấm Thêm cho {scope}")
            s.step(f"Chị Lan chọn phạm vi {scope} và gõ tháng {month}")
            choose_option(s, "scope", scope)
            type_into(p, "period_month", month)
            shown = press_save(s, "Chị Lan bấm Lưu để hệ thống tổng hợp công")
            check("new" not in p.url, f"kỳ công {scope} không lưu được: {shown[:180]}")
            REQ["kc"][scope] = re.search(r"TLC-KC-\d+", p.url).group(0)
            doc = api_get(s, f"/api/resource/{KC}/{REQ['kc'][scope]}").json()["data"]
            check(doc["employee_count"] > 0 and doc["open_count"] == 0, f"{scope}: {doc['employee_count']} người, {doc['open_count']} việc")
            out.append(f"{scope}: {doc['employee_count']} người, có mặt {doc['present_days']:g}, vắng {doc['absent_days']:g}, OT {doc['ot_hours']:g} giờ")
        r["actual"] = " | ".join(out) + " · " + headline(p)
    with case(s, "PD-02", "HR gửi trưởng nhà máy xác nhận, hội sở gửi thẳng đối soát",
              "Mở từng kỳ > Hành động > Gửi xác nhận (nhà máy) / Gửi đối soát (hội sở)",
              ", ".join(REQ["kc"].values()), "3 kỳ nhà máy Chờ quản lý xác nhận; kỳ hội sở Chờ nhân sự đối soát") as r:
        s.step("Chị Lan mở từng kỳ công vừa lập để gửi duyệt")
        states = {scope: period_action(s, REQ["kc"][scope], "Gửi đối soát" if scope == "Hội sở" else "Gửi xác nhận") for scope in SCOPES}
        check(states == {"Nhà máy 1": TO_HEAD, "Nhà máy 2": TO_HEAD, "Nhà máy 3": TO_HEAD, "Hội sở": PERIOD_TO_HR}, str(states))
        r["actual"] = "; ".join(f"{k}: {v}" for k, v in states.items())
    s.close()

    for scope, account in HEADS.items():
        s = Session(browser, "KC", account)
        login(s)
        p = s.page
        other = REQ["kc"]["Nhà máy 2" if scope == "Nhà máy 1" else "Nhà máy 1"]
        with case(s, f"PD-{3 + list(HEADS).index(scope):02d}", f"Trưởng {scope} xác nhận công của nhà máy mình",
                  "Workspace TLC Quản lý > thẻ Kỳ công chờ tôi xác nhận > mở kỳ > xem bảng công > Hành động > Xác nhận"
                  + (" (lần đầu Trả lại có lý do, HR làm mới rồi gửi lại)" if scope == "Nhà máy 3" else ""),
                  REQ["kc"][scope], "Thẻ đếm 1; kỳ nhà máy khác bị chặn 403; kỳ chuyển Chờ nhân sự đối soát") as r:
            s.step("Anh ấy đọc thẻ Kỳ công chờ tôi xác nhận trên workspace")
            waiting = card_value(p, "Kỳ công chờ tôi xác nhận")
            blocked = api_get(s, f"/api/resource/{KC}/{other}").status
            if scope == "Nhà máy 3":
                open_from_card(s, "Kỳ công chờ tôi xác nhận", REQ["kc"][scope], "tlc-attendance-period")
                act_on_open_form(s, "Trả lại", reason="Thiếu giờ tăng ca kiểm kê ngày 25, đề nghị HR kiểm tra")
                state = doc_state(s, KC, REQ["kc"][scope])
                check(state == DRAFT, state)
                hr = Session(browser, "KC", "lan")
                login(hr)
                open_period(hr, REQ["kc"][scope])
                hr.step("Chị Lan mở lại kỳ bị trả và bấm Làm mới tổng hợp")
                hr.page.get_by_role("button", name="Làm mới tổng hợp").click()
                hr.page.wait_for_timeout(3000)
                act_on_open_form(hr, "Gửi xác nhận")
                check(doc_state(hr, KC, REQ["kc"][scope]) == TO_HEAD, "gửi lại")
                hr.close()
                open_period(s, REQ["kc"][scope])
            else:
                open_from_card(s, "Kỳ công chờ tôi xác nhận", REQ["kc"][scope], "tlc-attendance-period")
            act_on_open_form(s, "Xác nhận")
            state = doc_state(s, KC, REQ["kc"][scope])
            check(waiting == 1 and blocked == 403 and state == PERIOD_TO_HR, f"thẻ {waiting}, khác {blocked}, {state}")
            r["actual"] = f"Thẻ chờ tôi {waiting}; kỳ nhà máy khác: {blocked}; {state}" + (" (sau 1 lần trả lại)" if scope == "Nhà máy 3" else "")
        s.close()

    s = Session(browser, "KC", "hoa")
    login(s)
    with case(s, "PD-06", "HR đối soát 4 kỳ công", "Workspace TLC Nhân sự > đọc thẻ Kỳ công chờ đối soát > bấm thẻ, mở từng kỳ > Hành động > Đối soát xong",
              ", ".join(REQ["kc"].values()), "Thẻ đếm 4; cả 4 Chờ giám đốc ký") as r:
        s.step("Chị Hòa đọc thẻ Kỳ công chờ đối soát trên workspace")
        waiting = card_value(s.page, "Kỳ công chờ đối soát")
        states = [period_action(s, REQ["kc"][scope], "Đối soát xong", card="Kỳ công chờ đối soát" if scope == SCOPES[0] else None)
                  for scope in SCOPES]
        check(waiting == 4 and states == [TO_CEO] * 4, f"{waiting} {states}")
        r["actual"] = f"Thẻ {waiting}; {', '.join(states)}"
    s.close()

    s = Session(browser, "KC", "thanh")
    login(s)
    with case(s, "PD-07", "CEO ký và khoá kỳ công", "Workspace TLC Điều hành > đọc thẻ Kỳ công chờ ký > bấm thẻ, mở từng kỳ > Hành động > Ký và khoá",
              ", ".join(REQ["kc"].values()), "Thẻ đếm 4; cả 4 Đã khoá, ghi người ký và thời điểm") as r:
        s.step("Anh Thành đọc thẻ Kỳ công chờ ký trên workspace")
        waiting = card_value(s.page, "Kỳ công chờ ký")
        states = [period_action(s, REQ["kc"][scope], "Ký và khoá", card="Kỳ công chờ ký" if scope == SCOPES[0] else None)
                  for scope in SCOPES]
        doc = api_get(s, f"/api/resource/{KC}/{REQ['kc']['Nhà máy 1']}").json()["data"]
        check(waiting == 4 and states == [LOCKED] * 4 and doc["locked_by"] == "thanh@demo.example", f"{waiting} {states}")
        r["actual"] = f"Thẻ {waiting}; {', '.join(states)}; khoá lúc {doc['locked_at']}"
    s.close()

    s = Session(browser, "KC", "lan")
    login(s)
    p = s.page
    found = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "binh@demo.example"]])
                    + "&fields=" + json.dumps(["name", "employee_name"])).json()["data"][0]
    worker, person = found["name"], found["employee_name"]
    absent = api_get(s, "/api/resource/Attendance?filters=" + json.dumps([["employee", "=", worker], ["status", "=", "Absent"],
                                                                          ["attendance_date", "like", f"{month}%"]])
                     + "&fields=" + json.dumps(["name", "attendance_date"])).json()["data"]
    day = absent[0]["attendance_date"] if absent else f"{month}-15"
    record = absent[0]["name"] if absent else ""
    open_requests = len(api_get(s, f"/api/resource/{AR}?limit_page_length=500&filters="
                                   + json.dumps([["employee", "=", worker], ["from_date", "=", day]])).json()["data"])
    with case(s, "PD-08", "Không sửa trực tiếp được công của kỳ đã khoá",
              "Mở bản ghi Chấm công ngày đã khoá > thử đổi trạng thái (form chỉ đọc) > bấm Hủy; sau đó thử lập giải trình thường "
              "cho cùng ngày trên form > Lưu; đọc thông báo từ chối trên màn hình",
              f"{person}, {vn(day)}, kỳ {REQ['kc']['Nhà máy 1']} đã khoá",
              "Mọi cách sửa trực tiếp đều bị màn hình từ chối: kỳ công đã khoá, HR phải lập 'Điều chỉnh sau chốt'") as r:
        refusals = []
        s.step("Chị Lan mở bảng công tháng đã khoá của Nhà máy 1")
        p.goto(f"{BASE}/desk/attendance")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        if record:
            s.step("Chị Lan mở đúng ngày công đã khoá của anh Bình")
            p.goto(f"{BASE}/desk/attendance/{record}")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2500)
            editable = p.locator("input[data-fieldname='status']:visible:enabled, select[data-fieldname='status']:visible:enabled")
            s.step("Chị Lan thử đổi trạng thái ngay trên biểu mẫu")
            status = p.locator(".frappe-control[data-fieldname='status']").first
            status.click(force=True)
            p.wait_for_timeout(1200)
            locked_form = editable.count() == 0 and not p.locator("button:visible").filter(has_text=re.compile(r"Lưu|Save")).count()
            refusals.append("biểu mẫu chỉ đọc, không có ô sửa được" if locked_form else "form vẫn cho sửa")
            s.step("Chị Lan bấm Hủy trong menu ⋮ để thử xóa bỏ ngày công đã khoá")
            check(press_cancel(p), f"biểu mẫu không có lệnh Hủy: {visible_message_text(p)[:120]}")
            dismiss_confirm(p)
            p.wait_for_timeout(3000)
            shown = visible_message_text(p)
            refusals.append(shown[:120])
            stored = api_get(s, f"/api/resource/Attendance/{record}").json()["data"]
            check(stored["docstatus"] == 1 and "khoá" in shown, f"màn hình: {shown[:160]}; bản ghi docstatus {stored['docstatus']}")
            dismiss_dialog(p)
        s.step("Chị Lan thử lập giải trình thường cho ngày đã khoá và bấm Lưu")
        open_new_form(s, "attendance-request", "Chị Lan mở danh sách giải trình công và bấm Thêm")
        pick_link(p, "employee", person)
        type_into(p, "from_date", user_date(s, day))
        type_into(p, "to_date", user_date(s, day))
        choose_option(s, "reason", "Đang làm việc|On Duty")
        choose_option(s, "tlc_correction_type", "Máy chấm công lỗi")
        type_into(p, "explanation", "Máy chấm công lỗi cả ca, đề nghị ghi lại công")
        shown = press_save(s, "Chị Lan bấm Lưu")
        after = len(api_get(s, f"/api/resource/{AR}?limit_page_length=500&filters="
                               + json.dumps([["employee", "=", worker], ["from_date", "=", day]])).json()["data"])
        check("/new" in p.url and after == open_requests, f"đơn vẫn được tạo: {p.url}; {open_requests} -> {after}")
        shown = visible_message_text(p)
        check("khoá" in shown, f"màn hình không nói vì sao bị chặn: {shown[:200]}")
        refusals.append(shown[:120])
        dismiss_dialog(p)
        r["actual"] = " · ".join(x for x in refusals if x)[:400]
    with case(s, "PD-09", "HR lập điều chỉnh sau chốt",
              "Giải trình công > Thêm: chọn công nhân, ngày, loại Điều chỉnh sau chốt, ghi lý do > Lưu > Hành động > Gửi duyệt",
              f"{person}, {vn(day)} (ngày vắng), đi giao hàng cho khách", "Chờ quản lý duyệt, người duyệt trưởng Nhà máy 1") as r:
        s.step("Chị Lan mở lại danh sách giải trình công để lập phiếu điều chỉnh sau chốt")
        open_new_form(s, "attendance-request", "Chị Lan bấm Thêm trong danh sách giải trình công")
        pick_link(p, "employee", person)
        type_into(p, "from_date", user_date(s, day))
        type_into(p, "to_date", user_date(s, day))
        choose_option(s, "reason", "Đang làm việc|On Duty")
        s.step("Chị Lan chọn loại 'Điều chỉnh sau chốt' và ghi lý do")
        choose_option(s, "tlc_correction_type", "Điều chỉnh sau chốt")
        type_into(p, "explanation", "Đi giao hàng cho khách theo lệnh của trưởng nhà máy, quên báo")
        shown = press_save(s, "Chị Lan bấm Lưu")
        check("new" not in p.url, f"điều chỉnh không lưu được: {shown[:180]}")
        REQ["adj"] = re.search(r"HR-ARQ-[\d-]+", p.url).group(0)
        p.wait_for_load_state("networkidle")
        act_on_open_form(s, "Gửi duyệt")
        p.wait_for_timeout(2000)
        doc = api_get(s, f"/api/resource/{AR}/{REQ['adj']}").json()["data"]
        check((doc["workflow_state"], doc["tlc_approver"]) == (TO_MANAGER, "hung@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['adj']}: {doc['workflow_state']}, duyệt bởi {doc['tlc_approver']}"
    s.close()
    for account, case_id, target in (("hung", "PD-10", TO_HR), ("hoa", "PD-11", APPROVED)):
        s = Session(browser, "KC", account)
        login(s)
        with case(s, case_id, "Duyệt điều chỉnh sau chốt" + (" (HR, ghi vào kỳ công)" if target == APPROVED else ""),
                  "Mở đơn > Hành động > Duyệt", REQ.get("adj", ""),
                  target + ("; ngày đó thành Có mặt; kỳ công ghi nhật ký điều chỉnh" if target == APPROVED else "")) as r:
            s.step(f"{account}: mở đơn điều chỉnh sau chốt")
            s.page.goto(f"{BASE}/desk/attendance-request/{REQ['adj']}")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            desk_action(s, REQ["adj"], "Duyệt", doctype=AR)
            state = doc_state(s, AR, REQ["adj"])
            check(state == target, state)
            r["actual"] = state
            if target == APPROVED:
                loaded = api_get(s, f"/api/method/frappe.desk.form.load.getdoc?doctype={KC}&name={REQ['kc']['Nhà máy 1']}").json()
                logs = loaded["docinfo"].get("comments", []) + loaded["docinfo"].get("info_logs", [])
                comments = [c for c in logs if REQ["adj"] in (c.get("content") or "")]
                check(comments, "không có nhật ký trên kỳ công")
                open_period(s, REQ["kc"]["Nhà máy 1"])
                r["actual"] = f"{state}; nhật ký điều chỉnh trên {REQ['kc']['Nhà máy 1']}"
        s.close()


JOURNEYS = [gps_checkin, correction, period_closing]
