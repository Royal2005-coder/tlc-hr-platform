"""Bằng chứng UAT W6 Khảo sát ẩn danh trên Desk chuẩn.

HR tạo khảo sát bằng form (điền từng ô, thêm dòng trong lưới câu hỏi, bấm Lưu, chọn trạng thái),
phát hành, tạo phiên bản mới bằng nút; nhân viên bấm nút Trả lời ẩn danh và gửi trong hộp thoại;
kết quả theo bộ phận đọc từ hộp thoại mà nút "Kết quả theo bộ phận" mở ra trên màn hình.
REST chỉ dùng dựng dữ liệu nền (năm nhân viên kinh doanh nộp phiếu) và đối chiếu sau thao tác.
"""
from urllib.parse import quote

from lib import *

CAMPAIGN = "TLC Survey Campaign"
DEPT_ACCOUNTING = "Tài chính Kế toán - TLC"
DEPT_SALES = "Kinh doanh - TLC"

QUESTIONS = [
    {"key": "env_rating", "label": "Môi trường làm việc tổng thể", "options": "Rất tốt\nTốt\nBình thường\nCần cải thiện"},
    {"key": "support_rating", "label": "Hỗ trợ từ bộ phận quản lý", "options": "Rất tốt\nTốt\nChưa tốt"},
]


def desk_navigate(s, doctype, name=None):
    slug = doctype.lower().replace(" ", "-")
    url = f"{BASE}/desk/{slug}/{quote(name)}" if name else f"{BASE}/desk/{slug}/new"
    s.page.goto(url)
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1500)


def _field(p, fieldname):
    return p.locator(f"input[data-fieldname='{fieldname}']:visible, textarea[data-fieldname='{fieldname}']:visible").last


def _type(p, fieldname, value):
    field = _field(p, fieldname)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    field.click()
    p.wait_for_timeout(300)
    p.keyboard.press("Escape")
    p.wait_for_timeout(200)
    field.fill(value)
    field.press("Tab")
    p.wait_for_timeout(600)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)


def _choose(p, fieldname, value):
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


def _press_button(p, label, wait=3000):
    button = visible_button(p, label)
    expect(button).to_be_visible()
    button.click()
    p.wait_for_timeout(wait)
    p.wait_for_load_state("networkidle")


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


def _dialog_text(p):
    modal = p.locator(".modal:visible")
    expect(modal.first).to_be_visible()
    return " ".join(modal.last.inner_text().split())


def _add_question(p, item):
    """Điền một câu hỏi vào lưới: dùng dòng trống có sẵn (dòng 1) hoặc thêm dòng, qua trình sửa dòng của lưới."""
    grid = p.locator('[data-fieldname="questions"]')
    rows = grid.locator(".grid-row")
    header = 1 if rows.first.locator(".row-index").inner_text().strip() == "Không." else 0
    index = p.evaluate("() => (cur_frm.doc.questions || []).findIndex(q => !q.question_key)")
    if index < 0:
        grid.locator(".grid-add-row").click()
        p.wait_for_timeout(1200)
        index = p.evaluate("() => (cur_frm.doc.questions || []).length") - 1
    row = rows.nth(index + header)
    row.locator('[data-fieldname="question_key"]:visible').last.click()  # mở ô nhập của dòng
    p.wait_for_timeout(900)
    for fieldname, value in (("question_key", item["key"]), ("label", item["label"])):
        box = p.locator(f"input[data-fieldname='{fieldname}']:visible, "
                        f"textarea[data-fieldname='{fieldname}']:visible").last
        box.click()
        box.fill(value)
        box.press("Tab")
        p.wait_for_timeout(300)
    box = p.locator("textarea[data-fieldname='options']:visible, input[data-fieldname='options']:visible").last
    box.click()
    box.fill(item["options"])
    box.press("Tab")
    p.wait_for_timeout(500)
    p.keyboard.press("Escape")  # close the row editor; the values stay on the row
    p.wait_for_timeout(900)
    if p.locator("#freeze:visible, .modal-backdrop.grid-form:visible").count():
        for label in ("Hoàn tất|Done", "Lưu tắt", "Đóng|Close"):
            button = p.locator("button:visible").filter(has_text=re.compile(rf"^({label})$")).last
            if button.count():
                button.click()
                p.wait_for_timeout(900)
                break
    check(not p.locator("#freeze:visible").count(), "lớp freeze của lưới câu hỏi còn mở")


def _open_list_row(s, slug, doctype, query, step_text):
    s.step(step_text)
    p = s.page
    p.goto(f"{BASE}/desk/{slug}{query}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1600)
    row = p.locator(f'.list-row-container a[data-doctype="{doctype}"]').first
    check(row.count() > 0, f"Danh sách {slug} không có hồ sơ nào để mở")
    row.click()
    p.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=doctype)
    p.wait_for_timeout(1200)
    return p


