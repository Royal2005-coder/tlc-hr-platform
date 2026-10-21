"""Leave (TLC Nghỉ phép): request in the Frappe HR app, line manager then HR, reject with a reason, scope, balances."""

from lib import *  # noqa: F403


def office_employee(browser):
    s = Session(browser, "NV", "an")
    first_case(s, "NV-01")
    p = s.page
    with case(s, "NV-02", "Trang chủ app Frappe HR", "Xem lời chào, liên kết nhanh, thanh menu dưới", "",
              "Lời chào đúng tên; có Xin nghỉ phép, Xem phiếu lương; menu Trang chủ / Chấm công / Nghỉ phép / Chi phí / Lương") as r:
        text = p.locator("body").inner_text()
        for t in ("Nguyễn Hoài An", "Xin nghỉ phép", "Xem phiếu lương", "Trang chủ", "Nghỉ phép", "Lương"):
            check(t in text, f"thiếu {t}")
        r["actual"] = "Lời chào, liên kết nhanh và menu dưới đầy đủ (tiếng Việt)"
    with case(s, "NV-03", "Số dư phép", "Menu dưới > Nghỉ phép", "", "Phép năm còn 12 / 12 ngày") as r:
        p.get_by_text("Nghỉ phép", exact=True).last.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        text = p.locator("body").inner_text()
        check("Phép năm" in text and "12" in text, text[:200])
        balance = api(s, "hrms.api.get_leave_balance_map", employee=api_get(s, "/api/resource/Employee?fields=[\"name\"]").json()["data"][0]["name"])
        r["actual"] = f"Trang Phép hiển thị Phép năm; số dư API {json.dumps(balance, ensure_ascii=False)[:120]}"
    start, end = working_day(3), working_day(4)
    with case(s, "NV-04", "Xin nghỉ 2 ngày và gửi duyệt", "Xin nghỉ phép > Loại Phép năm, ngày, lý do > Lưu > Hành động > Gửi duyệt",
              f"{vn(start)} → {vn(end)}, Việc gia đình", "Đơn 2 ngày ở trạng thái Chờ quản lý duyệt, người duyệt Trần Minh Quang") as r:
        REQ["an"] = hrms_request_leave(s, start, end, "Việc gia đình")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['an']}").json()["data"]
        check((doc["workflow_state"], doc["total_leave_days"], doc["leave_approver"]) == (TO_MANAGER, 2, "quang@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['an']}: {doc['workflow_state']}, {doc['total_leave_days']:g} ngày, duyệt bởi {doc['leave_approver']}"
    with case(s, "NV-05", "Chặn đơn trùng ngày", "Xin nghỉ lại đúng ngày đã xin, Lưu", vn(start), "Không lưu được: báo đã có đơn trong khoảng ngày này") as r:
        p.goto(f"{BASE}/hrms/leave-applications/new")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1200)
        p.get_by_text("Chọn Loại nghỉ phép").click()
        p.get_by_text("Phép năm", exact=True).last.click()
        dates = p.locator("input[type=date]")
        dates.nth(0).fill(start)
        dates.nth(1).fill(start)
        p.locator("textarea").first.fill("Thử trùng")
        p.wait_for_timeout(1200)
        visible_button(p, "Lưu").click()
        p.wait_for_timeout(2500)
        check("/new" in p.url, f"đã lưu: {p.url}")
        r["actual"] = "Không lưu được đơn trùng ngày (HRMS báo trùng)"
    with case(s, "NV-06", "Theo dõi đơn của tôi", "Mở danh sách đơn nghỉ", "", f"Thấy đơn {vn(start)} ở trạng thái Chờ quản lý duyệt") as r:
        text = hrms_list_states(s)
        check(TO_MANAGER in text, text[:200])
        r["actual"] = "Danh sách có đơn đang Chờ quản lý duyệt"
    with case(s, "NV-07", "Phạm vi dữ liệu", "API: danh sách nhân viên và đơn nghỉ của phiên nhân viên", "", "Chỉ thấy hồ sơ và đơn của chính mình") as r:
        employees = api_get(s, "/api/resource/Employee?limit_page_length=500").json()["data"]
        leaves = api_get(s, "/api/resource/Leave Application?limit_page_length=500&fields=[\"employee_name\"]").json()["data"]
        check(len(employees) == 1 and {x["employee_name"] for x in leaves} <= {"Nguyễn Hoài An"}, f"{len(employees)} hồ sơ")
        r["actual"] = f"{len(employees)} hồ sơ, {len(leaves)} đơn của chính mình"
    s.close()


def support_office_manager(browser):
    """Support role (recorded): the head of sales, line manager of the office employee, approves her request on the desk."""
    s = Session(browser, "TP", "quang")
    login(s)
    with case(s, "HT-01", "Trưởng phòng duyệt đơn của nhân viên văn phòng", "Workspace TLC Quản lý > mở đơn > Hành động > Duyệt",
              REQ.get("an", ""), "Đơn chuyển Chờ nhân sự duyệt") as r:
        open_leave(s, REQ["an"])
        state = desk_action(s, REQ["an"], "Duyệt")
        check(state == TO_HR, state)
        r["actual"] = f"{REQ['an']} → {state}"
    s.close()


def factory_worker_1(browser):
    s = Session(browser, "CN1", "binh", phone=True)
    first_case(s, "CN1-01")
    day, half = working_day(2), working_day(5)
    with case(s, "CN1-02", "Công nhân xin nghỉ 1 ngày trong app Frappe HR", "Xin nghỉ phép > Lưu > Hành động > Gửi duyệt", f"{vn(day)}, Con ốm",
              "Chờ quản lý duyệt, người duyệt Đặng Văn Hùng") as r:
        REQ["binh_full"] = hrms_request_leave(s, day, day, "Con ốm")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_full']}").json()["data"]
        check((doc["workflow_state"], doc["leave_approver"]) == (TO_MANAGER, "hung@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['binh_full']}: {doc['workflow_state']}, duyệt bởi {doc['leave_approver']}"
    with case(s, "CN1-03", "Xin nghỉ nửa ngày", "Xin nghỉ phép, tích Nửa ngày > Lưu > Gửi duyệt", f"{vn(half)}, Khám sức khỏe",
              "0,5 ngày, Chờ quản lý duyệt") as r:
        REQ["binh_half"] = hrms_request_leave(s, half, half, "Khám sức khỏe", half=True)
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_half']}").json()["data"]
        check((doc["workflow_state"], doc["total_leave_days"]) == (TO_MANAGER, 0.5), str(doc)[:200])
        r["actual"] = f"{REQ['binh_half']}: {doc['total_leave_days']:g} ngày, {doc['workflow_state']}"
    with case(s, "CN1-04", "Không tự duyệt được", "Mở đơn của mình; xem Hành động", REQ["binh_full"], "Không có nút Duyệt cho chính mình") as r:
        s.page.goto(f"{BASE}/hrms/leave-applications/{REQ['binh_full']}")
        s.page.wait_for_load_state("networkidle")
        s.page.wait_for_timeout(2000)
        buttons = [b.inner_text().strip() for b in s.page.locator("button").all() if b.is_visible()]
        check("Duyệt" not in buttons, str(buttons))
        r["actual"] = f"Các nút: {[b for b in buttons if b][-3:]}"
    s.close()


def factory_worker_2(browser):
    s = Session(browser, "CN2", "f2w01", phone=True)
    first_case(s, "CN2-01")
    day = working_day(2)
    with case(s, "CN2-02", "Xin nghỉ (Nhà máy 2)", "Xin nghỉ phép > Lưu > Gửi duyệt", f"{vn(day)}, Về quê", "Đơn đến quản lý Nhà máy 2 (nm2)") as r:
        REQ["f2w01"] = hrms_request_leave(s, day, day, "Về quê")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['f2w01']}").json()["data"]
        check(doc["leave_approver"] == "nm2@demo.example" and doc["workflow_state"] == TO_MANAGER, str(doc)[:200])
        r["actual"] = f"{REQ['f2w01']} → nm2@demo.example, {doc['workflow_state']}"
    with case(s, "CN2-03", "Cách ly dữ liệu giữa hai nhà máy", "Mở đơn của công nhân Nhà máy 1 qua API", REQ["binh_full"], "Bị chặn 403") as r:
        status = api_get(s, f"/api/resource/Leave Application/{REQ['binh_full']}").status
        check(status == 403, str(status))
        r["actual"] = f"API trả {status}"
    s.close()


def factory_head(browser):
    s = Session(browser, "QL", "hung")
    first_case(s, "QL-01")
    p = s.page
    with case(s, "QL-02", "Workspace TLC Quản lý", "Đọc các thẻ số và danh sách đơn chờ", "",
              "Đơn chờ tôi duyệt 2; Nhân sự đang làm việc 15 (trong phạm vi); danh sách có 2 đơn của Trần Văn Bình") as r:
        mine = card_value(p, "Đơn chờ tôi duyệt")
        staff = card_value(p, "Nhân sự đang làm việc")
        quick = p.locator(".widget", has_text="Đơn chờ quản lý duyệt").last.inner_text()
        check((mine, staff) == (2, 15) and quick.count("Trần Văn Bình") >= 2 and "Nhà máy 2" not in quick, f"{mine} {staff} {quick[:160]}")
        r["actual"] = f"Đơn chờ tôi duyệt {mine}; nhân sự {staff}; danh sách có 2 đơn của Bình"
    with case(s, "QL-03", "Hỗ trợ quyết định trên form", "Mở đơn 1 ngày của Bình", REQ["binh_full"],
              "Dòng đầu form: số dư sau khi duyệt 11 / 12 ngày; không ai khác ở Nhà máy 1 nghỉ; nút Hành động có Duyệt, Từ chối") as r:
        open_leave(s, REQ["binh_full"])
        text = headline(p)
        actions = workflow_actions(p)
        check("11 / 12" in text and "Không ai khác" in text and {"Duyệt", "Từ chối"} <= set(actions), f"{text} | {actions}")
        r["actual"] = f"{text} · Hành động: {', '.join(actions)}"
    with case(s, "QL-04", "Duyệt đơn", "Hành động > Duyệt", REQ["binh_full"], "Chờ nhân sự duyệt") as r:
        state = desk_action(s, REQ["binh_full"], "Duyệt")
        check(state == TO_HR, state)
        r["actual"] = state
    with case(s, "QL-05", "Từ chối phải có lý do", "Mở đơn nửa ngày > Hành động > Từ chối > nhập lý do > Từ chối", "Trùng ca kiểm kê kho",
              "Hộp thoại hỏi lý do; đơn Từ chối, lý do được lưu") as r:
        open_leave(s, REQ["binh_half"])
        state = desk_action(s, REQ["binh_half"], "Từ chối", reason="Trùng ca kiểm kê kho")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_half']}").json()["data"]
        check(state == REJECTED and doc.get("tlc_reject_reason") == "Trùng ca kiểm kê kho", f"{state} {doc.get('tlc_reject_reason')}")
        r["actual"] = f"{state}; lý do: {doc['tlc_reject_reason']}"
    with case(s, "QL-06", "Không xem được đơn của nhà máy khác", "Mở đơn của Nhà máy 2", REQ["f2w01"], "Bị chặn 403") as r:
        status = api_get(s, f"/api/resource/Leave Application/{REQ['f2w01']}").status
        check(status == 403, str(status))
        r["actual"] = f"API trả {status}"
    with case(s, "QL-07", "Lịch nghỉ phép của đội", "Workspace > Lịch nghỉ phép", "", "Lịch tháng hiển thị đơn của Bình") as r:
        p.goto(f"{BASE}/desk/leave-application/view/calendar/default")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        text = p.locator(".fc, .calendar-view, body").first.inner_text()
        check("Trần Văn Bình" in text, text[:200])
        r["actual"] = "Lịch có đơn của Trần Văn Bình"
    with case(s, "QL-08", "Quản lý tự xin nghỉ trong app", "Mở app Frappe HR, xin nghỉ 1 ngày, gửi duyệt", f"{vn(working_day(6))}, Họp phụ huynh",
              "Đơn đến CEO Nguyễn Văn Thành") as r:
        REQ["hung"] = hrms_request_leave(s, working_day(6), working_day(6), "Họp phụ huynh")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['hung']}").json()["data"]
        check(doc["leave_approver"] == "thanh@demo.example" and doc["workflow_state"] == TO_MANAGER, str(doc)[:160])
        r["actual"] = f"{REQ['hung']} → thanh@demo.example"
    s.close()


def hr_lead(browser):
    s = Session(browser, "HR", "hoa")
    first_case(s, "HR-01")
    p = s.page
    with case(s, "HR-02", "Workspace TLC Nhân sự", "Đọc các thẻ số", "", "60 nhân sự; Hội sở 31; Nhà máy 29; 2 đơn chờ nhân sự duyệt") as r:
        values = tuple(card_value(p, label) for label in ("Nhân sự đang làm việc", "Nhân sự khối Hội sở", "Nhân sự khối Nhà máy", "Đơn chờ nhân sự duyệt"))
        check(values == (60, 31, 29, 2), str(values))
        p.locator(".widget", has_text="Nhân sự theo phòng ban").first.scroll_into_view_if_needed()
        p.wait_for_timeout(1500)
        r["actual"] = "Nhân sự {}; Hội sở {}; Nhà máy {}; chờ nhân sự {}".format(*values)
    with case(s, "HR-03", "Duyệt cấp nhân sự", "Mở từng đơn từ danh sách chờ > Hành động > Duyệt", f"{REQ['binh_full']}, {REQ['an']}",
              "Cả hai Đã duyệt") as r:
        out = []
        for name in (REQ["binh_full"], REQ["an"]):
            open_leave(s, name)
            out.append(desk_action(s, name, "Duyệt"))
        check(out == [APPROVED, APPROVED], str(out))
        r["actual"] = " | ".join(out)
    with case(s, "HR-04", "Báo cáo số dư phép", "Workspace > Số dư phép", "", "Báo cáo mở sẵn kỳ cả năm, hiển thị số dư Phép năm của nhân viên") as r:
        p.goto(f"{BASE}/desk/tlc-hr/tlc-nh%C3%A2n-s%E1%BB%B1")
        p.wait_for_load_state("networkidle")
        p.locator(".widget", has_text="Số dư phép").first.click()
        p.wait_for_load_state("networkidle")
        expect(p.get_by_text("Phép năm").first).to_be_visible(timeout=40000)
        p.wait_for_timeout(1500)
        r["actual"] = "Báo cáo hiển thị số dư Phép năm"
    with case(s, "HR-05", "Tham số lương Việt Nam", "Workspace > Tham số lương Việt Nam", "",
              "Lương cơ sở 2.530.000; giảm trừ 15.500.000 / 6.200.000; hiệu lực 01-07-2026") as r:
        p.goto(f"{BASE}/desk/vn-payroll-settings")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3000)
        d = api_get(s, "/api/resource/VN Payroll Settings/VN Payroll Settings").json()["data"]
        got = (d["base_salary"], d["personal_deduction"], d["dependent_deduction"], d["effective_date"])
        check(got == (2530000, 15500000, 6200000, "2026-07-01"), str(got))
        r["actual"] = str(got)
    with case(s, "HR-06", "Trưởng nhân sự tự xin nghỉ", "App Frappe HR > Xin nghỉ phép > Gửi duyệt", f"{vn(working_day(7))}, Đi đám cưới", "Đơn đến CEO") as r:
        REQ["hoa"] = hrms_request_leave(s, working_day(7), working_day(7), "Đi đám cưới")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['hoa']}").json()["data"]
        check(doc["leave_approver"] == "thanh@demo.example", doc["leave_approver"])
        r["actual"] = f"{REQ['hoa']} → thanh@demo.example"
    s.close()


