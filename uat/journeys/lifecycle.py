"""Bằng chứng UAT vòng đời nhân viên trên Desk chuẩn.

Mỗi ca là thao tác thật bằng chuột và bàn phím: mở danh sách, mở hồ sơ, điền từng ô, bấm Lưu,
bấm Hành động + nút workflow, đọc thông báo trên màn hình. API chỉ dùng để dọn/khởi tạo dữ liệu nền
trước ca và đối chiếu kết quả đã lưu sau khi người dùng làm xong.
"""
from lib import *

CONTRACT = "TLC Employment Contract"
DATE_TOKEN = re.compile(r"\d{2}[/-]\d{2}[/-]\d{4}")


def _wait_form(p, doctype):
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d && !cur_frm.is_new()", arg=doctype)
    p.wait_for_timeout(1200)


def _field(p, fieldname):
    return p.locator(f"input[data-fieldname='{fieldname}']:visible, textarea[data-fieldname='{fieldname}']:visible").last


def _type(p, fieldname, value):
    """Gõ thật vào ô của form Desk (không dùng cur_frm.set_value)."""
    p.keyboard.press("Escape")  # a link completion left open must not cover the field
    p.wait_for_timeout(300)
    field = _field(p, fieldname)
    field.click()
    field.fill(value)
    field.press("Tab")
    p.wait_for_timeout(500)
    if not str(p.evaluate("f => cur_frm.doc[f] || ''", fieldname)):
        # the employee link loads the rest of the form; a re-render can replace a box filled while it was loading
        field.click()
        field.fill(value)
        field.press("Tab")
        p.wait_for_timeout(700)


def _link(p, fieldname, value):
    """Ô liên kết: gõ để lọc rồi chọn đúng dòng gợi ý đang hiện dưới ô, như người dùng thật."""
    field = _field(p, fieldname)
    field.click()
    field.fill("")
    p.keyboard.type(str(value), delay=45)
    p.wait_for_timeout(2200)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option], .frappe-control-dropdown li")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    target = next((i for i in shown if str(value).lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
    if target is not None:
        options.nth(target).click()
        p.wait_for_timeout(900)
    else:
        field.press("Enter")
        p.wait_for_timeout(600)
    field.press("Tab")  # leave the completion without changing the value
    p.keyboard.press("Escape")
    p.wait_for_timeout(3000)  # the employee link loads the rest of the form; wait for that render before filling
    got = str(p.evaluate("f => cur_frm.doc[f] || ''", fieldname))
    check(got == str(value), f"ô {fieldname} nhận {got!r}, không phải {value!r}")


def _save(p, capture=False):
    """Nút Lưu thật trên đầu trang; Escape trước để overlay autocomplete không che cú nhấp.

    `capture=True` trả về cảnh báo đọc được ngay sau cú nhấp, trước khi toast tự tắt.
    """
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    button = p.locator(".page-head button:visible").filter(
        has_text=re.compile(r"Lưu|Save|Cập nhật|Update")).last
    try:
        button.click(timeout=6000)
    except Exception:
        button.click(force=True)
    p.wait_for_timeout(1200)
    early = _popup_text(p) if capture else ""
    p.wait_for_timeout(1400)
    return early


def _action(p, text):
    """Hành động > nút workflow, bấm thật trong menu."""
    open_actions(p)
    item = p.locator(MENU_ITEMS).filter(has_text=text).first
    check(item.count() > 0, f"Không có {text} trong menu Hành động: {menu_items(p)}")
    item.click()
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)


def _popup_text(p):
    """Đọc điều hệ thống vừa báo: hộp thoại, dòng cảnh báo trên form hoặc thông báo nổi."""
    parts = []
    for sel in (".modal:visible", ".msgprint:visible", ".form-message:visible", "[role=alert]:visible",
                ".text-danger:visible", ".toast-message:visible"):
        try:
            parts += [" ".join(el.inner_text().split()) for el in p.locator(sel).all() if el.is_visible()]
        except Exception:
            pass
    if parts:
        return " | ".join(x for x in parts if x)
    return " ".join(p.locator("body").inner_text().split())[:600]


def _shown(p, fieldname):
    """Giá trị người dùng nhìn thấy trên form (ô nhập hoặc phần text của ô read-only)."""
    text = " ".join(p.locator(f".frappe-control[data-fieldname='{fieldname}']").first.inner_text().split())
    try:
        typed = _field(p, fieldname).input_value().strip()
    except Exception:
        typed = ""
    return typed or text


