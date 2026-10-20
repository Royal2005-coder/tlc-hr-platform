"""End-to-end UAT of TLC HRM on Frappe HR: one recorded browser session per account, real assertions, Excel sheet and evidence page.

Run (on the k3s node): ~/tlc-hr/uat/run_uat.sh   (needs a freshly seeded site: every expected number below assumes it)
Output: /uat/out/<run id>/  videos/*.webm, shots/*.png, UAT_TLC_HRM_<run id>.xlsx, results.json, index.html
The demo password comes from the environment (DEMO_PASSWORD) and is never written to the output.
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

ACCOUNTS = {
    "an": {"name": "Nguyễn Hoài An", "role": "Nhân viên văn phòng hội sở (Kinh doanh)", "workforce": "Hội sở", "approver": "Trần Minh Quang"},
    "binh": {"name": "Trần Văn Bình", "role": "Công nhân Nhà máy 1 (Nhân viên kho)", "workforce": "Nhà máy", "approver": "Đặng Văn Hùng"},
    "f2w01": {"name": None, "role": "Công nhân Nhà máy 2 (Nhân viên kho)", "workforce": "Nhà máy", "approver": "Lương Quốc Hải"},
    "hung": {"name": "Đặng Văn Hùng", "role": "Quản lý Nhà máy 1 (Head Manager nhà máy)", "workforce": "Nhà máy", "approver": "Nguyễn Văn Thành"},
    "hoa": {"name": "Lê Thị Hòa", "role": "HR hội sở - Giám đốc nhân sự (HR Lead)", "workforce": "Hội sở", "approver": "Nguyễn Văn Thành"},
    "lan": {"name": "Hoàng Thị Lan", "role": "HR hội sở - Chuyên viên nhân sự (HR Officer)", "workforce": "Hội sở", "approver": "Lê Thị Hòa"},
    "thanh": {"name": "Nguyễn Văn Thành", "role": "CEO hội sở - Tổng giám đốc", "workforce": "Hội sở", "approver": None},
}
SECTIONS = ["inbox", "leave-form-card", "no-approver", "my-requests", "team", "company", "links"]
SECTION_LABEL = {"inbox": "Việc chờ tôi duyệt", "leave-form-card": "Xin nghỉ phép", "no-approver": "Ghi chú không có cấp duyệt",
                 "my-requests": "Đơn của tôi", "team": "Đội của tôi", "company": "Tổng quan nhân sự", "links": "Mở nhanh"}
EXPECTED_SECTIONS = {
    "an": {"leave-form-card", "my-requests", "links"},
    "binh": {"leave-form-card", "my-requests", "links"},
    "f2w01": {"leave-form-card", "my-requests", "links"},
    "hung": {"inbox", "leave-form-card", "my-requests", "team", "links"},
    "hoa": {"inbox", "leave-form-card", "my-requests", "company", "links"},
    "lan": {"inbox", "leave-form-card", "my-requests", "company", "links"},
    "thanh": {"inbox", "leave-form-card", "no-approver", "my-requests", "team", "company", "links"},
}

RESULTS = []      # one row per test case
MATRIX = {}       # account -> visible sections
VIDEOS = []       # session videos
REQ = {}          # leave requests created during the run: key -> name


def working_day(n):
    """n-th working day after today (Monday to Friday)."""
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
    el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:rgba(17,24,39,.88);color:#fff;' +
      'font:600 14px/1.35 system-ui,sans-serif;padding:8px 12px;pointer-events:none';
    document.documentElement.appendChild(el); }
  el.textContent = t;
}
"""
CAPTION_INIT = "window.addEventListener('DOMContentLoaded', () => { (" + CAPTION_JS + ")(); });"


class Session:
    """One account, one browser context, one video."""

    def __init__(self, browser, code, account, phone=False):
        self.code, self.account, self.phone = code, account, phone
        self.label = ACCOUNTS[account]["role"]
        viewport = PHONE if phone else DESKTOP
        self.context = browser.new_context(
            viewport=viewport, record_video_dir=str(OUT / "videos" / "raw"), record_video_size=viewport,
            locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh", is_mobile=phone, has_touch=phone,
            device_scale_factor=2 if phone else 1)
        self.context.add_init_script(CAPTION_INIT)
        self.context.set_default_timeout(20000)
        self.page = self.context.new_page()
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

    def shot(self, case_id):
        path = OUT / "shots" / f"{case_id}.png"
        self.page.screenshot(path=str(path), full_page=False)
        return f"shots/{path.name}"

    def close(self):
        video = self.page.video
        self.context.close()
        name = f"{self.index:02d}_{self.code}_{self.account}.webm"
        target = OUT / "videos" / name
        Path(video.path()).rename(target)
        VIDEOS.append({"file": f"videos/{name}", "code": self.code, "account": self.account, "role": self.label,
                       "device": "Điện thoại 390x844" if self.phone else "Máy tính 1366x820",
                       "cases": [r["id"] for r in RESULTS if r["video"] == f"videos/{name}"]})
        return name


