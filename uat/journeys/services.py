"""Bằng chứng UAT W6 Dịch vụ nội bộ trên Desk chuẩn.

Người dùng thật mở form, gõ từng ô (kể cả ngày giờ theo định dạng hiển thị trên màn hình), bấm nút Lưu,
chọn trạng thái trong ô dropdown và bấm nút Xuất iCalendar. REST chỉ dùng để đọc đối chiếu sau khi thao tác.
"""
from pathlib import Path
from urllib.parse import quote

from lib import *

ROOM = "TLC Room Reservation"
MEAL = "TLC Meal Enrollment"
LOAN = "TLC Book Loan"
REQUEST = "TLC Service Request"
LETTER = "TLC Official Correspondence"


def desk_navigate(s, doctype, name=None):
    slug = doctype.lower().replace(" ", "-")
    url = f"{BASE}/desk/{slug}/{quote(name)}" if name else f"{BASE}/desk/{slug}/new"
    s.page.goto(url)
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1500)


def employee_id(s, account="an"):
    return api_get(s, "/api/resource/Employee?filters=" +
                   json.dumps([["user_id", "=", f"{account}@demo.example"]])).json()["data"][0]["name"]


def _field(p, fieldname):
    return p.locator(f"input[data-fieldname='{fieldname}']:visible, textarea[data-fieldname='{fieldname}']:visible").last


def _type(p, fieldname, value):
    """Gõ thật vào ô của form Desk (không dùng cur_frm.set_value)."""
    field = _field(p, fieldname)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    field.click()
    p.wait_for_timeout(300)
    p.keyboard.press("Escape")  # đóng bảng lịch che ô
    p.wait_for_timeout(200)
    field.fill(value)
    field.press("Tab")
    p.wait_for_timeout(600)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)


def _link(p, fieldname, value):
    """Ô liên kết: bấm, gõ để lọc rồi chọn đúng dòng gợi ý đang hiện (không bấm gợi ý ẩn của ô khác)."""
    field = _field(p, fieldname)
    field.click()
    field.fill("")
    p.keyboard.type(str(value), delay=40)
    p.wait_for_timeout(2200)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option]")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    target = next((i for i in shown
                   if str(value).lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
    check(target is not None, f"ô {fieldname} không có gợi ý hiển thị '{value}': "
                              f"{[options.nth(i).inner_text() for i in shown][:4]}")
    options.nth(target).click()
    p.wait_for_timeout(1000)


def _choose(p, fieldname, value):
    """Chọn trong ô dropdown thật của form."""
    select = p.locator(f"select[data-fieldname='{fieldname}']:visible").last
    try:
        select.select_option(label=value)
    except Exception:
        select.select_option(value=value)
    p.wait_for_timeout(500)


def _save(p):
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    button = p.locator(".page-head button:visible").filter(has_text=re.compile(r"Lưu|Save|Cập nhật|Update")).last
    try:
        button.click(timeout=6000)
    except Exception:
        button.click(force=True)
    p.wait_for_timeout(2600)


def _press_button(p, label, wait=2500):
    button = visible_button(p, label)
    expect(button).to_be_visible()
    button.click()
    p.wait_for_timeout(wait)


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


def _popup_text(p):
    modal = p.locator(".modal:visible")
    if modal.count():
        return " ".join(modal.last.inner_text().split())
    return " ".join(p.locator("body").inner_text().split())


def _doc(p):
    """Đọc lại chính hồ sơ đang mở để đối chiếu (chỉ đọc, không ghi)."""
    return p.evaluate("JSON.stringify(cur_frm.doc)")


def _user_day(n):
    """Ngày làm việc thứ n, định dạng hiển thị trên ô ngày của Desk (dd-mm-yyyy)."""
    return dt.date.fromisoformat(working_day(n)).strftime("%d-%m-%Y")


def _user_datetime(n, clock):
    return f"{_user_day(n)} {clock}"