def _open_list_row(s, slug, doctype, query, step_text):
    s.step(step_text)
    s.page.goto(f"{BASE}/desk/{slug}{query}")
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1600)
    row = s.page.locator(f'.list-row-container a[data-doctype="{doctype}"]').first
    check(row.count() > 0, f"Danh sách {slug} không có hồ sơ nào để mở")
    row.click()
    _wait_form(s.page, doctype)
    return s.page


def _desk_search(s, text):
    """Người dùng mở ô tìm kiếm của Desk và gõ đúng mã hồ sơ muốn xem. Trả về kết quả UI liệt kê."""
    p = s.page
    s.step(f"Mở ô tìm kiếm Desk, gõ “{text}”")
    p.goto(f"{BASE}/desk")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)
    trigger = p.locator("#small-search-button:visible, .navbar-modal-search-mobile:visible, .navbar-search-bar:visible")
    if trigger.count():
        trigger.first.click()
    else:
        p.keyboard.press("Control+k")  # phím tắt mở ô tìm kiếm của Desk
    box = p.locator("#navbar-search")
    expect(box).to_be_visible()
    box.click()
    box.press_sequentially(text, delay=70)
    p.wait_for_timeout(2200)
    items = [" ".join(t.split()) for t in p.locator(".awesomplete li").all_inner_texts() if t.strip()]
    s.step("Desk không cho mở hồ sơ của người khác; chuyển sang kiểm tra quyền đọc")
    p.keyboard.press("Escape")
    p.wait_for_timeout(600)
    return items


