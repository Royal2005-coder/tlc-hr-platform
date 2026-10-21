"""W6 Internal Services desktop-native journeys:
- Service requests with working-day SLA and requester satisfaction closure
- Room reservation concurrency conflict prevention and explicit iCalendar export
- Library book lending, waitlist handling and return
- Meal enrollment auto-cancellation on approved leave/travel
- Official correspondence dispatch and delivery tracking
"""

from urllib.parse import quote
import json

from lib import *  # noqa: F403


def desk_navigate(s, doctype, name=None):
    slug = doctype.lower().replace(" ", "-")
    url = f"{BASE}/desk/{slug}/{quote(name)}" if name else f"{BASE}/desk/{slug}/new"
    s.page.goto(url)
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1500)


def employee_id(s, account="an"):
    return api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", f"{account}@demo.example"]])).json()["data"][0]["name"]


def set_employee(s, account="an"):
    field = s.page.locator("input[data-fieldname='employee']")
    field.fill(employee_id(s, account))
    field.press("Tab")


def save_primary(page):
    """Native Save button; Escape first so a link autocomplete or select overlay cannot eat the click."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.locator("button.es-button.primary-action:visible").last.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1800)


def service_request_journey(browser):
    s_an = Session(browser, "SVC-AN", "an")
    s_lan = Session(browser, "SVC-LAN", "lan")
    try:
        login(s_an)
        emp_an = api_get(s_an, "/api/resource/Employee?filters=[[\"user_id\",\"=\",\"an@demo.example\"]]").json()["data"][0]["name"]
        REQ["emp_an"] = emp_an

        with case(s_an, "SVC-07", "Gửi yêu cầu dịch vụ nội bộ có SLA", "Mở TLC Service Request > Nhập dịch vụ, trích yếu > Lưu",
                  "Hành chính - Xác nhận công tác", "Yêu cầu ở trạng thái Requested; hạn SLA tự tính theo ngày làm việc") as r:
            desk_navigate(s_an, "TLC Service Request")
            set_employee(s_an, "an")
            p = s_an.page
            p.locator("input[data-fieldname='service']").fill("Hành chính - Xác nhận công tác")
            p.keyboard.press("Enter")
            p.locator("input[data-fieldname='subject']").fill("Xin giấy xác nhận công tác chuẩn bị hồ sơ thầu")
            p.locator("textarea[data-fieldname='description']").fill("Kính gửi Hành chính cấp giấy xác nhận công tác 2 ngày tại Đà Nẵng.")
            p.wait_for_timeout(1000)
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            doc_name = p.url.split("/")[-1]
            REQ["svc_request_name"] = doc_name
            req_data = api_get(s_an, f"/api/resource/TLC Service Request/{doc_name}").json()["data"]
            check(req_data["status"] == "Requested" and bool(req_data["due_date"]) and req_data["handler"] == "lan@demo.example", str(req_data)[:200])
            r["actual"] = f"{doc_name}: Trạng thái Requested, người xử lý {req_data['handler']}, hạn SLA {req_data['due_date']}"

        login(s_lan)
        with case(s_lan, "SVC-08", "HR xử lý và giải quyết yêu cầu dịch vụ", "Mở yêu cầu > Chuyển Processing > Resolved với kết quả",
                  REQ["svc_request_name"], "Trạng thái Resolved kèm kết quả xử lý") as r:
            desk_navigate(s_lan, "TLC Service Request", REQ["svc_request_name"])
            p = s_lan.page
            p.locator("select[data-fieldname='status']").select_option("Processing")
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(1500)

            p.locator("select[data-fieldname='status']").select_option("Resolved")
            resolution = p.locator("textarea[data-fieldname='resolution']")
            resolution.fill("Đã hoàn tất giấy xác nhận và gửi bản scan qua email.")
            resolution.press("Tab")
            p.wait_for_timeout(500)
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            state = api_get(s_lan, f"/api/resource/TLC Service Request/{REQ['svc_request_name']}").json()["data"]["status"]
            check(state == "Resolved", state)
            r["actual"] = f"Yêu cầu đã chuyển trạng thái {state}"

        with case(s_an, "SVC-09", "Người gửi xác nhận hài lòng và đóng yêu cầu", "Mở yêu cầu > Đánh giá 5 sao > Đóng",
                  REQ["svc_request_name"], "Trạng thái Closed có ghi nhận đánh giá hài lòng") as r:
            desk_navigate(s_an, "TLC Service Request", REQ["svc_request_name"])
            p = s_an.page
            p.locator("select[data-fieldname='satisfaction']").select_option("5")
            p.locator("select[data-fieldname='status']").select_option("Closed")
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            final_data = api_get(s_an, f"/api/resource/TLC Service Request/{REQ['svc_request_name']}").json()["data"]
            check(final_data["status"] == "Closed" and final_data["satisfaction"] == "5", str(final_data)[:200])
            r["actual"] = f"Đóng thành công, hài lòng {final_data['satisfaction']}/5"

    finally:
        s_an.close()
        s_lan.close()


def room_reservation_journey(browser):
    s_an = Session(browser, "ROOM-AN", "an")
    s_quang = Session(browser, "ROOM-QUANG", "quang")
    try:
        login(s_an)
        start_time = f"{working_day(3)} 09:00:00"
        end_time = f"{working_day(3)} 10:00:00"
        overlap_start = f"{working_day(3)} 09:30:00"
        overlap_end = f"{working_day(3)} 10:30:00"

        with case(s_an, "SVC-03", "Đặt phòng họp và xuất iCalendar", "Mở TLC Room Reservation > Chọn phòng, giờ > Lưu > Xuất iCalendar",
                  "Phòng họp Hội sở 1 (Lớn)", "Đặt phòng thành công; có nút xuất tệp iCalendar") as r:
            desk_navigate(s_an, "TLC Room Reservation")
            set_employee(s_an, "an")
            p = s_an.page
            p.locator("input[data-fieldname='room']").fill("Phòng họp Hội sở 1 (Lớn)")
            p.keyboard.press("Enter")
            p.locator("input[data-fieldname='subject']").fill("Họp rà soát tiến độ kinh doanh")
            p.evaluate("([a, b]) => { cur_frm.set_value('starts_at', a); cur_frm.set_value('ends_at', b); }", [start_time, end_time])
            p.wait_for_timeout(1000)
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            res_name = p.url.split("/")[-1]
            REQ["res_name"] = res_name
            res_data = api_get(s_an, f"/api/resource/TLC Room Reservation/{res_name}").json()["data"]
            check(res_data["status"] == "Booked", str(res_data)[:200])

            # Export iCalendar
            ics_url = f"{BASE}/api/method/tlc_hr.interface.services.export_calendar?name={res_name}"
            ics_res = s_an.page.request.get(ics_url)
            check("BEGIN:VCALENDAR" in ics_res.text() and res_name in ics_res.text(), ics_res.text()[:200])
            r["actual"] = f"Đặt phòng {res_name} thành công; xuất iCalendar hợp lệ chứa BEGIN:VCALENDAR"

        login(s_quang)
        with case(s_quang, "SVC-04", "Chặn trùng lịch phòng họp", "Người khác đặt trùng khung giờ vào cùng phòng",
                  "Phòng họp Hội sở 1 (Lớn), trùng 30 phút", "Hệ thống chặn và thông báo phòng đã được đặt") as r:
            desk_navigate(s_quang, "TLC Room Reservation")
            set_employee(s_quang, "quang")
            p = s_quang.page
            p.locator("input[data-fieldname='room']").fill("Phòng họp Hội sở 1 (Lớn)")
            p.keyboard.press("Enter")
            p.locator("input[data-fieldname='subject']").fill("Họp đột xuất bộ phận")
            p.evaluate("([a, b]) => { cur_frm.set_value('starts_at', a); cur_frm.set_value('ends_at', b); }", [overlap_start, overlap_end])
            p.wait_for_timeout(1000)
            save_primary(p)
            p.wait_for_timeout(2500)
            text = p.locator("body").inner_text()
            check("Phòng đã được đặt trong khoảng thời gian này" in text or "room_conflict" in text, text[:250])
            r["actual"] = "Bị chặn lưu với thông báo phòng đã được đặt trong khoảng thời gian này"

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

        book_code = "TLCLIB-001"
        with case(s_an, "SVC-05", "Mượn sách và HR duyệt cho mượn", "Mở TLC Book Loan > Chọn sách > Lưu. HR duyệt Lent",
                  book_code, "Phiếu mượn chuyển sang trạng thái Lent có ngày mượn và hạn trả") as r:
            desk_navigate(s_an, "TLC Book Loan")
            set_employee(s_an, "an")
            p = s_an.page
            p.locator("input[data-fieldname='book']").fill(book_code)
            p.keyboard.press("Enter")
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            loan_an = p.url.split("/")[-1]
            REQ["loan_an"] = loan_an

            # HR Lan lends book
            desk_navigate(s_lan, "TLC Book Loan", loan_an)
            p_lan = s_lan.page
            p_lan.locator("select[data-fieldname='status']").select_option("Lent")
            p_lan.evaluate("(d) => cur_frm.set_value('due_date', d)", working_day(14))
            save_primary(p_lan)
            p_lan.wait_for_load_state("networkidle")
            p_lan.wait_for_timeout(2000)
            loan_data = api_get(s_lan, f"/api/resource/TLC Book Loan/{loan_an}").json()["data"]
            check(loan_data["status"] == "Lent" and bool(loan_data["lent_on"]), str(loan_data)[:200])
            r["actual"] = f"{loan_an}: Trạng thái Lent, ngày mượn {loan_data['lent_on']}, hạn trả {loan_data['due_date']}"

        with case(s_binh, "SVC-06", "Tự động xếp hàng chờ khi sách đang được mượn", "Công nhân Bình mượn cuốn sách đang Lent",
                  book_code, "Yêu cầu tự động chuyển thành Waitlisted") as r:
            desk_navigate(s_binh, "TLC Book Loan")
            set_employee(s_binh, "binh")
            p_binh = s_binh.page
            p_binh.locator("input[data-fieldname='book']").fill(book_code)
            p_binh.keyboard.press("Enter")
            save_primary(p_binh)
            p_binh.wait_for_load_state("networkidle")
            p_binh.wait_for_timeout(2000)
            loan_binh = p_binh.url.split("/")[-1]
            REQ["loan_binh"] = loan_binh
            binh_data = api_get(s_binh, f"/api/resource/TLC Book Loan/{loan_binh}").json()["data"]
            check(binh_data["status"] == "Waitlisted", str(binh_data)[:200])
            r["actual"] = f"{loan_binh}: Tự động xếp hàng chờ Waitlisted"

        # Return book and verify waitlist notification
        desk_navigate(s_lan, "TLC Book Loan", REQ["loan_an"])
        s_lan.page.locator("select[data-fieldname='status']").select_option("Returned")
        save_primary(s_lan.page)
        s_lan.page.wait_for_load_state("networkidle")

    finally:
        s_an.close()
        s_binh.close()
        s_lan.close()


def meal_auto_cancellation_journey(browser):
    s_an = Session(browser, "MEAL-AN", "an")
    s_lan = Session(browser, "MEAL-LAN", "lan")
    try:
        login(s_an)
        target_day = working_day(5)

        with case(s_an, "SVC-01", "Đăng ký suất ăn và tự hủy khi nghỉ phép đã duyệt", "Đăng ký suất ăn ngày T > Đơn nghỉ ngày T duyệt > Kiểm tra",
                  target_day, "Suất ăn chuyển thành Cancelled kèm nguồn chứng từ") as r:
            desk_navigate(s_an, "TLC Meal Enrollment")
            set_employee(s_an, "an")
            p = s_an.page
            p.evaluate("(d) => cur_frm.set_value('meal_date', d)", target_day)
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            meal_name = p.url.split("/")[-1]
            REQ["meal_name"] = meal_name

            # An approved leave covering the day runs the native hook that cancels the meal.
            leave_name = hrms_request_leave(s_an, target_day, target_day, "UAT suất ăn - nghỉ phép")
            s_mgr = Session(browser, "SVC-MGR", "quang")
            try:
                login(s_mgr)
                open_leave(s_mgr, leave_name)
                desk_action(s_mgr, leave_name, "Duyệt")
            finally:
                s_mgr.close()
            login(s_lan)
            open_leave(s_lan, leave_name)
            state = desk_action(s_lan, leave_name, "Duyệt")
            check(state == "Đã duyệt", f"Đơn nghỉ chưa duyệt xong: {state}")
            meal_data = api_get(s_an, f"/api/resource/TLC Meal Enrollment/{meal_name}").json()["data"]
            check(meal_data["status"] == "Cancelled" and "tự hủy" in meal_data["reason"].lower(), str(meal_data)[:200])
            r["actual"] = f"Suất ăn {meal_name} đã tự hủy: {meal_data['reason']}, nguồn {meal_data['absence_source']}"

        with case(s_an, "SVC-02", "Chặn đăng ký suất ăn trong ngày vắng mặt đã duyệt", "Cố gắng đăng ký lại suất ăn ngày T",
                  target_day, "Hệ thống từ chối với lỗi meal_absent") as r:
            desk_navigate(s_an, "TLC Meal Enrollment")
            set_employee(s_an, "an")
            p = s_an.page
            p.evaluate("(d) => cur_frm.set_value('meal_date', d)", target_day)
            save_primary(p)
            p.wait_for_timeout(2500)
            text = p.locator("body").inner_text()
            check("meal_absent" in text or "Ngày nghỉ/công tác đã duyệt" in text or "Đã có đăng ký" in text, text[:250])
            r["actual"] = "Bị chặn: không được đăng ký ăn trong ngày nghỉ/công tác đã duyệt"

    finally:
        s_an.close()
        s_lan.close()


def official_correspondence_journey(browser):
    s_an = Session(browser, "MAIL-AN", "an")
    s_lan = Session(browser, "MAIL-LAN", "lan")
    try:
        login(s_an)
        login(s_lan)

        with case(s_an, "SVC-10", "Văn thư gửi đi và cập nhật vận chuyển", "Nhân viên tạo văn thư > HR gán vận đơn và chuyển Delivered",
                  "Hợp đồng kinh tế", "Cập nhật đơn vị vận chuyển, mã vận đơn và Delivered") as r:
            desk_navigate(s_an, "TLC Official Correspondence")
            set_employee(s_an, "an")
            p = s_an.page
            p.locator("input[data-fieldname='subject']").fill("Hợp đồng nguyên tắc cung ứng vật tư 2026")
            p.locator("input[data-fieldname='counterparty']").fill("Công ty Cổ phần Cơ khí Đồng Nai")
            p.locator("textarea[data-fieldname='address']").fill("KCN Biên Hòa 2, Đồng Nai")
            save_primary(p)
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            mail_name = p.url.split("/")[-1]
            REQ["mail_name"] = mail_name

            desk_navigate(s_lan, "TLC Official Correspondence", mail_name)
            p_lan = s_lan.page
            p_lan.locator("input[data-fieldname='courier']").fill("Viettel Post")
            p_lan.locator("input[data-fieldname='tracking_number']").fill("VT889900VN")
            p_lan.locator("select[data-fieldname='status']").select_option("With Courier")
            save_primary(p_lan)
            p_lan.wait_for_load_state("networkidle")
            p_lan.wait_for_timeout(1500)

            p_lan.locator("select[data-fieldname='status']").select_option("Delivered")
            save_primary(p_lan)
            p_lan.wait_for_load_state("networkidle")
            p_lan.wait_for_timeout(2000)
            doc_data = api_get(s_lan, f"/api/resource/TLC Official Correspondence/{mail_name}").json()["data"]
            check(doc_data["status"] == "Delivered" and doc_data["tracking_number"] == "VT889900VN", str(doc_data)[:200])
            r["actual"] = f"{mail_name}: Đã chuyển phát Delivered, đơn vị {doc_data['courier']}, mã vận đơn {doc_data['tracking_number']}"

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