def _system_day(n):
    return working_day(n)


def _next_month_date(day):
    """The attendance month is locked by the payroll fixtures; use a weekday of the next month."""
    first = (dt.date.today().replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    target = first.replace(day=day)
    while target.weekday() >= 5:
        target += dt.timedelta(days=1)
    return target


def _next_month_day(day):
    return _next_month_date(day).isoformat()


def _user_next_month_day(day):
    return _next_month_date(day).strftime("%d-%m-%Y")


def set_employee(p, emp):
    _link(p, "employee", emp)
    check(p.evaluate("d => cur_frm.doc.employee === d", emp), f"Ô nhân viên chưa nhận {emp}: {_shown(p, 'employee')}")


def service_request_journey(browser):
    s_an = Session(browser, "SVC-AN", "an")
    s_lan = Session(browser, "SVC-LAN", "lan")
    try:
        login(s_an)
        s = s_an
        emp_an = employee_id(s_an, "an")
        REQ["emp_an"] = emp_an

        with case(s_an, "SVC-07", "Gửi yêu cầu dịch vụ nội bộ có SLA",
                  "Desk > TLC Service Request (Mới) > chọn dịch vụ > nhập trích yếu và chi tiết > bấm Lưu",
                  "Hành chính - Xác nhận công tác",
                  "Yêu cầu ở trạng thái Requested; hạn SLA tự tính theo ngày làm việc và hiện trên form") as r:
            p = s_an.page
            s.step("An mở form yêu cầu dịch vụ mới")
            desk_navigate(s_an, REQUEST)
            s.step("An chọn dịch vụ Hành chính - Xác nhận công tác")
            set_employee(p, emp_an)
            _link(p, "service", "Hành chính - Xác nhận công tác")
            s.step("An nhập trích yếu và chi tiết yêu cầu")
            _type(p, "subject", "Xin giấy xác nhận công tác chuẩn bị hồ sơ thầu")
            p.locator("textarea[data-fieldname='description']:visible").last.fill(
                "Kính gửi Hành chính cấp giấy xác nhận công tác 2 ngày tại Đà Nẵng.")
            p.wait_for_timeout(400)
            s.step("An bấm Lưu")
            _save(p)
            doc_name = p.url.rstrip("/").split("/")[-1]
            check("new" not in doc_name, f"Yêu cầu chưa lưu: {p.url}")
            REQ["svc_request_name"] = doc_name
            s.step("An đọc trạng thái Requested và hạn SLA trên form")
            shown = {k: _shown(p, k) for k in ("status", "due_date", "handler")}
            req_data = api_get(s_an, f"/api/resource/{REQUEST}/{doc_name}").json()["data"]
            check(req_data["status"] == "Requested" and bool(req_data["due_date"])
                  and req_data["handler"] == "lan@demo.example", str(req_data)[:200])
            r["actual"] = (f"{doc_name}: form hiện {shown['status'][:30]}, người xử lý {shown['handler'][:20]}, "
                           f"hạn SLA {shown['due_date'][:20]}")

        login(s_lan)
        s = s_lan
        with case(s_lan, "SVC-08", "HR xử lý và giải quyết yêu cầu dịch vụ",
                  "Mở yêu cầu trong danh sách > chọn trạng thái Processing > Lưu > chọn Resolved + nhập kết quả > Lưu",
                  REQ.get("svc_request_name", ""), "Trạng thái Resolved kèm kết quả xử lý hiển thị trên form") as r:
            p = s_lan.page
            s.step("Lan mở danh sách yêu cầu dịch vụ và vào đúng phiếu của An")
            p.goto(f"{BASE}/desk/tlc-service-request")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(1600)
            row = p.locator(f'.list-row-container a[data-doctype="{REQUEST}"]').first
            check(row.count() > 0, "Danh sách yêu cầu dịch vụ trống")
            row.click()
            p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=REQUEST)
            p.wait_for_timeout(1200)
            s.step("Lan chuyển trạng thái sang Processing và bấm Lưu")
            _choose(p, "status", "Processing")
            _save(p)
            s.step("Lan chọn Resolved, nhập kết quả xử lý rồi bấm Lưu")
            _choose(p, "status", "Resolved")
            p.locator("textarea[data-fieldname='resolution']:visible").last.fill(
                "Đã hoàn tất giấy xác nhận và gửi bản scan qua email.")
            p.wait_for_timeout(400)
            _save(p)
            s.step("Lan đọc trạng thái Resolved trên form")
            shown = _shown(p, "status")
            state = api_get(s_lan, f"/api/resource/{REQUEST}/{REQ['svc_request_name']}").json()["data"]["status"]
            check(state == "Resolved", state)
            r["actual"] = f"Yêu cầu {REQ['svc_request_name']} chuyển {state} sau hai lần bấm Lưu (form hiện: {shown[:40]})"

        s = s_an
        with case(s_an, "SVC-09", "Người gửi xác nhận hài lòng và đóng yêu cầu",
                  "An mở lại yêu cầu > chọn mức hài lòng 5 > chọn trạng thái Closed > bấm Lưu",
                  REQ.get("svc_request_name", ""), "Trạng thái Closed có ghi nhận đánh giá hài lòng trên form") as r:
            p = s_an.page
            s.step("An mở lại yêu cầu dịch vụ của mình")
            p.goto(f"{BASE}/desk/tlc-service-request")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(1600)
            row = p.locator(f'.list-row-container a[data-doctype="{REQUEST}"]').first
            check(row.count() > 0, "Danh sách yêu cầu dịch vụ trống")
            row.click()
            p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=REQUEST)
            p.wait_for_timeout(1200)
            s.step("An chọn mức hài lòng 5 và trạng thái Closed")
            _choose(p, "satisfaction", "5")
            _choose(p, "status", "Closed")
            s.step("An bấm Lưu")
            _save(p)
            shown = {k: _shown(p, k) for k in ("status", "satisfaction")}
            final_data = api_get(s_an, f"/api/resource/{REQUEST}/{REQ['svc_request_name']}").json()["data"]
            check(final_data["status"] == "Closed" and final_data["satisfaction"] == "5", str(final_data)[:200])
            r["actual"] = f"Đóng thành công: form hiện {shown['status'][:24]}, hài lòng {shown['satisfaction'][:22]}"

    finally:
        s_an.close()
        s_lan.close()


