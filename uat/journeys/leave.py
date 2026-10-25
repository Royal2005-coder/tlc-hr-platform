"""Leave (TLC Nghỉ phép): request in the Frappe HR app, line manager then HR, reject with a reason, scope, balances.

Every demonstrated action is performed on screen (the recording is the evidence): requests are filled and saved in the
app, approvals/rejections go through `Hành động` and the workflow button on the desk form, the balance and the
duplicate-day block are read from what the screen shows. The API is used only to prepare fixtures and to confirm the
stored result after a person has actually done the work.
"""

from lib import *  # noqa: F403

# ---------------------------------------------------------------------------------------------------- UI-first helpers


def page_head_text(p):
    """The workflow state the user reads in the form header after an action (best effort, for the recording)."""
    try:
        return " ".join(" ".join(t.split()) for t in
                        p.locator(".page-head, .indicator-pill, .form-title, .title-text, .form-message").all_inner_texts())
    except Exception:
        return ""


def open_app_leaves(s):
    """Frappe HR app: click the bottom-nav `Nghỉ phép` (a real click) and return the rendered text of that page."""
    p = s.page
    p.goto(f"{BASE}/hrms/home")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(600)
    p.get_by_text("Nghỉ phép", exact=True).last.click()
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2500)
    return " ".join(p.locator("body").inner_text().split())


def app_leave_balance(s, expected, leave_type="Phép năm", total=12):
    """Read the balance ratio the app shows on the `Nghỉ phép` card (the big "còn / tổng" number above the label)."""
    text = open_app_leaves(s)
    idx = text.find(leave_type)
    check(idx >= 0, f"không thấy {leave_type} trên màn hình: {text[:160]}")
    window = text[max(0, idx - 70): idx + len(leave_type) + 12]
    match = re.search(r"(\d+)\s*/\s*(\d+)", window)
    check(match, f"không thấy dạng 'còn / tổng' cạnh {leave_type}: {window}")
    available, allocated = int(match.group(1)), int(match.group(2))
    check(available == expected and allocated == total,
          f"số dư trên màn hình {available}/{allocated}, cần {expected}/{total}: {window}")
    return f"{available}/{allocated}"


def visible_error_text(p):
    """Whatever validation message the interface shows to the user after a rejected save (toast / dialog / inline error)."""
    found = []
    for sel in (".toast-message:visible", ".toast:visible", ".frappe-toast:visible", ".msgprint:visible", ".modal:visible",
                ".text-danger:visible", ".error-message:visible", "[role=alert]:visible", ".indicator-red:visible",
                ".form-message:visible"):
        try:
            for el in p.locator(sel).all():
                found.append(" ".join(el.inner_text().split()))
        except Exception:
            pass
    return " | ".join(x for x in found if x)


def reason_on_screen(p, needle):
    """Value and read-only state of the on-screen field that carries the rejection reason (a read-only textarea)."""
    areas = p.locator("textarea")
    for i in range(areas.count()):
        try:
            value = areas.nth(i).input_value() or ""
        except Exception:
            value = ""
        if needle in value:
            try:
                editable = areas.nth(i).is_editable()
            except Exception:
                editable = True
            return value, editable
    return "", True


def desk_reject(s, name, reason, doctype="Leave Application"):
    """Hành động > Từ chối on the desk form: the dialog asks for the mandatory reason, the reason is typed, confirm.

    Returns (new state, dialog text) so the recording shows the prompt and the typed reason.
    """
    p = s.page
    open_actions(p)
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == "Từ chối"), None)
    check(target is not None, f"không có Từ chối trong {menu_items(p)}")
    items.nth(target).click()
    dialog = p.locator(".modal:visible").last
    expect(dialog).to_be_visible()
    p.wait_for_timeout(600)
    dialog_text = " ".join(dialog.inner_text().split())
    check("Lý do" in dialog_text, f"hộp thoại từ chối không hỏi lý do: {dialog_text[:140]}")
    dialog.locator("textarea").first.fill(reason)
    dialog.get_by_role("button", name="Từ chối").last.click()
    p.wait_for_timeout(3500)
    return doc_state(s, doctype, name), dialog_text


# ---------------------------------------------------------------------------------------------------- office employee


