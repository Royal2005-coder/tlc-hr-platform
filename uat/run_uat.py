"""End-to-end UAT v3 of TLC HRM on the standard Frappe HR interface: user journeys per role, recorded, with real assertions.

Employees work in the Frappe HR app (/hrms); line managers, HR and the director work on the Frappe desk in the workspace of their
role. The TLC rules under test: the approval route (line manager then HR), no self approval, a reason to reject, data scope.
Run (on the k3s node): ~/tlc-hr/tlc-hr-platform/uat/run_uat.sh --reset   (expected numbers assume the clean TLC demo)
"""

import datetime as dt
import json
import os
import re
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:30080")
PASSWORD = os.environ["DEMO_PASSWORD"]
RUN_ID = os.environ.get("RUN_ID") or dt.datetime.now().strftime("%Y%m%d-%H%M")
OUT = Path(os.environ.get("OUT_DIR", "/uat/out")) / RUN_ID
DESKTOP = {"width": 1366, "height": 820}
PHONE = {"width": 390, "height": 844}
SLOW_MO = int(os.environ.get("SLOW_MO", "250"))
TO_MANAGER, TO_HR, APPROVED, REJECTED, DRAFT = "Chờ quản lý duyệt", "Chờ nhân sự duyệt", "Đã duyệt", "Từ chối", "Nháp"

ACCOUNTS = {
    "an": {"name": "Nguyễn Hoài An", "role": "Nhân viên văn phòng hội sở (Kinh doanh)", "workforce": "Hội sở", "approver": "Trần Minh Quang"},
    "binh": {"name": "Trần Văn Bình", "role": "Công nhân Nhà máy 1 - điện thoại", "workforce": "Nhà máy", "approver": "Đặng Văn Hùng"},
    "f2w01": {"name": None, "role": "Công nhân Nhà máy 2 - điện thoại", "workforce": "Nhà máy", "approver": "Lương Quốc Hải"},
    "hung": {"name": "Đặng Văn Hùng", "role": "Quản lý Nhà máy 1 (Head Manager nhà máy)", "workforce": "Nhà máy", "approver": "Nguyễn Văn Thành"},
    "hoa": {"name": "Lê Thị Hòa", "role": "HR hội sở - Giám đốc nhân sự (HR Lead)", "workforce": "Hội sở", "approver": "Nguyễn Văn Thành"},
    "lan": {"name": "Hoàng Thị Lan", "role": "HR hội sở - Chuyên viên nhân sự (HR Officer)", "workforce": "Hội sở", "approver": "Lê Thị Hòa"},
    "thanh": {"name": "Nguyễn Văn Thành", "role": "CEO hội sở - Tổng giám đốc", "workforce": "Hội sở", "approver": None},
}
# Functional matrix: where each account works and what it may do (checked through the landing page and the API).
SECTIONS = ["hrms", "ws_manager", "ws_hr", "ws_ceo", "approve", "company"]
SECTION_LABEL = {"hrms": "App Frappe HR (/hrms)", "ws_manager": "Workspace TLC Quản lý", "ws_hr": "Workspace TLC Nhân sự",
                 "ws_ceo": "Workspace TLC Điều hành", "approve": "Duyệt đơn", "company": "Xem toàn công ty"}
EXPECTED_SECTIONS = {
    "an": {"hrms"}, "binh": {"hrms"}, "f2w01": {"hrms"},
    "hung": {"ws_manager", "approve"},
    "hoa": {"ws_hr", "approve", "company"}, "lan": {"ws_hr", "approve", "company"},
    "thanh": {"ws_ceo", "approve", "company"},
}
WORKSPACE_KEY = {"TLC Quản lý": "ws_manager", "TLC Nhân sự": "ws_hr", "TLC Điều hành": "ws_ceo"}

RESULTS, MATRIX, VIDEOS, REQ = [], {}, [], {}


def working_day(n):
    day, found = dt.date.today(), 0
    while found < n:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            found += 1
    return day.isoformat()


def vn(d):
    return dt.date.fromisoformat(d).strftime("%d-%m-%Y")


CAPTION_JS = """
(text) => {
  if (text !== undefined) sessionStorage.setItem('uat-cap', text);
  const t = sessionStorage.getItem('uat-cap'); if (!t) return;
  let el = document.getElementById('uat-cap');
  if (!el) { el = document.createElement('div'); el.id = 'uat-cap';
    const top = window.__uatPos === 'top';
    el.style.cssText = 'position:fixed;left:8px;' + (top ? 'top:64px;right:8px;' : 'bottom:8px;max-width:62%;') +
      'z-index:2147483647;background:rgba(17,24,39,.86);color:#fff;border-radius:8px;' +
      'font:600 13px/1.35 system-ui,sans-serif;padding:6px 12px;pointer-events:none';
    document.documentElement.appendChild(el); }
  el.textContent = t;
}
"""
CAPTION_INIT = "window.addEventListener('DOMContentLoaded', () => { (" + CAPTION_JS + ")(); });"