def room_reservation_journey(browser):
    s_an = Session(browser, "ROOM-AN", "an")
    s_quang = Session(browser, "ROOM-QUANG", "quang")
    try:
        login(s_an)
        s = s_an
        emp_an = employee_id(s_an, "an")
        system_start = f"{_system_day(3)} 09:00:00"
        system_end = f"{_system_day(3)} 10:00:00"

        with case(s_an, "SVC-03", "Đặt phòng họp và xuất iCalendar",
                  "Desk > TLC Room Reservation (Mới) > chọn phòng > nhập cuộc họp > gõ giờ bắt đầu/kết thúc > Lưu > bấm Xuất iCalendar",
                  "Phòng họp Hội sở 1 (Lớn)",
                  "Đặt phòng Booked trên form; bấm nút xuất để tải tệp .ics (nội dung tệp do server trả về)") as r:
            p = s_an.page
            s.step("An mở form đặt phòng họp mới")
            desk_navigate(s_an, ROOM)
            s.step("An chọn phòng và nhập tên cuộc họp")
            set_employee(p, emp_an)
            _link(p, "room", "Phòng họp Hội sở 1 (Lớn)")
            _type(p, "subject", "Họp rà soát tiến độ kinh doanh")
            s.step(f"An gõ khung giờ {system_start} → {system_end} ngay trên ô ngày giờ")
            _type(p, "starts_at", _user_datetime(3, "09:00:00"))
            _type(p, "ends_at", _user_datetime(3, "10:00:00"))
            typed = json.loads(_doc(p))
            check(typed["starts_at"] == system_start and typed["ends_at"] == system_end,
                  f"Desk nhận giờ khác chỗ An gõ: {typed['starts_at']} / {typed['ends_at']}")
            s.step("An bấm Lưu")
            _save(p)
            res_name = p.url.rstrip("/").split("/")[-1]
            check("new" not in res_name, f"Đặt phòng chưa lưu: {p.url}")
            REQ["res_name"] = res_name
            s.step("An đọc trạng thái Booked trên form")
            shown_status = _shown(p, "status")
            res_data = api_get(s_an, f"/api/resource/{ROOM}/{res_name}").json()["data"]
            check(res_data["status"] == "Booked", str(res_data)[:200])
            s.step("An bấm nút Xuất iCalendar và tải tệp lịch về máy")
            captured = []
            p.on("download", lambda d: captured.append(d))
            p.context.on("page", lambda page: page.on("download", lambda d: captured.append(d)))
            _press_button(p, "Xuất iCalendar")
            for _ in range(20):
                if captured:
                    break
                p.wait_for_timeout(500)
            check(bool(captured), "Bấm nút Xuất iCalendar mà trình duyệt không nhận được tệp nào")
            download = captured[-1]
            ics = Path(download.path()).read_text(encoding="utf-8", errors="ignore")
            check("BEGIN:VCALENDAR" in ics and res_name in ics, ics[:200])
            r["actual"] = (f"Đặt phòng {res_name} (form hiện {shown_status[:20]}); tệp tải về "
                           f"“{download.suggested_filename}” có BEGIN:VCALENDAR và UID chứa {res_name}")

        login(s_quang)
        s = s_quang
        with case(s_quang, "SVC-04", "Chặn trùng lịch phòng họp",
                  "Quang mở form đặt phòng > chọn đúng phòng đã có lịch > gõ khung giờ chồng lấn > bấm Lưu > đọc cảnh báo",
                  "Phòng họp Hội sở 1 (Lớn), trùng 30 phút",
                  "Màn hình báo phòng đã được đặt trong khoảng thời gian này và không lưu phiếu") as r:
            p = s_quang.page
            s.step("Quang mở form đặt phòng họp mới")
            desk_navigate(s_quang, ROOM)
            s.step("Quang chọn cùng phòng họp Hội sở 1 và nhập cuộc họp đột xuất")
            set_employee(p, employee_id(s_quang, "quang"))
            _link(p, "room", "Phòng họp Hội sở 1 (Lớn)")
            _type(p, "subject", "Họp đột xuất bộ phận")
            s.step(f"Quang gõ khung giờ chồng lấn {_system_day(3)} 09:30 → 10:30")
            _type(p, "starts_at", _user_datetime(3, "09:30:00"))
            _type(p, "ends_at", _user_datetime(3, "10:30:00"))
            s.step("Quang bấm Lưu và đọc cảnh báo trùng lịch")
            _save(p)
            p.wait_for_timeout(2000)
            text = _popup_text(p)
            check("Phòng đã được đặt trong khoảng thời gian này" in text or "room_conflict" in text, text[:250])
            still_new = p.evaluate("cur_frm.is_new()")
            check(still_new, "Phiếu trùng lịch vẫn được lưu")
            r["actual"] = f"Desk chặn ngay trên màn hình: {text[:140]}"

    finally:
        s_an.close()
        s_quang.close()


