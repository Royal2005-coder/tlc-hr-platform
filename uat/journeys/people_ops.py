"""Desktop evidence through native Desk forms, lists and server validation for W5 People Operations."""
from lib import *


def _wait_form(p, doctype):
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d && !cur_frm.is_new()", arg=doctype)


def people_ops_desktop(browser):
    # 1. Employee Session (An)
    s = Session(browser, "W5-PEOPLE-OPS-AN", "an")
    login(s)

    # Asset Movement Dual Receipt - Employee side
    with case(
        s,
        "W5-ASSET-RECEIPT-HAPPY",
        "Nhân viên xác nhận bàn giao tài sản trên Desk",
        "Desk > Asset Movement > mở phiếu cấp phát > bấm Xác nhận bàn giao",
        "Phiếu cấp phát ThinkPad cho An",
        "Dấu thời gian tlc_ops_employee_ack được ghi nhận",
    ) as result:
        s.page.goto(f"{BASE}/desk/asset-movement")
        s.page.wait_for_load_state("networkidle")
        row = s.page.locator('.list-row-container a[data-doctype="Asset Movement"]').first
        check(row.count() > 0, "Không tìm thấy phiếu Asset Movement mẫu")
        row.click()
        _wait_form(s.page, "Asset Movement")
        REQ["w5_movement"] = s.page.evaluate("cur_frm.doc.name")

        # Click custom button Xác nhận bàn giao
        btn = s.page.locator('button:visible:has-text("Xác nhận bàn giao")').first
        if btn.count() > 0:
            btn.click()
            s.page.wait_for_timeout(1000)
            s.page.wait_for_load_state("networkidle")
        ack = s.page.evaluate("cur_frm.doc.tlc_ops_employee_ack")
        check(bool(ack), "Chưa ghi nhận thời gian xác nhận của nhân viên")
        result["actual"] = f"Biên bản bàn giao {REQ['w5_movement']}: nhân viên đã xác nhận lúc {ack}"

    # Policy Version Acknowledgment
    with case(
        s,
        "W5-POLICY-ACK-HAPPY",
        "Nhân viên xác nhận đã đọc đúng phiên bản chính sách",
        "Desk > TLC People Ops Acknowledgment > mở thông báo > bấm Tôi đã đọc đúng phiên bản",
        "Văn bản chính sách POL-TLC-2026 v1",
        "Ghi nhận acknowledged_at và người ký",
    ) as result:
        s.page.goto(f"{BASE}/desk/tlc-people-ops-acknowledgment")
        s.page.wait_for_load_state("networkidle")
        row = s.page.locator('.list-row-container a[data-doctype="TLC People Ops Acknowledgment"]').first
        check(row.count() > 0, "Không tìm thấy thông báo Acknowledgment mẫu")
        row.click()
        _wait_form(s.page, "TLC People Ops Acknowledgment")
        REQ["w5_ack"] = s.page.evaluate("cur_frm.doc.name")

        btn = s.page.locator('button:visible:has-text("Tôi đã đọc đúng phiên bản")').first
        if btn.count() > 0:
            btn.click()
            s.page.wait_for_timeout(1000)
            s.page.wait_for_load_state("networkidle")
        ack_time = s.page.evaluate("cur_frm.doc.acknowledged_at")
        check(bool(ack_time), "Chưa ghi nhận thời gian nhân viên đọc chính sách")
        result["actual"] = f"Chính sách đã xác nhận lúc {ack_time}"

    # Employee Grievance
    with case(
        s,
        "W5-GRIEVANCE-SUBMIT",
        "Nhân viên gửi phản ánh/khiếu nại nội bộ trên Desk",
        "Desk > Employee Grievance > Mới > nhập nội dung > Lưu",
        "Đề xuất cải thiện nhiệt độ phòng làm việc",
        "Hồ sơ ở trạng thái Open, chỉ người gửi và HR xem được",
    ) as result:
        s.page.goto(f"{BASE}/desk/employee-grievance/new")
        s.page.wait_for_load_state("networkidle")
        s.page.locator('[data-fieldname="subject"] input').fill("Đề xuất cải thiện nhiệt độ phòng làm việc UAT")
        s.page.locator('[data-fieldname="grievance_type"] input').fill("Cơ sở vật chất")
        s.page.locator('[data-fieldname="description"] textarea').fill("Khu vực làm việc nhiệt độ quá lạnh, cần điều chỉnh hướng gió.")
        s.page.keyboard.press("Control+s")
        s.page.wait_for_timeout(1500)
        s.page.wait_for_load_state("networkidle")
        REQ["w5_grievance"] = s.page.evaluate("cur_frm.doc.name")
        status = s.page.evaluate("cur_frm.doc.status")
        check(status == "Open", f"Trạng thái khiếu nại không phải Open: {status}")
        result["actual"] = f"Hồ sơ khiếu nại {REQ['w5_grievance']} tạo thành công ở trạng thái Open"

    s.close()

    # 2. HR Lead Session (Hoa)
    s = Session(browser, "W5-PEOPLE-OPS-LEAD", "hoa")
    login(s)

    with case(
        s,
        "W5-ASSET-RECEIPT-STAFF",
        "HR xác nhận bàn giao và hoàn tất biên bản hai bên",
        "Mở lại Asset Movement > bấm Xác nhận bàn giao",
        REQ.get("w5_movement", ""),
        "Dấu thời gian tlc_ops_staff_ack được ghi nhận; đủ 2 bên để ghi sổ",
    ) as result:
        check(bool(REQ.get("w5_movement")), "Case nhận tài sản chưa chạy")
        s.page.goto(f"{BASE}/desk/asset-movement/{REQ['w5_movement']}")
        _wait_form(s.page, "Asset Movement")
        btn = s.page.locator('button:visible:has-text("Xác nhận bàn giao")').first
        if btn.count() > 0:
            btn.click()
            s.page.wait_for_timeout(1000)
            s.page.wait_for_load_state("networkidle")
        staff_ack = s.page.evaluate("cur_frm.doc.tlc_ops_staff_ack")
        check(bool(staff_ack), "Chưa ghi nhận xác nhận của cán bộ phụ trách tài sản")
        result["actual"] = f"Biên bản bàn giao đã có đủ 2 bên: staff {staff_ack}"

    with case(
        s,
        "W5-LICENSE-CLEARANCE-BLOCKER",
        "Kiểm tra điều kiện thôi việc: phát hiện tài sản và tài khoản còn mở",
        "Gọi hàm kiểm tra clearance_blockers cho nhân viên An",
        "An đang giữ tài sản và tài khoản Google Workspace",
        "Danh sách blocker trả về đúng các mục tồn đọng",
    ) as result:
        an_employee = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "an@demo.example"]])).json()["data"][0]["name"]
        res = api(s, "tlc_hr.interface.people_ops.exit_clearance", employee=an_employee)
        check(isinstance(res, list) and res, f"exit_clearance không trả về danh sách tồn đọng: {res}")
        check(any(item.startswith(("Tài sản chưa thu hồi", "Biên bản bàn giao chưa ghi sổ")) for item in res)
              and any(item.startswith("Tài khoản chưa khóa") for item in res),
              f"Thiếu cảnh báo tài sản/bàn giao hoặc tài khoản: {res}")
        result["actual"] = f"{an_employee}: phát hiện {len(res)} mục tồn đọng cần bàn giao: {res[:2]}"

    s.close()

    # 3. Line Manager Session (Quang)
    s = Session(browser, "W5-PEOPLE-OPS-MANAGER", "quang")
    login(s)

    with case(
        s,
        "W5-DISCIPLINE-WORKFLOW",
        "Quản lý lập đề xuất kỷ luật theo quy trình",
        "Desk > TLC People Ops Discipline > Mới > chọn nhân viên > nhập lý do > Lưu",
        "Đề xuất kỷ luật nhân viên đi muộn nhiều lần",
        "Hồ sơ ở trạng thái Proposal, gửi HR Review",
    ) as result:
        s.page.goto(f"{BASE}/desk/tlc-people-ops-discipline/new")
        s.page.wait_for_load_state("networkidle")
        emp_name = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "an@demo.example"]])).json()["data"][0]["name"]
        s.page.locator('[data-fieldname="employee"] input').fill(emp_name)
        s.page.locator('[data-fieldname="reason"] textarea').fill("Đi muộn không phép 3 lần trong tháng 10/2026")
        s.page.keyboard.press("Control+s")
        s.page.wait_for_timeout(1500)
        s.page.wait_for_load_state("networkidle")
        REQ["w5_discipline"] = s.page.evaluate("cur_frm.doc.name")
        status = s.page.evaluate("cur_frm.doc.status")
        check(status == "Proposal", f"Trạng thái đề xuất không phải Proposal: {status}")
        result["actual"] = f"Đề xuất kỷ luật {REQ['w5_discipline']} lập thành công ở trạng thái Proposal"

    s.close()

    # 4. Unauthorized Access Check (Binh - Worker)
    s = Session(browser, "W5-PEOPLE-OPS-PERMISSION", "binh")
    login(s)

    with case(
        s,
        "W5-DISCIPLINE-PERMISSION",
        "Công nhân không xem được hồ sơ kỷ luật của người khác",
        "Nhập URL form hồ sơ kỷ luật của An từ Desk",
        REQ.get("w5_discipline", ""),
        "Server từ chối quyền đọc, hiển thị thông báo không có quyền",
    ) as result:
        check(bool(REQ.get("w5_discipline")), "Case tạo đề xuất kỷ luật chưa chạy")
        s.page.goto(f"{BASE}/desk/tlc-people-ops-discipline/{REQ['w5_discipline']}")
        s.page.wait_for_load_state("networkidle")
        text = s.page.locator("body").inner_text()
        check(any(w in text.lower() for w in ("permission", "not permitted", "không có quyền", "không được phép", "not allowed", "forbidden")), text[:300])
        result["actual"] = "Server phân quyền chặn truy cập: không thể đọc hồ sơ kỷ luật."

    s.close()


JOURNEYS = [people_ops_desktop]