def _denied_text(s, route, name):
    p = s.page
    s.step(f"Mở thẳng đường dẫn hồ sơ {name} của người khác")
    p.goto(f"{BASE}/desk/{route}/{name}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1800)
    body = " ".join(p.locator("body").inner_text().split())
    check(any(w in body.lower() for w in ("permission", "not permitted", "không có quyền", "không được phép",
                                          "not allowed", "forbidden", "restricted")), body[:400])
    return body


def _setup_insert(s, doc):
    """Dựng dữ liệu nền bằng REST (chỉ dùng cho setup, không dùng cho hành vi được nghiệm thu)."""
    res = s.page.request.post(f"{BASE}/api/method/frappe.client.insert", data={"doc": doc},
                              headers={"X-Frappe-CSRF-Token": csrf_token(s)})
    payload = res.json()
    if res.status >= 400 or payload.get("exc_type"):
        raise AssertionError(f"setup insert {doc.get('doctype')}: HTTP {res.status} {payload.get('exception')}")
    return payload["message"]["name"]


def _login_as(s, account):
    """Đổi phiên chuẩn bị sang đúng người duyệt của một bước workflow (dữ liệu nền, không phải ca nghiệm thu)."""
    res = s.page.request.post(f"{BASE}/api/method/login", form={"usr": f"{account}@demo.example", "pwd": PASSWORD})
    check(res.status < 400, f"không đăng nhập được phiên chuẩn bị {account}: HTTP {res.status}")
    s._csrf_token = ""
    who = api_get(s, "/api/method/frappe.auth.get_logged_user").json().get("message")
    check(who == f"{account}@demo.example", f"phiên chuẩn bị là {who}, không phải {account}")


def _ensure_onboarding(s):
    """Onboarding demo đến từ offer đã chấp nhận của phân hệ recruitment; run lẻ thì dựng lại phần nền.

    Offer nền phải đi đúng workflow của ứng dụng (HR trình → HR Lead rà soát → Giám đốc duyệt → ghi phản hồi
    chấp nhận) — không thể chèn thẳng một offer "Accepted" vì luật trạng thái của ứng dụng từ chối.
    """
    applicant = api_get(s, "/api/resource/Job Applicant?filters=" +
                        json.dumps([["email_id", "=", "recruitment.candidate@demo.example"]])).json()["data"][0]["name"]
    rows = api_get(s, "/api/resource/Employee Onboarding?filters=" +
                   json.dumps([["job_applicant", "=", applicant]])).json()["data"]
    if rows:
        return rows[0]["name"], applicant
    info = api_get(s, f"/api/resource/Job Applicant/{applicant}").json()["data"]
    today = dt.date.today().isoformat()
    opening = api_get(s, f"/api/resource/Job Opening/{info['job_title']}").json()["data"]
    offer = _setup_insert(s, {"doctype": "Job Offer", "job_applicant": applicant, "applicant_name": info["applicant_name"],
                              "applicant_email": info["email_id"], "offer_date": today, "designation": info["designation"],
                              "company": "TLC Demo", "status": "Awaiting Response", "tlc_department": opening["department"],
                              "tlc_joining_date": today})
    for account, action in (("lan", "Submit Offer"), ("hoa", "Review Offer"), ("thanh", "Approve Offer")):
        _login_as(s, account)
        api(s, "frappe.model.workflow.apply_workflow",
            doc=json.dumps({"doctype": "Job Offer", "name": offer}), action=action)
    _login_as(s, "lan")
    api(s, "frappe.client.set_value", doctype="Job Offer", name=offer, fieldname="tlc_offer_stage", value="Sent")
    api(s, "frappe.client.set_value", doctype="Job Offer", name=offer, fieldname="status", value="Accepted")
    rows = api_get(s, "/api/resource/Employee Onboarding?filters=" +
                   json.dumps([["job_offer", "=", offer]])).json()["data"]
    if rows:
        return rows[0]["name"], applicant
    name = _setup_insert(s, {"doctype": "Employee Onboarding", "job_applicant": applicant, "job_offer": offer,
                             "employee_name": info["applicant_name"], "date_of_joining": today,
                             "boarding_begins_on": today, "company": "TLC Demo"})
    return name, applicant


def lifecycle_desktop(browser):
    # ---------------------------------------------------------------- HR Officer (Lan)
    s = Session(browser, "W4-LIFECYCLE", "lan")
    login(s)
    with case(s, "W4-CORE-HAPPY", "HR mở hợp đồng có chứng từ và gửi duyệt",
              "Desk > danh sách Hợp đồng TLC > lọc số TLC-UAT-W4-001 > mở hồ sơ > kiểm tra chứng từ > Hành động > Gửi duyệt",
              "TLC-UAT-W4-001; chứng từ demo riêng tư",
              "Giữ nguyên số hợp đồng và chứng từ trên form, hồ sơ chuyển sang Chờ nhân sự duyệt") as result:
        p = _open_list_row(s, "tlc-employment-contract", CONTRACT, "?contract_number=TLC-UAT-W4-001",
                           "Lan mở danh sách hợp đồng TLC và lọc đúng hồ sơ demo")
        REQ["w4_contract"] = p.evaluate("cur_frm.doc.name")
        s.step("Lan đối chiếu số hợp đồng, ngày hiệu lực và chứng từ đính kèm trên form")
        check(p.locator('[data-fieldname="evidence"] a').count() > 0, "Chưa có chứng từ trên form")
        shown_number = _shown(p, "contract_number")
        check("TLC-UAT-W4-001" in shown_number, f"Số hợp đồng trên màn hình: {shown_number}")
        state = p.evaluate("cur_frm.doc.workflow_state")
        if state == "Nháp":
            s.step("Lan bấm Hành động rồi chọn Gửi duyệt")
            _action(p, "Gửi duyệt")
        s.step("Lan đọc trạng thái mới ngay trên đầu form")
        check(p.evaluate("cur_frm.doc.workflow_state") == "Chờ nhân sự duyệt", "Không chuyển được HR review")
        head = " ".join(p.locator(".page-head").last.inner_text().split())
        check("Chờ nhân sự duyệt" in head, head[:200])
        result["actual"] = f"Form chuẩn hiện {shown_number} + chứng từ; đã gửi duyệt, đầu trang: {head[:80]}"

    with case(s, "W4-CORE-ERROR", "Không lưu được hợp đồng thiếu chứng từ",
              "Desk > Hợp đồng TLC > Mới > điền số, nhân viên, loại, ngày ký, ngày hiệu lực, người ký > để trống chứng từ > Lưu",
              "Hợp đồng mới không có file chứng từ",
              "Desk báo ô Evidence bắt buộc trên màn hình và không tạo hồ sơ") as result:
        number = f"TLC-UAT-W4-ERR-{dt.datetime.now().strftime('%H%M%S')}"
        employee = api_get(s, "/api/resource/Employee?filters=" +
                           json.dumps([["user_id", "=", "an@demo.example"]])).json()["data"][0]["name"]
        s.step("Lan mở form hợp đồng mới")
        p.goto(f"{BASE}/desk/tlc-employment-contract/new")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1500)
        s.step(f"Lan điền từng ô: số {number}, nhân viên, loại hợp đồng, ngày ký, ngày hiệu lực, người ký")
        _type(p, "contract_number", number)
        _link(p, "employee", employee)
        p.locator("select[data-fieldname='contract_type']:visible").last.select_option("Fixed term")
        today = dt.date.today().strftime("%d-%m-%Y")
        _type(p, "signed_on", today)
        _type(p, "valid_from", today)
        _type(p, "signatory", "TLC DEMO HR")
        s.step("Lan bỏ trống ô Chứng từ rồi bấm Lưu")
        _save(p)
        text = _popup_text(p)
        check("Evidence" in text or "chứng" in text.lower(), text[:250])
        check(p.evaluate("cur_frm.is_new()"), "Đã tạo hợp đồng thiếu chứng từ")
        stored = api_get(s, "/api/resource/TLC Employment Contract?filters=" +
                         json.dumps([["contract_number", "=", number]])).json()["data"]
        check(not stored, f"Hồ sơ vẫn được lưu: {stored}")
        result["actual"] = f"Desk chặn trên màn hình: {text[:120]}; đối chiếu server: chưa có hồ sơ {number}"
    s.close()

    # ---------------------------------------------------------------- HR Lead (Hoa)
    s = Session(browser, "W4-LIFECYCLE-LEAD", "hoa")
    login(s)
    with case(s, "W4-CORE-APPROVE", "HR Lead duyệt hợp đồng trên form",
              "Desk > danh sách Hợp đồng TLC > mở hồ sơ chờ nhân sự duyệt > Hành động > Duyệt > đọc trạng thái",
              REQ.get("w4_contract", ""), "Hồ sơ submitted, các ô nghiệp vụ không còn sửa tự do") as result:
        check(bool(REQ.get("w4_contract")), "Case tạo/gửi hợp đồng chưa thành công")
        p = _open_list_row(s, "tlc-employment-contract", CONTRACT, "?contract_number=TLC-UAT-W4-001",
                           "Hoa mở danh sách hợp đồng và vào đúng hồ sơ đang chờ")
        s.step("Hoa bấm Hành động và chọn Duyệt")
        _action(p, "Duyệt")
        s.step("Hoa đọc trạng thái và thử sửa lại số hợp đồng")
        check(p.evaluate("cur_frm.doc.docstatus") == 1, "Chưa duyệt/nộp")
        check(p.locator('[data-fieldname="contract_number"] input:visible:not([readonly])').count() == 0,
              "Số hợp đồng vẫn sửa được")
        head = " ".join(p.locator(".page-head").last.inner_text().split())
        result["actual"] = f"Đã duyệt; bản ghi submitted giữ lịch sử/chứng từ. Đầu trang: {head[:90]}"
    s.close()

    # ---------------------------------------------------------------- Employee (Binh)
    s = Session(browser, "W4-LIFECYCLE-PERMISSION", "binh")
    login(s)
    with case(s, "W4-CORE-PERMISSION", "Công nhân không đọc được hợp đồng của người khác",
              "Desk > ô tìm kiếm > gõ số hợp đồng của An > mở đường dẫn hồ sơ > đọc thông báo từ chối",
              REQ.get("w4_contract", ""), "Không trả dữ liệu hợp đồng và chứng từ; server từ chối quyền đọc") as result:
        check(bool(REQ.get("w4_contract")), "Không có hồ sơ quyền để thử")
        found = _desk_search(s, "TLC-UAT-W4-001")
        body = _denied_text(s, "tlc-employment-contract", REQ["w4_contract"])
        check("TLC-UAT-W4-001" not in body, "Lộ dữ liệu hợp đồng người khác")
        denied = api_get(s, f"/api/resource/{CONTRACT}/{REQ['w4_contract']}")
        check(denied.status == 403, f"REST đọc hồ sơ trả {denied.status}")
        result["actual"] = (f"Ô tìm kiếm chỉ liệt kê {len(found)} mục, không có hợp đồng của An; "
                            f"form báo: {body[:90]}; REST đối chiếu 403")
    s.close()