def library_loan_journey(browser):
    s_an = Session(browser, "LIB-AN", "an")
    s_binh = Session(browser, "LIB-BINH", "binh")
    s_lan = Session(browser, "LIB-LAN", "lan")
    try:
        login(s_an)
        login(s_lan)
        login(s_binh)
        s = s_an
        book_code = "TLCLIB-001"

        with case(s_an, "SVC-05", "Mượn sách và HR duyệt cho mượn",
                  "An mở TLC Book Loan (Mới) > chọn sách > Lưu. Lan mở phiếu > chọn Lent, gõ hạn trả > Lưu",
                  book_code, "Phiếu mượn chuyển sang Lent, có ngày mượn và hạn trả trên form") as r:
            p = s_an.page
            s.step("An mở form mượn sách và chọn cuốn TLCLIB-001")
            desk_navigate(s_an, LOAN)
            set_employee(p, employee_id(s_an, "an"))
            _link(p, "book", book_code)
            s.step("An bấm Lưu yêu cầu mượn")
            _save(p)
            loan_an = p.url.rstrip("/").split("/")[-1]
            check("new" not in loan_an, f"Phiếu mượn chưa lưu: {p.url}")
            REQ["loan_an"] = loan_an

            s = s_lan
            s.step("Lan mở danh sách phiếu mượn và vào phiếu của An")
            p_lan = s_lan.page
            p_lan.goto(f"{BASE}/desk/tlc-book-loan?name={loan_an}")
            p_lan.wait_for_load_state("networkidle")
            p_lan.wait_for_timeout(1600)
            row = p_lan.locator(f'.list-row-container a[data-doctype="{LOAN}"]').first
            check(row.count() > 0, "Lan không thấy phiếu mượn của An trong danh sách")
            row.click()
            p_lan.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=LOAN)
            p_lan.wait_for_timeout(1200)
            s.step("Lan chọn trạng thái Lent và gõ hạn trả 14 ngày làm việc")
            _choose(p_lan, "status", "Lent")
            _type(p_lan, "due_date", _user_day(14))
            s.step("Lan bấm Lưu")
            _save(p_lan)
            shown = {k: _shown(p_lan, k) for k in ("status", "lent_on", "due_date")}
            loan_data = api_get(s_lan, f"/api/resource/{LOAN}/{loan_an}").json()["data"]
            check(loan_data["status"] == "Lent" and bool(loan_data["lent_on"]), str(loan_data)[:200])
            check(loan_data["due_date"] == _system_day(14), f"Hạn trả lưu {loan_data['due_date']}")
            r["actual"] = (f"{loan_an}: form hiện {shown['status'][:24]}, ngày mượn {shown['lent_on'][:22]}, "
                           f"hạn trả {shown['due_date'][:22]}")

        s = s_binh
        with case(s_binh, "SVC-06", "Tự động xếp hàng chờ khi sách đang được mượn",
                  "Bình mở form mượn sách > chọn đúng cuốn đang Lent > bấm Lưu > đọc trạng thái Waitlisted",
                  book_code, "Yêu cầu tự chuyển Waitlisted và hiện trên form") as r:
            p_binh = s_binh.page
            s.step("Bình mở form mượn sách, chọn cuốn TLCLIB-001 đang có người mượn")
            desk_navigate(s_binh, LOAN)
            set_employee(p_binh, employee_id(s_binh, "binh"))
            _link(p_binh, "book", book_code)
            s.step("Bình bấm Lưu")
            _save(p_binh)
            loan_binh = p_binh.url.rstrip("/").split("/")[-1]
            check("new" not in loan_binh, f"Phiếu của Bình chưa lưu: {p_binh.url}")
            REQ["loan_binh"] = loan_binh
            s.step("Bình đọc trạng thái xếp hàng chờ trên form")
            shown = _shown(p_binh, "status")
            binh_data = api_get(s_binh, f"/api/resource/{LOAN}/{loan_binh}").json()["data"]
            check(binh_data["status"] == "Waitlisted", str(binh_data)[:200])
            r["actual"] = f"{loan_binh}: form hiện “{shown[:30]}” vì sách đang được mượn"

        # Lan nhận lại sách: dữ liệu nền cho các ca sau của phân hệ khác.
        desk_navigate(s_lan, LOAN, REQ["loan_an"])
        s_lan.page.locator("select[data-fieldname='status']:visible").last.select_option("Returned")
        _save(s_lan.page)

    finally:
        s_an.close()
        s_binh.close()
        s_lan.close()