def office_employee(browser):
    s = Session(browser, "NV", "an")
    first_case(s, "NV-01")
    p = s.page
    with case(s, "NV-02", "Trang chủ app Frappe HR", "Đọc lời chào, liên kết nhanh, thanh menu dưới; bấm liên kết Xin nghỉ phép", "",
              "Lời chào đúng tên; có Xin nghỉ phép, Xem phiếu lương; menu Trang chủ / Chấm công / Nghỉ phép / Chi phí / Lương") as r:
        s.step("An đọc trang chủ app Frappe HR rồi bấm liên kết nhanh Xin nghỉ phép")
        text = p.locator("body").inner_text()
        for t in ("Nguyễn Hoài An", "Xin nghỉ phép", "Xem phiếu lương", "Trang chủ", "Nghỉ phép", "Lương"):
            check(t in text, f"thiếu {t}")
        p.get_by_text("Xin nghỉ phép", exact=True).first.click()
        p.wait_for_url(re.compile(r".*/leave-applications/new"), timeout=30000)
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1200)
        r["actual"] = "Lời chào, liên kết nhanh và menu dưới đầy đủ (tiếng Việt); liên kết Xin nghỉ phép mở form đơn"
    with case(s, "NV-03", "Số dư phép", "Menu dưới > Nghỉ phép, đọc thẻ số dư Phép năm", "", "Phép năm còn 12 / 12 ngày") as r:
        s.step("An mở mục Nghỉ phép để xem số dư phép năm")
        segment = app_leave_balance(s, 12)
        r["actual"] = f"Trang Phép hiển thị {segment}"
    start, end = working_day(3), working_day(4)
    with case(s, "NV-04", "Xin nghỉ 2 ngày và gửi duyệt", "Xin nghỉ phép > Loại Phép năm, ngày, lý do > Lưu > Hành động > Gửi duyệt",
              f"{vn(start)} → {vn(end)}, Việc gia đình", "Đơn 2 ngày ở trạng thái Chờ quản lý duyệt, người duyệt Trần Minh Quang") as r:
        s.step("An điền đơn nghỉ 2 ngày rồi bấm Lưu và Gửi duyệt")
        REQ["an"] = hrms_request_leave(s, start, end, "Việc gia đình")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['an']}").json()["data"]
        check((doc["workflow_state"], doc["total_leave_days"], doc["leave_approver"]) == (TO_MANAGER, 2, "quang@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['an']}: {doc['workflow_state']}, {doc['total_leave_days']:g} ngày, duyệt bởi {doc['leave_approver']}"
    with case(s, "NV-05", "Chặn đơn trùng ngày", "Xin nghỉ lại đúng ngày đã xin, bấm Lưu, đọc thông báo", vn(start),
              "Không lưu được: màn hình báo đã có đơn trong khoảng ngày này") as r:
        s.step("An thử xin nghỉ lại đúng ngày đã có đơn và bấm Lưu")
        before = len(api_get(s, "/api/resource/Leave Application?limit_page_length=500").json()["data"])
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
        shown = visible_error_text(p)
        joined = " ".join(p.locator("body").inner_text().split())
        check("/new" in p.url, f"đã lưu: {p.url}")
        # the interface shows the duplicate inline in red: "Nhân viên ... đã đăng ký Phép năm từ ... đến ...: HR-LAP-..."
        pos = joined.find("đã đăng ký")
        if pos < 0:
            pos = joined.lower().find("already applied")
        snippet = joined[max(0, pos - 30): pos + 130] if pos >= 0 else (shown or joined[-160:])
        check(any(k in joined.lower() for k in ("đã đăng ký", "already applied", "error creating")) or REQ.get("an", "@") in joined,
              f"không đọc được thông báo trùng trên màn hình: {snippet}")
        after = len(api_get(s, "/api/resource/Leave Application?limit_page_length=500").json()["data"])
        check(after == before, f"số đơn thay đổi {before} -> {after}")
        r["actual"] = f"Không lưu được; thông báo trên màn hình: {snippet[:160]}"
    with case(s, "NV-06", "Theo dõi đơn của tôi", "Bấm Nghỉ phép, mở danh sách đơn nghỉ", "", f"Thấy đơn {vn(start)} ở trạng thái Chờ quản lý duyệt") as r:
        s.step("An mở danh sách đơn nghỉ để theo dõi tiến trình")
        text = open_app_leaves(s)
        if TO_MANAGER not in text:
            p.goto(f"{BASE}/hrms/leave-applications")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2500)
            text = " ".join(p.locator("body").inner_text().split())
        check(TO_MANAGER in text, text[:200])
        r["actual"] = "Danh sách có đơn đang Chờ quản lý duyệt"
    with case(s, "NV-07", "Phạm vi dữ liệu", "Đọc trang chủ + mở danh sách nghỉ; đối chiếu bằng API", "", "Chỉ thấy hồ sơ và đơn của chính mình") as r:
        s.step("An kiểm tra mình chỉ nhìn thấy dữ liệu của chính mình")
        p.goto(f"{BASE}/hrms/home")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1000)
        home = p.locator("body").inner_text()
        check("Nguyễn Hoài An" in home and "Trần Văn Bình" not in home, home[:120])
        open_app_leaves(s)  # real click: the employee opens their own leaves page
        check("Trần Văn Bình" not in p.locator("body").inner_text(), "thấy người khác trên màn hình")
        employees = api_get(s, "/api/resource/Employee?limit_page_length=500").json()["data"]
        leaves = api_get(s, "/api/resource/Leave Application?limit_page_length=500&fields=[\"employee_name\"]").json()["data"]
        check(len(employees) == 1 and {x["employee_name"] for x in leaves} <= {"Nguyễn Hoài An"}, f"{len(employees)} hồ sơ")
        r["actual"] = f"Màn hình chỉ có hồ sơ của An; API đối chiếu {len(employees)} hồ sơ, {len(leaves)} đơn của chính mình"
    s.close()