def _answer_anonymously(p, answers):
    """Bấm Trả lời ẩn danh, chọn từng phương án trong hộp thoại rồi bấm Gửi phản hồi."""
    _press_button(p, "Trả lời ẩn danh", wait=1500)
    dialog = p.locator(".modal:visible").last
    expect(dialog).to_be_visible()
    selects = dialog.locator("select")
    check(selects.count() >= len(answers), f"Hộp thoại chỉ có {selects.count()} ô chọn")
    for position, option in enumerate(answers.values()):
        selects.nth(position).select_option(option)
        p.wait_for_timeout(250)
    p.locator(".modal:visible .btn-modal-primary").last.click()
    p.wait_for_timeout(3000)


def survey_lifecycle_and_versioning(browser):
    s_lan = Session(browser, "SUR-HR", "lan")
    try:
        login(s_lan)
        s = s_lan
        year = dt.date.today().year

        with case(s_lan, "SUR-01", "HR tạo khảo sát ẩn danh và phát hành",
                  "Desk > TLC Survey Campaign (Mới) > nhập tiêu đề, ngày mở/đóng, ngưỡng > thêm từng câu hỏi trong lưới > Lưu > chọn Open > Lưu",
                  f"Khảo sát môi trường làm việc {year}",
                  "Khảo sát ở trạng thái Open, phiên bản 1, ngưỡng >= 5, hai câu hỏi hiện trong lưới") as r:
            p = s_lan.page
            s.step("Lan mở form khảo sát mới")
            desk_navigate(s_lan, CAMPAIGN)
            s.step("Lan nhập tiêu đề, ngày mở, ngày đóng và ngưỡng công bố tối thiểu")
            _type(p, "title", f"Khảo sát môi trường làm việc {year}")
            _type(p, "opens_on", f"01-01-{year}")
            _type(p, "closes_on", f"31-12-{year}")
            _type(p, "minimum_results", "5")
            for item in QUESTIONS:
                s.step(f"Lan thêm câu hỏi “{item['label']}” vào lưới")
                _add_question(p, item)
            s.step("Lan bấm Lưu")
            _save(p)
            camp_name = p.url.rstrip("/").split("/")[-1]
            check("new" not in camp_name, f"Khảo sát chưa lưu: {camp_name}")
            REQ["camp_v1"] = camp_name
            s.step("Lan chọn trạng thái Open và bấm Lưu để phát hành")
            _choose(p, "status", "Open")
            _save(p)
            s.step("Lan đọc trạng thái, phiên bản và ngưỡng trên form")
            shown = {k: _shown(p, k) for k in ("status", "version", "minimum_results")}
            doc_data = api_get(s_lan, f"/api/resource/{CAMPAIGN}/{camp_name}").json()["data"]
            check(doc_data["status"] == "Open" and doc_data["version"] == 1
                  and doc_data["minimum_results"] >= 5, str(doc_data)[:200])
            rows = p.locator('[data-fieldname="questions"] .grid-row').filter(has_not_text="Không.").count()
            check(rows >= len(QUESTIONS), f"Lưới câu hỏi chỉ có {rows} dòng")
            r["actual"] = (f"{camp_name}: form hiện {shown['status'][:24]}, phiên bản {shown['version'][:14]}, "
                           f"ngưỡng {shown['minimum_results'][:14]}, lưới {rows} dòng câu hỏi")

        with case(s_lan, "SUR-02", "Tạo phiên bản khảo sát mới",
                  "Mở lại khảo sát đã phát hành trong danh sách > bấm nút Tạo phiên bản mới > đọc phiên bản và trạng thái",
                  REQ.get("camp_v1", ""), "Khảo sát mới Draft, phiên bản 2, liên kết phiên bản 1") as r:
            p = _open_list_row(s_lan, "tlc-survey-campaign", CAMPAIGN, f"?name={REQ['camp_v1']}",
                               "Lan mở lại khảo sát đã phát hành")
            s.step("Lan bấm nút Tạo phiên bản mới")
            _press_button(p, "Tạo phiên bản mới")
            v2_name = p.url.rstrip("/").split("/")[-1]
            check("new" not in v2_name and v2_name != REQ["camp_v1"], f"Không mở được phiên bản mới: {p.url}")
            REQ["camp_v2"] = v2_name
            s.step("Lan đọc số phiên bản, bản trước và trạng thái Nháp trên form")
            shown = {k: _shown(p, k) for k in ("version", "previous_version", "status")}
            v2_data = api_get(s_lan, f"/api/resource/{CAMPAIGN}/{v2_name}").json()["data"]
            check(v2_data["version"] == 2 and v2_data["previous_version"] == REQ["camp_v1"]
                  and v2_data["status"] == "Draft", str(v2_data)[:200])
            r["actual"] = (f"{v2_name}: form hiện phiên bản {shown['version'][:12]}, kế thừa "
                           f"{shown['previous_version'][:24]}, trạng thái {shown['status'][:16]}")

    finally:
        s_lan.close()


