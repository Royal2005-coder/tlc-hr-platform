"""Desktop evidence through native Desk forms, lists, workflow menus and server validation dialogs."""
from lib import *


def _wait_form(p, doctype):
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d && !cur_frm.is_new()", arg=doctype)


def _open_seed_contract(p):
    p.goto(f"{BASE}/desk/tlc-employment-contract?contract_number=TLC-UAT-W4-001")
    p.wait_for_load_state("networkidle")
    p.locator('.list-row-container a[data-doctype="TLC Employment Contract"]').first.click()
    _wait_form(p, "TLC Employment Contract")


def _action(p, text):
    open_actions(p)
    p.locator(MENU_ITEMS).filter(has_text=text).first.click()
    p.wait_for_load_state("networkidle")


def lifecycle_desktop(browser):
    s = Session(browser, "W4-LIFECYCLE", "lan")
    login(s)
    with case(s, "W4-CORE-HAPPY", "HR tạo và gửi hợp đồng có chứng từ", "Desk > Hợp đồng TLC > mở hồ sơ mẫu > Gửi duyệt",
              "TLC-UAT-W4-001; chứng từ demo riêng tư", "Giữ số hợp đồng duy nhất và chuyển Chờ nhân sự duyệt") as result:
        _open_seed_contract(s.page)
        REQ["w4_contract"] = s.page.evaluate("cur_frm.doc.name")
        check(s.page.locator('[data-fieldname="evidence"] a').count() > 0, "Chưa có chứng từ trên form")
        state = s.page.evaluate("cur_frm.doc.workflow_state")
        if state == "Nháp":
            _action(s.page, "Gửi duyệt")
        check(s.page.evaluate("cur_frm.doc.workflow_state") == "Chờ nhân sự duyệt", "Không chuyển được HR review")
        result["actual"] = "Form chuẩn: số hợp đồng, ngày hiệu lực và chứng từ; đã gửi HR Lead."
    with case(s, "W4-CORE-ERROR", "Không lưu hợp đồng thiếu chứng từ", "Desk > Mới > điền số và nhân viên > để trống chứng từ > Lưu",
              "Hợp đồng mới không có file", "Native bắt buộc chứng từ, không tạo hợp đồng") as result:
        s.page.goto(f"{BASE}/desk/tlc-employment-contract/new")
        s.page.wait_for_load_state("networkidle")
        s.page.keyboard.press("Control+s")
        expect(s.page.locator('.modal:visible')).to_be_visible()
        text = s.page.locator('.modal:visible').inner_text()
        check("Evidence" in text or "chứng" in text.lower() or "Bằng chứng" in text, text)
        check(s.page.evaluate("cur_frm.is_new()"), "Đã tạo hồ sơ thiếu chứng từ")
        result["actual"] = text[:250]
    s.close()
    s = Session(browser, "W4-LIFECYCLE-LEAD", "hoa")
    login(s)
    with case(s, "W4-CORE-APPROVE", "HR Lead duyệt hợp đồng", "Mở hồ sơ đã gửi > Hành động > Duyệt",
              REQ.get("w4_contract", ""), "Hợp đồng submitted, dữ liệu không còn sửa tự do") as result:
        check(bool(REQ.get("w4_contract")), "Case tạo/gửi hợp đồng chưa thành công")
        s.page.goto(f"{BASE}/desk/tlc-employment-contract/{REQ['w4_contract']}")
        _wait_form(s.page, "TLC Employment Contract")
        _action(s.page, "Duyệt")
        check(s.page.evaluate("cur_frm.doc.docstatus") == 1, "Chưa duyệt/nộp")
        check(s.page.locator('[data-fieldname="contract_number"] input:visible:not([readonly])').count() == 0, "Số hợp đồng vẫn sửa được")
        result["actual"] = "Đã duyệt; bản ghi submitted giữ lịch sử/chứng từ."
    s.close()
    s = Session(browser, "W4-LIFECYCLE-PERMISSION", "binh")
    login(s)
    with case(s, "W4-CORE-PERMISSION", "Công nhân không đọc hợp đồng người khác", "Nhập URL form hợp đồng của An từ Desktop",
              REQ.get("w4_contract", ""), "Không trả dữ liệu hợp đồng và chứng từ") as result:
        check(bool(REQ.get("w4_contract")), "Không có hồ sơ quyền để thử")
        s.page.goto(f"{BASE}/desk/tlc-employment-contract/{REQ['w4_contract']}")
        s.page.wait_for_load_state("networkidle")
        body = s.page.locator("body").inner_text()
        check("TLC-UAT-W4-001" not in body, "Lộ dữ liệu hợp đồng người khác")
        check(any(word in body.lower() for word in ("permission", "not permitted", "không có quyền", "không được phép", "not allowed", "forbidden")), body[:300])
        result["actual"] = body[:250]
    s.close()