class Session:
    def __init__(self, browser, code, account, phone=False):
        self.code, self.account, self.phone = code, account, phone
        self.label = ACCOUNTS[account]["role"]
        viewport = PHONE if phone else DESKTOP
        self.context = browser.new_context(viewport=viewport, record_video_dir=str(OUT / "videos" / "raw"), record_video_size=viewport,
                                           locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh", is_mobile=phone, has_touch=phone,
                                           device_scale_factor=2 if phone else 1)
        self.context.add_init_script("window.__uatPos = '" + ("top" if phone else "bottom") + "';")
        self.context.add_init_script(CAPTION_INIT)
        self.context.set_default_timeout(25000)
        self.page = self.context.new_page()
        self.page.on("dialog", lambda d: d.accept())
        self.t0 = time.monotonic()
        self.index = len(VIDEOS) + 1

    def caption(self, text):
        try:
            self.page.evaluate(CAPTION_JS, f"{self.code} · {self.account}@demo.example · {text}")
        except Exception:
            pass

    def stamp(self):
        seconds = int(time.monotonic() - self.t0)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def close(self):
        video = self.page.video
        self.context.close()
        name = f"{self.index:02d}_{self.code}_{self.account}.webm"
        Path(video.path()).rename(OUT / "videos" / name)
        VIDEOS.append({"file": f"videos/{name}", "code": self.code, "account": self.account, "role": self.label,
                       "device": "Điện thoại 390x844" if self.phone else "Máy tính 1366x820"})


@contextmanager
def case(s, case_id, function, steps, data, expected):
    row = {"id": case_id, "account": f"{s.account}@demo.example", "role": s.label, "function": function, "steps": steps,
           "data": data, "expected": expected, "actual": "", "status": "", "time": s.stamp(), "shot": "",
           "run_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "video": f"videos/{s.index:02d}_{s.code}_{s.account}.webm"}
    s.caption(f"{case_id} · {function}")
    found = {}
    try:
        yield found
        row["actual"], row["status"] = found.get("actual", "Đúng như mong đợi"), "Đạt"
    except Exception as exc:
        row["actual"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
        row["status"] = "Không đạt"
        row["trace"] = traceback.format_exc()[-1500:]
    s.page.wait_for_timeout(700)
    try:
        path = OUT / "shots" / f"{case_id}.png"
        s.page.screenshot(path=str(path))
        row["shot"] = f"shots/{path.name}"
    except Exception:
        pass
    RESULTS.append(row)
    print(f"{row['status']:10} {case_id:8} {function}: {row['actual'][:150]}", flush=True)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------------------------------- common steps

def login(s):
    p = s.page
    p.goto(f"{BASE}/login")
    s.caption("Đăng nhập")
    p.locator("#login_email").fill(f"{s.account}@demo.example")
    p.locator("#login_password").fill(PASSWORD)
    p.locator("form.form-login button[type=submit]").click()
    p.wait_for_url(lambda url: "/login" not in url, timeout=30000)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)


def api(s, method, **params):
    res = s.page.request.get(f"{BASE}/api/method/{method}", params=params)
    return res.json().get("message")


def api_get(s, path):
    return s.page.request.get(f"{BASE}{path}")


def state_of(s, name):
    return api_get(s, f"/api/resource/Leave Application/{name}").json()["data"]["workflow_state"]


def visible_button(p, text):
    return p.locator("button:visible", has_text=text).last


def first_case(s, case_id):
    """Login: the account lands on the standard interface of its role; the functional matrix is read from the server."""
    info = ACCOUNTS[s.account]
    expected = EXPECTED_SECTIONS[s.account]
    where = "app Frappe HR (/hrms)" if "hrms" in expected else "desk, " + next(SECTION_LABEL[k] for k in expected if k.startswith("ws_"))
    with case(s, case_id, "Đăng nhập vào đúng giao diện của vai trò", "Đăng nhập", f"{s.account}@demo.example",
              f"Vào {where}; quyền: {', '.join(SECTION_LABEL[k] for k in SECTIONS if k in expected)}") as r:
        login(s)
        p = s.page
        url = p.url.replace(BASE, "")
        shown = set()
        if url.startswith("/hrms"):
            shown.add("hrms")
        else:
            ws = next((name for name in WORKSPACE_KEY if name in p.locator("body").inner_text()), None)
            if ws:
                shown.add(WORKSPACE_KEY[ws])
        roles = set(p.evaluate("(window.frappe && frappe.user_roles) || []")) if not url.startswith("/hrms") else set()
        if roles.intersection({"Leave Approver", "TLC HR Lead", "TLC HR Officer"}):
            shown.add("approve")
        if len(api_get(s, "/api/resource/Employee?limit_page_length=500").json().get("data", [])) == 60:
            shown.add("company")
        MATRIX[s.account] = [k for k in SECTIONS if k in shown]
        check(shown == expected, f"vào {url}; quyền {sorted(shown)}")
        if s.phone:
            overflow = p.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(overflow <= 1, f"tràn ngang {overflow}px")
        r["actual"] = f"Vào {url}; quyền: {', '.join(SECTION_LABEL[k] for k in MATRIX[s.account])}"


# ---------------------------------------------------------------------------------------------------- the Frappe HR app

def hrms_request_leave(s, start, end, reason, half=False):
    """Frappe HR app: Xin nghỉ phép → fill → Lưu → Hành động → Gửi duyệt. Returns the request name."""
    p = s.page
    p.goto(f"{BASE}/hrms/home")
    p.wait_for_load_state("networkidle")
    p.get_by_text("Xin nghỉ phép", exact=True).first.click()
    p.wait_for_url(re.compile(r".*/leave-applications/new"))
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1200)
    p.get_by_text("Chọn Loại nghỉ phép").click()
    p.get_by_text("Phép năm", exact=True).last.click()
    dates = p.locator("input[type=date]")
    dates.nth(0).fill(start)
    dates.nth(1).fill(end)
    if half:
        p.get_by_text("Nửa ngày", exact=True).click()
    p.locator("textarea").first.fill(reason)
    p.wait_for_timeout(1500)
    visible_button(p, "Lưu").click()
    p.wait_for_url(re.compile(r".*/leave-applications/HR-LAP-\d{4}-\d+"), timeout=30000)
    name = re.search(r"HR-LAP-\d{4}-\d+", p.url).group(0)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1200)
    visible_button(p, "Hành động").click()
    p.wait_for_timeout(800)
    p.get_by_role("button", name="Gửi duyệt").last.click()
    p.wait_for_timeout(2500)
    return name


