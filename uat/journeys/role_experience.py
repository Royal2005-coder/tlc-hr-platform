"""W8 desktop-native role surfaces. Navigation and evidence are real browser actions.

API reads only supply cross-factory fixture identifiers and independently compare
permission-scoped counts; no API calls substitute for the recorded native navigation.
"""

from urllib.parse import quote

from lib import *  # noqa: F403


def workspace(s, title):
    s.page.goto(f"{BASE}/desk/{quote(title.lower().replace(' ', '-'))}")
    s.page.wait_for_load_state("networkidle")
    expect(s.page.get_by_text(title, exact=True).last).to_be_visible()


def shortcut(s, label, route):
    p = s.page
    try:
        with s.context.expect_page(timeout=6000) as info:
            p.get_by_text(label, exact=True).first.click()
        popup = info.value
    except Exception:
        popup = None
    if popup is not None:
        # URL shortcuts open the native app in a new tab; verify it, then show the same destination here.
        popup.wait_for_load_state("networkidle")
        check(route in popup.url, f"Native destination is {popup.url}")
        check(not re.search(r"Not permitted|Insufficient Permission|Không có quyền", popup.locator("body").inner_text(), re.I),
              "Native destination denied")
        popup.close()
        p.goto(f"{BASE}{route}")
    else:
        p.wait_for_url(lambda url: route in url, timeout=15000)
    p.wait_for_load_state("networkidle")
    check(not re.search(r"Not permitted|Insufficient Permission|Không có quyền", p.locator("body").inner_text(), re.I), "Native destination denied")


def employee_surfaces(browser):
    for index, account in enumerate(("binh", "f2w01", "f3w01", "an"), 1):
        s = Session(browser, "ROLE-ESS", account)
        try:
            with case(s, f"RX-{index:02d}", "Nhân viên dùng trang chủ HR và Desk bổ sung", "Đăng nhập /hrms; mở workspace Cá nhân; bấm số dư phép, phiếu lương, tăng ca và việc được giao", account,
                      "Trang chủ HR gốc; các shortcut mở đúng màn hình gốc; không có portal TLC riêng") as result:
                login(s)
                check("/hrms" in s.page.url, "Nhân viên không vào HRMS mặc định")
                own = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", account + "@demo.example"]])).json().get("data", [])
                check(len(own) == 1, "Không xác định được nhân viên gắn user")
                REQ["role_employee_" + account] = own[0]["name"]
                for label, route in (("ESS Số dư và đơn nghỉ", "/hrms/dashboard/leaves"), ("ESS Phiếu lương của tôi", "/hrms/dashboard/salary-slips"),
                                     ("ESS Đồng ý tăng ca", "/tlc-overtime-request"), ("ESS Việc được giao", "/todo")):
                    workspace(s, "TLC Cá nhân")
                    shortcut(s, label, route)
                result["actual"] = "Đã điều hướng bằng shortcut: HRMS nghỉ phép/phiếu lương và Desk tăng ca/ToDo; không khẳng định đã duyệt hay trả lương."
        finally:
            s.close()