# ---------------------------------------------------------------------------------------------------- support office manager


def support_office_manager(browser):
    """Support role (recorded): the head of sales, line manager of the office employee, approves her request on the desk."""
    s = Session(browser, "TP", "quang")
    login(s)
    with case(s, "HT-01", "Trưởng phòng duyệt đơn của nhân viên văn phòng", "Workspace TLC Quản lý > mở đơn > Hành động > Duyệt",
              REQ.get("an", ""), "Đơn chuyển Chờ nhân sự duyệt") as r:
        s.step("Anh Quang mở đơn của An trong form desk")
        open_leave(s, REQ["an"])
        s.step("Anh Quang bấm Hành động > Duyệt")
        state = desk_action(s, REQ["an"], "Duyệt")
        check(state == TO_HR, state)
        r["actual"] = f"{REQ['an']} → {state} · trên form: {page_head_text(s.page)[:80]}"
    s.close()


# ---------------------------------------------------------------------------------------------------- factory worker 1


def factory_worker_1(browser):
    s = Session(browser, "CN1", "binh", phone=True)
    first_case(s, "CN1-01")
    day, half = working_day(2), working_day(5)
    with case(s, "CN1-02", "Công nhân xin nghỉ 1 ngày trong app Frappe HR", "Xin nghỉ phép > Lưu > Hành động > Gửi duyệt", f"{vn(day)}, Con ốm",
              "Chờ quản lý duyệt, người duyệt Đặng Văn Hùng") as r:
        s.step("Anh Bình điền đơn nghỉ 1 ngày trên app rồi Gửi duyệt")
        REQ["binh_full"] = hrms_request_leave(s, day, day, "Con ốm")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_full']}").json()["data"]
        check((doc["workflow_state"], doc["leave_approver"]) == (TO_MANAGER, "hung@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['binh_full']}: {doc['workflow_state']}, duyệt bởi {doc['leave_approver']}"
    with case(s, "CN1-03", "Xin nghỉ nửa ngày", "Xin nghỉ phép, tích Nửa ngày > Lưu > Gửi duyệt", f"{vn(half)}, Khám sức khỏe",
              "0,5 ngày, Chờ quản lý duyệt") as r:
        s.step("Anh Bình xin nghỉ nửa ngày, chọn Nửa ngày và Gửi duyệt")
        REQ["binh_half"] = hrms_request_leave(s, half, half, "Khám sức khỏe", half=True)
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_half']}").json()["data"]
        check((doc["workflow_state"], doc["total_leave_days"]) == (TO_MANAGER, 0.5), str(doc)[:200])
        r["actual"] = f"{REQ['binh_half']}: {doc['total_leave_days']:g} ngày, {doc['workflow_state']}"
    with case(s, "CN1-04", "Không tự duyệt được", "Mở mục Nghỉ phép, mở đơn của mình, bấm Hành động xem có nút Duyệt không", REQ["binh_full"],
              "Không có nút Duyệt cho chính mình") as r:
        s.step("Anh Bình mở lại đơn của mình và thử bấm Hành động để tự duyệt")
        open_app_leaves(s)  # real click into the employee's own leaves area
        s.page.goto(f"{BASE}/hrms/leave-applications/{REQ['binh_full']}")
        s.page.wait_for_load_state("networkidle")
        s.page.wait_for_timeout(2000)
        opened = open_actions(s.page)
        actions = menu_items(s.page) if opened else []
        s.page.keyboard.press("Escape")
        buttons = [b.inner_text().strip() for b in s.page.locator("button").all() if b.is_visible()]
        check("Duyệt" not in actions and "Duyệt" not in buttons, f"có nút duyệt: {actions} {buttons}")
        r["actual"] = f"Hành động: {actions or 'không có'}; các nút: {[b for b in buttons if b][-3:]}"
    s.close()


# ---------------------------------------------------------------------------------------------------- factory worker 2


def factory_worker_2(browser):
    s = Session(browser, "CN2", "f2w01", phone=True)
    first_case(s, "CN2-01")
    day = working_day(2)
    with case(s, "CN2-02", "Xin nghỉ (Nhà máy 2)", "Xin nghỉ phép > Lưu > Gửi duyệt", f"{vn(day)}, Về quê", "Đơn đến quản lý Nhà máy 2 (nm2)") as r:
        s.step("Công nhân Nhà máy 2 điền đơn nghỉ và Gửi duyệt")
        REQ["f2w01"] = hrms_request_leave(s, day, day, "Về quê")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['f2w01']}").json()["data"]
        check(doc["leave_approver"] == "nm2@demo.example" and doc["workflow_state"] == TO_MANAGER, str(doc)[:200])
        r["actual"] = f"{REQ['f2w01']} → nm2@demo.example, {doc['workflow_state']}"
    with case(s, "CN2-03", "Cách ly dữ liệu giữa hai nhà máy", "Mở mục Nghỉ phép (chỉ thấy đơn mình); thử mở đơn Nhà máy 1 (403)", REQ["binh_full"],
              "Danh sách trên màn hình không có đơn Nhà máy 1; đối tượng nghiệm thu là trả lời 403 của server khi mở trực tiếp") as r:
        s.step("Công nhân Nhà máy 2 mở danh sách nghỉ của mình, rồi thử mở đơn của Nhà máy 1")
        open_app_leaves(s)  # real click: the worker checks what their own list shows
        check("Trần Văn Bình" not in s.page.locator("body").inner_text(), "danh sách hiện đơn nhà máy khác")
        status = api_get(s, f"/api/resource/Leave Application/{REQ['binh_full']}").status
        check(status == 403, str(status))
        r["actual"] = f"Danh sách chỉ có đơn của mình; server trả {status} khi mở đơn Nhà máy 1"
    s.close()


# ---------------------------------------------------------------------------------------------------- factory head


def factory_head(browser):
    s = Session(browser, "QL", "hung")
    first_case(s, "QL-01")
    p = s.page
    with case(s, "QL-02", "Workspace TLC Quản lý", "Đọc thẻ số; bấm thẻ Đơn chờ tôi duyệt mở danh sách", "",
              "Thẻ đơn chờ tôi duyệt và thẻ nhân sự trong phạm vi bằng đúng số server trả cho hung; danh sách có 2 đơn của Trần Văn Bình") as r:
        s.step("Anh Hùng đọc các thẻ số trên workspace TLC Quản lý")
        mine = card_value(p, "Đơn chờ tôi duyệt")
        staff = card_value(p, "Nhân sự đang làm việc")
        quick = p.locator(".widget", has_text="Đơn chờ quản lý duyệt").last.inner_text()
        server = (len(list_of(s, "Leave Application", filters={"workflow_state": TO_MANAGER, "leave_approver": "hung@demo.example"},
                              fields=["name"], limit=500)),
                  len(list_of(s, "Employee", filters={"status": "Active", "tlc_workforce": "factory"}, fields=["name"], limit=500)))
        check((mine, staff) == server and server[0] >= 2 and quick.count("Trần Văn Bình") >= 2 and "Nhà máy 2" not in quick,
              f"thẻ ({mine}, {staff}) ≠ server {server} · {quick[:160]}")
        s.step("Anh Hùng bấm thẻ Đơn chờ tôi duyệt để mở danh sách đơn chờ")
        p.locator(".widget", has_text="Đơn chờ tôi duyệt").first.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        r["actual"] = f"Đơn chờ tôi duyệt {mine}; nhân sự {staff}; danh sách có 2 đơn của Bình"
    with case(s, "QL-03", "Hỗ trợ quyết định trên form", "Mở đơn 1 ngày của Bình", REQ["binh_full"],
              "Dòng đầu form: số dư sau khi duyệt 11 / 12 ngày; không ai khác ở Nhà máy 1 nghỉ; nút Hành động có Duyệt, Từ chối") as r:
        s.step("Anh Hùng mở đơn 1 ngày của Bình để xem dòng hỗ trợ quyết định")
        open_leave(s, REQ["binh_full"])
        text = headline(p)
        actions = workflow_actions(p)
        check("11 / 12" in text and "Không ai khác" in text and {"Duyệt", "Từ chối"} <= set(actions), f"{text} | {actions}")
        r["actual"] = f"{text} · Hành động: {', '.join(actions)}"
    with case(s, "QL-04", "Duyệt đơn", "Hành động > Duyệt", REQ["binh_full"], "Chờ nhân sự duyệt") as r:
        s.step("Anh Hùng bấm Hành động > Duyệt đơn của Bình")
        state = desk_action(s, REQ["binh_full"], "Duyệt")
        check(state == TO_HR, state)
        r["actual"] = f"{state} · trên form: {page_head_text(p)[:80]}"
    with case(s, "QL-05", "Từ chối phải có lý do", "Mở đơn nửa ngày > Hành động > Từ chối > nhập lý do > Từ chối", "Trùng ca kiểm kê kho",
              "Hộp thoại hỏi lý do; đơn Từ chối, lý do được lưu") as r:
        s.step("Anh Hùng mở đơn nửa ngày và bấm Hành động > Từ chối")
        open_leave(s, REQ["binh_half"])
        state, dialog_text = desk_reject(s, REQ["binh_half"], "Trùng ca kiểm kê kho")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_half']}").json()["data"]
        check(state == REJECTED and doc.get("tlc_reject_reason") == "Trùng ca kiểm kê kho", f"{state} {doc.get('tlc_reject_reason')}")
        r["actual"] = f"Hộp thoại '{dialog_text[:70]}' → {state}; lý do lưu: {doc['tlc_reject_reason']}"
    with case(s, "QL-06", "Không xem được đơn của nhà máy khác", "Mở danh sách Đơn chờ tôi duyệt (chỉ phạm vi nhà máy mình); thử mở đơn Nhà máy 2 (403)", REQ["f2w01"],
              "Danh sách trên màn hình chỉ có đơn Nhà máy 1; đối tượng nghiệm thu là trả lời 403 của server khi mở trực tiếp đơn Nhà máy 2") as r:
        s.step("Anh Hùng mở danh sách đơn chờ của mình, rồi thử mở đơn của Nhà máy 2")
        p.goto(f"{BASE}/desk/tlc-hr/tlc-qu%E1%BA%A3n-l%C3%BD")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        p.locator(".widget", has_text="Đơn chờ tôi duyệt").first.click()  # real click: opens the scoped queue
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        check("Nhà máy 2" not in p.locator("body").inner_text(), "danh sách thấy nhà máy khác")
        status = api_get(s, f"/api/resource/Leave Application/{REQ['f2w01']}").status
        check(status == 403, str(status))
        r["actual"] = f"Danh sách chỉ phạm vi NM1; server trả {status} khi mở đơn Nhà máy 2"
    with case(s, "QL-07", "Lịch nghỉ phép của đội", "Workspace > bấm shortcut Lịch nghỉ phép", "", "Lịch tháng hiển thị đơn của Bình") as r:
        s.step("Anh Hùng mở shortcut Lịch nghỉ phép trên workspace")
        p.goto(f"{BASE}/desk/tlc-hr/tlc-qu%E1%BA%A3n-l%C3%BD")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        p.locator(".widget", has_text="Lịch nghỉ phép").first.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        text = p.locator(".fc, .calendar-view, body").first.inner_text()
        check("Trần Văn Bình" in text, text[:200])
        r["actual"] = "Lịch có đơn của Trần Văn Bình"
    with case(s, "QL-08", "Quản lý tự xin nghỉ trong app", "Mở app Frappe HR, xin nghỉ 1 ngày, gửi duyệt", f"{vn(working_day(6))}, Họp phụ huynh",
              "Đơn đến CEO Nguyễn Văn Thành") as r:
        s.step("Anh Hùng tự xin nghỉ 1 ngày trong app và Gửi duyệt")
        REQ["hung"] = hrms_request_leave(s, working_day(6), working_day(6), "Họp phụ huynh")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['hung']}").json()["data"]
        check(doc["leave_approver"] == "thanh@demo.example" and doc["workflow_state"] == TO_MANAGER, str(doc)[:160])
        r["actual"] = f"{REQ['hung']} → thanh@demo.example"
    s.close()