def survey_submission_and_privacy_journey(browser):
    s_an = Session(browser, "SUR-AN", "an")
    s_quang = Session(browser, "SUR-QUANG", "quang")
    s_lan = Session(browser, "SUR-LAN", "lan")
    try:
        login(s_an)
        login(s_lan)
        s = s_an
        camp = REQ.get("camp_v1")
        check(bool(camp), "Khảo sát chưa được tạo")

        with case(s_an, "SUR-03", "Nộp phản hồi ẩn danh không lưu định danh",
                  "An mở khảo sát trong danh sách > bấm Trả lời ẩn danh > chọn từng phương án > bấm Gửi phản hồi > đọc xác nhận",
                  camp, "Hệ thống ghi nhận trên màn hình; bảng tổng hợp/tham gia nội bộ vẫn bị từ chối quyền đọc (403)") as r:
            p = _open_list_row(s_an, "tlc-survey-campaign", CAMPAIGN, f"?name={camp}",
                               "An mở danh sách khảo sát và vào đúng khảo sát đang mở")
            s.step("An bấm nút Trả lời ẩn danh")
            s.step("An chọn phương án cho từng câu hỏi rồi bấm Gửi phản hồi")
            _answer_anonymously(p, {"env_rating": "Rất tốt", "support_rating": "Tốt"})
            text = _dialog_text(p)
            check("ghi nhận" in text.lower() or "hidden" in text.lower() or "ẩn danh" in text.lower(), text[:250])
            p.keyboard.press("Escape")
            p.wait_for_timeout(600)
            # Đối chiếu sau khi người dùng nộp xong: không có bảng phiếu cá nhân, bảng nội bộ không ai đọc được.
            leak = api_get(s_an, f"/api/resource/TLC Survey Aggregate?filters=[[\"campaign\",\"=\",\"{camp}\"]]")
            check(leak.status == 403, f"Đọc được bản tổng hợp nội bộ: {leak.status}")
            participation = api_get(s_an, f"/api/resource/TLC Survey Participation?filters=[[\"campaign\",\"=\",\"{camp}\"]]")
            check(participation.status == 403, f"Đọc được bảng tham gia nội bộ: {participation.status}")
            r["actual"] = (f"An bấm nút và gửi trong hộp thoại, màn hình báo: {text[:70]}; "
                           f"bảng tổng hợp/tham gia đối chiếu 403, không có phiếu cá nhân")

        with case(s_an, "SUR-04", "Chặn nộp trùng trong cùng một phiên bản",
                  "An mở lại chính khảo sát > bấm Trả lời ẩn danh lần hai > chọn phương án > bấm Gửi phản hồi > đọc thông báo chặn",
                  camp, "Màn hình báo đã gửi phản hồi cho phiên bản này (survey_duplicate), không ghi nhận phiếu thứ hai") as r:
            p = _open_list_row(s_an, "tlc-survey-campaign", CAMPAIGN, f"?name={camp}",
                               "An mở lại khảo sát vừa nộp")
            s.step("An bấm Trả lời ẩn danh lần thứ hai và cố gửi tiếp")
            _answer_anonymously(p, {"env_rating": "Tốt", "support_rating": "Tốt"})
            text = _dialog_text(p)
            check("survey_duplicate" in text or "đã gửi phản hồi" in text.lower(), text[:250])
            r["actual"] = f"Desk chặn ngay trên màn hình: {text[:120]}"

        # Dữ liệu nền cho ngưỡng công bố: năm nhân viên Kinh doanh khác cũng nộp phiếu.
        for number, code in enumerate(("sales01", "sales02", "sales03", "sales04", "sales05"), 1):
            s_sales = Session(browser, f"SUR-S{number}", code)
            s_sales.label = "Nhân viên kinh doanh hội sở"
            try:
                login(s_sales)
                api(s_sales, "tlc_hr.interface.survey.submit_anonymous", campaign=camp,
                    answers=json.dumps({"env_rating": "Rất tốt", "support_rating": "Tốt"}))
            finally:
                s_sales.close()

        # Lan đóng khảo sát bằng form thật: kết quả chỉ công bố sau khi đóng.
        s = s_lan
        p_lan = s_lan.page
        s_lan.step("Lan mở khảo sát và chuyển trạng thái Closed bằng nút Lưu")
        p_lan.goto(f"{BASE}/desk/tlc-survey-campaign?name={camp}")
        p_lan.wait_for_load_state("networkidle")
        p_lan.wait_for_timeout(1600)
        row = p_lan.locator(f'.list-row-container a[data-doctype="{CAMPAIGN}"]').first
        check(row.count() > 0, "Không thấy khảo sát trong danh sách")
        row.click()
        p_lan.wait_for_function("d => window.cur_frm && cur_frm.doctype === d", arg=CAMPAIGN)
        p_lan.wait_for_timeout(1200)
        _choose(p_lan, "status", "Closed")
        _save(p_lan)

        with case(s_lan, "SUR-05", "Bảo vệ riêng tư: chặn hiển thị dưới ngưỡng tối thiểu",
                  "Lan mở khảo sát đã đóng > bấm Kết quả theo bộ phận > gõ bộ phận Tài chính Kế toán > đọc hộp thoại báo bị ẩn",
                  DEPT_ACCOUNTING, "Hộp thoại trên màn hình báo chưa đủ ngưỡng công bố và không hiện phân bố câu trả lời") as r:
            p = _open_list_row(s_lan, "tlc-survey-campaign", CAMPAIGN, f"?name={camp}",
                               "Lan mở lại khảo sát đã đóng")
            s.step("Lan bấm nút Kết quả theo bộ phận")
            _press_button(p, "Kết quả theo bộ phận", wait=1500)
            s.step("Lan gõ bộ phận Tài chính Kế toán - TLC và xác nhận")
            box = p.locator(".modal:visible input[data-fieldname='department']").last
            expect(box).to_be_visible()
            box.click()
            box.press_sequentially(DEPT_ACCOUNTING, delay=45)
            p.wait_for_timeout(2200)
            box.press("Enter")
            p.wait_for_timeout(1200)
            primary = p.locator(".modal:visible .btn-modal-primary")
            if primary.count() and primary.last.is_visible():
                primary.last.click()
            p.wait_for_timeout(2500)
            text = _dialog_text(p)
            check("ngưỡng" in text.lower() or "suppressed" in text.lower(), text[:250])
            check("Rất tốt" not in text, f"Lộ phân bố câu trả lời dưới ngưỡng: {text[:200]}")
            api_check = s_lan.page.request.get(
                f"{BASE}/api/method/tlc_hr.interface.survey.results?campaign={camp}"
                f"&department={quote(DEPT_ACCOUNTING)}")
            msg = api_check.json().get("message", {})
            check(msg.get("suppressed") is True and "questions" not in msg, str(msg)[:200])
            r["actual"] = f"Hộp thoại trên màn hình: {text[:110]}; đối chiếu server suppressed=True"

        login(s_quang)
        s = s_quang
        with case(s_quang, "SUR-06", "Hiển thị tổng hợp khi đạt đủ ngưỡng tối thiểu",
                  "Quang mở khảo sát đã đóng > bấm Kết quả theo bộ phận > gõ bộ phận Kinh doanh > đọc phân bố trên màn hình",
                  f"{DEPT_SALES}, 6 phản hồi", "Hộp thoại hiện số phản hồi và phân bố câu trả lời của từng câu hỏi") as r:
            p = _open_list_row(s_quang, "tlc-survey-campaign", CAMPAIGN, f"?name={camp}",
                               "Quang mở danh sách khảo sát và vào khảo sát đã đóng")
            s.step("Quang bấm nút Kết quả theo bộ phận")
            _press_button(p, "Kết quả theo bộ phận", wait=1500)
            s.step("Quang gõ bộ phận Kinh doanh - TLC và xác nhận")
            box = p.locator(".modal:visible input[data-fieldname='department']").last
            expect(box).to_be_visible()
            box.click()
            box.press_sequentially(DEPT_SALES, delay=45)
            p.wait_for_timeout(2200)
            box.press("Enter")
            p.wait_for_timeout(1200)
            primary = p.locator(".modal:visible .btn-modal-primary")
            if primary.count() and primary.last.is_visible():
                primary.last.click()
            p.wait_for_timeout(2500)
            text = _dialog_text(p)
            check("Môi trường làm việc tổng thể" in text, text[:250])
            check("Rất tốt" in text and "Tốt" in text, f"Phân bố câu trả lời không hiện trên màn hình: {text[:200]}")
            api_check = p.request.get(f"{BASE}/api/method/tlc_hr.interface.survey.results?campaign={camp}"
                                      f"&department={quote(DEPT_SALES)}")
            msg = api_check.json().get("message", {})
            check(not msg.get("suppressed") and msg.get("responses", 0) >= 5 and "questions" in msg, str(msg)[:250])
            r["actual"] = (f"Hộp thoại hiện kết quả {msg['responses']} phản hồi của {len(msg['questions'])} câu hỏi; "
                           f"màn hình: {text[:90]}")

    finally:
        s_an.close()
        s_quang.close()
        s_lan.close()


JOURNEYS = [
    survey_lifecycle_and_versioning,
    survey_submission_and_privacy_journey,
]