def meal_auto_cancellation_journey(browser):
    s_an = Session(browser, "MEAL-AN", "an")
    s_lan = Session(browser, "MEAL-LAN", "lan")
    try:
        login(s_an)
        s = s_an
        target_day = _next_month_day(10)

        with case(s_an, "SVC-01", "Đăng ký suất ăn và tự hủy khi nghỉ phép đã duyệt",
                  "An đăng ký suất ăn ngày T trên form > gửi đơn nghỉ qua app > Quang và Lan duyệt trên Desk > An mở lại suất ăn",
                  target_day, "Suất ăn chuyển thành Cancelled kèm lý do tự hủy và nguồn chứng từ trên form") as r:
            p = s_an.page
            s.step("An mở form đăng ký suất ăn và gõ ngày ăn")
            desk_navigate(s_an, MEAL)
            set_employee(p, employee_id(s_an, "an"))
            _type(p, "meal_date", _user_next_month_day(10))
            s.step("An bấm Lưu đăng ký")
            _save(p)
            meal_name = p.url.rstrip("/").split("/")[-1]
            check("new" not in meal_name, f"Suất ăn chưa lưu: {p.url}")
            REQ["meal_name"] = meal_name

            s.step("An mở app Frappe HR và điền đơn nghỉ phép đúng ngày T")
            leave_name = hrms_request_leave(s_an, target_day, target_day, "UAT suất ăn - nghỉ phép")

            s_mgr = Session(browser, "SVC-MGR", "quang")
            try:
                login(s_mgr)
                s_mgr.step("Quang mở đơn nghỉ của An và bấm Hành động > Duyệt cấp 1")
                open_leave(s_mgr, leave_name)
                desk_action(s_mgr, leave_name, "Duyệt")
            finally:
                s_mgr.close()
            s = s_lan
            s.step("Lan mở cùng đơn nghỉ và bấm Hành động > Duyệt cấp 2")
            login(s_lan)
            open_leave(s_lan, leave_name)
            state = desk_action(s_lan, leave_name, "Duyệt")
            check(state == "Đã duyệt", f"Đơn nghỉ chưa duyệt xong: {state}")

            s.step("An mở lại phiếu suất ăn để đọc lý do tự hủy")
            desk_navigate(s_an, MEAL, meal_name)
            shown = {k: _shown(s_an.page, k) for k in ("status", "reason", "absence_source")}
            meal_data = api_get(s_an, f"/api/resource/{MEAL}/{meal_name}").json()["data"]
            check(meal_data["status"] == "Cancelled" and "tự hủy" in meal_data["reason"].lower(), str(meal_data)[:200])
            r["actual"] = (f"Suất ăn {meal_name}: form hiện {shown['status'][:22]} — {shown['reason'][:60]}; "
                           f"nguồn {meal_data['absence_source']}")

        s = s_an
        with case(s_an, "SVC-02", "Chặn đăng ký suất ăn trong ngày vắng mặt đã duyệt",
                  "An mở form suất ăn mới > gõ lại ngày T > bấm Lưu > đọc cảnh báo",
                  target_day, "Màn hình báo không được đăng ký ăn trong ngày nghỉ đã duyệt (meal_absent)") as r:
            p = s_an.page
            s.step("An mở form đăng ký suất ăn mới cho đúng ngày đã nghỉ")
            desk_navigate(s_an, MEAL)
            set_employee(p, employee_id(s_an, "an"))
            _type(p, "meal_date", _user_next_month_day(10))
            s.step("An bấm Lưu và đọc cảnh báo chặn")
            _save(p)
            p.wait_for_timeout(2000)
            text = _popup_text(p)
            check("meal_absent" in text or "Ngày nghỉ/công tác đã duyệt" in text or "Đã có đăng ký" in text, text[:250])
            check(p.evaluate("cur_frm.is_new()"), "Phiếu suất ăn trái quy tắc vẫn được lưu")
            r["actual"] = f"Desk chặn khi lưu: {text[:140]}"

    finally:
        s_an.close()
        s_lan.close()