# ---------------------------------------------------------------------------------------------------- hr lead


def hr_lead(browser):
    s = Session(browser, "HR", "hoa")
    first_case(s, "HR-01")
    p = s.page
    with case(s, "HR-02", "Workspace TLC Nhân sự", "Đọc các thẻ số; bấm thẻ Đơn chờ nhân sự duyệt mở danh sách", "",
              "Thẻ nhân sự / Hội sở / Nhà máy / đơn chờ bằng đúng số server trả cho hoa") as r:
        s.step("Chị Hòa đọc các thẻ số trên workspace TLC Nhân sự")
        values = tuple(card_value(p, label) for label in ("Nhân sự đang làm việc", "Nhân sự khối Hội sở", "Nhân sự khối Nhà máy", "Đơn chờ nhân sự duyệt"))
        server = (len(list_of(s, "Employee", filters={"status": "Active"}, fields=["name"], limit=500)),
                  len(list_of(s, "Employee", filters={"status": "Active", "tlc_workforce": "head_office"}, fields=["name"], limit=500)),
                  len(list_of(s, "Employee", filters={"status": "Active", "tlc_workforce": "factory"}, fields=["name"], limit=500)),
                  len(list_of(s, "Leave Application", filters={"workflow_state": "Chờ nhân sự duyệt"}, fields=["name"], limit=500)))
        check(values == server and server[0] >= 60, f"thẻ {values} ≠ server {server}")
        s.step("Chị Hòa bấm thẻ Đơn chờ nhân sự duyệt để xem danh sách")
        p.locator(".widget", has_text="Đơn chờ nhân sự duyệt").first.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        r["actual"] = "Nhân sự {}; Hội sở {}; Nhà máy {}; chờ nhân sự {}".format(*values)
    with case(s, "HR-03", "Duyệt cấp nhân sự", "Mở từng đơn từ danh sách chờ > Hành động > Duyệt", f"{REQ['binh_full']}, {REQ['an']}",
              "Cả hai Đã duyệt") as r:
        out, heads = [], []
        for name in (REQ["binh_full"], REQ["an"]):
            s.step(f"Chị Hòa mở đơn {name} và bấm Hành động > Duyệt")
            open_leave(s, name)
            out.append(desk_action(s, name, "Duyệt"))
            heads.append(page_head_text(p)[:50])
        check(out == [APPROVED, APPROVED], str(out))
        r["actual"] = " | ".join(out) + f" · trên form: {heads[0]}"
    with case(s, "HR-04", "Báo cáo số dư phép", "Workspace > bấm Số dư phép", "", "Báo cáo mở sẵn kỳ cả năm, hiển thị số dư Phép năm của nhân viên") as r:
        s.step("Chị Hòa mở báo cáo Số dư phép từ workspace")
        p.goto(f"{BASE}/desk/tlc-hr/tlc-nh%C3%A2n-s%E1%BB%B1")
        p.wait_for_load_state("networkidle")
        p.locator(".widget", has_text="Số dư phép").first.click()
        p.wait_for_load_state("networkidle")
        expect(p.get_by_text("Phép năm").first).to_be_visible(timeout=40000)
        p.wait_for_timeout(1500)
        r["actual"] = "Báo cáo hiển thị số dư Phép năm"
    with case(s, "HR-06", "Trưởng nhân sự tự xin nghỉ", "App Frappe HR > Xin nghỉ phép > Gửi duyệt", f"{vn(working_day(7))}, Đi đám cưới", "Đơn đến CEO") as r:
        s.step("Chị Hòa tự xin nghỉ trong app và Gửi duyệt")
        REQ["hoa"] = hrms_request_leave(s, working_day(7), working_day(7), "Đi đám cưới")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['hoa']}").json()["data"]
        check(doc["leave_approver"] == "thanh@demo.example", doc["leave_approver"])
        r["actual"] = f"{REQ['hoa']} → thanh@demo.example"
    s.close()