def hrms_list_states(s):
    p = s.page
    p.goto(f"{BASE}/hrms/leave-applications")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)
    return p.locator("body").inner_text()


# ---------------------------------------------------------------------------------------------------- the desk

def card_value(p, label):
    """Value of a number card of the workspace (waits for it to load)."""
    widget = p.locator(".widget", has_text=label).first
    expect(widget).to_be_visible()
    for _ in range(30):
        numbers = re.findall(r"\d[\d.,]*", widget.inner_text().replace(label, ""))
        if numbers:
            return int(numbers[0].replace(".", "").replace(",", ""))
        p.wait_for_timeout(300)
    raise AssertionError(f"thẻ {label} không có số")


def open_leave(s, name):
    p = s.page
    p.goto(f"{BASE}/desk/leave-application/{name}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2500)


MENU_ITEMS = "[role=menuitem]:visible, .es-menu__item:visible, .dropdown-menu.show .dropdown-item"


def headline(p):
    message = p.locator(".form-message:visible").first
    return " ".join(message.inner_text().split()) if message.count() else ""


def menu_items(p):
    return [" ".join(t.split()) for t in p.locator(MENU_ITEMS).all_inner_texts() if t.strip()]


def workflow_actions(p):
    button = p.get_by_role("button", name="Hành động")
    if not button.count() or not button.first.is_visible():
        return []
    button.first.click()
    p.wait_for_timeout(600)
    items = menu_items(p)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    return items


def desk_action(s, name, action, reason=None):
    """Hành động → Duyệt or Từ chối on the standard form; Từ chối asks the reason in a dialog. Returns the new state."""
    p = s.page
    p.get_by_role("button", name="Hành động").first.click()
    p.wait_for_timeout(600)
    items = p.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if " ".join(items.nth(i).inner_text().split()) == action), None)
    check(target is not None, f"không có {action} trong {menu_items(p)}")
    items.nth(target).click()
    if action == "Từ chối":
        dialog = p.locator(".modal:visible").last
        expect(dialog).to_be_visible()
        p.wait_for_timeout(600)
        if reason:
            dialog.locator("textarea").first.fill(reason)
        dialog.get_by_role("button", name="Từ chối").last.click()
    p.wait_for_timeout(3500)
    return state_of(s, name)


# ---------------------------------------------------------------------------------------------------- journeys