def factory_surfaces(browser):
    accounts = (("hung", "binh", "f2w01"), ("nm2", "f2w01", "f3w01"), ("nm3", "f3w01", "binh"))
    for index, (account, own_worker, other_worker) in enumerate(accounts, 11):
        s = Session(browser, "ROLE-FACTORY", account)
        try:
            with case(s, f"RX-{index}", "Nhà máy có hàng đợi và phạm vi riêng", "Mở Nhà máy; xem thẻ; bấm nhân sự, ngoại lệ, chốt công và duyệt phép; thử mở hồ sơ nhân viên nhà máy khác", account,
                      "Thẻ nhân sự khớp số người có quyền; danh sách đúng phạm vi; hồ sơ nhà máy khác bị từ chối trên UI") as result:
                login(s)
                workspace(s, "TLC Nhà máy")
                count = card_value(s.page, "Nhà máy nhân sự trong phạm vi")
                scoped = api_get(s, "/api/resource/Employee?fields=" + json.dumps(["name"]) + "&filters=" + json.dumps([["status", "=", "Active"], ["tlc_workforce", "=", "factory"]]) + "&limit_page_length=500").json().get("data", [])
                names = {row["name"] for row in scoped}
                own_name, other_name = REQ.get("role_employee_" + own_worker), REQ.get("role_employee_" + other_worker)
                check(own_name and other_name, "Chạy employee_surfaces trước để có fixture scope")
                check(count == len(names) and own_name in names and other_name not in names, "Số liệu nhà máy bị lẫn phạm vi hoặc sai count")
                for label, route in (("Nhà máy nhân sự và định biên", "/employee"), ("Nhà máy bảng công ngoại lệ", "/attendance"),
                                     ("Nhà máy chốt kỳ công", "/tlc-attendance-period"), ("Nhà máy duyệt phép", "/leave-application")):
                    workspace(s, "TLC Nhà máy")
                    shortcut(s, label, route)
                s.page.goto(f"{BASE}/desk/employee/{quote(other_name)}")
                s.page.wait_for_load_state("networkidle")
                expect(s.page.locator("body")).to_contain_text(re.compile("Not permitted|Insufficient Permission|Không có quyền|không được phép", re.I))
                result["actual"] = f"{account}: thẻ {count} = số Employee được cấp quyền; có nhân viên của mình, không có nhà máy khác; UI từ chối hồ sơ khác nhà máy."
        finally:
            s.close()


def administrative_surfaces(browser):
    targets = (
        ("hoa", "TLC HR Hạn xử lý", "RX-21", ("HR Việc mở đến hạn tuần này", "HR Việc mở quá hạn"), (("HR Theo dõi hạn công việc", "/todo"), ("HR Hội nhập", "/employee-onboarding"), ("HR Nghỉ việc", "/employee-separation"))),
        ("lan", "TLC HR Hạn xử lý", "RX-22", ("HR Việc mở quá hạn",), (("HR Theo dõi hạn công việc", "/todo"), ("HR Tuyển dụng", "/job-opening"))),
        ("thanh", "TLC CEO Chi phí", "RX-23", ("Điều hành lương gross tháng này", "Bảng lương chờ ký", "Kỳ công chờ ký"), (("Điều hành chi phí lương", "/salary-slip"), ("Điều hành ký bảng lương", "/payroll-entry"), ("Điều hành duyệt tăng ca", "/tlc-overtime-request"))),
        ("phuong", "TLC Tác nghiệp lương", "RX-24", ("Bảng lương chờ chi",), (("Điều hành ký bảng lương", "/payroll-entry"),)),
        ("chi", "TLC Kế toán chi trả", "RX-25", ("Bảng lương chờ chi",), (("Kế toán tạm ứng", "/employee-advance"), ("Kế toán quyết toán chi phí", "/expense-claim"))),
        ("quang", "TLC Quản lý", "RX-26", ("Đơn chờ tôi duyệt",), (("Đơn chờ duyệt", "/leave-application"),)),
    )
    for account, title, cid, cards, links in targets:
        s = Session(browser, "ROLE-DESK", account)
        try:
            with case(s, cid, "Màn hình công việc đúng vai trò", "Đăng nhập Desk; mở workspace; đọc thẻ và bấm từng shortcut nghiệp vụ", account + ": " + title,
                      "Thẻ có dữ liệu số; shortcut vào màn hình Frappe được cấp quyền, không giả lập hành động phê duyệt") as result:
                login(s)
                workspace(s, title)
                for card in cards:
                    card_value(s.page, card)
                for label, route in links:
                    workspace(s, title)
                    shortcut(s, label, route)
                result["actual"] = f"Đã mở {title}, đọc {len(cards)} thẻ, điều hướng {len(links)} màn hình native. Gross/net không được gọi là tổng chi phí lao động."
        finally:
            s.close()


JOURNEYS = [employee_surfaces, factory_surfaces, administrative_surfaces]