# ---------------------------------------------------------------------------------------------------- ceo


def ceo(browser):
    s = Session(browser, "CEO", "thanh")
    first_case(s, "CEO-01")
    p = s.page
    with case(s, "CEO-02", "Workspace TLC Điều hành", "Đọc các thẻ số; bấm thẻ Đơn chờ tôi duyệt mở danh sách", "",
              "Thẻ nhân sự / đơn chờ của tôi / đơn chờ quản lý bằng đúng số server trả cho thanh") as r:
        s.step("Anh Thành đọc các thẻ số trên workspace TLC Điều hành")
        values = (card_value(p, "Nhân sự đang làm việc"), card_value(p, "Đơn chờ tôi duyệt"), card_value(p, "Đơn chờ quản lý duyệt"))
        server = (len(list_of(s, "Employee", filters={"status": "Active"}, fields=["name"], limit=500)),
                  len(list_of(s, "Leave Application", filters={"workflow_state": TO_MANAGER, "leave_approver": "thanh@demo.example"},
                              fields=["name"], limit=500)),
                  len(list_of(s, "Leave Application", filters={"workflow_state": TO_MANAGER}, fields=["name"], limit=500)))
        check(values == server and server[0] >= 60, f"thẻ {values} ≠ server {server}")
        s.step("Anh Thành bấm thẻ Đơn chờ tôi duyệt để mở danh sách")
        p.locator(".widget", has_text="Đơn chờ tôi duyệt").first.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        r["actual"] = "Nhân sự {}; chờ tôi {}; chờ quản lý {}".format(*values)
    with case(s, "CEO-03", "Duyệt đơn của cấp dưới trực tiếp", "Mở đơn của Quản lý NM1 và Trưởng nhân sự > Hành động > Duyệt",
              f"{REQ['hung']}, {REQ['hoa']}", "Cả hai Chờ nhân sự duyệt") as r:
        out, heads = [], []
        for name in (REQ["hung"], REQ["hoa"]):
            s.step(f"Anh Thành mở đơn {name} và bấm Hành động > Duyệt")
            open_leave(s, name)
            out.append(desk_action(s, name, "Duyệt"))
            heads.append(page_head_text(p)[:50])
        check(out == [TO_HR, TO_HR], str(out))
        r["actual"] = " | ".join(out) + f" · trên form: {heads[0]}"
    with case(s, "CEO-04", "Biểu đồ điều hành", "Mở workspace TLC Điều hành; bấm vào biểu đồ; xem Nhân sự theo phòng ban và Ngày nghỉ theo tháng", "", "Hai biểu đồ hiển thị") as r:
        s.step("Anh Thành mở workspace TLC Điều hành để xem biểu đồ")
        p.goto(f"{BASE}/desk/tlc-hr/tlc-%C4%91i%E1%BB%81u-h%C3%A0nh")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        charts = p.locator(".widget", has_text="Nhân sự theo phòng ban")
        charts.first.scroll_into_view_if_needed()
        p.wait_for_timeout(1500)
        check(charts.count() >= 1 and p.locator(".widget svg, .widget canvas").count() >= 1, "không thấy biểu đồ")
        s.step("Anh Thành bấm vào biểu đồ nhân sự theo phòng ban")
        p.locator(".widget", has_text="Nhân sự theo phòng ban").first.click()
        p.wait_for_timeout(1500)
        r["actual"] = "Biểu đồ hiển thị"
    s.close()