def office_employee(browser):
    s = Session(browser, "NV", "an")
    first_case(s, "NV-01")
    p = s.page
    with case(s, "NV-02", "Trang chủ app Frappe HR", "Xem lời chào, liên kết nhanh, thanh menu dưới", "",
              "Lời chào đúng tên; có Xin nghỉ phép, Xem phiếu lương; menu Trang chủ / Chấm công / Nghỉ phép / Chi phí / Lương") as r:
        text = p.locator("body").inner_text()
        for t in ("Nguyễn Hoài An", "Xin nghỉ phép", "Xem phiếu lương", "Trang chủ", "Nghỉ phép", "Lương"):
            check(t in text, f"thiếu {t}")
        r["actual"] = "Lời chào, liên kết nhanh và menu dưới đầy đủ (tiếng Việt)"
    with case(s, "NV-03", "Số dư phép", "Menu dưới > Nghỉ phép", "", "Phép năm còn 12 / 12 ngày") as r:
        p.get_by_text("Nghỉ phép", exact=True).last.click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2500)
        text = p.locator("body").inner_text()
        check("Phép năm" in text and "12" in text, text[:200])
        balance = api(s, "hrms.api.get_leave_balance_map", employee=api_get(s, "/api/resource/Employee?fields=[\"name\"]").json()["data"][0]["name"])
        r["actual"] = f"Trang Phép hiển thị Phép năm; số dư API {json.dumps(balance, ensure_ascii=False)[:120]}"
    start, end = working_day(3), working_day(4)
    with case(s, "NV-04", "Xin nghỉ 2 ngày và gửi duyệt", "Xin nghỉ phép > Loại Phép năm, ngày, lý do > Lưu > Hành động > Gửi duyệt",
              f"{vn(start)} → {vn(end)}, Việc gia đình", "Đơn 2 ngày ở trạng thái Chờ quản lý duyệt, người duyệt Trần Minh Quang") as r:
        REQ["an"] = hrms_request_leave(s, start, end, "Việc gia đình")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['an']}").json()["data"]
        check((doc["workflow_state"], doc["total_leave_days"], doc["leave_approver"]) == (TO_MANAGER, 2, "quang@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['an']}: {doc['workflow_state']}, {doc['total_leave_days']:g} ngày, duyệt bởi {doc['leave_approver']}"
    with case(s, "NV-05", "Chặn đơn trùng ngày", "Xin nghỉ lại đúng ngày đã xin, Lưu", vn(start), "Không lưu được: báo đã có đơn trong khoảng ngày này") as r:
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
        check("/new" in p.url, f"đã lưu: {p.url}")
        r["actual"] = "Không lưu được đơn trùng ngày (HRMS báo trùng)"
    with case(s, "NV-06", "Theo dõi đơn của tôi", "Mở danh sách đơn nghỉ", "", f"Thấy đơn {vn(start)} ở trạng thái Chờ quản lý duyệt") as r:
        text = hrms_list_states(s)
        check(TO_MANAGER in text, text[:200])
        r["actual"] = "Danh sách có đơn đang Chờ quản lý duyệt"
    with case(s, "NV-07", "Phạm vi dữ liệu", "API: danh sách nhân viên và đơn nghỉ của phiên nhân viên", "", "Chỉ thấy hồ sơ và đơn của chính mình") as r:
        employees = api_get(s, "/api/resource/Employee?limit_page_length=500").json()["data"]
        leaves = api_get(s, "/api/resource/Leave Application?limit_page_length=500&fields=[\"employee_name\"]").json()["data"]
        check(len(employees) == 1 and {x["employee_name"] for x in leaves} <= {"Nguyễn Hoài An"}, f"{len(employees)} hồ sơ")
        r["actual"] = f"{len(employees)} hồ sơ, {len(leaves)} đơn của chính mình"
    s.close()


def support_office_manager(playwright):
    """Precondition outside the brief: the head of sales (an's line manager) approves her request through the API."""
    row = {"id": "HT-01", "account": "quang@demo.example", "role": "Hỗ trợ - Trưởng phòng Kinh doanh (quản lý của an)",
           "function": "Quản lý trực tiếp duyệt đơn của nhân viên văn phòng", "steps": "API tlc_hr.api.decide (tiền điều kiện)",
           "data": REQ.get("an", ""), "expected": "Đơn chuyển Chờ nhân sự duyệt", "video": "", "time": "", "shot": "",
           "run_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        client = playwright.request.new_context(base_url=BASE)
        client.post("/api/method/login", data={"usr": "quang@demo.example", "pwd": PASSWORD})
        state = client.post("/api/method/tlc_hr.api.decide", data={"name": REQ["an"], "decision": "approve"}).json()["message"]["workflow_state"]
        check(state == TO_HR, state)
        row.update(actual=f"{REQ['an']} → {state}", status="Đạt")
        client.dispose()
    except Exception as exc:
        row.update(actual=f"{type(exc).__name__}: {exc}", status="Không đạt")
    RESULTS.append(row)
    print(f"{row['status']:10} HT-01    {row['actual']}", flush=True)


def factory_worker_1(browser):
    s = Session(browser, "CN1", "binh", phone=True)
    first_case(s, "CN1-01")
    day, half = working_day(2), working_day(5)
    with case(s, "CN1-02", "Xin nghỉ 1 ngày trên điện thoại", "Xin nghỉ phép > Lưu > Hành động > Gửi duyệt", f"{vn(day)}, Con ốm",
              "Chờ quản lý duyệt, người duyệt Đặng Văn Hùng") as r:
        REQ["binh_full"] = hrms_request_leave(s, day, day, "Con ốm")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_full']}").json()["data"]
        check((doc["workflow_state"], doc["leave_approver"]) == (TO_MANAGER, "hung@demo.example"), str(doc)[:200])
        r["actual"] = f"{REQ['binh_full']}: {doc['workflow_state']}, duyệt bởi {doc['leave_approver']}"
    with case(s, "CN1-03", "Xin nghỉ nửa ngày", "Xin nghỉ phép, tích Nửa ngày > Lưu > Gửi duyệt", f"{vn(half)}, Khám sức khỏe",
              "0,5 ngày, Chờ quản lý duyệt") as r:
        REQ["binh_half"] = hrms_request_leave(s, half, half, "Khám sức khỏe", half=True)
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_half']}").json()["data"]
        check((doc["workflow_state"], doc["total_leave_days"]) == (TO_MANAGER, 0.5), str(doc)[:200])
        r["actual"] = f"{REQ['binh_half']}: {doc['total_leave_days']:g} ngày, {doc['workflow_state']}"
    with case(s, "CN1-04", "Không tự duyệt được", "Mở đơn của mình; xem Hành động", REQ["binh_full"], "Không có nút Duyệt cho chính mình") as r:
        s.page.goto(f"{BASE}/hrms/leave-applications/{REQ['binh_full']}")
        s.page.wait_for_load_state("networkidle")
        s.page.wait_for_timeout(2000)
        buttons = [b.inner_text().strip() for b in s.page.locator("button").all() if b.is_visible()]
        check("Duyệt" not in buttons, str(buttons))
        r["actual"] = f"Các nút: {[b for b in buttons if b][-3:]}"
    s.close()


def factory_worker_2(browser):
    s = Session(browser, "CN2", "f2w01", phone=True)
    first_case(s, "CN2-01")
    day = working_day(2)
    with case(s, "CN2-02", "Xin nghỉ (Nhà máy 2)", "Xin nghỉ phép > Lưu > Gửi duyệt", f"{vn(day)}, Về quê", "Đơn đến quản lý Nhà máy 2 (nm2)") as r:
        REQ["f2w01"] = hrms_request_leave(s, day, day, "Về quê")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['f2w01']}").json()["data"]
        check(doc["leave_approver"] == "nm2@demo.example" and doc["workflow_state"] == TO_MANAGER, str(doc)[:200])
        r["actual"] = f"{REQ['f2w01']} → nm2@demo.example, {doc['workflow_state']}"
    with case(s, "CN2-03", "Cách ly dữ liệu giữa hai nhà máy", "Mở đơn của công nhân Nhà máy 1 qua API", REQ["binh_full"], "Bị chặn 403") as r:
        status = api_get(s, f"/api/resource/Leave Application/{REQ['binh_full']}").status
        check(status == 403, str(status))
        r["actual"] = f"API trả {status}"
    s.close()


def factory_head(browser):
    s = Session(browser, "QL", "hung")
    first_case(s, "QL-01")
    p = s.page
    with case(s, "QL-02", "Workspace TLC Quản lý", "Đọc các thẻ số và danh sách đơn chờ", "",
              "Đơn chờ tôi duyệt 2; Nhân sự đang làm việc 15 (trong phạm vi); danh sách có 2 đơn của Trần Văn Bình") as r:
        mine = card_value(p, "Đơn chờ tôi duyệt")
        staff = card_value(p, "Nhân sự đang làm việc")
        quick = p.locator(".widget", has_text="Đơn chờ quản lý duyệt").last.inner_text()
        check((mine, staff) == (2, 15) and quick.count("Trần Văn Bình") >= 2 and "Nhà máy 2" not in quick, f"{mine} {staff} {quick[:160]}")
        r["actual"] = f"Đơn chờ tôi duyệt {mine}; nhân sự {staff}; danh sách có 2 đơn của Bình"
    with case(s, "QL-03", "Hỗ trợ quyết định trên form", "Mở đơn 1 ngày của Bình", REQ["binh_full"],
              "Dòng đầu form: số dư sau khi duyệt 11 / 12 ngày; không ai khác ở Nhà máy 1 nghỉ; nút Hành động có Duyệt, Từ chối") as r:
        open_leave(s, REQ["binh_full"])
        text = headline(p)
        actions = workflow_actions(p)
        check("11 / 12" in text and "Không ai khác" in text and {"Duyệt", "Từ chối"} <= set(actions), f"{text} | {actions}")
        r["actual"] = f"{text} · Hành động: {', '.join(actions)}"
    with case(s, "QL-04", "Duyệt đơn", "Hành động > Duyệt", REQ["binh_full"], "Chờ nhân sự duyệt") as r:
        state = desk_action(s, REQ["binh_full"], "Duyệt")
        check(state == TO_HR, state)
        r["actual"] = state
    with case(s, "QL-05", "Từ chối phải có lý do", "Mở đơn nửa ngày > Hành động > Từ chối > nhập lý do > Từ chối", "Trùng ca kiểm kê kho",
              "Hộp thoại hỏi lý do; đơn Từ chối, lý do được lưu") as r:
        open_leave(s, REQ["binh_half"])
        state = desk_action(s, REQ["binh_half"], "Từ chối", reason="Trùng ca kiểm kê kho")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['binh_half']}").json()["data"]
        check(state == REJECTED and doc.get("tlc_reject_reason") == "Trùng ca kiểm kê kho", f"{state} {doc.get('tlc_reject_reason')}")
        r["actual"] = f"{state}; lý do: {doc['tlc_reject_reason']}"
    with case(s, "QL-06", "Không xem được đơn của nhà máy khác", "Mở đơn của Nhà máy 2", REQ["f2w01"], "Bị chặn 403") as r:
        status = api_get(s, f"/api/resource/Leave Application/{REQ['f2w01']}").status
        check(status == 403, str(status))
        r["actual"] = f"API trả {status}"
    with case(s, "QL-07", "Lịch nghỉ phép của đội", "Workspace > Lịch nghỉ phép", "", "Lịch tháng hiển thị đơn của Bình") as r:
        p.goto(f"{BASE}/desk/leave-application/view/calendar/default")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        text = p.locator(".fc, .calendar-view, body").first.inner_text()
        check("Trần Văn Bình" in text, text[:200])
        r["actual"] = "Lịch có đơn của Trần Văn Bình"
    with case(s, "QL-08", "Quản lý tự xin nghỉ trong app", "Mở app Frappe HR, xin nghỉ 1 ngày, gửi duyệt", f"{vn(working_day(6))}, Họp phụ huynh",
              "Đơn đến CEO Nguyễn Văn Thành") as r:
        REQ["hung"] = hrms_request_leave(s, working_day(6), working_day(6), "Họp phụ huynh")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['hung']}").json()["data"]
        check(doc["leave_approver"] == "thanh@demo.example" and doc["workflow_state"] == TO_MANAGER, str(doc)[:160])
        r["actual"] = f"{REQ['hung']} → thanh@demo.example"
    s.close()


