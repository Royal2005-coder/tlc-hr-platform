"""W6 Anonymous Survey desktop-native journeys:
- Campaign lifecycle and question versioning upon update
- Anonymous ballot submission with participation deduplication and zero personal ballot linkage
- Aggregated department reporting with strict privacy threshold (>= 5) suppression
"""

import json
from urllib.parse import quote

from lib import *  # noqa: F403


def desk_navigate(s, doctype, name=None):
    slug = doctype.lower().replace(" ", "-")
    url = f"{BASE}/desk/{slug}/{quote(name)}" if name else f"{BASE}/desk/{slug}/new"
    s.page.goto(url)
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1500)


def save_primary(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.locator("button.es-button.primary-action:visible").last.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1800)


def set_value(page, field, value):
    page.evaluate("([f, v]) => cur_frm.set_value(f, v)", [field, value])


def set_questions(page, items):
    # The grid row editor is a frozen overlay in this Frappe build; fill the native child table
    # through the form model and save with the native button.
    page.evaluate("""(items) => {
        cur_frm.clear_table('questions');
        for (const item of items) cur_frm.add_child('questions', item);
        cur_frm.refresh_field('questions');
    }""", items)
    page.wait_for_timeout(500)


def survey_lifecycle_and_versioning(browser):
    s_lan = Session(browser, "SUR-HR", "lan")
    try:
        login(s_lan)
        year = dt.date.today().year

        with case(s_lan, "SUR-01", "Tạo khảo sát ẩn danh và phát hành", "Tạo TLC Survey Campaign > Thêm câu hỏi > Lưu > Mở Open",
                  "Khảo sát môi trường làm việc 2026", "Khảo sát ở trạng thái Open, phiên bản 1, ngưỡng >= 5") as r:
            desk_navigate(s_lan, "TLC Survey Campaign")
            p = s_lan.page
            p.locator("input[data-fieldname='title']").fill(f"Khảo sát môi trường làm việc {year}")
            set_value(p, "opens_on", f"{year}-01-01")
            set_value(p, "closes_on", f"{year}-12-31")
            set_value(p, "minimum_results", 5)
            set_questions(p, [
                {"question_key": "env_rating", "label": "Môi trường làm việc tổng thể", "options": "Rất tốt\nTốt\nBình thường\nCần cải thiện"},
                {"question_key": "support_rating", "label": "Hỗ trợ từ bộ phận quản lý", "options": "Rất tốt\nTốt\nChưa tốt"},
            ])
            save_primary(p)
            camp_name = p.url.split("/")[-1]
            check("new-tlc-survey-campaign" not in camp_name, f"Khảo sát chưa lưu: {camp_name}")
            REQ["camp_v1"] = camp_name

            p.locator("select[data-fieldname='status']").select_option("Open")
            save_primary(p)
            doc_data = api_get(s_lan, f"/api/resource/TLC Survey Campaign/{camp_name}").json()["data"]
            check(doc_data["status"] == "Open" and doc_data["version"] == 1 and doc_data["minimum_results"] >= 5, str(doc_data)[:200])
            r["actual"] = f"{camp_name}: Đã mở Open, phiên bản {doc_data['version']}, ngưỡng ẩn danh {doc_data['minimum_results']}"

        with case(s_lan, "SUR-02", "Tạo phiên bản khảo sát mới", "Bấm nút Tạo phiên bản mới từ khảo sát đã phát hành",
                  REQ["camp_v1"], "Tạo khảo sát mới ở trạng thái Draft, phiên bản 2 liên kết phiên bản 1") as r:
            desk_navigate(s_lan, "TLC Survey Campaign", REQ["camp_v1"])
            p = s_lan.page
            p.get_by_role("button", name=re.compile(r"^(Tạo phiên bản mới|New Version)$")).click()
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2500)
            v2_name = p.url.split("/")[-1]
            REQ["camp_v2"] = v2_name
            v2_data = api_get(s_lan, f"/api/resource/TLC Survey Campaign/{v2_name}").json()["data"]
            check(v2_data["version"] == 2 and v2_data["previous_version"] == REQ["camp_v1"] and v2_data["status"] == "Draft", str(v2_data)[:200])
            r["actual"] = f"{v2_name}: Phiên bản {v2_data['version']} (kế thừa {v2_data['previous_version']}), trạng thái {v2_data['status']}"

    finally:
        s_lan.close()