# ---------------------------------------------------------------------------------------------------- hr lead, second pass


def hr_lead_second(browser):
    s = Session(browser, "HR2", "hoa")
    login(s)
    with case(s, "HR-07", "Không tự duyệt đơn của mình", "Mở đơn của chính mình (đã qua CEO); bấm menu Hành động (dấu ba chấm) xem có nút Duyệt không", REQ["hoa"],
              "Không có Duyệt/Từ chối cho chính mình") as r:
        s.step("Chị Hòa mở đơn của chính mình và bấm menu Hành động để thử tự duyệt")
        open_leave(s, REQ["hoa"])
        p = s.page
        more = p.locator(".page-head button.menu-more-button, button.menu-more-button").first
        more.wait_for(state="visible", timeout=15000)
        more.click()  # real click: the only action entry on her own (read-only) request
        p.wait_for_timeout(700)
        actions = menu_items(p)
        p.keyboard.press("Escape")
        p.wait_for_timeout(300)
        check("Duyệt" not in actions and "Từ chối" not in actions, str(actions))
        r["actual"] = f"Menu Hành động: {actions or 'không có'}"
    with case(s, "HR-08", "Duyệt đơn của Quản lý NM1", "Mở đơn > Hành động > Duyệt", REQ["hung"], "Đã duyệt") as r:
        s.step("Chị Hòa mở đơn của Quản lý NM1 và bấm Hành động > Duyệt")
        open_leave(s, REQ["hung"])
        state = desk_action(s, REQ["hung"], "Duyệt")
        check(state == APPROVED, state)
        r["actual"] = f"{state} · trên form: {page_head_text(s.page)[:80]}"
    s.close()