@contextmanager
def case(s, case_id, function, steps, data, expected):
    """Run one test case inside a session: caption on the video, screenshot, result row with the real outcome."""
    row = {"id": case_id, "account": f"{s.account}@demo.example", "role": s.label, "function": function, "steps": steps,
           "data": data, "expected": expected, "actual": "", "status": "", "video": None, "time": s.stamp(),
           "shot": "", "run_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    s.caption(f"{case_id} · {function}")
    found = {}
    try:
        yield found
        row["actual"] = found.get("actual", "Đúng như mong đợi")
        row["status"] = "Đạt"
    except Exception as exc:  # the case fails, the run goes on
        row["actual"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
        row["status"] = "Không đạt"
        row["trace"] = traceback.format_exc()[-1500:]
    s.page.wait_for_timeout(600)
    try:
        row["shot"] = s.shot(case_id)
    except Exception:
        pass
    row["video_name"] = f"{s.index:02d}_{s.code}_{s.account}.webm"
    row["video"] = f"videos/{row['video_name']}"
    RESULTS.append(row)
    print(f"{row['status']:10} {case_id:8} {function}: {row['actual'][:140]}", flush=True)


# ---------------------------------------------------------------------------------------------------- page helpers

def login(s):
    p = s.page
    p.goto(f"{BASE}/login")
    s.caption("Đăng nhập")
    p.locator("#login_email").fill(f"{s.account}@demo.example")
    p.locator("#login_password").fill(PASSWORD)
    p.locator("form.form-login button[type=submit]").click()
    p.wait_for_url(re.compile(r".*/tlc.*"), timeout=30000)
    p.wait_for_load_state("networkidle")


def home(s):
    s.page.goto(f"{BASE}/tlc")
    s.page.wait_for_load_state("networkidle")


def visible_sections(p):
    return [t for t in SECTIONS if p.get_by_test_id(t).count() and p.get_by_test_id(t).first.is_visible()]


def balance(p):
    return float(p.get_by_test_id("stat-balance").first.locator(".n").inner_text().replace(",", "."))


def toast(p):
    t = p.get_by_test_id("toast")
    expect(t).to_be_visible(timeout=20000)
    return (t.get_attribute("class") or ""), t.inner_text()


def after_reload(p):
    p.wait_for_timeout(2300)
    p.wait_for_load_state("networkidle")


def submit_leave(s, start, end, reason, half=False):
    p = s.page
    form = p.get_by_test_id("leave-form-card")
    form.scroll_into_view_if_needed()
    p.get_by_test_id("lf-from").fill(start)
    p.get_by_test_id("lf-to").fill(end)
    if half:
        p.get_by_test_id("lf-half").check()
    p.get_by_test_id("lf-reason").fill(reason)
    p.get_by_test_id("lf-submit").click()
    kind, text = toast(p)
    return kind, text


def created_name(text):
    match = re.search(r"HR-LAP-\d{4}-\d+", text)
    if not match:
        raise AssertionError(f"không thấy số đơn trong thông báo: {text}")
    return match.group(0)


def my_request_state(p, name):
    row = p.locator(f'[data-testid=my-request][data-name="{name}"]')
    expect(row).to_be_visible()
    row.scroll_into_view_if_needed()
    return row.get_by_test_id("my-request-state").inner_text().strip(), row


def inbox_item(p, name):
    return p.locator(f'[data-testid=inbox-item][data-name="{name}"]')


def decide(s, name, decision, reason=None):
    p = s.page
    item = inbox_item(p, name)
    expect(item).to_be_visible()
    item.scroll_into_view_if_needed()
    if decision == "approve":
        item.get_by_test_id("approve").click()
    else:
        item.get_by_test_id("reject-open").click()
        if reason is not None:
            item.get_by_test_id("reject-reason").fill(reason)
        item.get_by_test_id("reject-confirm").click()
    return toast(p)


def api_status(s, path):
    return s.page.request.get(f"{BASE}{path}").status


def api_json(s, path):
    return s.page.request.get(f"{BASE}{path}").json()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def show_desk(s, path, wait_ms=3500):
    s.page.goto(f"{BASE}{path}")
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(wait_ms)
    s.caption("(màn hình desk)")


def desk_ok(s, expect_text=None):
    """A desk screen that should open: no permission error dialog, and the expected text on screen."""
    p = s.page
    error = p.locator(".modal-dialog:visible, .msgprint-dialog:visible").filter(has_text=re.compile("quyền|Permission", re.I))
    check(error.count() == 0, "popup lỗi quyền: " + (error.first.inner_text()[:160] if error.count() else ""))
    if expect_text:
        expect(p.locator(".page-head, .page-title, .title-text").filter(has_text=expect_text).first).to_be_visible()


def first_case(s, case_id):
    """Login, home of the account: identity, workforce, approver, sections shown (functional matrix)."""
    info = ACCOUNTS[s.account]
    with case(s, case_id, "Đăng nhập và trang chủ theo vai trò",
              "Mở /login, nhập tài khoản, đăng nhập; hệ thống chuyển về trang chủ /tlc",
              f"{s.account}@demo.example / mật khẩu demo",
              f"Vào /tlc; hiển thị họ tên, khối {info['workforce']}" + (f", người duyệt {info['approver']}" if info["approver"] else ", không có cấp duyệt")
              + "; chỉ các mục: " + ", ".join(SECTION_LABEL[x] for x in SECTIONS if x in EXPECTED_SECTIONS[s.account])) as r:
        login(s)
        p = s.page
        name = p.get_by_test_id("person-name").inner_text().strip()
        if info["name"]:
            check(name == info["name"], f"tên hiển thị {name!r}")
        ACCOUNTS[s.account]["name"] = name
        workforce = p.get_by_test_id("workforce").inner_text().strip()
        check(workforce == info["workforce"], f"khối {workforce!r}")
        if info["approver"]:
            approver = p.get_by_test_id("my-approver").inner_text().strip()
            check(approver == info["approver"], f"người duyệt {approver!r}")
        shown = visible_sections(p)
        MATRIX[s.account] = shown
        check(set(shown) == EXPECTED_SECTIONS[s.account], f"các mục hiển thị {shown}")
        if s.phone:
            overflow = p.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(overflow <= 1, f"tràn ngang {overflow}px trên điện thoại")
        r["actual"] = f"{name} · khối {workforce} · mục: {', '.join(SECTION_LABEL[x] for x in shown)}" + (" · không tràn ngang trên điện thoại" if s.phone else "")


# ---------------------------------------------------------------------------------------------------- scenarios

def office_employee(browser):
    s = Session(browser, "NV", "an")
    first_case(s, "NV-01")
    p = s.page
    with case(s, "NV-02", "Xem số ngày phép còn lại", "Đọc ô chỉ số trên trang chủ", "Phép năm cấp 12 ngày", "Phép năm còn 12 ngày") as r:
        value = balance(p)
        check(value == 12, f"còn {value}")
        r["actual"] = f"Phép năm còn {value:g} ngày"
    bad_from, bad_to = working_day(4), working_day(3)
    with case(s, "NV-03", "Chặn đơn sai ngày", "Nhập Từ ngày sau Đến ngày, bấm Gửi đơn", f"{vn(bad_from)} → {vn(bad_to)}",
              "Báo lỗi 'Ngày kết thúc phải sau hoặc bằng ngày bắt đầu', không tạo đơn") as r:
        kind, text = submit_leave(s, bad_from, bad_to, "Thử ngày sai")
        check("bad" in kind and "Ngày kết thúc" in text, f"thông báo {text!r}")
        r["actual"] = f"Thông báo lỗi: {text}"
    start, end = working_day(3), working_day(4)
    home(s)
    with case(s, "NV-04", "Gửi đơn nghỉ phép năm 2 ngày", "Chọn Phép năm, nhập ngày, lý do, bấm Gửi đơn",
              f"{vn(start)} → {vn(end)}, lý do: Việc gia đình", "Thông báo đã gửi; đơn 2 ngày ở trạng thái Chờ quản lý duyệt, gửi đến Trần Minh Quang") as r:
        kind, text = submit_leave(s, start, end, "Việc gia đình")
        check("ok" in kind, f"thông báo {text!r}")
        REQ["an"] = created_name(text)
        after_reload(p)
        state, _ = my_request_state(p, REQ["an"])
        check(state == "Chờ quản lý duyệt", f"trạng thái {state!r}")
        detail = api_json(s, f"/api/resource/Leave Application/{REQ['an']}")["data"]
        check(detail["leave_approver"] == "quang@demo.example" and detail["total_leave_days"] == 2, f"{detail['leave_approver']} {detail['total_leave_days']}")
        r["actual"] = f"{text} · {REQ['an']} chờ quang@demo.example duyệt, 2 ngày"
    with case(s, "NV-05", "Xem hồ sơ của tôi", "Bấm Mở nhanh > Hồ sơ của tôi (desk)", "", "Mở được hồ sơ nhân viên của chính mình") as r:
        p.get_by_test_id("link").filter(has_text="Hồ sơ của tôi").click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        s.caption("NV-05 · Hồ sơ của tôi (desk)")
        desk_ok(s, "Nguyễn Hoài An")
        r["actual"] = f"Mở {p.url.replace(BASE, '')}, thấy hồ sơ Nguyễn Hoài An, không có lỗi quyền"
    with case(s, "NV-06", "Không xem được hồ sơ người khác", "Mở trực tiếp hồ sơ của Giám đốc nhân sự bằng URL và API", "Hồ sơ của lan@ / hoa@",
              "Bị chặn: API trả 403, danh sách nhân viên chỉ có chính mình") as r:
        employees = api_json(s, "/api/resource/Employee?limit_page_length=500")["data"]
        check(len(employees) == 1, f"thấy {len(employees)} hồ sơ")
        other = api_json(s, "/api/resource/Employee?filters=" + json.dumps([["user_id", "=", "hoa@demo.example"]]))["data"]
        check(other == [], f"thấy hồ sơ người khác: {other}")
        hoa_id = "HR-EMP-00003"
        status = api_status(s, f"/api/resource/Employee/{hoa_id}")
        check(status == 403, f"mở hồ sơ {hoa_id} trả {status}")
        show_desk(s, f"/desk/employee/{hoa_id}")
        r["actual"] = f"Danh sách chỉ có {len(employees)} hồ sơ (chính mình); tìm hồ sơ hoa@ trả rỗng; mở {hoa_id} trả {status}"
    with case(s, "NV-07", "Không có chức năng duyệt và quản trị", "Kiểm tra trang chủ không có Hộp duyệt, Đội, Tổng quan; gọi API duyệt",
              "decide trên đơn của chính mình", "Không có các mục đó; API duyệt bị từ chối") as r:
        home(s)
        for t in ("inbox", "team", "company"):
            check(p.get_by_test_id(t).count() == 0, f"đang hiện mục {t}")
        token = p.evaluate("TLC_CSRF")
        res = p.request.post(f"{BASE}/api/method/tlc_hr.api.decide", headers={"X-Frappe-CSRF-Token": token},
                             data={"name": REQ["an"], "decision": "approve"})
        check(res.status >= 400, f"API duyệt trả {res.status}")
        r["actual"] = f"Không có Hộp duyệt/Đội/Tổng quan; tự duyệt đơn của mình qua API bị chặn ({res.status})"
    s.close()


def support_office_manager(playwright):
    """Precondition, not a persona of the brief: the head of sales approves the office request (API, no video)."""
    row = {"id": "HT-01", "account": "quang@demo.example", "role": "Hỗ trợ - Trưởng phòng Kinh doanh (quản lý của an)",
           "function": "Quản lý trực tiếp duyệt đơn của nhân viên văn phòng", "steps": "Gọi API tlc_hr.api.decide (bước tiền điều kiện)",
           "data": REQ.get("an", ""), "expected": "Đơn chuyển sang Chờ nhân sự duyệt", "video": "", "time": "", "shot": "",
           "run_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        api = playwright.request.new_context(base_url=BASE)
        api.post("/api/method/login", data={"usr": "quang@demo.example", "pwd": PASSWORD})
        res = api.post("/api/method/tlc_hr.api.decide", data={"name": REQ["an"], "decision": "approve"})
        state = res.json()["message"]["workflow_state"]
        check(state == "Chờ nhân sự duyệt", state)
        row.update(actual=f"{REQ['an']} → {state}", status="Đạt")
        api.dispose()
    except Exception as exc:
        row.update(actual=f"{type(exc).__name__}: {exc}", status="Không đạt")
    RESULTS.append(row)
    print(f"{row['status']:10} HT-01    {row['actual']}", flush=True)


def factory_worker_1(browser):
    s = Session(browser, "CN1", "binh", phone=True)
    first_case(s, "CN1-01")
    p = s.page
    day = working_day(2)
    with case(s, "CN1-02", "Gửi đơn nghỉ 1 ngày trên điện thoại", "Cuộn tới Xin nghỉ phép, nhập ngày và lý do, bấm Gửi đơn",
              f"{vn(day)}, lý do: Con ốm", "Đơn 1 ngày Chờ quản lý duyệt, gửi đến Đặng Văn Hùng") as r:
        kind, text = submit_leave(s, day, day, "Con ốm")
        check("ok" in kind, text)
        REQ["binh_full"] = created_name(text)
        after_reload(p)
        state, _ = my_request_state(p, REQ["binh_full"])
        check(state == "Chờ quản lý duyệt", state)
        r["actual"] = f"{text} · trạng thái {state}"
    half = working_day(5)
    home(s)
    with case(s, "CN1-03", "Gửi đơn nghỉ nửa ngày", "Tích Nghỉ nửa ngày, nhập lý do, Gửi đơn", f"{vn(half)} nửa ngày, lý do: Khám sức khỏe",
              "Đơn 0,5 ngày Chờ quản lý duyệt") as r:
        kind, text = submit_leave(s, half, half, "Khám sức khỏe", half=True)
        check("ok" in kind and "(0.5 ngày)" in text, text)
        REQ["binh_half"] = created_name(text)
        after_reload(p)
        state, _ = my_request_state(p, REQ["binh_half"])
        check(state == "Chờ quản lý duyệt", state)
        r["actual"] = f"{text} · trạng thái {state}"
    with case(s, "CN1-04", "Phạm vi dữ liệu của công nhân", "Gọi danh sách nhân viên và đơn nghỉ qua API phiên của công nhân", "",
              "Chỉ thấy hồ sơ của mình và đơn của mình") as r:
        employees = api_json(s, "/api/resource/Employee?limit_page_length=500")["data"]
        leaves = api_json(s, "/api/resource/Leave Application?limit_page_length=500&fields=[\"employee_name\"]")["data"]
        others = {x["employee_name"] for x in leaves} - {"Trần Văn Bình"}
        check(len(employees) == 1 and not others, f"{len(employees)} hồ sơ, đơn của người khác: {others}")
        r["actual"] = f"Thấy {len(employees)} hồ sơ, {len(leaves)} đơn - đều của chính mình"
    s.close()


def factory_worker_2(browser):
    s = Session(browser, "CN2", "f2w01", phone=True)
    first_case(s, "CN2-01")
    day = working_day(2)
    with case(s, "CN2-02", "Gửi đơn nghỉ 1 ngày (Nhà máy 2)", "Nhập ngày, lý do, Gửi đơn", f"{vn(day)}, lý do: Về quê",
              "Đơn Chờ quản lý duyệt, gửi đến quản lý Nhà máy 2 (Lương Quốc Hải), không phải quản lý Nhà máy 1") as r:
        kind, text = submit_leave(s, day, day, "Về quê")
        check("ok" in kind, text)
        REQ["f2w01"] = created_name(text)
        after_reload(s.page)
        detail = api_json(s, f"/api/resource/Leave Application/{REQ['f2w01']}")["data"]
        check(detail["leave_approver"] == "nm2@demo.example", detail["leave_approver"])
        r["actual"] = f"{text} · người duyệt nm2@demo.example"
    with case(s, "CN2-03", "Không xem được đơn của nhà máy khác", "Mở trực tiếp đơn của công nhân Nhà máy 1 qua API", REQ.get("binh_full", ""),
              "Bị chặn (403)") as r:
        status = api_status(s, f"/api/resource/Leave Application/{REQ['binh_full']}")
        check(status == 403, f"trả {status}")
        r["actual"] = f"API trả {status}"
    s.close()


def factory_head(browser):
    s = Session(browser, "QL", "hung")
    first_case(s, "QL-01")
    p = s.page
    with case(s, "QL-02", "Hộp duyệt chỉ có đơn của người thuộc quyền", "Xem mục Việc chờ tôi duyệt",
              "Đơn của binh (NM1) và f2w01 (NM2)", "Có 2 đơn của Trần Văn Bình; không có đơn của Nhà máy 2") as r:
        names = [x.get_attribute("data-name") for x in p.get_by_test_id("inbox-item").all()]
        check(REQ["binh_full"] in names and REQ["binh_half"] in names, f"hộp duyệt {names}")
        check(REQ["f2w01"] not in names, "thấy đơn của Nhà máy 2")
        r["actual"] = f"Hộp duyệt: {', '.join(names)} (không có {REQ['f2w01']} của Nhà máy 2)"
    with case(s, "QL-03", "Xem đội của tôi", "Xem mục Đội của tôi", "", "14 người thuộc Nhà máy 1, trạng thái đi làm/nghỉ hôm nay") as r:
        p.get_by_test_id("team").scroll_into_view_if_needed()
        size = p.get_by_test_id("team-member").count()
        check(size == 14, f"{size} người")
        p.wait_for_timeout(1200)
        r["actual"] = f"Đội có {size} người"
        p.evaluate("window.scrollTo(0, 0)")
    with case(s, "QL-04", "Duyệt đơn 1 ngày của công nhân", "Bấm Duyệt trên đơn của Trần Văn Bình", REQ["binh_full"],
              "Thông báo đã duyệt; đơn chuyển sang Chờ nhân sự duyệt") as r:
        kind, text = decide(s, REQ["binh_full"], "approve")
        check("ok" in kind and "Chờ nhân sự duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    with case(s, "QL-05", "Từ chối phải có lý do", "Bấm Từ chối…, để trống lý do, Xác nhận từ chối", REQ["binh_half"],
              "Báo lỗi 'Nhập lý do từ chối', đơn giữ nguyên") as r:
        kind, text = decide(s, REQ["binh_half"], "reject", reason="")
        check("bad" in kind and "lý do" in text.lower(), text)
        r["actual"] = f"Thông báo lỗi: {text}"
    with case(s, "QL-06", "Từ chối đơn nửa ngày có lý do", "Nhập lý do, Xác nhận từ chối", "Lý do: Trùng ca kiểm kê kho",
              "Đơn chuyển Từ chối, lý do được lưu") as r:
        item = inbox_item(p, REQ["binh_half"])
        item.get_by_test_id("reject-reason").fill("Trùng ca kiểm kê kho")
        item.get_by_test_id("reject-confirm").click()
        kind, text = toast(p)
        check("ok" in kind and "Từ chối" in text, text)
        after_reload(p)
        r["actual"] = text
    with case(s, "QL-07", "Không duyệt được đơn của nhà máy khác", "Gọi API duyệt đơn của công nhân Nhà máy 2; mở đơn trên desk", REQ["f2w01"],
              "Bị chặn") as r:
        token = p.evaluate("TLC_CSRF")
        res = p.request.post(f"{BASE}/api/method/tlc_hr.api.decide", headers={"X-Frappe-CSRF-Token": token},
                             data={"name": REQ["f2w01"], "decision": "approve"})
        check(res.status >= 400, f"trả {res.status}")
        show_desk(s, f"/desk/leave-application/{REQ['f2w01']}")
        r["actual"] = f"API duyệt trả {res.status}; desk không mở được đơn"
    with case(s, "QL-08", "Danh sách nhân viên thuộc quyền (desk)", "Mở Mở nhanh > Danh sách nhân viên thuộc quyền", "",
              "Chỉ thấy 15 hồ sơ của Nhà máy 1 (14 người + bản thân)") as r:
        home(s)
        p.get_by_test_id("link").filter(has_text="thuộc quyền").click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        s.caption("QL-08 · Danh sách nhân viên thuộc quyền (desk)")
        desk_ok(s)
        employees = api_json(s, "/api/resource/Employee?limit_page_length=500&fields=[\"department\"]")["data"]
        departments = {x["department"] for x in employees}
        check(len(employees) == 15 and departments == {"Nhà máy 1 - TLC"}, f"{len(employees)} hồ sơ, {departments}")
        r["actual"] = f"{len(employees)} hồ sơ, tất cả thuộc Nhà máy 1"
    day = working_day(6)
    home(s)
    with case(s, "QL-09", "Quản lý tự xin nghỉ", "Gửi đơn nghỉ của chính mình", f"{vn(day)}, lý do: Họp phụ huynh",
              "Đơn đến CEO Nguyễn Văn Thành; không nằm trong hộp duyệt của chính mình") as r:
        kind, text = submit_leave(s, day, day, "Họp phụ huynh")
        check("ok" in kind, text)
        REQ["hung"] = created_name(text)
        after_reload(p)
        names = [x.get_attribute("data-name") for x in p.get_by_test_id("inbox-item").all()]
        check(REQ["hung"] not in names, "đơn của mình nằm trong hộp duyệt của mình")
        r["actual"] = f"{text}; không có trong hộp duyệt của chính mình"
    s.close()


def hr_lead_first(browser):
    s = Session(browser, "HR", "hoa")
    first_case(s, "HR-01")
    p = s.page
    with case(s, "HR-02", "Tổng quan nhân sự toàn công ty", "Xem mục Tổng quan nhân sự", "",
              "60 nhân sự; khối Hội sở 31, Nhà máy 29; số nhân sự theo từng địa điểm") as r:
        p.get_by_test_id("company").scroll_into_view_if_needed()
        headcount = int(p.get_by_test_id("stat-headcount").locator(".n").inner_text())
        text = p.get_by_test_id("company").inner_text()
        office = re.search(r"Khối Hội sở\s+(\d+)", text)
        factory = re.search(r"Khối Nhà máy\s+(\d+)", text)
        check(headcount == 60 and office and factory and (office.group(1), factory.group(1)) == ("31", "29"), text[:300])
        sites = p.get_by_test_id("site-row").count()
        check(sites == 9, f"{sites} địa điểm/phòng ban")
        p.wait_for_timeout(1500)
        r["actual"] = f"{headcount} nhân sự, 9 địa điểm/phòng ban, Hội sở 31 / Nhà máy 29"
        p.evaluate("window.scrollTo(0, 0)")
    with case(s, "HR-03", "Hộp duyệt cấp nhân sự", "Xem Việc chờ tôi duyệt", "",
              "Có đơn của Trần Văn Bình (đã qua quản lý NM1) và Nguyễn Hoài An (đã qua trưởng phòng)") as r:
        names = [x.get_attribute("data-name") for x in p.get_by_test_id("inbox-item").all()]
        check(REQ["binh_full"] in names and REQ["an"] in names, f"{names}")
        r["actual"] = f"Hộp duyệt: {', '.join(names)}"
    with case(s, "HR-04", "Duyệt đơn công nhân nhà máy", "Bấm Duyệt trên đơn của Trần Văn Bình", REQ["binh_full"], "Đơn Đã duyệt") as r:
        kind, text = decide(s, REQ["binh_full"], "approve")
        check("ok" in kind and "Đã duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    with case(s, "HR-05", "Duyệt đơn nhân viên văn phòng", "Bấm Duyệt trên đơn của Nguyễn Hoài An", REQ["an"], "Đơn Đã duyệt") as r:
        kind, text = decide(s, REQ["an"], "approve")
        check("ok" in kind and "Đã duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    day = working_day(7)
    with case(s, "HR-06", "Trưởng nhân sự tự xin nghỉ", "Gửi đơn nghỉ của chính mình", f"{vn(day)}, lý do: Đi đám cưới",
              "Đơn đến CEO Nguyễn Văn Thành") as r:
        kind, text = submit_leave(s, day, day, "Đi đám cưới")
        check("ok" in kind, text)
        REQ["hoa"] = created_name(text)
        after_reload(p)
        r["actual"] = text
    with case(s, "HR-07", "Báo cáo số dư phép", "Mở nhanh > Báo cáo số dư phép", "", "Báo cáo Employee Leave Balance mở được, có dữ liệu nhân viên") as r:
        p.get_by_test_id("link").filter(has_text="Báo cáo số dư phép").click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(6000)
        s.caption("HR-07 · Báo cáo số dư phép (desk)")
        desk_ok(s)
        check("query-report" in p.url, p.url)
        r["actual"] = f"Mở {p.url.replace(BASE, '')}"
    with case(s, "HR-08", "Tham số lương Việt Nam 2026", "Mở nhanh > Thiết lập lương Việt Nam; đọc tham số", "",
              "Lương cơ sở 2.530.000; giảm trừ bản thân 15.500.000; người phụ thuộc 6.200.000; hiệu lực 01-07-2026") as r:
        home(s)
        p.get_by_test_id("link").filter(has_text="Thiết lập lương").click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(4000)
        s.caption("HR-08 · Thiết lập lương Việt Nam (desk)")
        desk_ok(s)
        data = api_json(s, "/api/resource/VN Payroll Settings/VN Payroll Settings")["data"]
        got = (data["base_salary"], data["personal_deduction"], data["dependent_deduction"], data["effective_date"])
        check(got == (2530000, 15500000, 6200000, "2026-07-01"), str(got))
        r["actual"] = f"Lương cơ sở {got[0]:,.0f}; giảm trừ {got[1]:,.0f} / {got[2]:,.0f}; hiệu lực {got[3]}".replace(",", ".")
    with case(s, "HR-09", "Danh sách nhân sự toàn công ty", "Mở nhanh > Danh sách nhân sự", "", "Thấy đủ 60 hồ sơ") as r:
        home(s)
        p.get_by_test_id("link").filter(has_text="Danh sách nhân sự").click()
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(3500)
        s.caption("HR-09 · Danh sách nhân sự (desk)")
        desk_ok(s)
        employees = api_json(s, "/api/resource/Employee?limit_page_length=500")["data"]
        check(len(employees) == 60, f"{len(employees)} hồ sơ")
        r["actual"] = f"{len(employees)} hồ sơ"
    s.close()


def ceo(browser):
    s = Session(browser, "CEO", "thanh")
    first_case(s, "CEO-01")
    p = s.page
    with case(s, "CEO-02", "Tổng quan điều hành", "Xem các ô chỉ số và Tổng quan nhân sự", "",
              "60 nhân sự; 3 đơn chờ quản lý duyệt (NM2, Quản lý NM1, Trưởng nhân sự); 0 đơn chờ nhân sự") as r:
        p.get_by_test_id("company").scroll_into_view_if_needed()
        waiting_manager = int(p.get_by_test_id("waiting-manager").inner_text())
        waiting_hr = int(p.get_by_test_id("waiting-hr").inner_text())
        check((waiting_manager, waiting_hr) == (3, 0), f"{waiting_manager} / {waiting_hr}")
        p.wait_for_timeout(1500)
        r["actual"] = f"Chờ quản lý duyệt {waiting_manager}, chờ nhân sự {waiting_hr}"
        p.evaluate("window.scrollTo(0, 0)")
    with case(s, "CEO-03", "Không có form xin nghỉ cho CEO", "Xem mục Xin nghỉ phép", "",
              "Hiện ghi chú: không có cấp trên duyệt, báo phòng Nhân sự ghi nhận") as r:
        check(p.get_by_test_id("no-approver").is_visible() and p.locator("#leave-form").count() == 0, "vẫn có form")
        r["actual"] = p.get_by_test_id("no-approver").inner_text()
    with case(s, "CEO-04", "Duyệt đơn của Quản lý Nhà máy 1", "Bấm Duyệt trên đơn của Đặng Văn Hùng", REQ["hung"], "Chờ nhân sự duyệt") as r:
        kind, text = decide(s, REQ["hung"], "approve")
        check("ok" in kind and "Chờ nhân sự duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    with case(s, "CEO-05", "Duyệt đơn của Trưởng nhân sự", "Bấm Duyệt trên đơn của Lê Thị Hòa", REQ["hoa"], "Chờ nhân sự duyệt") as r:
        kind, text = decide(s, REQ["hoa"], "approve")
        check("ok" in kind and "Chờ nhân sự duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    with case(s, "CEO-06", "Đội của tôi toàn công ty", "Xem Đội của tôi và lịch nghỉ 14 ngày tới", "",
              "59 người; lịch nghỉ có đơn đã duyệt của Trần Văn Bình và Nguyễn Hoài An") as r:
        p.get_by_test_id("team").scroll_into_view_if_needed()
        size = p.get_by_test_id("team-member").count()
        upcoming = " | ".join(x.inner_text() for x in p.get_by_test_id("team-upcoming").all())
        check(size == 59 and "Trần Văn Bình" in upcoming and "Nguyễn Hoài An" in upcoming, f"{size}; {upcoming}")
        p.wait_for_timeout(1500)
        r["actual"] = f"{size} người; lịch nghỉ: {upcoming}"
    s.close()


def hr_lead_second(browser):
    s = Session(browser, "HR2", "hoa")
    login(s)
    p = s.page
    with case(s, "HR-10", "Không tự duyệt đơn của mình", "Xem hộp duyệt sau khi CEO duyệt đơn của chính mình; thử API duyệt", REQ["hoa"],
              "Đơn của mình không có trong hộp duyệt; API duyệt bị chặn") as r:
        names = [x.get_attribute("data-name") for x in p.get_by_test_id("inbox-item").all()]
        check(REQ["hoa"] not in names, "đơn của mình nằm trong hộp duyệt")
        token = p.evaluate("TLC_CSRF")
        res = p.request.post(f"{BASE}/api/method/tlc_hr.api.decide", headers={"X-Frappe-CSRF-Token": token},
                             data={"name": REQ["hoa"], "decision": "approve"})
        check(res.status >= 400, f"API trả {res.status}")
        r["actual"] = f"Hộp duyệt {names}; tự duyệt qua API bị chặn ({res.status})"
    with case(s, "HR-11", "Duyệt đơn của Quản lý Nhà máy 1", "Bấm Duyệt trên đơn của Đặng Văn Hùng", REQ["hung"], "Đơn Đã duyệt") as r:
        kind, text = decide(s, REQ["hung"], "approve")
        check("ok" in kind and "Đã duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    s.close()


def hr_officer(browser):
    s = Session(browser, "HR3", "lan")
    first_case(s, "HR-12")
    p = s.page
    with case(s, "HR-13", "Chuyên viên nhân sự duyệt đơn của Trưởng nhân sự", "Bấm Duyệt trên đơn của Lê Thị Hòa", REQ["hoa"], "Đơn Đã duyệt") as r:
        kind, text = decide(s, REQ["hoa"], "approve")
        check("ok" in kind and "Đã duyệt" in text, text)
        after_reload(p)
        r["actual"] = text
    s.close()


def factory_worker_1_result(browser):
    s = Session(browser, "CN1b", "binh", phone=True)
    login(s)
    p = s.page
    with case(s, "CN1-05", "Xem kết quả đơn", "Mở trang chủ, xem Đơn của tôi", f"{REQ['binh_full']}, {REQ['binh_half']}",
              "Đơn 1 ngày Đã duyệt; đơn nửa ngày Từ chối, hiện lý do 'Trùng ca kiểm kê kho'") as r:
        full, _ = my_request_state(p, REQ["binh_full"])
        half, row = my_request_state(p, REQ["binh_half"])
        reason = row.get_by_test_id("my-request-reason").inner_text()
        check(full == "Đã duyệt" and half == "Từ chối" and "Trùng ca kiểm kê kho" in reason, f"{full} / {half} / {reason}")
        p.wait_for_timeout(1500)
        r["actual"] = f"{full} / {half} ({reason})"
    with case(s, "CN1-06", "Số dư phép sau khi được duyệt", "Đọc ô phép năm", "", "Phép năm còn 11 ngày (đơn bị từ chối không trừ)") as r:
        p.evaluate("window.scrollTo(0, 0)")
        value = balance(p)
        check(value == 11, f"còn {value}")
        r["actual"] = f"Còn {value:g} ngày"
    s.close()


def office_employee_result(browser):
    s = Session(browser, "NVb", "an")
    login(s)
    p = s.page
    with case(s, "NV-08", "Xem kết quả đơn và số dư", "Xem Đơn của tôi và ô phép năm", REQ["an"], "Đơn Đã duyệt; phép năm còn 10 ngày") as r:
        state, _ = my_request_state(p, REQ["an"])
        p.evaluate("window.scrollTo(0, 0)")
        value = balance(p)
        check(state == "Đã duyệt" and value == 10, f"{state} / {value}")
        r["actual"] = f"{state}; còn {value:g} ngày"
    s.close()


def factory_head_result(browser):
    s = Session(browser, "QLb", "hung")
    login(s)
    p = s.page
    with case(s, "QL-10", "Lịch nghỉ của đội và đơn của tôi", "Xem Đội của tôi (14 ngày tới) và Đơn của tôi", "",
              "Lịch nghỉ có Trần Văn Bình; đơn của tôi Đã duyệt") as r:
        state, _ = my_request_state(p, REQ["hung"])
        p.get_by_test_id("team").scroll_into_view_if_needed()
        upcoming = " | ".join(x.inner_text() for x in p.get_by_test_id("team-upcoming").all())
        check(state == "Đã duyệt" and "Trần Văn Bình" in upcoming, f"{state}; {upcoming}")
        p.wait_for_timeout(1500)
        r["actual"] = f"Đơn của tôi {state}; lịch nghỉ: {upcoming}"
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
        steps = [office_employee, None, factory_worker_1, factory_worker_2, factory_head, hr_lead_first, ceo, hr_lead_second,
                 hr_officer, factory_worker_1_result, office_employee_result, factory_head_result]
        for step in steps:
            try:
                support_office_manager(playwright) if step is None else step(browser)
            except Exception as exc:  # a scenario that breaks early still leaves the other evidence
                print("SCENARIO ERROR", getattr(step, "__name__", "support"), exc, flush=True)
                traceback.print_exc()
        browser.close()
    write_outputs()
    passed = sum(1 for r in RESULTS if r["status"] == "Đạt")
    print(f"UAT {RUN_ID}: {passed}/{len(RESULTS)} đạt", flush=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
