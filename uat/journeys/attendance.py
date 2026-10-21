"""Attendance: GPS check-in at the work site, corrections, and the monthly closing (TLC Chốt công) of the three factories and the
head office: HR sends, each factory head confirms only their factory, HR reconciles, the CEO signs and locks; after the lock a
direct change is refused and HR goes through a post-lock adjustment."""

from lib import *  # noqa: F403

KC, AR = "TLC Attendance Period", "Attendance Request"
SITES = {"Nhà máy 1": (10.850632, 106.772010), "Nhà máy 2": (10.980410, 106.651871), "Nhà máy 3": (10.957413, 106.842687)}
HOME = (10.762622, 106.660172)  # a worker's home in the city, kilometres away from every site
TO_HEAD, PERIOD_TO_HR, TO_CEO, LOCKED = "Chờ quản lý xác nhận", "Chờ nhân sự đối soát", "Chờ giám đốc ký", "Đã khoá"
SCOPES = ["Nhà máy 1", "Nhà máy 2", "Nhà máy 3", "Hội sở"]
HEADS = {"Nhà máy 1": "hung", "Nhà máy 2": "nm2", "Nhà máy 3": "nm3"}


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
        text = press_checkin(p)
        after = checkin_count(s)
        check(after == before, f"{before} -> {after}: {text[-300:]}")
        r["actual"] = f"Không có lượt chấm công mới ({after}); thông báo lỗi trên app"
    s.context.set_geolocation({"latitude": SITES[site][0] + 0.0003, "longitude": SITES[site][1] - 0.0002})
    with case(s, "AT-02", "Chấm công GPS tại cổng nhà máy", "App > Vào ca tại nhà máy > Xác nhận", f"{account}@demo.example tại {site}",
              "Ghi nhận lượt chấm công với toạ độ, gắn ca đang mở") as r:
        before = checkin_count(s)
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


def period_action(s, name, action, reason=None):
    open_period(s, name)
    p = s.page
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
    return doc_state(s, KC, name)