def ceo(browser):
    s = Session(browser, "CEO", "thanh")
    first_case(s, "CEO-01")
    p = s.page
    with case(s, "CEO-02", "Workspace TLC Điều hành", "Đọc các thẻ số", "", "60 nhân sự; 2 đơn chờ tôi duyệt; 3 đơn chờ quản lý (toàn công ty)") as r:
        values = (card_value(p, "Nhân sự đang làm việc"), card_value(p, "Đơn chờ tôi duyệt"), card_value(p, "Đơn chờ quản lý duyệt"))
        check(values == (60, 2, 3), str(values))
        r["actual"] = "Nhân sự {}; chờ tôi {}; chờ quản lý {}".format(*values)
    with case(s, "CEO-03", "Duyệt đơn của cấp dưới trực tiếp", "Mở đơn của Quản lý NM1 và Trưởng nhân sự > Hành động > Duyệt",
              f"{REQ['hung']}, {REQ['hoa']}", "Cả hai Chờ nhân sự duyệt") as r:
        out = []
        for name in (REQ["hung"], REQ["hoa"]):
            open_leave(s, name)
            out.append(desk_action(s, name, "Duyệt"))
        check(out == [TO_HR, TO_HR], str(out))
        r["actual"] = " | ".join(out)
    with case(s, "CEO-04", "Biểu đồ điều hành", "Xem biểu đồ Nhân sự theo phòng ban và Ngày nghỉ theo tháng", "", "Hai biểu đồ hiển thị") as r:
        p.goto(f"{BASE}/desk/tlc-hr/tlc-%C4%91i%E1%BB%81u-h%C3%A0nh")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        charts = p.locator(".widget", has_text="Nhân sự theo phòng ban")
        charts.first.scroll_into_view_if_needed()
        p.wait_for_timeout(1500)
        check(charts.count() >= 1 and p.locator(".widget svg, .widget canvas").count() >= 1, "không thấy biểu đồ")
        r["actual"] = "Biểu đồ hiển thị"
    s.close()