def hr_lead(browser):
    s = Session(browser, "HR", "hoa")
    first_case(s, "HR-01")
    p = s.page
    with case(s, "HR-02", "Workspace TLC Nhân sự", "Đọc các thẻ số", "", "60 nhân sự; Hội sở 31; Nhà máy 29; 2 đơn chờ nhân sự duyệt") as r:
        values = tuple(card_value(p, label) for label in ("Nhân sự đang làm việc", "Nhân sự khối Hội sở", "Nhân sự khối Nhà máy", "Đơn chờ nhân sự duyệt"))
        check(values == (60, 31, 29, 2), str(values))
        p.locator(".widget", has_text="Nhân sự theo phòng ban").first.scroll_into_view_if_needed()
        p.wait_for_timeout(1500)
        r["actual"] = "Nhân sự {}; Hội sở {}; Nhà máy {}; chờ nhân sự {}".format(*values)
    with case(s, "HR-03", "Duyệt cấp nhân sự", "Mở từng đơn từ danh sách chờ > Hành động > Duyệt", f"{REQ['binh_full']}, {REQ['an']}",
              "Cả hai Đã duyệt") as r:
        out = []
        for name in (REQ["binh_full"], REQ["an"]):
            open_leave(s, name)
            out.append(desk_action(s, name, "Duyệt"))
        check(out == [APPROVED, APPROVED], str(out))
        r["actual"] = " | ".join(out)
    with case(s, "HR-04", "Báo cáo số dư phép", "Workspace > Số dư phép", "", "Báo cáo mở sẵn kỳ cả năm, hiển thị số dư Phép năm của nhân viên") as r:
        p.goto(f"{BASE}/desk/tlc-hr/tlc-nh%C3%A2n-s%E1%BB%B1")
        p.wait_for_load_state("networkidle")
        p.locator(".widget", has_text="Số dư phép").first.click()
        p.wait_for_load_state("networkidle")
        expect(p.get_by_text("Phép năm").first).to_be_visible(timeout=40000)
        p.wait_for_timeout(1500)
        r["actual"] = "Báo cáo hiển thị số dư Phép năm"
    with case(s, "HR-05", "Tham số lương Việt Nam", "Workspace > Tham số lương Việt Nam", "",
              "Lương cơ sở 2.530.000; giảm trừ 15.500.000 / 6.200.000; hiệu lực 01-07-2026") as r:
        p.goto(f"{BASE}/desk/vn-payroll-settings")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3000)
        d = api_get(s, "/api/resource/VN Payroll Settings/VN Payroll Settings").json()["data"]
        got = (d["base_salary"], d["personal_deduction"], d["dependent_deduction"], d["effective_date"])
        check(got == (2530000, 15500000, 6200000, "2026-07-01"), str(got))
        r["actual"] = str(got)
    with case(s, "HR-06", "Trưởng nhân sự tự xin nghỉ", "App Frappe HR > Xin nghỉ phép > Gửi duyệt", f"{vn(working_day(7))}, Đi đám cưới", "Đơn đến CEO") as r:
        REQ["hoa"] = hrms_request_leave(s, working_day(7), working_day(7), "Đi đám cưới")
        doc = api_get(s, f"/api/resource/Leave Application/{REQ['hoa']}").json()["data"]
        check(doc["leave_approver"] == "thanh@demo.example", doc["leave_approver"])
        r["actual"] = f"{REQ['hoa']} → thanh@demo.example"
    s.close()