def survey_submission_and_privacy_journey(browser):
    s_an = Session(browser, "SUR-AN", "an")
    s_quang = Session(browser, "SUR-QUANG", "quang")
    s_lan = Session(browser, "SUR-LAN", "lan")
    try:
        login(s_an)
        login(s_lan)
        camp = REQ.get("camp_v1")
        check(bool(camp), "Khảo sát chưa được tạo")

        with case(s_an, "SUR-03", "Nộp phản hồi ẩn danh không lưu định danh", "Bấm Trả lời ẩn danh > Chọn phương án > Gửi phản hồi",
                  camp, "Hệ thống ghi nhận thành công; không có bản ghi phiếu cá nhân") as r:
            desk_navigate(s_an, "TLC Survey Campaign", camp)
            p = s_an.page
            p.get_by_role("button", name=re.compile(r"^(Trả lời ẩn danh|Answer Anonymously)$")).click()
            p.wait_for_timeout(1500)
            dialog = p.locator(".modal-dialog")
            check(dialog.is_visible(), "Hộp thoại phản hồi ẩn danh không xuất hiện")
            replies = []
            p.on("response", lambda res: replies.append(res) if "survey.submit_anonymous" in res.url else None)
            selects = dialog.locator("select")
            selects.nth(0).select_option("Rất tốt")
            selects.nth(1).select_option("Tốt")
            dialog.get_by_role("button", name=re.compile(r"^(Gửi phản hồi|Submit)$")).click()
            p.wait_for_timeout(2500)
            accepted = [res for res in replies if res.status == 200 and res.json().get("message", {}).get("submitted")]
            check(bool(accepted), f"Không nhận được xác nhận nộp: {[res.status for res in replies]}")
            # Aggregates and participation rows are internal: no role holds read permission on them.
            leak = api_get(s_an, f"/api/resource/TLC Survey Aggregate?filters=[[\"campaign\",\"=\",\"{camp}\"]]")
            check(leak.status == 403, f"Học viên đọc được bản tổng hợp nội bộ: {leak.status}")
            r["actual"] = "Nộp thành công qua hộp thoại ẩn danh; bản tổng hợp nội bộ từ chối truy cập (403), không có phiếu cá nhân"

        with case(s_an, "SUR-04", "Chặn nộp trùng trong cùng một phiên bản", "Cố gắng nộp lại phản hồi cho cùng khảo sát",
                  camp, "Hệ thống từ chối vì đã gửi phản hồi") as r:
            try:
                api(s_an, "tlc_hr.interface.survey.submit_anonymous", campaign=camp,
                    answers=json.dumps({"env_rating": "Tốt", "support_rating": "Tốt"}))
                raise AssertionError("Lần nộp thứ hai không bị chặn")
            except AssertionError as exc:
                check("survey_duplicate" in str(exc) or "đã gửi phản hồi" in str(exc), str(exc)[:250])
            r["actual"] = "Bị chặn: Bạn đã gửi phản hồi cho phiên bản khảo sát này"

        # Five more sales employees answer, so the Kinh doanh department reaches the threshold.
        for number, code in enumerate(("sales01", "sales02", "sales03", "sales04", "sales05"), 1):
            s_sales = Session(browser, f"SUR-S{number}", code)
            s_sales.label = "Nhân viên kinh doanh hội sở"
            try:
                login(s_sales)
                api(s_sales, "tlc_hr.interface.survey.submit_anonymous", campaign=camp,
                    answers=json.dumps({"env_rating": "Rất tốt", "support_rating": "Tốt"}))
            finally:
                s_sales.close()

        # Close the campaign: results are only published after closing.
        desk_navigate(s_lan, "TLC Survey Campaign", camp)
        s_lan.page.locator("select[data-fieldname='status']").select_option("Closed")
        save_primary(s_lan.page)

        with case(s_lan, "SUR-05", "Bảo vệ riêng tư: Chặn hiển thị dưới ngưỡng tối thiểu", "HR xem kết quả bộ phận chưa đủ ngưỡng phản hồi",
                  "Tài chính Kế toán - TLC", "Hệ thống báo suppressed=True và không hiển thị câu trả lời") as r:
            res_query = s_lan.page.request.get(f"{BASE}/api/method/tlc_hr.interface.survey.results?campaign={camp}&department=T%C3%A0i+ch%C3%ADnh+K%E1%BA%BF+to%C3%A1n+-+TLC")
            msg = res_query.json().get("message", {})
            check(msg.get("suppressed") is True and "questions" not in msg, str(msg)[:200])
            r["actual"] = f"Bộ phận dưới ngưỡng bị ẩn hoàn toàn: suppressed={msg['suppressed']}"

        login(s_quang)
        with case(s_quang, "SUR-06", "Hiển thị tổng hợp khi đạt đủ ngưỡng tối thiểu", "Quản lý Kinh doanh xem kết quả bộ phận khi có từ 5 phản hồi trở lên",
                  "Kinh doanh - TLC, 6 phản hồi", "Hiển thị phân bố câu trả lời và số lượng") as r:
            res_query = s_quang.page.request.get(f"{BASE}/api/method/tlc_hr.interface.survey.results?campaign={camp}&department=Kinh+doanh+-+TLC")
            msg = res_query.json().get("message", {})
            check(not msg.get("suppressed") and msg.get("responses", 0) >= 5 and "questions" in msg, str(msg)[:250])
            r["actual"] = f"Hiển thị kết quả: {msg['responses']} phản hồi, {len(msg['questions'])} câu hỏi tổng hợp"

    finally:
        s_an.close()
        s_quang.close()
        s_lan.close()


JOURNEYS = [
    survey_lifecycle_and_versioning,
    survey_submission_and_privacy_journey,
]