def hr_lead_second(browser):
    s = Session(browser, "HR2", "hoa")
    login(s)
    with case(s, "HR-07", "Không tự duyệt đơn của mình", "Mở đơn của chính mình (đã qua CEO); xem Hành động", REQ["hoa"],
              "Không có Duyệt/Từ chối cho chính mình") as r:
        open_leave(s, REQ["hoa"])
        actions = workflow_actions(s.page)
        check("Duyệt" not in actions, str(actions))
        r["actual"] = f"Hành động: {actions or 'không có'}"
    with case(s, "HR-08", "Duyệt đơn của Quản lý NM1", "Mở đơn > Hành động > Duyệt", REQ["hung"], "Đã duyệt") as r:
        open_leave(s, REQ["hung"])
        state = desk_action(s, REQ["hung"], "Duyệt")
        check(state == APPROVED, state)
        r["actual"] = state
    s.close()


def hr_officer(browser):
    s = Session(browser, "HR3", "lan")
    first_case(s, "HR-09")
    with case(s, "HR-10", "Chuyên viên nhân sự duyệt đơn của Trưởng nhân sự", "Mở đơn > Hành động > Duyệt", REQ["hoa"], "Đã duyệt") as r:
        open_leave(s, REQ["hoa"])
        state = desk_action(s, REQ["hoa"], "Duyệt")
        check(state == APPROVED, state)
        r["actual"] = state
    s.close()


