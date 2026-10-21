"""Shared helpers of the TLC HRM UAT: accounts, recorded sessions, test cases, login, desk and Frappe HR app steps.

Journeys (journeys/<module>.py) use `from lib import *`; run_uat.py runs them and writes the evidence.
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
# Workers use the phone in real life; the evidence pack is recorded on the desktop web unless PHONE_UAT=1.
PHONE_UAT = os.environ.get("PHONE_UAT") == "1"
TO_MANAGER, TO_HR, APPROVED, REJECTED, DRAFT = "Chờ quản lý duyệt", "Chờ nhân sự duyệt", "Đã duyệt", "Từ chối", "Nháp"

ACCOUNTS = {
    "an": {"name": "Nguyễn Hoài An", "role": "Nhân viên văn phòng hội sở (Kinh doanh)", "workforce": "Hội sở", "approver": "Trần Minh Quang"},
    "binh": {"name": "Trần Văn Bình", "role": "Công nhân Nhà máy 1", "workforce": "Nhà máy", "approver": "Đặng Văn Hùng"},
    "f2w01": {"name": None, "role": "Công nhân Nhà máy 2", "workforce": "Nhà máy", "approver": "Lương Quốc Hải"},
    "hung": {"name": "Đặng Văn Hùng", "role": "Quản lý Nhà máy 1 (Head Manager nhà máy)", "workforce": "Nhà máy", "approver": "Nguyễn Văn Thành"},
    "hoa": {"name": "Lê Thị Hòa", "role": "HR hội sở - Giám đốc nhân sự (HR Lead)", "workforce": "Hội sở", "approver": "Nguyễn Văn Thành"},
    "lan": {"name": "Hoàng Thị Lan", "role": "HR hội sở - Chuyên viên nhân sự (HR Officer)", "workforce": "Hội sở", "approver": "Lê Thị Hòa"},
    "quang": {"name": "Trần Minh Quang", "role": "Hỗ trợ - Trưởng phòng Kinh doanh hội sở", "workforce": "Hội sở", "approver": "Nguyễn Văn Thành"},
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
        phone = phone and PHONE_UAT
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


def open_actions(p):
    """The workflow actions: a "Hành động" button on a computer, the last icon button of the page head on a phone."""
    button = p.get_by_role("button", name="Hành động")
    if button.count() and button.first.is_visible():
        button.first.click()
    else:
        icon = p.locator(".page-head button.es-button:not(.menu-more-button):visible")
        if not icon.count():
            return False
        icon.last.click()
    p.wait_for_timeout(600)
    return True


def workflow_actions(p):
    if not open_actions(p):
        return []
    p.wait_for_timeout(600)
    items = menu_items(p)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    return items


def desk_action(s, name, action, reason=None):
    """Hành động → Duyệt or Từ chối on the standard form; Từ chối asks the reason in a dialog. Returns the new state."""
    p = s.page
    open_actions(p)
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


def doc_state(s, doctype, name):
    return api_get(s, f"/api/resource/{doctype}/{name}").json()["data"]["workflow_state"]