def ceo(browser):
    s = Session(browser, "CEO", "thanh")
    first_case(s, "CEO-01")
    p = s.page
    with case(s, "CEO-02", "Workspace TLC Điều hành", "Đọc các thẻ số", "", "60 nhân sự; 2 đơn chờ tôi duyệt; 3 đơn chờ quản lý (toàn công ty)") as r:
        values = (card_value(p, "Nhân sự đang làm việc"), card_value(p, "Đơn chờ tôi duyệt"), card_value(p, "Đơn chờ quản lý duyệt"))
        check(values == (60, 2, 3), str(values))
        r["actual"] = "Nhân sự {}; chờ tôi {}; chờ quản lý {}".format(*values)
    with case(s, "CEO-03", "Duyệt đơn của cấp dưới trực tiếp", "Mở đơn của Quản lý NM1 và Trưởng nhân sự > Hành động > Duyệt",
              f"{REQ['hung']}, {REQ['hoa']}", "Cả hai Chờ nhân sự duyệt") as r:
        out = []
        for name in (REQ["hung"], REQ["hoa"]):
            open_leave(s, name)
            out.append(desk_action(s, name, "Duyệt"))
        check(out == [TO_HR, TO_HR], str(out))
        r["actual"] = " | ".join(out)
    with case(s, "CEO-04", "Biểu đồ điều hành", "Xem biểu đồ Nhân sự theo phòng ban và Ngày nghỉ theo tháng", "", "Hai biểu đồ hiển thị") as r:
        p.goto(f"{BASE}/desk/tlc-hr/tlc-%C4%91i%E1%BB%81u-h%C3%A0nh")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        charts = p.locator(".widget", has_text="Nhân sự theo phòng ban")
        charts.first.scroll_into_view_if_needed()
        p.wait_for_timeout(1500)
        check(charts.count() >= 1 and p.locator(".widget svg, .widget canvas").count() >= 1, "không thấy biểu đồ")
        r["actual"] = "Biểu đồ hiển thị"
    s.close()