# ---------------------------------------------------------------------------------------------------- hr officer


def hr_officer(browser):
    s = Session(browser, "HR3", "lan")
    first_case(s, "HR-09")
    with case(s, "HR-10", "Chuyên viên nhân sự duyệt đơn của Trưởng nhân sự", "Mở đơn > Hành động > Duyệt", REQ["hoa"], "Đã duyệt") as r:
        s.step("Chị Lan mở đơn của Trưởng nhân sự và bấm Hành động > Duyệt")
        open_leave(s, REQ["hoa"])
        state = desk_action(s, REQ["hoa"], "Duyệt")
        check(state == APPROVED, state)
        r["actual"] = f"{state} · trên form: {page_head_text(s.page)[:80]}"
    s.close()


# ---------------------------------------------------------------------------------------------------- results check


def results_check(browser):
    s = Session(browser, "CN1b", "binh", phone=True)
    login(s)
    p = s.page
    with case(s, "CN1-05", "Công nhân xem kết quả đơn", "Bấm Nghỉ phép mở danh sách; mở đơn bị từ chối, đọc lý do", f"{REQ['binh_full']}, {REQ['binh_half']}",
              "Đơn 1 ngày Đã duyệt; đơn nửa ngày Từ chối, thấy lý do 'Trùng ca kiểm kê kho' (chỉ đọc)") as r:
        s.step("Anh Bình mở danh sách đơn để xem kết quả")
        text = open_app_leaves(s)
        if APPROVED not in text or REJECTED not in text:
            p.goto(f"{BASE}/hrms/leave-applications")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2500)
            text = " ".join(p.locator("body").inner_text().split())
        check(APPROVED in text and REJECTED in text, text[:200])
        s.step("Anh Bình mở đơn bị từ chối để đọc lý do")
        p.goto(f"{BASE}/hrms/leave-applications/{REQ['binh_half']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        value, editable = reason_on_screen(p, "Trùng ca kiểm kê kho")
        check("Trùng ca kiểm kê kho" in value and not editable, f"giá trị: {value!r} sửa được: {editable}")
        r["actual"] = f"Danh sách có Đã duyệt và Từ chối; lý do trên form (chỉ đọc): {value}"
    with case(s, "CN1-06", "Số dư phép sau khi được duyệt", "Menu dưới > Nghỉ phép, đọc số dư Phép năm", "", "Phép năm còn 11 (đơn bị từ chối không trừ)") as r:
        s.step("Anh Bình mở mục Nghỉ phép để đọc số dư còn lại")
        segment = app_leave_balance(s, 11)
        r["actual"] = f"Phép năm trên màn hình: {segment}"
    s.close()

    s = Session(browser, "NVb", "an")
    login(s)
    with case(s, "NV-08", "Kết quả đơn và số dư", "Bấm Nghỉ phép: thấy đơn Đã duyệt và số dư còn 10", REQ["an"], "Đã duyệt; còn 10 ngày") as r:
        s.step("An mở mục Nghỉ phép để xem kết quả và số dư")
        segment = app_leave_balance(s, 10)
        text = s.page.locator("body").inner_text()
        if APPROVED not in text:
            s.page.goto(f"{BASE}/hrms/leave-applications")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            text = " ".join(s.page.locator("body").inner_text().split())
        check(APPROVED in text, text[:120])
        r["actual"] = f"Đã duyệt; Phép năm còn {segment}"
    s.close()


JOURNEYS = [office_employee, support_office_manager, factory_worker_1, factory_worker_2, factory_head, hr_lead, ceo,
            hr_lead_second, hr_officer, results_check]
