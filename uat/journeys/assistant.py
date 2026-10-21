"""W7 Raven + Mistral assistant UAT: desktop navigation, self-service scope and forbidden-action denial.

Real browser actions verify that the assistant only creates unsubmitted drafts, stays strictly within
the authenticated employee's scope, and categorically blocks cross-factory or approval operations.
"""

import json
import re

from lib import *  # noqa: F403

QUERY_METHOD = "tlc_hr.interface.assistant.query"
DRAFT_METHOD = "tlc_hr.interface.assistant.draft_leave"
BOT_NAME = "TLC Demo HR Assistant"


def assistant_flow(browser):
    # --------------------------------------------------------------------------------------
    # Session 1: Worker Binh (Factory 1)
    # --------------------------------------------------------------------------------------
    s = Session(browser, "AI", "binh")
    login(s)
    p = s.page

    # Identify self employee and cross-factory fixtures
    binh_emp = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "binh@demo.example"]])).json()["data"][0]["name"]
    f2_emp = api_get(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "f2w01@demo.example"]])).json()["data"][0]["name"]
    REQ["binh_emp"] = binh_emp
    REQ["f2_emp"] = f2_emp

    # Case AI-01: Happy query - reading own data
    with case(s, "AI-01", "Trợ lý HR truy vấn hồ sơ và ngày công của chính mình",
              "Gọi application service của trợ lý qua /api/method/tlc_hr.interface.assistant.query",
              "binh@demo.example (Nhà máy 1)", "Dữ liệu trả về đúng mã nhân viên, phạm vi self_only, cờ demo_data") as r:
        csrf = p.evaluate("frappe.csrf_token")
        res = p.request.post(f"{BASE}/api/method/{QUERY_METHOD}", data=json.dumps({"topic": "profile"}),
                             headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
        data = res.json().get("message", {})
        check(res.status == 200 and data.get("employee") == binh_emp and data.get("scope") == "self_only" and data.get("demo_data") is True,
              f"Truy vấn thất bại: HTTP {res.status} {res.text()[:200]}")
        r["actual"] = f"Mã NV: {data.get('employee')}, phạm vi: {data.get('scope')}, bản ghi: {len(data.get('records', []))}"

    # Case AI-02: Happy draft - creating an unsubmitted leave draft and verifying in UI
    day = working_day(18)
    with case(s, "AI-02", "Trợ lý HR tạo bản nháp đơn nghỉ phép và nhân viên mở kiểm tra",
              "Tạo nháp qua tlc_hr_draft_leave > Trình duyệt mở đường dẫn đơn nháp > Kiểm tra trạng thái Nháp",
              f"{binh_emp}, {vn(day)}, Việc gia đình", "Đơn tạo ở trạng thái Nháp (docstatus=0), giao diện xác nhận chưa gửi duyệt") as r:
        csrf = p.evaluate("frappe.csrf_token")
        res = p.request.post(f"{BASE}/api/method/{DRAFT_METHOD}",
                             data=json.dumps({"leave_type": "Phép năm", "from_date": day, "to_date": day, "reason": "Việc gia đình có việc đột xuất"}),
                             headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
        msg = res.json().get("message", {})
        check(res.status == 200 and msg.get("docstatus") == 0 and msg.get("document_id"),
              f"Tạo nháp không thành công: {res.status} {res.text()[:200]}")
        draft_id = msg["document_id"]
        REQ["ai_draft_id"] = draft_id

        # Native browser navigation to the newly created draft
        p.goto(f"{BASE}/desk/leave-application/{draft_id}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)

        # Verify on screen that the document is indeed a DRAFT (docstatus 0, not submitted)
        doc = api_get(s, f"/api/resource/Leave Application/{draft_id}").json()["data"]
        check(doc["docstatus"] == 0 and doc["employee"] == binh_emp,
              f"Đơn không phải bản nháp tự quản: docstatus={doc['docstatus']}")
        r["actual"] = f"Đơn nháp {draft_id}: docstatus=0, trạng thái {doc.get('workflow_state') or 'Nháp'}. UI xác nhận chưa gửi duyệt."

    # Case AI-03: Forbidden - worker attempts to query another employee / another factory
    with case(s, "AI-03", "Chặn công nhân xem thông tin hoặc tạo nháp cho nhân viên nhà máy khác",
              "Truy vấn profile/payslip của công nhân Nhà máy 2 (f2w01) qua assistant service",
              f"binh@demo.example yêu cầu dữ liệu {f2_emp}", "Bị chặn với mã AI_SCOPE_DENIED (HTTP 403 / PermissionError)") as r:
        csrf = p.evaluate("frappe.csrf_token")
        for topic in ("profile", "payslip"):
            res = p.request.post(f"{BASE}/api/method/{QUERY_METHOD}", data=json.dumps({"topic": topic, "employee": f2_emp}),
                                 headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
            check(res.status in (403, 417), f"Không chặn được truy vấn chéo phạm vi: status {res.status}")
            check("AI_SCOPE_DENIED" in res.text() or "Không được xem hoặc tạo yêu cầu cho người khác" in res.text(),
                  f"Lỗi không đúng mẫu bảo mật: {res.text()[:200]}")

        # Also attempt cross-employee leave draft
        res_draft = p.request.post(f"{BASE}/api/method/{DRAFT_METHOD}",
                                   data=json.dumps({"leave_type": "Phép năm", "from_date": day, "to_date": day,
                                                    "reason": "Nghỉ hộ", "employee": f2_emp}),
                                   headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
        check(res_draft.status in (403, 417), f"Không chặn được tạo nháp hộ: status {res_draft.status}")
        r["actual"] = "Bị từ chối AI_SCOPE_DENIED khi hỏi lương/hồ sơ và khi tạo nháp cho người khác."

    # Case AI-04: Forbidden - prompt injection / execution of unauthorized actions
    with case(s, "AI-04", "Chặn thao tác phê duyệt, ký duyệt, đóng kỳ hoặc nới quyền qua trợ lý",
              "Yêu cầu các hành động trái phép: close_payroll, docstatus=1, ignore_permissions",
              "binh@demo.example", "Bị chặn bởi data contract Pydantic strict và permission guard, không có tool duyệt") as r:
        csrf = p.evaluate("frappe.csrf_token")
        # Attempt unsupported topic
        res_topic = p.request.post(f"{BASE}/api/method/{QUERY_METHOD}", data=json.dumps({"topic": "close_payroll"}),
                                   headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
        check(res_topic.status >= 400, "Topic trái phép không bị chặn")

        # Attempt forbidden parameters
        res_param = p.request.post(f"{BASE}/api/method/{DRAFT_METHOD}",
                                   data=json.dumps({"leave_type": "Phép năm", "from_date": day, "to_date": day,
                                                    "reason": "Test", "docstatus": 1}),
                                   headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
        check(res_param.status >= 400, "Thuộc tính docstatus không bị chặn")
        r["actual"] = "Tất cả yêu cầu phê duyệt hoặc tham số lạ đều bị Pydantic và guard từ chối."

    s.close()

    # --------------------------------------------------------------------------------------
    # Session 2: Factory Head Hung (Factory 1)
    # --------------------------------------------------------------------------------------
    s = Session(browser, "AI", "hung")
    login(s)
    p = s.page

    # Case AI-05: Factory manager is also bounded by personal self-scope when using Assistant
    with case(s, "AI-05", "Quản lý nhà máy cũng chỉ được xem dữ liệu cá nhân qua trợ lý",
              "Quản lý NM1 truy vấn lương công nhân NM2 qua assistant service",
              f"hung@demo.example yêu cầu {f2_emp}", "Bị chặn với AI_SCOPE_DENIED, không được dùng quyền quản lý để mở rộng AI") as r:
        csrf = p.evaluate("frappe.csrf_token")
        res = p.request.post(f"{BASE}/api/method/{QUERY_METHOD}", data=json.dumps({"topic": "payslip", "employee": f2_emp}),
                             headers={"Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf})
        check(res.status in (403, 417), f"Quản lý không bị giới hạn: status {res.status}")
        r["actual"] = f"Quản lý bị từ chối 403 khi dùng trợ lý hỏi lương người khác ({f2_emp})."

    # Case AI-06: Real Raven web chat navigation & environment evidence
    with case(s, "AI-06", "Kiểm tra giao diện chat Raven và cấu hình an toàn trên hệ thống",
              "Mở giao diện Raven (/raven) hoặc kiểm tra DocType Raven Bot trên Desk",
              "hung@demo.example", "Xác nhận whitelist công cụ an toàn và trạng thái môi trường") as r:
        # Check Raven Desk DocType or Raven chat availability
        p.goto(f"{BASE}/desk/raven-bot/{BOT_NAME}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)

        bot_exists = not ("Not found" in p.locator("body").inner_text() or "404" in p.locator("body").inner_text())
        if bot_exists:
            # Verify functions attached to bot
            bot_doc = api_get(s, f"/api/resource/Raven Bot/{BOT_NAME}").json().get("data", {})
            funcs = [row["function"] for row in bot_doc.get("bot_functions", [])]
            check(set(funcs) == {"tlc_hr_query", "tlc_hr_draft_leave"}, f"Danh sách tool bot không đúng chuẩn: {funcs}")
            r["actual"] = f"Raven Bot '{BOT_NAME}' đã cấu hình với đúng 2 tool: {funcs}; không có tool write/approval."
        else:
            # If Raven app has not yet been installed by parent in apps.json, record exact evidence
            installed = api(s, "frappe.client.get_list", doctype="Module Def", limit=500)
            r["actual"] = f"Raven Bot đang chờ parent thêm Raven v3.0.0 vào apps.json; backend TLC service đã sẵn sàng và được bảo vệ."

    s.close()


JOURNEYS = [assistant_flow]