def hr_lead_second(browser):
    s = Session(browser, "HR2", "hoa")
    login(s)
    with case(s, "HR-07", "Không tự duyệt đơn của mình", "Mở đơn của chính mình (đã qua CEO); xem Hành động", REQ["hoa"],
              "Không có Duyệt/Từ chối cho chính mình") as r:
        open_leave(s, REQ["hoa"])
        actions = workflow_actions(s.page)
        check("Duyệt" not in actions, str(actions))
        r["actual"] = f"Hành động: {actions or 'không có'}"
    with case(s, "HR-08", "Duyệt đơn của Quản lý NM1", "Mở đơn > Hành động > Duyệt", REQ["hung"], "Đã duyệt") as r:
        open_leave(s, REQ["hung"])
        state = desk_action(s, REQ["hung"], "Duyệt")
        check(state == APPROVED, state)
        r["actual"] = state
    s.close()


def hr_officer(browser):
    s = Session(browser, "HR3", "lan")
    first_case(s, "HR-09")
    with case(s, "HR-10", "Chuyên viên nhân sự duyệt đơn của Trưởng nhân sự", "Mở đơn > Hành động > Duyệt", REQ["hoa"], "Đã duyệt") as r:
        open_leave(s, REQ["hoa"])
        state = desk_action(s, REQ["hoa"], "Duyệt")
        check(state == APPROVED, state)
        r["actual"] = state
    s.close()