def official_correspondence_journey(browser):
    s_an = Session(browser, "MAIL-AN", "an")
    s_lan = Session(browser, "MAIL-LAN", "lan")
    try:
        login(s_an)
        login(s_lan)
        s = s_an

        with case(s_an, "SVC-10", "Văn thư gửi đi và cập nhật vận chuyển",
                  "An tạo văn thư trên form (trích yếu, nơi nhận, địa chỉ) > Lưu. Lan nhập đơn vị + mã vận đơn, chuyển With Courier rồi Delivered",
                  "Hợp đồng kinh tế",
                  "Form hiện đơn vị vận chuyển, mã vận đơn và trạng thái Delivered") as r:
            p = s_an.page
            s.step("An mở form văn thư gửi đi và điền trích yếu, nơi nhận, địa chỉ")
            desk_navigate(s_an, LETTER)
            set_employee(p, employee_id(s_an, "an"))
            _type(p, "subject", "Hợp đồng nguyên tắc cung ứng vật tư 2026")
            _type(p, "counterparty", "Công ty Cổ phần Cơ khí Đồng Nai")
            p.locator("textarea[data-fieldname='address']:visible").last.fill("KCN Biên Hòa 2, Đồng Nai")
            p.wait_for_timeout(400)
            s.step("An bấm Lưu")
            _save(p)
            mail_name = p.url.rstrip("/").split("/")[-1]
            check("new" not in mail_name, f"Văn thư chưa lưu: {p.url}")
            REQ["mail_name"] = mail_name

            s = s_lan
            p_lan = s_lan.page
            s.step("Lan mở văn thư vừa gửi trong danh sách")
            p_lan.goto(f"{BASE}/desk/tlc-official-correspondence?name={mail_name}")
            p_lan.wait_for_load_state("networkidle")
            p_lan.wait_for_timeout(1600)
            row = p_lan.locator(f'.list-row-container a[data-doctype="{LETTER}"]').first
            check(row.count() > 0, "Lan không thấy văn thư trong danh sách")
            row.click()
            p_lan.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=LETTER)
            p_lan.wait_for_timeout(1200)
            s.step("Lan nhập đơn vị Viettel Post và mã vận đơn VT889900VN, chọn With Courier")
            _type(p_lan, "courier", "Viettel Post")
            _type(p_lan, "tracking_number", "VT889900VN")
            _choose(p_lan, "status", "With Courier")
            _save(p_lan)
            s.step("Lan chuyển trạng thái sang Delivered và bấm Lưu")
            _choose(p_lan, "status", "Delivered")
            _save(p_lan)
            s.step("Lan đọc lại vận đơn và trạng thái trên form")
            shown = {k: _shown(p_lan, k) for k in ("status", "courier", "tracking_number")}
            doc_data = api_get(s_lan, f"/api/resource/{LETTER}/{mail_name}").json()["data"]
            check(doc_data["status"] == "Delivered" and doc_data["tracking_number"] == "VT889900VN", str(doc_data)[:200])
            r["actual"] = (f"{mail_name}: form hiện {shown['status'][:24]}, {shown['courier'][:24]}, "
                           f"vận đơn {shown['tracking_number'][:20]}")

    finally:
        s_an.close()
        s_lan.close()


JOURNEYS = [
    service_request_journey,
    room_reservation_journey,
    library_loan_journey,
    meal_auto_cancellation_journey,
    official_correspondence_journey,
]