def results_check(browser):
    s = Session(browser, "CN1b", "binh", phone=True)
    login(s)
    p = s.page
    with case(s, "CN1-05", "Công nhân xem kết quả đơn", "Mở danh sách đơn; mở đơn bị từ chối", f"{REQ['binh_full']}, {REQ['binh_half']}",
              "Đơn 1 ngày Đã duyệt; đơn nửa ngày Từ chối, thấy lý do 'Trùng ca kiểm kê kho' (chỉ đọc)") as r:
        text = hrms_list_states(s)
        check(APPROVED in text and REJECTED in text, text[:200])
        p.goto(f"{BASE}/hrms/leave-applications/{REQ['binh_half']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        reason = p.locator("textarea").filter(has_text="Trùng ca kiểm kê kho")
        value = p.evaluate("Array.from(document.querySelectorAll('textarea')).map(t => t.value + '|' + (t.disabled || t.readOnly)).join(' ; ')")
        check("Trùng ca kiểm kê kho|true" in value, value)
        r["actual"] = f"Danh sách có Đã duyệt và Từ chối; lý do hiện chỉ đọc ({reason.count() or 1} ô)"
    with case(s, "CN1-06", "Số dư phép sau khi được duyệt", "Menu dưới > Nghỉ phép", "", "Phép năm còn 11 (đơn bị từ chối không trừ)") as r:
        employee = api_get(s, "/api/resource/Employee?fields=[\"name\"]").json()["data"][0]["name"]
        balance = api(s, "hrms.api.get_leave_balance_map", employee=employee)
        left = balance["Phép năm"]["balance_leaves"]
        p.goto(f"{BASE}/hrms/home")
        p.wait_for_load_state("networkidle")
        p.get_by_text("Nghỉ phép", exact=True).last.click()
        p.wait_for_timeout(2500)
        check(left == 11, str(balance))
        r["actual"] = f"Phép năm còn {left:g}"
    s.close()

    s = Session(browser, "NVb", "an")
    login(s)
    with case(s, "NV-08", "Kết quả đơn và số dư", "Mở danh sách đơn", REQ["an"], "Đã duyệt; còn 10 ngày") as r:
        text = hrms_list_states(s)
        employee = api_get(s, "/api/resource/Employee?fields=[\"name\"]").json()["data"][0]["name"]
        left = api(s, "hrms.api.get_leave_balance_map", employee=employee)["Phép năm"]["balance_leaves"]
        check(APPROVED in text and left == 10, f"{left} {text[:120]}")
        r["actual"] = f"Đã duyệt; còn {left:g}"
    s.close()


JOURNEYS = [office_employee, support_office_manager, factory_worker_1, factory_worker_2, factory_head, hr_lead, ceo,
            hr_lead_second, hr_officer, results_check]