def results_check(browser):
    s = Session(browser, "CN1b", "binh", phone=True)
    login(s)
    p = s.page
    with case(s, "CN1-05", "Kết quả đơn trên điện thoại", "Mở danh sách đơn; mở đơn bị từ chối", f"{REQ['binh_full']}, {REQ['binh_half']}",
              "Đơn 1 ngày Đã duyệt; đơn nửa ngày Từ chối, thấy lý do 'Trùng ca kiểm kê kho' (chỉ đọc)") as r:
        text = hrms_list_states(s)
        check(APPROVED in text and REJECTED in text, text[:200])
        p.goto(f"{BASE}/hrms/leave-applications/{REQ['binh_half']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        reason = p.locator("textarea").filter(has_text="Trùng ca kiểm kê kho")
        value = p.evaluate("Array.from(document.querySelectorAll('textarea')).map(t => t.value + '|' + (t.disabled || t.readOnly)).join(' ; ')")
        check("Trùng ca kiểm kê kho|true" in value, value)
        r["actual"] = f"Danh sách có Đã duyệt và Từ chối; lý do hiện chỉ đọc ({reason.count() or 1} ô)"
    with case(s, "CN1-06", "Số dư phép sau khi được duyệt", "Menu dưới > Nghỉ phép", "", "Phép năm còn 11 (đơn bị từ chối không trừ)") as r:
        employee = api_get(s, "/api/resource/Employee?fields=[\"name\"]").json()["data"][0]["name"]
        balance = api(s, "hrms.api.get_leave_balance_map", employee=employee)
        left = balance["Phép năm"]["balance_leaves"]
        p.goto(f"{BASE}/hrms/home")
        p.wait_for_load_state("networkidle")
        p.get_by_text("Nghỉ phép", exact=True).last.click()
        p.wait_for_timeout(2500)
        check(left == 11, str(balance))
        r["actual"] = f"Phép năm còn {left:g}"
    s.close()

    s = Session(browser, "NVb", "an")
    login(s)
    with case(s, "NV-08", "Kết quả đơn và số dư", "Mở danh sách đơn", REQ["an"], "Đã duyệt; còn 10 ngày") as r:
        text = hrms_list_states(s)
        employee = api_get(s, "/api/resource/Employee?fields=[\"name\"]").json()["data"][0]["name"]
        left = api(s, "hrms.api.get_leave_balance_map", employee=employee)["Phép năm"]["balance_leaves"]
        check(APPROVED in text and left == 10, f"{left} {text[:120]}")
        r["actual"] = f"Đã duyệt; còn {left:g}"
    s.close()


# ---------------------------------------------------------------------------------------------------- outputs

def write_outputs():
    (OUT / "results.json").write_text(json.dumps({"run": RUN_ID, "base": BASE, "results": RESULTS, "matrix": MATRIX, "videos": VIDEOS},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    from uat_report import write_html, write_xlsx

    xlsx = write_xlsx(OUT, RUN_ID, RESULTS, MATRIX, VIDEOS, ACCOUNTS, SECTIONS, SECTION_LABEL, EXPECTED_SECTIONS)
    write_html(OUT, RUN_ID, RESULTS, VIDEOS, xlsx)


def main():
    for sub in ("videos/raw", "shots"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(slow_mo=SLOW_MO)
        for step in (office_employee, None, factory_worker_1, factory_worker_2, factory_head, hr_lead, ceo, hr_lead_second,
                     hr_officer, results_check):
            try:
                support_office_manager(playwright) if step is None else step(browser)
            except Exception as exc:
                print("SCENARIO ERROR", getattr(step, "__name__", "support"), exc, flush=True)
                traceback.print_exc()
        browser.close()
    write_outputs()
    passed = sum(1 for r in RESULTS if r["status"] == "Đạt")
    print(f"UAT {RUN_ID}: {passed}/{len(RESULTS)} đạt", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