def period_closing(browser):
    month = last_month()
    REQ["kc"] = {}
    s = Session(browser, "KC", "lan")
    login(s)
    p = s.page
    with case(s, "PD-01", "HR lập kỳ công tháng trước cho 3 nhà máy và hội sở", "Chốt công > Mới > chọn phạm vi, tháng > Lưu; xem tổng hợp",
              f"Tháng {month}; Nhà máy 1, 2, 3, Hội sở", "4 kỳ công Nháp, có bảng công từng người, không còn việc chưa xử lý") as r:
        out = []
        for scope in SCOPES:
            p.goto(f"{BASE}/desk/tlc-attendance-period")
            p.wait_for_load_state("networkidle")
            p.evaluate("([s, m]) => frappe.new_doc('TLC Attendance Period', {scope: s, period_month: m})", [scope, month])
            p.wait_for_url(re.compile(r".*/tlc-attendance-period/new.*"))
            p.wait_for_timeout(2000)
            p.keyboard.press("Control+s")
            p.wait_for_url(re.compile(r".*/tlc-attendance-period/TLC-KC-\d+"), timeout=30000)
            p.wait_for_timeout(2500)
            REQ["kc"][scope] = re.search(r"TLC-KC-\d+", p.url).group(0)
            doc = api_get(s, f"/api/resource/{KC}/{REQ['kc'][scope]}").json()["data"]
            check(doc["employee_count"] > 0 and doc["open_count"] == 0, f"{scope}: {doc['employee_count']} người, {doc['open_count']} việc")
            out.append(f"{scope}: {doc['employee_count']} người, có mặt {doc['present_days']:g}, vắng {doc['absent_days']:g}, OT {doc['ot_hours']:g} giờ")
        r["actual"] = " | ".join(out) + " · " + headline(p)
    with case(s, "PD-02", "HR gửi trưởng nhà máy xác nhận, hội sở gửi thẳng đối soát", "Hành động > Gửi xác nhận (nhà máy) / Gửi đối soát (hội sở)",
              ", ".join(REQ["kc"].values()), "3 kỳ nhà máy Chờ quản lý xác nhận; kỳ hội sở Chờ nhân sự đối soát") as r:
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
            waiting = card_value(p, "Kỳ công chờ tôi xác nhận")
            blocked = api_get(s, f"/api/resource/{KC}/{other}").status
            if scope == "Nhà máy 3":
                state = period_action(s, REQ["kc"][scope], "Trả lại", reason="Thiếu giờ tăng ca kiểm kê ngày 25, đề nghị HR kiểm tra")
                check(state == DRAFT, state)
                hr = Session(browser, "KC", "lan")
                login(hr)
                open_period(hr, REQ["kc"][scope])
                hr.page.get_by_role("button", name="Làm mới tổng hợp").click()
                hr.page.wait_for_timeout(3000)
                check(period_action(hr, REQ["kc"][scope], "Gửi xác nhận") == TO_HEAD, "gửi lại")
                hr.close()
            state = period_action(s, REQ["kc"][scope], "Xác nhận")
            check(waiting == 1 and blocked == 403 and state == PERIOD_TO_HR, f"thẻ {waiting}, khác {blocked}, {state}")
            r["actual"] = f"Thẻ chờ tôi {waiting}; kỳ nhà máy khác: {blocked}; {state}" + (" (sau 1 lần trả lại)" if scope == "Nhà máy 3" else "")
        s.close()

    s = Session(browser, "KC", "hoa")
    login(s)
    with case(s, "PD-06", "HR đối soát 4 kỳ công", "Workspace TLC Nhân sự > thẻ Kỳ công chờ đối soát > mở từng kỳ > Hành động > Đối soát xong",
              ", ".join(REQ["kc"].values()), "Thẻ đếm 4; cả 4 Chờ giám đốc ký") as r:
        waiting = card_value(s.page, "Kỳ công chờ đối soát")
        states = [period_action(s, REQ["kc"][scope], "Đối soát xong") for scope in SCOPES]
        check(waiting == 4 and states == [TO_CEO] * 4, f"{waiting} {states}")
        r["actual"] = f"Thẻ {waiting}; {', '.join(states)}"
    s.close()

    s = Session(browser, "KC", "thanh")
    login(s)
    with case(s, "PD-07", "CEO ký và khoá kỳ công", "Workspace TLC Điều hành > thẻ Kỳ công chờ ký > mở từng kỳ > Hành động > Ký và khoá",
              ", ".join(REQ["kc"].values()), "Thẻ đếm 4; cả 4 Đã khoá, ghi người ký và thời điểm") as r:
        waiting = card_value(s.page, "Kỳ công chờ ký")
        states = [period_action(s, REQ["kc"][scope], "Ký và khoá") for scope in SCOPES]
        doc = api_get(s, f"/api/resource/{KC}/{REQ['kc']['Nhà máy 1']}").json()["data"]
        check(waiting == 4 and states == [LOCKED] * 4 and doc["locked_by"] == "thanh@demo.example", f"{waiting} {states}")
        r["actual"] = f"Thẻ {waiting}; {', '.join(states)}; khoá lúc {doc['locked_at']}"
    s.close()

    s = Session(browser, "KC", "lan")
    login(s)
    p = s.page
    worker = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "binh@demo.example"]])).json()["data"][0]["name"]
    absent = api_get(s, "/api/resource/Attendance?filters=" + json.dumps([["employee", "=", worker], ["status", "=", "Absent"],
                                                                          ["attendance_date", "like", f"{month}%"]])
                     + "&fields=" + json.dumps(["attendance_date"])).json()["data"]
    day = absent[0]["attendance_date"] if absent else f"{month}-15"
    token = {"Content-Type": "application/json", "X-Frappe-CSRF-Token": p.evaluate("frappe.csrf_token")}
    with case(s, "PD-08", "Không sửa trực tiếp được công của kỳ đã khoá", "Tạo giải trình thường cho ngày trong kỳ đã khoá",
              f"Trần Văn Bình, {vn(day)}", "Bị chặn: kỳ công đã khoá, phải dùng điều chỉnh sau chốt") as r:
        res = p.request.post(f"{BASE}/api/resource/{AR}", headers=token, data=json.dumps({
            "employee": worker, "from_date": day, "to_date": day, "reason": "On Duty", "tlc_correction_type": "Máy chấm công lỗi",
            "explanation": "Máy lỗi"}))
        check(res.status >= 400 and "khoá" in res.text(), f"{res.status} {res.text()[:200]}")
        r["actual"] = f"HTTP {res.status}: kỳ công đã khoá"
    with case(s, "PD-09", "HR lập điều chỉnh sau chốt", "Giải trình công > Mới: loại Điều chỉnh sau chốt, lý do > Lưu > Gửi duyệt",
              f"Trần Văn Bình, {vn(day)} (ngày vắng), đi giao hàng cho khách", "Chờ quản lý duyệt, người duyệt trưởng Nhà máy 1") as r:
        p.goto(f"{BASE}/desk/attendance-request")
        p.wait_for_load_state("networkidle")
        p.evaluate("([e, d]) => frappe.new_doc('Attendance Request', {employee: e, from_date: d, to_date: d, reason: 'On Duty', "
                   "tlc_correction_type: 'Điều chỉnh sau chốt', explanation: 'Đi giao hàng cho khách theo lệnh của trưởng nhà máy, quên báo'})",
                   [worker, day])
        p.wait_for_url(re.compile(r".*/attendance-request/new.*"))
        p.wait_for_timeout(2500)
        p.keyboard.press("Control+s")
        p.wait_for_url(re.compile(r".*/attendance-request/HR-ARQ-[\d-]+"), timeout=30000)
        REQ["adj"] = re.search(r"HR-ARQ-[\d-]+", p.url).group(0)
        p.wait_for_timeout(2000)
        open_actions(p)
        p.locator(MENU_ITEMS).filter(has_text="Gửi duyệt").first.click()
        p.wait_for_timeout(3000)
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
