"""Overtime (TLC Tăng ca): the factory head proposes, the worker consents, the CEO approves; Labour Code limits."""

from lib import *  # noqa: F403

OT = "TLC Overtime Request"
TO_WORKER, TO_DIRECTOR = "Chờ người lao động đồng ý", "Chờ giám đốc duyệt"


def ot_state(s, name):
    return doc_state(s, OT, name)


def overtime_flow(browser):
    """Head of factory 1 proposes overtime for a worker on the desk, the worker consents on the phone, the CEO approves."""
    day = working_day(9)
    s = Session(browser, "OT", "hung")
    login(s)
    p = s.page
    worker = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "binh@demo.example"]])).json()["data"][0]["name"]
    with case(s, "OT-01", "Quản lý nhà máy đề xuất tăng ca", "Workspace > Tăng ca > Mới; chọn công nhân, ngày, giờ, lý do > Lưu > Hành động > Đề nghị",
              f"Trần Văn Bình, {vn(day)} 17:30-20:30, Kiểm kê kho", "Đơn 3 giờ ngày thường, Chờ người lao động đồng ý; dòng đầu form hiện giới hạn 40/200 giờ") as r:
        p.goto(f"{BASE}/desk/tlc-overtime-request")
        p.wait_for_load_state("networkidle")
        p.evaluate("([e, d]) => frappe.new_doc('TLC Overtime Request', {employee: e, ot_date: d, from_time: '17:30:00', to_time: '20:30:00', "
                   "reason: 'Kiểm kê kho cuối quý'})", [worker, day])
        p.wait_for_url(re.compile(r".*/tlc-overtime-request/new.*"))
        p.wait_for_timeout(2500)
        p.keyboard.press("Control+s")
        p.wait_for_url(re.compile(r".*/tlc-overtime-request/TLC-OT-\d{4}-\d+"), timeout=30000)
        REQ["ot"] = re.search(r"TLC-OT-\d{4}-\d+", p.url).group(0)
        p.wait_for_timeout(2500)
        text = headline(p)
        open_actions(p)
        p.locator(MENU_ITEMS).filter(has_text="Đề nghị").first.click()
        p.wait_for_timeout(3500)
        doc = api_get(s, f"/api/resource/{OT}/{REQ['ot']}").json()["data"]
        check((doc["workflow_state"], doc["hours"], doc["day_type"]) == (TO_WORKER, 3, "Ngày thường") and "/40" in text, f"{doc['workflow_state']} {text}")
        r["actual"] = f"{REQ['ot']}: {doc['hours']:g} giờ {doc['day_type']}, {doc['workflow_state']} · {text}"
    with case(s, "OT-02", "Chặn vượt trần ngày theo luật", "Đề xuất thêm 2 giờ cùng ngày cho cùng người (tổng 5 giờ)", f"{vn(day)} 20:30-22:30",
              "Bị chặn: quá 4 giờ tăng ca trong một ngày thường (BLLĐ 2019 điều 107)") as r:
        res = s.page.request.post(f"{BASE}/api/resource/{OT}", data=json.dumps({"employee": worker, "ot_date": day, "from_time": "20:30:00",
                                                                                 "to_time": "22:30:00", "reason": "Thêm giờ"}),
                                  headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": p.evaluate("frappe.csrf_token")})
        body = res.text()
        check(res.status >= 400 and "4 giờ" in body, f"{res.status} {body[:200]}")
        r["actual"] = f"HTTP {res.status}: Quá 4 giờ tăng ca trong một ngày thường"
    with case(s, "OT-03", "Quản lý không đồng ý thay công nhân", "Mở đơn; xem Hành động", REQ["ot"], "Không có Đồng ý / Từ chối") as r:
        p.goto(f"{BASE}/desk/tlc-overtime-request/{REQ['ot']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        actions = workflow_actions(p)
        check("Đồng ý" not in actions, str(actions))
        r["actual"] = f"Hành động: {actions or 'không có'}"
    s.close()

    s = Session(browser, "OT", "binh", phone=True)
    login(s)
    p = s.page
    with case(s, "OT-04", "Công nhân nhận thông báo và đồng ý tăng ca", "Chuông thông báo > mở đơn > Hành động > Đồng ý", REQ["ot"],
              "Có thông báo; đơn chuyển Chờ giám đốc duyệt, ghi thời điểm đồng ý") as r:
        logs = api_get(s, "/api/resource/Notification Log?fields=[\"subject\",\"document_name\"]&filters=" +
                       json.dumps([["document_name", "=", REQ["ot"]]])).json()["data"]
        check(logs, "không có thông báo")
        p.goto(f"{BASE}/desk/tlc-overtime-request/{REQ['ot']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        text = headline(p)
        open_actions(p)
        p.locator(MENU_ITEMS).filter(has_text="Đồng ý").first.click()
        p.wait_for_timeout(3500)
        doc = api_get(s, f"/api/resource/{OT}/{REQ['ot']}").json()["data"]
        check(doc["workflow_state"] == TO_DIRECTOR and doc["consent_at"], str(doc)[:200])
        r["actual"] = f"Thông báo: {logs[0]['subject']} · {doc['workflow_state']} lúc {doc['consent_at']}"
    s.close()

    s = Session(browser, "OT", "thanh")
    login(s)
    p = s.page
    with case(s, "OT-05", "CEO duyệt tăng ca", "Workspace TLC Điều hành > thẻ Tăng ca chờ giám đốc duyệt > mở đơn > Hành động > Duyệt", REQ["ot"],
              "Thẻ đếm 6 đơn (5 demo + 1); đơn Đã duyệt") as r:
        waiting = card_value(p, "Tăng ca chờ giám đốc duyệt")
        p.goto(f"{BASE}/desk/tlc-overtime-request/{REQ['ot']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        open_actions(p)
        p.locator(MENU_ITEMS).filter(has_text="Duyệt").first.click()
        p.wait_for_timeout(3500)
        state = ot_state(s, REQ["ot"])
        check(waiting == 6 and state == APPROVED, f"{waiting} {state}")
        r["actual"] = f"Thẻ chờ giám đốc {waiting}; đơn {state}"
    s.close()


JOURNEYS = [overtime_flow]