def lifecycle_boarding_desktop(browser):
    s = Session(browser, "W4-BOARDING", "lan")
    login(s)
    with case(s, "W4-EXIT-HAPPY", "HR kiểm tra ngày báo trước và hạn quyết toán", "Desk > Nghỉ việc > hồ sơ mẫu > xem ngày được tính",
              "Hợp đồng không xác định thời hạn; 45 ngày báo trước", "Ngày sớm nhất và hạn thanh toán hiện trên form chuẩn") as result:
        s.page.goto(f"{BASE}/desk/employee-separation?custom_tlc_reason=TLC%20UAT%20W4%20notice%20and%20clearance")
        s.page.wait_for_load_state("networkidle")
        s.page.locator('.list-row-container a[data-doctype="Employee Separation"]').first.click()
        _wait_form(s.page, "Employee Separation")
        REQ["w4_separation"] = s.page.evaluate("cur_frm.doc.name")
        dates = s.page.evaluate("({earliest:cur_frm.doc.custom_tlc_earliest_last_day,last:cur_frm.doc.custom_tlc_last_day,due:cur_frm.doc.custom_tlc_settlement_due})")
        check(dates["earliest"] == dates["last"] and bool(dates["due"]), str(dates))
        result["actual"] = str(dates)
    with case(s, "W4-EXIT-ERROR", "Ngoại lệ pháp lý không có chứng từ bị chặn", "Trên form > chọn ngoại lệ luật > Lưu",
              "Statutory employee exception; thiếu hồ sơ/xác nhận", "Thông báo EXIT-LEGAL, không lưu ngoại lệ") as result:
        s.page.locator('[data-fieldname="custom_tlc_notice_exception"] select').select_option("Statutory employee exception")
        s.page.keyboard.press("Control+s")
        expect(s.page.locator(".modal:visible")).to_be_visible()
        text = s.page.locator(".modal:visible").inner_text()
        check("EXIT-LEGAL" in text, text)
        result["actual"] = text[:250]
    s.close()
    s = Session(browser, "W4-ONBOARDING", "lan")
    login(s)
    with case(s, "W4-OB-HAPPY", "HR mở onboarding từ offer đã được chấp nhận", "Desk > Employee Onboarding > lọc ứng viên tuyển dụng demo > mở",
              "recruitment.candidate@demo.example; chạy recruitment journey trước", "Form native giữ liên kết offer/ứng viên và ngày nhận việc") as result:
        s.page.goto(f"{BASE}/desk/employee-onboarding?job_applicant=recruitment.candidate%40demo.example")
        s.page.wait_for_load_state("networkidle")
        s.page.locator('.list-row-container a[data-doctype="Employee Onboarding"]').first.click()
        _wait_form(s.page, "Employee Onboarding")
        REQ["w4_onboarding"] = s.page.evaluate("cur_frm.doc.name")
        data = s.page.evaluate("({offer:cur_frm.doc.job_offer,applicant:cur_frm.doc.job_applicant,joining:cur_frm.doc.date_of_joining})")
        check(data["offer"] and data["applicant"] and data["joining"], str(data))
        result["actual"] = str(data)
    with case(s, "W4-OB-ERROR", "Xác nhận hồ sơ onboarding không có file bị chặn", "Thêm dòng bằng grid native > xác nhận đã nhận > không đính file > Lưu",
              "Required Document Received, thiếu attachment", "Thông báo LC-EVIDENCE; không ghi nhận thay người khác") as result:
        check(bool(REQ.get("w4_onboarding")), "Recruitment chưa tạo onboarding")
        grid = s.page.locator('[data-fieldname="custom_tlc_evidence"]')
        grid.locator(".grid-add-row").click()
        row = grid.locator(".grid-row").last
        row.locator('[data-fieldname="item"] input').fill("UAT missing identity evidence")
        row.locator('[data-fieldname="category"] select').select_option("Document")
        row.locator('[data-fieldname="status"] select').select_option("Received")
        s.page.keyboard.press("Control+s")
        expect(s.page.locator(".modal:visible")).to_be_visible()
        text = s.page.locator(".modal:visible").inner_text()
        check("LC-EVIDENCE" in text, text)
        result["actual"] = text[:250]
    s.close()
    s = Session(browser, "W4-BOARDING-PERMISSION", "binh")
    login(s)
    for key, route, case_id in (("w4_separation", "employee-separation", "W4-EXIT-PERMISSION"),
                                 ("w4_onboarding", "employee-onboarding", "W4-OB-PERMISSION")):
        with case(s, case_id, "Công nhân không xem hồ sơ vòng đời người khác", "Nhập URL form native của người khác",
                  REQ.get(key, ""), "Server từ chối quyền đọc") as result:
            check(bool(REQ.get(key)), "Chưa có hồ sơ cần kiểm tra quyền")
            s.page.goto(f"{BASE}/desk/{route}/{REQ[key]}")
            s.page.wait_for_load_state("networkidle")
            text = s.page.locator("body").inner_text()
            check(any(word in text.lower() for word in ("permission", "not permitted", "không có quyền", "không được phép", "not allowed", "forbidden")), text[:300])
            result["actual"] = text[:250]
    s.close()


JOURNEYS = [lifecycle_desktop, lifecycle_boarding_desktop]