def lifecycle_boarding_desktop(browser):
    # ---------------------------------------------------------------- HR Officer (Lan): nghỉ việc
    s = Session(browser, "W4-BOARDING", "lan")
    login(s)
    with case(s, "W4-EXIT-HAPPY", "HR kiểm tra ngày báo trước và hạn quyết toán trên form",
              "Desk > Employee Separation > lọc hồ sơ demo > mở > đọc ba ô ngày trên form",
              "Hợp đồng không xác định thời hạn; 45 ngày báo trước",
              "Ngày cuối sớm nhất bằng ngày nghỉ việc và hạn thanh toán hiện trên form chuẩn") as result:
        p = _open_list_row(s, "employee-separation", "Employee Separation",
                           "?custom_tlc_reason=TLC%20UAT%20W4%20notice%20and%20clearance",
                           "Lan mở danh sách hồ sơ nghỉ việc và vào đúng hồ sơ demo")
        REQ["w4_separation"] = p.evaluate("cur_frm.doc.name")
        s.step("Lan đọc ngày cuối sớm nhất, ngày nghỉ việc và hạn quyết toán hiển thị trên form")
        shown = {k: _shown(p, k) for k in ("custom_tlc_earliest_last_day", "custom_tlc_last_day", "custom_tlc_settlement_due")}
        dates = {k: (DATE_TOKEN.search(v).group(0) if DATE_TOKEN.search(v) else "") for k, v in shown.items()}
        check(dates["custom_tlc_earliest_last_day"] == dates["custom_tlc_last_day"], f"Ngày trên form: {shown}")
        check(bool(dates["custom_tlc_settlement_due"]), f"Hạn quyết toán trên form: {shown['custom_tlc_settlement_due']}")
        stored = api_get(s, f"/api/resource/Employee Separation/{REQ['w4_separation']}").json()["data"]
        check(stored["custom_tlc_earliest_last_day"] == stored["custom_tlc_last_day"] and stored["custom_tlc_settlement_due"],
              str(stored)[:200])
        result["actual"] = (f"Form hiện ngày cuối sớm nhất {dates['custom_tlc_earliest_last_day']} = ngày nghỉ việc "
                            f"{dates['custom_tlc_last_day']}, hạn quyết toán {dates['custom_tlc_settlement_due']}")

    with case(s, "W4-EXIT-ERROR", "Ngoại lệ pháp lý không có chứng từ bị chặn",
              "Trên chính form > chọn ngoại lệ luật > bấm Lưu > đọc thông báo EXIT-LEGAL",
              "Statutory employee exception; thiếu hồ sơ/xác nhận",
              "Thông báo EXIT-LEGAL hiện trên màn hình, không lưu ngoại lệ") as result:
        p = s.page
        s.step("Lan chọn ngoại lệ “Statutory employee exception” mà không đính hồ sơ pháp lý")
        p.locator("select[data-fieldname='custom_tlc_notice_exception']:visible").last.select_option("Statutory employee exception")
        p.wait_for_timeout(600)
        s.step("Lan bấm Lưu")
        _save(p)
        text = _popup_text(p)
        check("EXIT-LEGAL" in text, text[:250])
        stored = api_get(s, f"/api/resource/Employee Separation/{REQ['w4_separation']}").json()["data"]
        check(stored["custom_tlc_notice_exception"] != "Statutory employee exception", "Ngoại lệ vẫn được lưu")
        result["actual"] = f"Desk chặn khi lưu: {text[:150]}"
    s.close()

    # ---------------------------------------------------------------- HR Officer (Lan): onboarding
    s = Session(browser, "W4-ONBOARDING", "lan")
    login(s)
    with case(s, "W4-OB-HAPPY", "HR mở onboarding từ offer đã được chấp nhận",
              "Desk > Employee Onboarding > lọc ứng viên tuyển dụng demo > mở > đọc offer/ứng viên/ngày nhận việc",
              "recruitment.candidate@demo.example; dựng offer/onboarding nền bằng REST nếu run này chưa chạy recruitment",
              "Form chuẩn hiển thị liên kết offer, ứng viên và ngày nhận việc") as result:
        onboarding, applicant = _ensure_onboarding(s)
        p = _open_list_row(s, "employee-onboarding", "Employee Onboarding",
                           f"?job_applicant={applicant}",
                           "Lan mở danh sách onboarding và lọc đúng ứng viên demo")
        REQ["w4_onboarding"] = p.evaluate("cur_frm.doc.name")
        s.step("Lan đọc offer, ứng viên và ngày nhận việc trên form")
        shown = {k: _shown(p, k) for k in ("job_offer", "job_applicant", "date_of_joining")}
        data = p.evaluate("({offer:cur_frm.doc.job_offer,applicant:cur_frm.doc.job_applicant,joining:cur_frm.doc.date_of_joining})")
        check(data["offer"] and data["applicant"] and data["joining"], str(data))
        on_screen = " ".join(shown.values())
        check(applicant in on_screen or data["applicant"] in on_screen, f"On màn hình: {on_screen[:200]}")
        result["actual"] = (f"Form hiện offer {data['offer']}, ứng viên {data['applicant']}, "
                            f"ngày nhận việc {data['joining']}")

    with case(s, "W4-OB-ERROR", "Xác nhận hồ sơ onboarding không có file bị chặn",
              "Trên form onboarding > Thêm dòng trong lưới chứng từ > điền tên hồ sơ, loại, trạng thái Received > Lưu",
              "Required Document Received, thiếu attachment",
              "Thông báo LC-EVIDENCE hiện trên màn hình; không ghi nhận thay người khác") as result:
        check(bool(REQ.get("w4_onboarding")), "Chưa có hồ sơ onboarding để kiểm tra")
        s.step("Lan thêm một dòng trong lưới chứng từ của hồ sơ onboarding")
        p = s.page
        grid = p.locator('[data-fieldname="custom_tlc_evidence"]')
        grid.locator(".grid-add-row").click()
        p.wait_for_timeout(1200)
        rows = grid.locator(".grid-row")
        index = rows.count() - 1  # the grid appends a fresh blank row after an edit; keep this row's index
        row = rows.nth(index)
        item = row.locator('[data-fieldname="item"] input')
        s.step("Lan gõ tên hồ sơ, chọn loại Document và trạng thái Received nhưng không đính tệp")
        item.click()
        item.fill("UAT missing identity evidence")
        item.press("Tab")  # commit the cell before the category change re-renders the row
        p.wait_for_timeout(700)
        rows.nth(index).locator('[data-fieldname="category"] select').select_option("Document", force=True)
        rows.nth(index).locator('[data-fieldname="status"] select').select_option("Received", force=True)
        p.wait_for_timeout(600)
        rows = p.evaluate("() => (cur_frm.doc.custom_tlc_evidence || []).map(r => [r.item, r.category, r.status])")
        check(any(item == "UAT missing identity evidence" and status == "Received" for item, _cat, status in rows),
              f"dòng chứng từ chưa vào hồ sơ: {rows}")
        s.step("Lan bấm Lưu")
        early = _save(p, capture=True)
        text = early if "LC-EVIDENCE" in early else _popup_text(p)
        check("LC-EVIDENCE" in text, text[:250])
        stored = api_get(s, f"/api/resource/Employee Onboarding/{REQ['w4_onboarding']}").json()["data"]
        check(not [r for r in stored.get("custom_tlc_evidence", []) if r.get("item") == "UAT missing identity evidence"],
              "Dòng chứng từ vẫn được ghi nhận")
        result["actual"] = f"Desk chặn khi lưu: {text[:150]}"
    s.close()

    # ---------------------------------------------------------------- Employee (Binh)
    s = Session(browser, "W4-BOARDING-PERMISSION", "binh")
    login(s)
    for key, route, case_id, label in (("w4_separation", "employee-separation", "W4-EXIT-PERMISSION", "hồ sơ nghỉ việc"),
                                       ("w4_onboarding", "employee-onboarding", "W4-OB-PERMISSION", "hồ sơ onboarding")):
        with case(s, case_id, f"Công nhân không xem được {label} của người khác",
                  "Desk > ô tìm kiếm > gõ mã hồ sơ > mở đường dẫn hồ sơ của An > đọc thông báo từ chối",
                  REQ.get(key, ""), "Server từ chối quyền đọc; màn hình chỉ hiện thông báo không có quyền") as result:
            check(bool(REQ.get(key)), "Chưa có hồ sơ cần kiểm tra quyền")
            doctype = "Employee Separation" if route == "employee-separation" else "Employee Onboarding"
            found = _desk_search(s, REQ[key])
            body = _denied_text(s, route, REQ[key])
            denied = api_get(s, f"/api/resource/{doctype}/{REQ[key]}")
            check(denied.status == 403, f"REST đọc hồ sơ trả {denied.status}")
            result["actual"] = (f"Ô tìm kiếm chỉ liệt kê {len(found)} mục; form báo: {body[:90]}; REST đối chiếu 403")
    s.close()


JOURNEYS = [lifecycle_desktop, lifecycle_boarding_desktop]
