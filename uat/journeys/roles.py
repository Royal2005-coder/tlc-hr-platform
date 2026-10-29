"""Một video liền mạch cho mỗi vai trò: ngày làm việc thật của một người, mọi bước đều làm trên giao diện chuẩn.

R1 công nhân (binh) · R2 nhân viên văn phòng (an) · R3 trưởng nhà máy (hung) · R4 ba người HR (lan/hoa/phuong) ·
R5 CEO (thanh) · R6 trưởng phòng và kế toán (quang/chi). Vai trò nào cần nhiều tài khoản thì quay lần lượt từng tài khoản;
`roles_stitch.sh` nối các clip đó thành MỘT video cho vai trò.

Hành vi được nghiệm thu là cú nhấp chuột / lần gõ phím thật, điều kiểm lấy từ màn hình. API chỉ có hai việc ở đây:
`prepare_state` dựng dữ liệu nền trước khi quay (setup), và đọc lại một con số để đối chiếu sau khi người dùng đã làm xong.

Chạy: ONLY=roles ./run_uat.sh
"""

import base64
import datetime as dt
import json
import re
from urllib.parse import quote

from lib import *  # noqa: F401,F403

OT, KC, AR, PE, EA = "TLC Overtime Request", "TLC Attendance Period", "Attendance Request", "Payroll Entry", "Employee Advance"
TO_WORKER, TO_DIRECTOR = "Chờ người lao động đồng ý", "Chờ giám đốc duyệt"
P_TO_HEAD, P_TO_HR, P_TO_CEO, P_LOCKED = "Chờ quản lý xác nhận", "Chờ nhân sự đối soát", "Chờ giám đốc ký", "Đã khoá"
COMPUTED, SIGNED, PAID = "Đã tính lương", "Đã ký", "Đã chi"
SCOPES = ["Nhà máy 1", "Nhà máy 2", "Nhà máy 3", "Hội sở"]
HEADS = {"Nhà máy 1": "hung", "Nhà máy 2": "nm2", "Nhà máy 3": "nm3"}
SITE_OF = {"Nhà máy 1": (10.850632, 106.772010), "Nhà máy 2": (10.980410, 106.651871), "Nhà máy 3": (10.957413, 106.842687)}
SHIFT_TIMES = {"TLC Hành chính": ((7, 52), (17, 8)), "TLC Ca đêm": ((21, 52), (6, 8)), "TLC Cao điểm": ((6, 52), (19, 8))}


# --------------------------------------------------------------------------------- lịch quay: tháng nào dùng việc gì
def month_of(back):
    """Tháng `back` tháng trước tháng hiện tại, định dạng YYYY-MM."""
    first = dt.date.today().replace(day=1)
    for _ in range(back):
        first = (first - dt.timedelta(days=1)).replace(day=1)
    return first.strftime("%Y-%m")


def bounds(month):
    first = dt.date.fromisoformat(month + "-01")
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()


M_PAID = M_UI = M_SIGN = M_NOW = None  # assigned from unoccupied, SSA-covered months in prepare_state


def shift_open_now():
    """Ca nào đang mở lúc này, để công nhân chấm công GPS được thật (None nếu lọt vào khoảng trống giữa hai ca)."""
    now = dt.datetime.now()
    for name, (start, end) in SHIFT_TIMES.items():
        opened = now.replace(hour=start[0], minute=start[1], second=0, microsecond=0)
        closing = now.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
        if closing > opened:
            if opened <= now < closing:
                return name
        elif now >= opened or now < closing:
            return name
    return None


# --------------------------------------------------------------------------------------------- desk primitives

def desk(s, doctype, name=None):
    """Danh sách, form mới, hoặc một bản ghi trên desk. Không bấm "Thêm" của danh sách: nó mở quick-entry thiếu trường TLC."""
    path = f"{BASE}/desk/{doctype.lower().replace(' ', '-')}"
    s.page.goto(f"{path}/new" if name is None else f"{path}/{quote(name, safe='')}")
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1800)


def wait_frm(s, doctype):
    s.page.wait_for_function("d => window.cur_frm && cur_frm.doctype === d && !!cur_frm.doc "
                             "&& cur_frm.wrapper && cur_frm.wrapper.getClientRects().length > 0", arg=doctype)
    s.page.wait_for_timeout(600)


def form_value(s, fname):
    return s.page.evaluate("f => cur_frm.doc[f] || ''", fname)


def display_in(box, value):
    """Use the current user's configured date format, retaining the time for Datetime."""
    dtype = box.get_attribute("data-fieldtype") or ""
    text = str(value)
    if dtype in ("Date", "Datetime") and re.match(r"^\d{4}-\d{2}-\d{2}", text):
        d = dt.date.fromisoformat(text[:10])
        fmt = box.page.evaluate("() => frappe.boot.sysdefaults.date_format || 'yyyy-mm-dd'")
        text = fmt.replace("yyyy", f"{d.year:04d}").replace("mm", f"{d.month:02d}").replace("dd", f"{d.day:02d}")
        if dtype == "Datetime" and len(str(value)) > 10:
            text += " " + str(value)[11:19]
    return text


def write(s, fname, value):
    """Điền vào một trường của form đang mở: chọn ô, gõ, rời ô — như người dùng thật."""
    box = s.page.locator(f"input[data-fieldname='{fname}']:visible, textarea[data-fieldname='{fname}']:visible").first
    box.fill(display_in(box, value))
    box.press("Tab")
    s.page.wait_for_timeout(600)
    s.page.keyboard.press("Escape")  # đóng bảng gợi ý/lịch còn mở
    s.page.wait_for_timeout(300)
    return form_value(s, fname)


def write_time(s, fname, value):
    box = s.page.locator(f"input[data-fieldname='{fname}']:visible").first
    box.fill(display_in(box, value))
    box.press("Enter")
    s.page.wait_for_timeout(600)
    box.press("Tab")
    s.page.wait_for_timeout(600)
    s.page.keyboard.press("Escape")
    s.page.wait_for_timeout(300)
    return form_value(s, fname)


def pick(s, fname, needle):
    """Ô liên kết/dropdown: bấm, gõ để lọc rồi nhấp đúng dòng gợi ý hiện ra."""
    p = s.page
    sel = p.locator(f"select[data-fieldname='{fname}']:visible")
    if sel.count():
        try:
            sel.first.select_option(label=str(needle))
        except Exception:
            sel.first.select_option(value=str(needle))
        p.wait_for_timeout(600)
        return form_value(s, fname)
    box = p.locator(f"input[data-fieldname='{fname}']:visible").first
    box.click()
    box.fill("")
    p.keyboard.type(str(needle), delay=40)
    p.wait_for_timeout(2200)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option]")
    target = next((i for i in range(options.count())
                   if str(needle).lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
    if target is None:  # an exact document name can be committed with Enter even without a suggestion row
        p.keyboard.press("Enter")
        p.wait_for_timeout(1000)
        if str(form_value(s, fname)) == str(needle):
            return form_value(s, fname)
    check(target is not None, f"ô {fname}: không có gợi ý '{needle}': {options.all_inner_texts()[:4]}")
    options.nth(target).click()
    p.wait_for_timeout(1000)
    return form_value(s, fname)


def choose(s, fname, value):
    """Chọn giá trị: ô select thì chọn trong danh sách, ô liên kết thì gõ rồi chọn kết quả gợi ý."""
    return pick(s, fname, value)


def save(s):
    s.page.keyboard.press("Escape")
    s.page.wait_for_timeout(400)
    button = s.page.locator(".page-head button.es-button.primary-action:visible, .page-head button:visible").filter(
        has_text=re.compile(r"Lưu|Save|Cập nhật|Update")).last
    try:
        button.click(timeout=6000)
    except Exception:
        button.click(force=True)
    s.page.wait_for_load_state("networkidle")
    s.page.wait_for_timeout(1600)
    reason_dialog(s)


def reason_dialog(s, reason="Kế toán cập nhật chứng từ ngân hàng"):
    """Form đã ghi sổ thì desk hỏi lý do cập nhật: điền và bấm nút cập nhật thật."""
    dialog = s.page.locator(".modal:visible")
    if not dialog.count():
        return
    box = dialog.last.locator("textarea, input[type=text]")
    if box.count():
        box.first.fill(reason)
    button = dialog.get_by_role("button", name=re.compile(r"^(Update|Cập nhật)$"))
    if button.count():
        button.last.click()
        s.page.wait_for_timeout(2500)


def open_menu(p):
    """Hành động, or the ⋮ menu when the workflow actions live there; wait for visible menu rows."""
    for _ in range(4):
        if p.locator(MENU_ITEMS).count():
            return True
        button = p.get_by_role("button", name="Hành động")
        if button.count() and button.first.is_visible():
            button.first.click()
        else:
            more = p.locator(".page-head .menu-more-button:visible, .page-actions .menu-more-button:visible")
            if not more.count():
                return False
            more.last.click()
        p.wait_for_timeout(1000)
    return bool(p.locator(MENU_ITEMS).count())


def action(s, name):
    """Bấm `Hành động` (hoặc ⋮) rồi chọn một nút quy trình trên form đang mở."""
    check(open_menu(s.page), f"không mở được menu hành động: {[t.strip() for t in s.page.locator('.page-head button:visible').all_inner_texts()]}")
    items = s.page.locator(MENU_ITEMS)
    target = next((i for i in range(items.count()) if name in " ".join(items.nth(i).inner_text().split())), None)
    check(target is not None, f"không có nút {name} trong {menu_items(s.page)}")
    items.nth(target).click()
    s.page.wait_for_timeout(3500)


def open_form(s, doctype, name):
    desk(s, doctype, name)
    wait_frm(s, doctype)
    s.page.wait_for_function(
        "v => window.cur_frm && cur_frm.doctype === v.doctype && cur_frm.doc.name === v.name",
        arg={"doctype": doctype, "name": name})


def body(s):
    return " ".join(s.page.locator("body").inner_text().split())


def body_with_inputs(s):
    """Text of the page plus the values of its read-only controls (the app prints money inside inputs)."""
    values = []
    inputs = s.page.locator("input:visible")
    for i in range(inputs.count()):
        try:
            values.append(inputs.nth(i).input_value())
        except Exception:
            pass
    return body(s) + " " + " ".join(values)


def created(s):
    """Tên bản ghi vừa lưu, đọc từ chính form đang mở."""
    return s.page.evaluate("() => cur_frm.doc.name")


def list_text(s, doctype):
    desk(s, doctype)
    s.page.wait_for_timeout(2500)
    return body(s)


def workspace(s, title):
    """Mở workspace của vai trò theo đường dẫn của nó (/desk/tlc-hr/<slug>)."""
    s.page.goto(f"{BASE}/desk/tlc-hr/{quote(title.lower().replace(' ', '-'))}")
    s.page.wait_for_load_state("networkidle")
    try:
        s.page.get_by_text(title, exact=True).last.wait_for(timeout=30000)
    except Exception:
        check(title in body(s), f"không mở được workspace {title}: {s.page.url} · {body(s)[:220]}")
    s.page.wait_for_timeout(2500)


def shortcut(s, label, route):
    """Bấm một shortcut của workspace và kiểm tra nó mở đúng màn hình nghiệp vụ."""
    p = s.page
    wanted = route.replace(BASE, "").strip("/")
    token = wanted.rsplit("/", 1)[-1]  # a DocType shortcut opens /desk/<module>/<doctype>/view/list
    try:
        with s.context.expect_page(timeout=6000) as info:
            p.get_by_text(label, exact=True).first.click()
        popup = info.value
    except Exception:
        popup = None
    if popup is not None:
        popup.wait_for_load_state("networkidle")
        check(token in popup.url or wanted in popup.url, f"shortcut mở {popup.url}")
        popup.close()
        p.goto(route if route.startswith("http") else f"{BASE}{route}")
    else:
        p.wait_for_url(lambda url: token in url or wanted in url, timeout=15000)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(1500)


def money(text, value):
    """Con tiền hiện trên màn hình có đúng bằng giá trị đọc được từ server (vi-VN dùng dấu chấm phân nghìn)."""
    digits = int(round(value))
    for candidate in (f"{digits:,}".replace(",", "."), f"{digits:,}", f"{digits}"):
        if candidate in text:
            return candidate
    return None


def shows_number(text, value):
    for candidate in (f"{value:g}", f"{value:.1f}", f"{value:.1f}".replace(".", ","), f"{int(value)}"):
        if candidate in text:
            return candidate
    return None


# ------------------------------------------------------------------- API: dựng dữ liệu nền và đối chiếu sau thao tác

def find(s, doctype, filters=(), fields=("name",), limit=100, order=None):
    query = (f"/api/resource/{doctype}?filters=" + quote(json.dumps(list(filters), ensure_ascii=False))
             + "&fields=" + quote(json.dumps(list(fields), ensure_ascii=False))
             + f"&limit_page_length={limit}" + ("&order_by=" + quote(order) if order else ""))
    return api_get(s, query).json().get("data", [])


def emp(s, account):
    return find(s, "Employee", [["user_id", "=", f"{account}@demo.example"]],
                ("name", "employee_name", "department", "designation", "company"))[0]


def as_user(s, account):
    """Đổi người dùng của phiên chuẩn bị: dữ liệu nền phải do đúng quyền tạo ra, như ngoài đời."""
    res = s.page.request.post(f"{BASE}/api/method/login", form={"usr": f"{account}@demo.example", "pwd": PASSWORD})
    s._csrf_token = ""
    who = api_get(s, "/api/method/frappe.auth.get_logged_user").json().get("message")
    if who != f"{account}@demo.example":
        raise AssertionError(f"không chuyển được phiên sang {account} (login {res.status}, đang là {who})")
    return account


def ins(s, doctype, values, submit=False):
    name = api(s, "frappe.client.insert", doc=json.dumps({**values, "doctype": doctype}, ensure_ascii=False))["name"]
    if submit:
        api(s, "frappe.client.submit", doc=json.dumps({"doctype": doctype, "name": name}))
    return name


def wflow(s, doctype, name, action_name):
    api(s, "frappe.model.workflow.apply_workflow", doc=json.dumps({"doctype": doctype, "name": name}), action=action_name)
    return doc_state(s, doctype, name)


def field(s, doctype, name, key):
    return api_get(s, f"/api/resource/{doctype}/{quote(name, safe='')}").json()["data"].get(key)


def set_field(s, doctype, name, key, value):
    api(s, "frappe.client.set_value", doctype=doctype, name=name, fieldname=key, value=value)


def balance_of(s, employee, leave_type, on_day=None, application=None):
    return api(s, "hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on",
               employee=employee, leave_type=leave_type, date=on_day or dt.date.today().isoformat(),
               consider_all_leaves_in_the_allocation_period=True, leave_application=application or "")


def wait_slips(s, name, docstatus, minimum, timeout=240, required=()):
    for _ in range(timeout // 5):
        found = find(s, "Salary Slip", [["payroll_entry", "=", name], ["docstatus", "=", docstatus]],
                     ("name", "employee"), limit=500)
        employees = {row["employee"] for row in found}
        if len(found) >= minimum and set(required) <= employees:
            return len(found)
        s.page.wait_for_timeout(5000)
    raise AssertionError(f"{name}: phiếu lương trạng thái {docstatus} được {len(found)}/{minimum}; "
                         f"thiếu nhân viên {sorted(set(required) - employees)}")


def ensure_payroll_period(s, company, month):
    """The Frappe HR app groups payslips by payroll period; without one the worker's app list is empty."""
    first, last = bounds(month)
    as_user(s, "phuong")
    existing = find(s, "Payroll Period", [["company", "=", company]], ("name", "start_date", "end_date"), limit=100)
    if any(row.get("start_date") and row.get("end_date") and row["start_date"] <= first
           and row["end_date"] >= last for row in existing):
        return
    year = first[:4]
    ins(s, "Payroll Period", {"company": company, "start_date": f"{year}-01-01", "end_date": f"{year}-12-31"})
    covered = find(s, "Payroll Period", [["company", "=", company], ["start_date", "<=", first],
                                       ["end_date", ">=", last]], limit=2)
    check(covered, f"thiếu Payroll Period bao phủ {month}")



def reserve_months(s, company, required):
    """Do not create a second paid slip: choose unused months with real effective assignments for both readers."""
    global M_PAID, M_UI, M_SIGN, M_NOW
    as_user(s, "phuong")
    assignments = find(s, "Salary Structure Assignment", [["company", "=", company], ["docstatus", "=", 1]],
                       ("employee", "from_date", "salary_structure"), limit=2000)
    joined = {person: field(s, "Employee", person, "date_of_joining") for person in required}
    occupied = {row["start_date"][:7] for row in find(s, PE,
        [["company", "=", company], ["docstatus", "<", 2]], ("start_date",), limit=500) if row.get("start_date")}
    slip_months = {row["start_date"][:7] for row in find(s, "Salary Slip",
        [["employee", "in", list(required)], ["docstatus", "<", 2]], ("start_date",), limit=1000) if row.get("start_date")}
    periods = find(s, KC, [["company", "=", company]], ("period_month",), limit=500)
    used_periods = {row["period_month"] for row in periods}
    eligible = []
    for back in range(1, 25):
        month = month_of(back)
        first, _ = bounds(month)
        if month in occupied or month in slip_months:
            continue
        if any(joined[person] and joined[person] > first for person in required):
            continue
        if all(any(row["employee"] == person and row["from_date"] <= first for row in assignments) for person in required):
            eligible.append(month)
    check(len(eligible) >= 3, f"cần ba tháng chưa có bảng/phiếu lương và SSA có hiệu lực, chỉ có {eligible}")
    M_PAID, M_SIGN, M_NOW = eligible[:3]
    M_UI = next((month_of(back) for back in range(1, 25)
                 if month_of(back) not in used_periods | occupied | slip_months | {M_PAID, M_SIGN, M_NOW}
                 and all(not joined[person] or joined[person] <= bounds(month_of(back))[0] for person in required)), None)
    check(M_UI, "không có tháng chưa lập kỳ công để HR tạo thật trên UI")
    REQ["role_months"] = {"paid": M_PAID, "sign": M_SIGN, "draft": M_NOW, "attendance": M_UI}
    as_user(s, "lan")

# =========================================================================== 0. Nền dữ liệu (setup — không phải nghiệm thu)

def prepare_state(browser):
    """Dựng nền để sáu video chỉ còn quay phần con người quyết định.

    Mỗi màn hình nghiệm thu phải có đúng một chứng từ chờ tới tay người của video đó: đơn nghỉ dừng ở các bước duyệt, đề nghị
    tăng ca chờ công nhân đồng ý, giải trình công chờ trưởng nhà máy, kỳ công của các tháng tính lương đã khoá, bảng lương
    đã tính / chờ ký / đã chi, tạm ứng chờ kế toán gắn chứng từ, khảo sát đang mở, và một ca đang mở cho lượt chấm công GPS.
    """
    s = Session(browser, "R0-PREPARE", "lan")
    notes = []
    stage = "mở phiên"
    try:
        login(s)
        stage = "HR tìm công ty, nhân viên và đối chứng phạm vi"
        company = find(s, "Company", limit=1)[0]["name"]
        binh, an = emp(s, "binh"), emp(s, "an")
        binh_id, an_id = binh["name"], an["name"]
        reserve_months(s, company, (binh_id, an_id))
        workers = find(s, "Employee", [["company", "=", company], ["status", "=", "Active"],
                                      ["leave_approver", "=", "hung@demo.example"], ["user_id", "like", "%@demo.example"]],
                       ("name", "user_id", "employee_name", "default_shift"))
        locked_for_correction = {row["period_month"] for row in find(s, KC,
            [["company", "=", company], ["scope", "=", "Nhà máy 1"], ["docstatus", "=", 1]], ("period_month",), limit=100)}

        def usable_absence_day(worker):
            """One weekday this worker was really absent in a month still open, with no correction filed for it yet.

            Every roles run files one correction, so the search cannot assume a particular worker still has a free day.
            """
            today = dt.date.today()
            days = find(s, "Attendance", [["employee", "=", worker["name"]], ["status", "=", "Absent"], ["docstatus", "=", 1],
                                         ["attendance_date", ">=", (today - dt.timedelta(days=370)).isoformat()],
                                         ["attendance_date", "<", today.isoformat()]], ("attendance_date",),
                        limit=100, order="attendance_date desc")
            taken = find(s, AR, [["employee", "=", worker["name"]], ["docstatus", "<", 2]], ("from_date", "to_date"), limit=200)
            open_months = locked_for_correction | {M_PAID, M_SIGN, M_UI}
            return next((d["attendance_date"] for d in days
                         if d["attendance_date"][:7] not in open_months
                         and dt.date.fromisoformat(d["attendance_date"]).weekday() < 5
                         and not any(c["from_date"] <= d["attendance_date"] <= c["to_date"] for c in taken)), None)

        mate = next((w for w in workers if w["name"] != binh_id and usable_absence_day(w)), None)
        check(mate, "thiếu công nhân Nhà máy 1 khác Bình còn ngày vắng trong kỳ chưa khoá để dựng giải trình chờ trưởng nhà máy")
        mate_account = mate["user_id"].split("@")[0]
        # Two names for the scope case: one worker of each factory, looked up by a company-wide account.
        for key, factory in (("nm1_worker", "Nhà máy 1"), ("nm2_worker", "Nhà máy 2")):
            rows = find(s, "Employee", [["department", "like", f"%{factory}%"]], ("employee_name",), limit=1, order="name asc")
            check(rows, f"thiếu nhân viên {factory} để đối chứng phạm vi")
            REQ[key] = rows[0]["employee_name"]

        # 1. Đơn nghỉ: chờ quản lý trực tiếp (R3), đã qua cấp 1 chờ nhân sự (R4), của An chờ trưởng phòng (R6)
        def new_leave(employee, account, start, end, reason):
            nonlocal stage
            stage = f"đơn nghỉ của {employee} do {account} tạo"
            as_user(s, account)
            name = ins(s, "Leave Application", {"employee": employee, "company": company, "leave_type": "Phép năm",
                                                "from_date": start, "to_date": end, "description": reason})
            state = wflow(s, "Leave Application", name, "Gửi duyệt")
            check(state == TO_MANAGER, f"{name}: cần chờ quản lý, nhận {state}")
            return name, state

        lay_team, _ = new_leave(mate["name"], mate_account, working_day(24), working_day(25), "Việc gia đình, đã báo tổ trưởng")
        lay_hr, _ = new_leave(binh_id, "binh", working_day(26), working_day(26), "Nghỉ phép năm, đã bố trí người thay ca")
        stage = "Hùng duyệt đơn Bình tới nhân sự"
        as_user(s, "hung")
        check(wflow(s, "Leave Application", lay_hr, "Duyệt") == TO_HR, f"{lay_hr} chưa chờ nhân sự")
        lay_an, _ = new_leave(an["name"], "an", working_day(20), working_day(21), "Gặp khách hàng cuối quý, đã bàn giao")
        REQ["leave_team"], REQ["leave_hr"], REQ["leave_an"] = lay_team, lay_hr, lay_an
        notes.append(f"đơn nghỉ: {lay_team} chờ quản lý, {lay_hr} chờ nhân sự, {lay_an} của An chờ trưởng phòng")

        # 2. Tăng ca: một đề nghị chờ Bình đồng ý (R1), một đề nghị công nhân khác đã đồng ý chờ giám đốc duyệt (R5)
        def new_overtime(employee, day, start, end, reason):
            nonlocal stage
            stage = f"Hùng đề nghị tăng ca cho {employee} ngày {day}"
            as_user(s, "hung")
            name = ins(s, OT, {"employee": employee, "company": company, "ot_date": day, "from_time": start,
                               "to_time": end, "reason": reason})
            state = wflow(s, OT, name, "Đề nghị")
            check(state == TO_WORKER, f"{name}: cần {TO_WORKER}, nhận {state}")
            return name, state

        ot_consent, _ = new_overtime(binh_id, working_day(22), "18:30:00", "21:00:00", "Kiểm kê kho cuối tháng, cần 2,5 giờ")
        ot_director, _ = new_overtime(mate["name"], working_day(23), "18:30:00", "21:00:00", "Chuyến hàng gấp, cần tăng ca")
        stage = f"{mate_account} đồng ý tăng ca {ot_director}"
        as_user(s, mate_account)
        check(wflow(s, OT, ot_director, "Đồng ý") == TO_DIRECTOR, f"{ot_director} chưa chờ giám đốc")
        REQ["ot_consent"], REQ["ot_director"] = ot_consent, ot_director
        notes.append(f"tăng ca: {ot_consent} chờ công nhân đồng ý, {ot_director} chờ giám đốc duyệt")

        # 3. Giải trình chấm công chờ trưởng nhà máy (R3): ngày đã qua, không rơi vào kỳ đã khoá
        stage = f"{mate_account} gửi giải trình chấm công"
        day = usable_absence_day(mate)
        check(day, f"{mate['name']}: thiếu ngày vắng thật trong kỳ chưa khoá để giải trình")
        as_user(s, mate_account)
        arq = ins(s, AR, {"employee": mate["name"], "company": company, "from_date": day, "to_date": day, "reason": "On Duty",
                          "tlc_correction_type": "Quên chấm ra", "explanation": "Hết ca quên bấm Ra ca, có tổ trưởng xác nhận"})
        check(wflow(s, AR, arq, "Gửi duyệt") == TO_MANAGER, f"{arq} chưa chờ quản lý")
        REQ["arq"] = arq
        notes.append(f"giải trình {arq} ({day}) chờ trưởng nhà máy")

        # 4. Kỳ công đã khoá của hai tháng tính lương (nền). Kỳ công quay video chỉ lập sẵn của Nhà máy 1
        def lock_month(month):
            nonlocal stage
            locked = []
            for scope in SCOPES:
                stage = f"khoá kỳ công {month} · {scope}"
                as_user(s, "lan")
                existing = find(s, KC, [["company", "=", company], ["scope", "=", scope], ["period_month", "=", month]],
                                ("name", "workflow_state", "docstatus"), limit=2)
                check(len(existing) <= 1, f"{month} · {scope}: trùng kỳ công {existing}")
                name = existing[0]["name"] if existing else ins(s, KC, {"company": company, "scope": scope, "period_month": month})
                state = doc_state(s, KC, name)
                if state in (DRAFT, None, ""):
                    state = wflow(s, KC, name, "Gửi đối soát" if scope == "Hội sở" else "Gửi xác nhận")
                if state == P_TO_HEAD:
                    check(scope in HEADS, f"{name}: Hội sở không có trưởng nhà máy")
                    as_user(s, HEADS[scope])
                    state = wflow(s, KC, name, "Xác nhận")
                if state == P_TO_HR:
                    as_user(s, "lan")
                    state = wflow(s, KC, name, "Đối soát xong")
                if state == P_TO_CEO:
                    as_user(s, "thanh")
                    state = wflow(s, KC, name, "Ký và khoá")
                check(state == P_LOCKED and field(s, KC, name, "docstatus") == 1,
                      f"{name}: kỳ công chưa khoá/ghi sổ ({state})")
                locked.append(name)
            as_user(s, "lan")
            verified = find(s, KC, [["company", "=", company], ["period_month", "=", month],
                                    ["workflow_state", "=", P_LOCKED], ["docstatus", "=", 1]], ("scope",), limit=100)
            check(set(SCOPES) <= {row["scope"] for row in verified}, f"{month}: chưa khoá đủ bốn phạm vi")
            return locked

        locked_paid, locked_sign = lock_month(M_PAID), lock_month(M_SIGN)

        stage = f"kỳ công {M_UI} Nhà máy 1 chờ Hùng xác nhận"
        as_user(s, "lan")
        existing = find(s, KC, [["company", "=", company], ["scope", "=", "Nhà máy 1"], ["period_month", "=", M_UI]],
                        ("name",), limit=2)
        check(len(existing) <= 1, f"{M_UI}: trùng kỳ công Nhà máy 1")
        period_nm1 = existing[0]["name"] if existing else ins(s, KC, {"company": company, "scope": "Nhà máy 1", "period_month": M_UI})
        if doc_state(s, KC, period_nm1) in (DRAFT, None, ""):
            wflow(s, KC, period_nm1, "Gửi xác nhận")
        check(doc_state(s, KC, period_nm1) == P_TO_HEAD, f"{period_nm1} không còn chờ Hùng xác nhận")
        occupied = find(s, KC, [["company", "=", company], ["period_month", "=", M_UI],
                               ["scope", "in", ["Nhà máy 2", "Nhà máy 3", "Hội sở"]]], ("name", "scope"), limit=100)
        check(not occupied, f"các kỳ công phải do HR tạo trên UI đã tồn tại: {occupied}")
        REQ["period_nm1"] = period_nm1
        notes.append(f"kỳ công đã khoá: {M_PAID} {len(locked_paid)} kỳ, {M_SIGN} {len(locked_sign)} kỳ; "
                     f"{M_UI} Nhà máy 1 = {period_nm1} chờ trưởng nhà máy")

        # 5. Bảng lương: một tháng đã chi (phiếu lương đọc trên app), một tháng chờ giám đốc ký, một nháp để lấy nhân viên
        stage = "Phương tìm nhân viên và tài khoản ngân hàng cho bảng lương"
        as_user(s, "phuong")
        staff = find(s, "Employee", [["company", "=", company], ["status", "=", "Active"]],
                     ("name", "employee_name", "department", "designation", "date_of_joining", "relieving_date"), limit=500)
        assignments = find(s, "Salary Structure Assignment", [["company", "=", company], ["docstatus", "=", 1]],
                           ("employee", "from_date", "salary_structure"), limit=2000, order="from_date asc")
        structures = {row["name"] for row in find(s, "Salary Structure",
                      [["company", "=", company], ["docstatus", "=", 1], ["is_active", "=", "Yes"],
                       ["payroll_frequency", "=", "Monthly"], ["currency", "=", "VND"]], limit=500)}
        bank = find(s, "Account", [["company", "=", company], ["account_number", "=", "1121"]], ("name",), limit=1)[0]["name"]
        # the payable account is a company default, which the desk fills in and an API insert does not
        payable = (find(s, "Company", [["name", "=", company]], ("default_payroll_payable_account",), limit=1)
                   or [{}])[0].get("default_payroll_payable_account")

        def payroll_entry(month, fetch=True):
            nonlocal stage
            stage = f"Phương chuẩn bị bảng lương {month}"
            first, last = bounds(month)
            as_user(s, "phuong")
            selected = []
            if fetch:
                for person in staff:
                    if person.get("date_of_joining") and person["date_of_joining"] > last:
                        continue
                    if person.get("relieving_date") and person["relieving_date"] < first:
                        continue
                    actual_start = max(first, person.get("date_of_joining") or first)
                    dated = [row for row in assignments if row["employee"] == person["name"] and row["from_date"] <= last]
                    active = [row for row in dated if row["from_date"] <= actual_start]
                    if not active:
                        continue
                    relevant = [active[-1]] + [row for row in dated if actual_start < row["from_date"] <= last]
                    if len({row["salary_structure"] for row in relevant}) != 1 or active[-1]["salary_structure"] not in structures:
                        continue
                    selected.append(person)
                missing = {binh_id, an_id} - {person["name"] for person in selected}
                check(not missing, f"{month}: thiếu phân bổ/cấu trúc lương tháng có hiệu lực cho {sorted(missing)}")
            rows = [{"employee": p["name"], "employee_name": p["employee_name"], "department": p["department"],
                     "designation": p.get("designation") or ""} for p in selected]
            name = ins(s, PE, {"company": company, "posting_date": last, "start_date": first, "end_date": last,
                               "payroll_frequency": "Monthly", "payment_account": bank, "currency": "VND",
                               "exchange_rate": 1, "payroll_payable_account": payable,
                               "number_of_employees": len(rows), "employees": rows})
            return name

        def compute(name):
            nonlocal stage
            stage = f"Phương tính lương {name}"
            as_user(s, "phuong")
            wflow(s, PE, name, "Tính lương")
            count = int(field(s, PE, name, "number_of_employees"))
            wait_slips(s, name, 0, count, required=(binh_id, an_id))
            stage = f"Phương rà soát sai lệch trước gửi ký {name}"
            method = "tlc_hr.interface.payroll_compliance."
            issues = api(s, method + "inspect_reviews", name=name)
            for issue in issues:
                check(issue["issue"] == "Variance",
                      f"{name}: cần hoàn thiện quyết định lương thực trước ký: {issue['employee']} · {issue['details']}")
                review = api(s, method + "new_review", name=name, employee=issue["employee"], issue=issue["issue"])
                evidence = api(s, "frappe.client.attach_file", filename=f"review-{name}-{issue['employee']}.txt",
                               filedata=base64.b64encode((f"Đối chiếu fixture UAT {name}\n{issue['details']}\n"
                                         "Kỳ công đã khoá đủ phạm vi; biến động được chuyên viên lương rà soát."
                                         ).encode()).decode(), doctype=PE, docname=name, is_private=1)
                ins(s, "TLC Payroll Review", {"payroll_entry": name, "employee": issue["employee"], "issue": issue["issue"],
                    "review_fingerprint": review["review_fingerprint"], "reason": review["reason"],
                    "evidence": evidence["file_url"]}, submit=True)
            stage = f"Phương gửi ký bảng lương {name}"
            state = wflow(s, PE, name, "Gửi ký")
            check(state == P_TO_CEO, f"{name}: chưa chờ giám đốc ký ({state})")
            return state

        pe_paid = payroll_entry(M_PAID)
        compute(pe_paid)
        stage = f"CEO ký bảng lương đã chi {pe_paid}"
        as_user(s, "thanh")
        wflow(s, PE, pe_paid, "Ký duyệt")
        wait_slips(s, pe_paid, 1, int(field(s, PE, pe_paid, "number_of_employees")), required=(binh_id, an_id))
        stage = f"kế toán xác nhận đã chi bảng lương {pe_paid}"
        as_user(s, "chi")
        reference = f"VCB-UNC-{M_PAID.replace('-', '')}-PREPARE"
        set_field(s, PE, pe_paid, "tlc_bank_reference", reference)
        set_field(s, PE, pe_paid, "tlc_paid_on", dt.date.today().isoformat())
        proof = api(s, "frappe.client.attach_file", filename=f"UNC-PAYROLL-{pe_paid}.txt",
                    filedata=base64.b64encode(f"UNC chi lương thực tế {pe_paid}".encode()).decode(),
                    doctype=PE, docname=pe_paid, is_private=1)
        set_field(s, PE, pe_paid, "tlc_bank_proof", proof["file_url"])
        paid_state = wflow(s, PE, pe_paid, "Xác nhận đã chi")
        check(paid_state == PAID, f"{pe_paid}: chưa đã chi ({paid_state})")
        REQ["pe_paid"] = pe_paid

        pe_sign = payroll_entry(M_SIGN)
        sign_state = compute(pe_sign)
        REQ["pe_sign"] = pe_sign

        pe_draft = payroll_entry(M_NOW, fetch=False)
        REQ["pe_draft"] = pe_draft
        as_user(s, "phuong")
        stage = f"Payroll Period bao phủ {M_PAID}"
        ensure_payroll_period(s, company, M_PAID)
        notes.append(f"bảng lương: {pe_paid} {paid_state}, {pe_sign} {sign_state}, nháp {pe_draft} chờ bấm Lấy nhân viên")

        # 6. Tạm ứng của An tới bước chờ kế toán chi, kèm chứng từ ngân hàng đã ghi sổ (R2 sẽ tạo đơn khác trên màn hình)
        stage = "An tạo và gửi tạm ứng nền"
        as_user(s, "an")
        advance = ins(s, EA, {"employee": an["name"], "company": company, "currency": "VND",
                              "posting_date": dt.date.today().isoformat(), "purpose": "Tạm ứng chi phí công tác quý",
                              "advance_amount": 4000000, "tlc_needed_on": working_day(1),
                              "tlc_settlement_due": working_day(20)})
        wflow(s, EA, advance, "Gửi duyệt")
        stage = f"Quang duyệt tạm ứng {advance}"
        as_user(s, "quang")
        wflow(s, EA, advance, "Duyệt")
        stage = f"CEO duyệt tạm ứng {advance}"
        as_user(s, "thanh")
        wflow(s, EA, advance, "Duyệt")
        stage = f"kế toán kiểm tra hồ sơ tạm ứng {advance}"
        as_user(s, "chi")
        adv_state = wflow(s, EA, advance, "Hồ sơ hợp lệ")
        check(adv_state == "Chờ chi", f"{advance}: chưa chờ chi ({adv_state})")
        stage = f"kế toán lập chứng từ Pay và đính kèm bằng chứng trước ghi sổ {advance}"
        adv_account = find(s, "Account", [["company", "=", company], ["account_number", "=", "141"]], ("name",), limit=1)[0]["name"]
        proof = ins(s, "Payment Entry", {"payment_type": "Pay", "payment_order_type": "Payment Order", "party_type": "Employee",
                                         "party": an["name"], "company": company, "paid_from": bank, "paid_to": adv_account,
                                         "paid_amount": 4000000, "received_amount": 4000000,
                                         "reference_no": f"UNC-TU-{advance}", "reference_date": dt.date.today().isoformat(),
                                         "references": [{"reference_doctype": EA, "reference_name": advance, "total_amount": 4000000,
                                                         "outstanding_amount": 4000000, "allocated_amount": 4000000}]})
        uploaded = api(s, "frappe.client.attach_file", filename=f"UNC-{advance}.txt",
                       filedata=base64.b64encode("Uỷ nhiệm chi demo".encode()).decode(),
                       doctype="Payment Entry", docname=proof, is_private=1)
        set_field(s, "Payment Entry", proof, "tlc_bank_proof", uploaded["file_url"])
        full = api(s, "frappe.client.get", doctype="Payment Entry", name=proof)
        api(s, "frappe.client.submit", doc=json.dumps(full))
        check(field(s, "Payment Entry", proof, "docstatus") == 1, f"{proof}: chứng từ ngân hàng chưa ghi sổ")
        REQ["advance"], REQ["advance_pe"] = advance, proof
        notes.append(f"tạm ứng {advance} ở {adv_state}, chứng từ {proof} chờ kế toán gắn vào đơn")

        # 7. Khảo sát ẩn danh đang mở (R1) — chiến dịch mới để Bình chắc chắn chưa trả lời phiên bản này
        stage = "HR mở chiến dịch khảo sát ẩn danh mới"
        as_user(s, "lan")
        campaign = ins(s, "TLC Survey Campaign", {"title": f"Khảo sát UAT theo vai trò {dt.datetime.now():%H%M%S}",
                                                  "status": "Draft", "opens_on": dt.date.today().isoformat(),
                                                  "closes_on": working_day(30), "minimum_results": 5,
                                                  "questions": [{"question_key": "bua_an", "label": "Chất lượng bữa ăn ca",
                                                                "options": "Tốt\nBình thường\nKém"},
                                                               {"question_key": "ho_tro", "label": "Hỗ trợ từ bộ phận quản lý",
                                                                "options": "Rất tốt\nTốt\nChưa tốt"}]})
        set_field(s, "TLC Survey Campaign", campaign, "status", "Open")
        check(field(s, "TLC Survey Campaign", campaign, "status") == "Open", f"{campaign}: khảo sát chưa mở")
        REQ["campaign"] = campaign

        # 8. Ca đang mở cho lượt chấm công GPS của Bình (R1): Bình làm ca đêm nên ban ngày phải được phân ca trực trong ngày
        stage = "HR chuẩn bị phân ca hiện hành và địa điểm GPS cho Bình"
        as_user(s, "lan")
        today = dt.date.today().isoformat()
        need = shift_open_now()
        check(need, "không có ca đang mở để quay lượt chấm công GPS; cần chạy trong giờ ca thực")
        binh_shift = find(s, "Shift Assignment", [["employee", "=", binh_id], ["docstatus", "=", 1],
                          ["status", "=", "Active"], ["start_date", "<=", today]],
                          ("name", "shift_type", "shift_location", "start_date", "end_date"), limit=100, order="start_date desc")
        effective = [row for row in binh_shift if not row.get("end_date") or row["end_date"] >= today]
        check(effective, "Bình thiếu Shift Assignment có hiệu lực hôm nay")
        matching = next((row for row in effective if row["shift_type"] == need and row.get("shift_location")), None)
        if not matching:
            location = next((row["shift_location"] for row in effective if row.get("shift_location")), None)
            check(location, "phân ca của Bình thiếu Shift Location cho chấm công GPS")
            assignment = ins(s, "Shift Assignment", {"employee": binh_id, "company": company, "shift_type": need,
                                                     "shift_location": location, "start_date": today,
                                                     "end_date": today, "status": "Active"}, submit=True)
            check(field(s, "Shift Assignment", assignment, "docstatus") == 1, f"{assignment}: phân ca chưa ghi sổ")
            notes.append(f"phân ca {need} hôm nay cho Bình ({assignment}) để chấm công GPS trong ca")
        else:
            notes.append(f"Bình có phân ca {need} đang mở: {matching['name']}")
    except Exception as exc:
        message = f"CHUẨN BỊ HƯ ({stage}): {type(exc).__name__}: {exc}"
        notes.append(message)
        raise AssertionError(message) from exc
    finally:
        REQ["prepare_notes"] = notes
        print("prepare:", " | ".join(notes), flush=True)
        s.close()


# ==================================================================================== 1. Công nhân: Trần Văn Bình

def worker_day(browser):
    """Bình (Nhà máy 1) làm việc trên app Frappe HR, điện thoại ở cổng nhà máy: chấm công, xin nghỉ, trả lời tăng ca,
    đọc phiếu lương, trả lời khảo sát ẩn danh."""
    s = Session(browser, "R1-CONGNHAN", "binh", geolocation=SITE_OF["Nhà máy 1"])
    try:
        login(s)
        with case(s, "RV-11", "Mở app và đọc số dư phép của mình",
                  "App > Trang chủ > mục Nghỉ phép > đọc thẻ số dư Phép năm",
                  "binh@demo.example", "Lời chào đúng người và số dư Phép năm còn lại hiện ngay trên màn hình Nghỉ phép") as r:
            s.step("Bình mở app Frappe HR")
            s.page.goto(f"{BASE}/hrms/home")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            text = body(s)
            check("Bình" in text, text[:180])
            s.step("Bình mở mục Nghỉ phép dưới thanh điều hướng của app")
            leaves_tab = s.page.locator("ion-tab-button[href*='/dashboard/leaves'], a[href*='/dashboard/leaves']").last
            if leaves_tab.count():
                leaves_tab.click()
                s.page.wait_for_url(re.compile(r".*/hrms/dashboard/leaves"), timeout=25000)
            else:
                s.page.goto(f"{BASE}/hrms/dashboard/leaves")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            text = body(s)
            balance = float(balance_of(s, emp(s, "binh")["name"], "Phép năm"))
            idx = text.find("Phép năm")
            check(idx >= 0, f"không thấy thẻ Phép năm trên màn hình: {text[:280]}")
            found = re.search(r"(\d+)\s*/\s*(\d+)", text[max(0, idx - 80): idx + 20])
            check(found and int(found.group(1)) == int(balance),
                  f"số dư trên màn hình {found.group(0) if found else '(không thấy)'}, cần {balance:g}: {text[:280]}")
            r["actual"] = f"App báo Bình còn {found.group(1)}/{found.group(2)} ngày Phép năm trên màn hình Nghỉ phép"

        with case(s, "RV-12", "Chấm công GPS khi vào ca", "App > Vào ca > Xác nhận vị trí tại cổng Nhà máy 1",
                  "vị trí trong bán kính Nhà máy 1", "có lượt chấm công mới gắn ca và vĩ độ, app báo vừa ghi nhận") as r:
            before = len(find(s, "Employee Checkin", [["employee", "=", emp(s, "binh")["name"]]], limit=500))
            s.step("Bình bấm Vào ca ngay tại cổng nhà máy")
            s.page.goto(f"{BASE}/hrms/home")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2000)
            s.page.locator("button:visible", has_text=re.compile("Vào ca|Ra ca")).first.click()
            s.page.wait_for_timeout(2500)
            s.step("Bình xác nhận vị trí để ghi nhận lượt vào ca")
            s.page.locator("button:visible", has_text=re.compile("Xác nhận|Confirm")).last.click()
            s.page.wait_for_timeout(4000)
            after = len(find(s, "Employee Checkin", [["employee", "=", emp(s, "binh")["name"]]], limit=500))
            newest = find(s, "Employee Checkin", [["employee", "=", emp(s, "binh")["name"]]],
                          ("log_type", "time", "shift", "latitude"), limit=1, order="creation desc")
            check(after == before + 1 and newest and newest[0]["shift"], f"{before} -> {after}: {body(s)[-280:]}")
            r["actual"] = f"{newest[0]['log_type']} lúc {newest[0]['time']}, ca {newest[0]['shift']}, vĩ độ {newest[0]['latitude']:.5f}"

        with case(s, "RV-13", "Xin nghỉ một ngày và thấy đơn của mình trong danh sách",
                  "App > Xin nghỉ phép > điền > Lưu > Gửi duyệt > Đơn của tôi > mở lại đơn", "nghỉ 1 ngày có lý do",
                  "đơn ở bước chờ quản lý duyệt, thấy trong danh sách và mở lại đúng đơn vừa gửi") as r:
            s.step("Bình điền đơn xin nghỉ ngay trên app")
            day = working_day(3)
            name = hrms_request_leave(s, day, day, "Việc gia đình đã báo trước tổ trưởng")
            s.step("Bình mở danh sách Đơn của tôi để xem đơn vừa gửi")
            s.page.goto(f"{BASE}/hrms/leave-applications")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            rows = s.page.locator(f"a[href*='/hrms/leave-applications/{quote(name, safe='')}']")
            check(rows.count(), f"{name} không có trong danh sách: {body(s)[:260]}")
            rows.first.click()
            s.page.wait_for_url(re.compile(re.escape(name)), timeout=25000)
            s.page.wait_for_timeout(2500)
            state = doc_state(s, "Leave Application", name)
            check(state == TO_MANAGER and "Phép năm" in body(s), f"{name} ở {state}: {body(s)[:240]}")
            r["actual"] = f"{name}: {state}; thấy trong Đơn của tôi và mở lại đúng đơn vừa gửi"

        with case(s, "RV-14", "Đọc đề nghị tăng ca và bấm Đồng ý",
                  "Desk > TLC Overtime Request > mở phiếu của mình > Hành động > Đồng ý",
                  "đề nghị tăng ca đang chờ người lao động", "ghi nhận đồng ý, đơn chuyển sang bước giám đốc duyệt") as r:
            s.step("Bình mở đề nghị tăng ca của mình để đọc trước khi quyết định")
            waiting = find(s, OT, [["name", "=", REQ["ot_consent"]], ["employee", "=", emp(s, "binh")["name"]],
                                  ["workflow_state", "=", TO_WORKER]], ("name", "ot_date", "hours"), limit=1)
            check(waiting, "không còn đề nghị tăng ca chờ công nhân đồng ý")
            open_form(s, OT, waiting[0]["name"])
            text = body(s)
            check("Bình" in text and TO_WORKER in text, text[:260])
            s.step("Bình bấm Đồng ý")
            action(s, "Đồng ý")
            after = doc_state(s, OT, waiting[0]["name"])
            consent = field(s, OT, waiting[0]["name"], "consent_at")
            check(after == TO_DIRECTOR and consent, f"vẫn {after}")
            r["actual"] = f"{waiting[0]['name']}: {waiting[0]['hours']:g} giờ ngày {vn(waiting[0]['ot_date'])}, đồng ý lúc {consent} -> {after}"

        with case(s, "RV-15", "Mở phiếu lương và đọc tiền thực nhận",
                  "App > Phiếu lương > mở phiếu > Thu nhập & Khấu trừ > Thông tin thực nhận",
                  f"kỳ lương {vn(bounds(M_PAID)[0])}", "thấy số tiền thực nhận đúng bằng dữ liệu lương và các cấu phần") as r:
            s.step("Bình mở danh sách phiếu lương của mình")
            slips = find(s, "Salary Slip", [["employee", "=", emp(s, "binh")["name"]], ["docstatus", "=", 1],
                                           ["payroll_entry", "=", REQ["pe_paid"]]], ("name", "net_pay", "start_date"), limit=2)
            check(slips, "công nhân chưa có phiếu lương đã ghi sổ")
            s.page.goto(f"{BASE}/hrms/dashboard/salary-slips")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(3000)
            amount = f"{int(round(slips[0]['net_pay'])):,}".replace(",", ".")
            rows = s.page.locator("div.cursor-pointer").filter(has_text=amount)
            check(rows.count(), f"phiếu {slips[0]['name']} ({amount}) không thấy trong danh sách: {body(s)[:220]}")
            rows.first.click()
            s.page.wait_for_url(re.compile(r".*/salary-slips/"), timeout=25000)
            s.page.wait_for_timeout(3000)
            s.step("Bình mở phần thu nhập, khấu trừ rồi đọc tiền thực nhận")
            s.page.get_by_text(re.compile(r"^(Earnings & Deductions|Thu nhập & Khấu trừ)$")).click()
            s.page.wait_for_timeout(2000)
            text = body(s)
            check(any(c in text for c in ("Phụ cấp ăn trưa", "BHXH", "Thu nhập")), text[:260])
            s.page.get_by_text(re.compile(r"^(Net Pay Info|Thông tin thực lĩnh|Thông tin thực nhận)$")).click()
            s.page.wait_for_timeout(2000)
            got = money(body_with_inputs(s), slips[0]["net_pay"])
            check(got, f"thực nhận {slips[0]['net_pay']:,.0f} không hiện trên màn hình: {body(s)[:300]}")
            r["actual"] = f"{slips[0]['name']} ({vn(slips[0]['start_date'])}): thực nhận {got} đ kèm cấu phần trên app"

        with case(s, "RV-16", "Trả lời khảo sát ẩn danh",
                  "Desk > TLC Survey Campaign > Trả lời ẩn danh > chọn phương án > Gửi phản hồi",
                  "một chiến dịch đang mở", "gửi được phiếu mà server không lưu phiếu cá nhân") as r:
            s.step("Bình mở phiếu khảo sát ẩn danh của kỳ này")
            campaign = REQ["campaign"]
            check(campaign, "không có chiến dịch khảo sát đang mở")
            open_form(s, "TLC Survey Campaign", campaign)
            s.page.get_by_role("button", name=re.compile(r"^(Trả lời ẩn danh|Answer Anonymously)$")).click()
            dialog = s.page.locator(".modal-dialog")
            dialog.wait_for(state="visible")
            s.page.wait_for_timeout(1200)
            s.step("Bình chọn phương án cho từng câu rồi gửi")
            answers = []
            s.page.on("response", lambda res: answers.append(res) if "survey.submit_anonymous" in res.url else None)
            selects = dialog.locator("select")
            check(selects.count() >= 2, f"hộp thoại không có câu hỏi nào: {body(s)[:200]}")
            for i in range(selects.count()):
                selects.nth(i).select_option(index=1)
            s.page.wait_for_timeout(600)
            dialog.get_by_role("button", name=re.compile(r"^(Gửi phản hồi|Submit)$")).click()
            s.page.wait_for_timeout(3000)
            sent = [a for a in answers if a.status == 200 and (a.json().get("message") or {}).get("submitted")]
            check(sent, f"server không xác nhận đã gửi: {[a.status for a in answers]}")
            r["actual"] = f"Đã gửi phiếu ẩn danh cho {campaign}; server chỉ cộng vào tổng hợp, không lưu phiếu danh tính"
    finally:
        s.close()


# ---------------------------------------------------------------------- 2. Nhân viên văn phòng: Nguyễn Hoài An

def office_day(browser):
    """An (Kinh doanh hội sở) dùng cả app lẫn desk: xin nghỉ, đăng ký công tác, xin tạm ứng, đặt phòng họp, đọc phiếu lương."""
    s = Session(browser, "R2-VANPHONG", "an")
    try:
        login(s)
        with case(s, "RV-21", "Xin nghỉ hai ngày trên app", "App > Xin nghỉ phép > điền > Lưu > Gửi duyệt",
                  "2 ngày làm việc", "đơn vào bước chờ quản lý trực tiếp là Trần Minh Quang") as r:
            s.step("An gửi đơn nghỉ hai ngày từ app")
            start, end = working_day(4), working_day(5)
            name = hrms_request_leave(s, start, end, "Gặp khách hàng cuối kỳ, đã bàn giao công việc")
            state = doc_state(s, "Leave Application", name)
            approver = field(s, "Leave Application", name, "leave_approver")
            check(state == TO_MANAGER and approver == "quang@demo.example", f"{name} ở {state}, duyệt bởi {approver}")
            r["actual"] = f"{name}: {state}; người duyệt {approver}"

        with case(s, "RV-22", "Đăng ký công tác trên desk",
                  "Desk > Travel Request > Mới > điền từng ô > Lưu > Hành động > Gửi duyệt", "Công tác Đà Nẵng",
                  "đơn nháp lưu được rồi chuyển sang bước quản lý trực tiếp") as r:
            s.step("An mở màn hình công tác và điền từng ô")
            start, end = working_day(10), working_day(12)
            desk(s, "Travel Request")
            wait_frm(s, "Travel Request")
            pick(s, "employee", emp(s, "an")["name"])
            choose(s, "travel_type", "Domestic")
            pick(s, "purpose_of_travel", "TLC Công tác")
            write(s, "tlc_destination", "Chi nhánh Đà Nẵng")
            if not s.page.locator("textarea[data-fieldname='description']:visible, input[data-fieldname='description']:visible").count():
                for header in s.page.locator(".section-head:visible").filter(has_text=re.compile("Mô tả|Description")).all():
                    header.click()
                    s.page.wait_for_timeout(800)
                    if s.page.locator("textarea[data-fieldname='description']:visible").count():
                        break
            write(s, "description", "Bàn giao hồ sơ thầu và ký phụ lục hợp đồng")
            check(write(s, "tlc_from_date", start) == start, f"ngày đi không nhận giá trị {start}: {form_value(s, 'tlc_from_date')}")
            write(s, "tlc_to_date", end)
            save(s)
            name = created(s)
            check("new-travel-request" not in name, f"chưa lưu được đơn: {name} · {body(s)[:200]}")
            s.step("An gửi đơn lên quản lý trực tiếp")
            action(s, "Gửi duyệt")
            state = doc_state(s, "Travel Request", name)
            manager = field(s, "Travel Request", name, "tlc_manager_user")
            check(state == "Chờ quản lý duyệt", f"{name} ở {state}: {body(s)[:220]}")
            r["actual"] = f"{name}: {state}, người duyệt {manager}, đi {vn(start)} về {vn(end)}"

        with case(s, "RV-23", "Xin tạm ứng 5 triệu cho chuyến đi",
                  "Desk > Employee Advance > Mới > điền > Lưu > Hành động > Gửi duyệt", "5.000.000 đ",
                  "đơn tạm ứng vào bước chờ quản lý, số tiền lưu đúng trên form") as r:
            s.step("An lập phiếu tạm ứng 5.000.000 đ")
            desk(s, "Employee Advance")
            wait_frm(s, "Employee Advance")
            pick(s, "employee", emp(s, "an")["name"])
            write(s, "purpose", "Tạm ứng chi phí công tác Đà Nẵng")
            check(write(s, "advance_amount", "5000000") in ("5000000", "5000000.0", 5000000), form_value(s, "advance_amount"))
            write(s, "tlc_needed_on", working_day(9))
            write(s, "tlc_settlement_due", working_day(14))
            save(s)
            adv = created(s)
            check("new-employee-advance" not in adv, f"chưa lưu được tạm ứng: {adv}")
            s.step("An gửi đơn tạm ứng để quản lý duyệt")
            action(s, "Gửi duyệt")
            state = doc_state(s, "Employee Advance", adv)
            amount = field(s, "Employee Advance", adv, "advance_amount")
            check(state not in (DRAFT, None) and amount == 5000000, f"{adv} ở {state}, số tiền {amount}")
            r["actual"] = f"{adv}: {state}, {amount:,.0f} đ"

        with case(s, "RV-24", "Đặt phòng họp và bị chặn khi trùng giờ",
                  "Desk > TLC Room Reservation > Mới > chọn phòng và giờ > Lưu; đặt trùng khung giờ lần hai",
                  "phòng Hội sở 1", "phiếu đầu đặt được; phiếu trùng giờ bị chặn ngay trên màn hình") as r:
            s.step("An đặt phòng họp cho buổi tổng kết quý")
            day = working_day(6)
            desk(s, "TLC Room Reservation")
            wait_frm(s, "TLC Room Reservation")
            pick(s, "employee", emp(s, "an")["name"])
            pick(s, "room", "Phòng họp Hội sở 1 (Lớn)")
            write(s, "subject", "Tổng kết kinh doanh quý")
            check(write_time(s, "starts_at", f"{day} 09:00:00").startswith(day), f"giờ bắt đầu không nhận: {form_value(s, 'starts_at')}")
            write_time(s, "ends_at", f"{day} 10:30:00")
            save(s)
            first = created(s)
            status = field(s, "TLC Room Reservation", first, "status")
            check(status == "Booked", f"{first} ở {status}")
            s.step("An thử đặt trùng đúng khung giờ đó để xem hệ thống chặn")
            desk(s, "TLC Room Reservation")
            wait_frm(s, "TLC Room Reservation")
            pick(s, "employee", emp(s, "an")["name"])
            pick(s, "room", "Phòng họp Hội sở 1 (Lớn)")
            write(s, "subject", "Họp đột xuất trùng giờ")
            write_time(s, "starts_at", f"{day} 10:00:00")
            write_time(s, "ends_at", f"{day} 11:00:00")
            save(s)
            text = body(s)
            check("đã được đặt" in text or "room_conflict" in text, text[:260])
            r["actual"] = f"Đặt được {first}; phiếu trùng giờ bị chặn: {text[:130]}"

        with case(s, "RV-25", "Đọc phiếu lương và bảng công của mình",
                  "App > Phiếu lương > mở phiếu > thực nhận; App > bảng chấm công của tôi", f"kỳ {M_PAID}",
                  "đọc được tiền thực nhận và mở được màn hình chấm công của chính mình") as r:
            s.step("An mở phiếu lương tháng trước")
            slips = find(s, "Salary Slip", [["employee", "=", emp(s, "an")["name"]], ["docstatus", "=", 1],
                                           ["payroll_entry", "=", REQ["pe_paid"]]], ("name", "net_pay", "start_date"), limit=2)
            check(slips, "An chưa có phiếu lương")
            s.page.goto(f"{BASE}/hrms/dashboard/salary-slips")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(3000)
            amount = f"{int(round(slips[0]['net_pay'])):,}".replace(",", ".")
            rows = s.page.locator("div.cursor-pointer").filter(has_text=amount)
            check(rows.count(), f"không thấy phiếu của An ({amount}): {body(s)[:200]}")
            rows.first.click()
            s.page.wait_for_url(re.compile(r".*/salary-slips/"), timeout=25000)
            s.page.wait_for_timeout(3000)
            s.page.get_by_text(re.compile(r"^(Net Pay Info|Thông tin thực lĩnh|Thông tin thực nhận)$")).click()
            s.page.wait_for_timeout(2000)
            got = money(body_with_inputs(s), slips[0]["net_pay"])
            check(got, f"thực nhận không hiện trên màn hình: {body(s)[:260]}")
            s.step("An xem tiếp bảng công của mình trên app")
            s.page.goto(f"{BASE}/hrms/attendance-requests")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            check("An" in body(s) or "chấm công" in body(s).lower(), body(s)[:200])
            r["actual"] = f"Phiếu {slips[0]['name']} ({vn(slips[0]['start_date'])}) thực nhận {got} đ; màn hình công mở được"
    finally:
        s.close()


# --------------------------------------------------------------------------- 3. Ba người phòng nhân sự (lan/hoa/phuong)

def hr_day(browser):
    """Chuyên viên nhân sự lập và gửi kỳ công tháng, không tự duyệt đơn của mình; trưởng phòng nhân sự duyệt cấp cuối,
    kể cả đơn của chính chuyên viên; chuyên viên tính lương mở bảng lương và bấm Lấy nhân viên."""
    lan = Session(browser, "R4-HR-OFFICER", "lan")
    try:
        login(lan)
        with case(lan, "RV-41", "Chuyên viên lập và gửi kỳ công tháng cho các phạm vi",
                  "Desk > TLC Attendance Period > Mới > chọn phạm vi + tháng > Lưu > Hành động > Gửi xác nhận/Gửi đối soát "
                  "> Đối soát xong kỳ hội sở",
                  f"tháng {M_UI}", "kỳ tạo từ giao diện có số người; hội sở vào bước chờ giám đốc ký") as r:
            out = []
            for scope in ("Nhà máy 2", "Nhà máy 3", "Hội sở"):
                lan.step(f"Lan lập kỳ công {M_UI} cho {scope}")
                desk(lan, KC)
                wait_frm(lan, KC)
                choose(lan, "scope", scope)
                check(write(lan, "period_month", M_UI) == M_UI, f"tháng không nhận giá trị: {form_value(lan, 'period_month')}")
                save(lan)
                name = created(lan)
                check("new-tlc-attendance-period" not in name, f"{scope}: chưa lưu được kỳ công ({name}) · {body(lan)[:200]}")
                people = form_value(lan, "employee_count")
                state = doc_state(lan, KC, name)
                if state not in (DRAFT, None):
                    out.append(f"{scope} {people} người (đã gửi: {state})")
                    continue
                lan.step(f"Lan gửi {scope} cho {'trưởng nhà máy xác nhận' if scope != 'Hội sở' else 'nhân sự đối soát'}")
                action(lan, "Gửi đối soát" if scope == "Hội sở" else "Gửi xác nhận")
                state = doc_state(lan, KC, name)
                out.append(f"{scope} {people} người -> {state}")
                if scope == "Hội sở" and state == P_TO_HR:
                    lan.step("Lan đối soát xong kỳ hội sở và trình giám đốc ký")
                    action(lan, "Đối soát xong")
                    out[-1] += f" -> {doc_state(lan, KC, name)}"
            waiting = find(lan, KC, [["period_month", "=", M_UI], ["workflow_state", "=", P_TO_CEO]], ("name",), limit=5)
            check(waiting, f"không có kỳ công {M_UI} nào ở bước chờ giám đốc ký: {out}")
            r["actual"] = f"Kỳ công {M_UI}: " + "; ".join(out)

        with case(lan, "RV-42", "Chuyên viên nhân sự không tự duyệt đơn của mình",
                  "App > Xin nghỉ phép > gửi > Desk > mở đơn của mình > Hành động", "đơn do chính Lan tạo",
                  "không có nút Duyệt cho người tạo đơn") as r:
            lan.step("Lan gửi đơn nghỉ của chính mình rồi thử tự duyệt")
            name = hrms_request_leave(lan, working_day(7), working_day(7), "Nghỉ phép cá nhân")
            REQ["leave_lan"] = name
            open_form(lan, "Leave Application", name)
            items = workflow_actions(lan.page)
            check(not any("Duyệt" in i and "Gửi" not in i for i in items), f"có nút duyệt: {items}")
            r["actual"] = f"{name}: Hành động chỉ có {items or 'không có nút'} — chuyên viên không tự duyệt được"
    finally:
        lan.close()

    hoa = Session(browser, "R4-HR-LEAD", "hoa")
    try:
        login(hoa)
        with case(hoa, "RV-43", "Trưởng phòng nhân sự duyệt cấp cuối",
                  "Desk > Leave Application > mở đơn chờ nhân sự > Hành động > Duyệt", "đơn đã qua cấp quản lý",
                  "đơn Đã duyệt và số dư phép trừ đúng số ngày") as r:
            hoa.step("Hòa mở danh sách đơn chờ nhân sự duyệt")
            list_text(hoa, "Leave Application")
            pending = find(hoa, "Leave Application", [["name", "=", REQ["leave_hr"]], ["workflow_state", "=", TO_HR]],
                           ("name", "employee_name", "leave_type", "total_leave_days"), limit=5, order="creation asc")
            check(pending, "không còn đơn chờ nhân sự duyệt")
            person = field(hoa, "Leave Application", pending[0]["name"], "employee")
            before = float(balance_of(hoa, person, pending[0]["leave_type"], application=pending[0]["name"]))
            open_form(hoa, "Leave Application", pending[0]["name"])
            check(pending[0]["employee_name"] in body(hoa), body(hoa)[:200])
            hoa.step("Hòa bấm Duyệt cấp cuối")
            action(hoa, "Duyệt")
            state = doc_state(hoa, "Leave Application", pending[0]["name"])
            after = float(balance_of(hoa, person, pending[0]["leave_type"]))
            check(state == APPROVED, f"{pending[0]['name']} ở {state}")
            r["actual"] = (f"{pending[0]['name']} ({pending[0]['employee_name']}, {pending[0]['total_leave_days']:g} ngày): {state}; "
                           f"số dư {before:g} -> {after:g}")

        with case(hoa, "RV-44", "Duyệt đơn của chính người làm nhân sự",
                  "Desk > mở đơn của Lan > Hành động > Duyệt (cấp 1) > mở lại > Duyệt (cấp cuối)",
                  "đơn do chuyên viên nhân sự gửi", "Hòa duyệt được vì đây không phải đơn của mình") as r:
            hoa.step("Hòa duyệt đơn mà Lan vừa gửi")
            mine = find(hoa, "Leave Application", [["name", "=", REQ["leave_lan"]],
                        ["workflow_state", "in", [TO_MANAGER, TO_HR]]], ("name",), limit=1)
            check(mine, "không còn đơn của Lan để duyệt")
            steps = []
            for _ in range(2):
                state = doc_state(hoa, "Leave Application", mine[0]["name"])
                if state == APPROVED:
                    break
                open_form(hoa, "Leave Application", mine[0]["name"])
                action(hoa, "Duyệt")
                steps.append(doc_state(hoa, "Leave Application", mine[0]["name"]))
            check(steps and steps[-1] == APPROVED, f"{mine[0]['name']} qua {steps}")
            r["actual"] = f"{mine[0]['name']}: Hòa duyệt hết {steps}"
    finally:
        hoa.close()

    phuong = Session(browser, "R4-HR-PAYROLL", "phuong")
    try:
        login(phuong)
        with case(phuong, "RV-45", "Chuyên viên lương mở bảng lương và lấy đúng danh sách nhân viên",
                  "Desk > Payroll Entry > mở bảng nháp > bấm Lấy nhân viên > đọc dòng trên lưới",
                  f"kỳ lương {M_NOW}", "dòng nhân viên hiện ra trên form sau một cú nhấp thật") as r:
            phuong.step("Phương mở bảng lương nháp của tháng này")
            company = find(phuong, "Company", limit=1)[0]["name"]
            drafts = find(phuong, PE, [["name", "=", REQ["pe_draft"]], ["workflow_state", "=", DRAFT],
                                      ["company", "=", company]], ("name",), limit=1)
            check(drafts, "không có bảng lương nháp để lấy nhân viên")
            open_form(phuong, PE, drafts[0]["name"])
            before_rows = int(phuong.page.evaluate("() => (cur_frm.doc.employees || []).length"))
            phuong.step("Phương bấm Lấy nhân viên")
            phuong.page.get_by_role("button", name=re.compile(r"^(Get Employees|Lấy nhân viên)$")).click()
            phuong.page.wait_for_function("() => window.cur_frm && (cur_frm.doc.employees || []).length > 0", timeout=90000)
            phuong.page.wait_for_timeout(3000)
            rows = int(phuong.page.evaluate("() => (cur_frm.doc.employees || []).length"))
            names = phuong.page.evaluate("() => (cur_frm.doc.employees || []).slice(0, 3).map(e => e.employee_name)")
            text = body(phuong)
            check(rows > before_rows and rows >= 10, f"chỉ có {rows} dòng: {text[:200]}")
            check(all(n in text for n in names if n), f"tên nhân viên không hiện trên lưới: {names}")
            r["actual"] = f"{drafts[0]['name']}: bấm Lấy nhân viên được {rows} dòng trên form ({', '.join([n for n in names if n][:2])} ...)"
    finally:
        phuong.close()


# --------------------------------------------------------------------- 4. Trưởng nhà máy: Đặng Văn Hùng (Nhà máy 1)

def factory_head_day(browser):
    """Hùng chỉ làm việc trong phạm vi Nhà máy 1: hàng đợi trên workspace, duyệt đơn của công nhân, duyệt giải trình công,
    đề nghị tăng ca (hỏi ý kiến người lao động), xác nhận kỳ công, và thấy rõ mình không với tới nhà máy khác."""
    s = Session(browser, "R3-TRUONGNM", "hung")
    try:
        login(s)
        with case(s, "RV-31", "Vào workspace của mình và bấm thẻ việc chờ",
                  "Desk > TLC Nhà máy > đọc thẻ đơn chờ và kỳ công chờ xác nhận > bấm shortcut Đơn chờ duyệt",
                  "hàng đợi của Nhà máy 1", "thẻ có số thật và shortcut mở đúng danh sách việc chờ") as r:
            s.step("Hùng mở workspace TLC Quản lý và đọc thẻ việc chờ")
            workspace(s, "TLC Quản lý")
            pending = card_value(s.page, "Đơn chờ tôi duyệt")
            periods = card_value(s.page, "Kỳ công chờ tôi xác nhận")
            s.step("Hùng bấm shortcut Đơn chờ duyệt để mở hàng đợi")
            shortcut(s, "Đơn chờ duyệt", "/desk/leave-application")
            check(pending >= 1 and periods >= 1, f"thẻ đơn {pending}, thẻ kỳ công {periods}")
            r["actual"] = f"TLC Nhà máy: {pending} đơn nghỉ chờ duyệt, {periods} kỳ công chờ xác nhận; shortcut mở đúng danh sách"

        with case(s, "RV-32", "Duyệt đơn nghỉ của công nhân nhà máy mình",
                  "Desk > Leave Application > mở đơn > Hành động > Duyệt", "một đơn của Nhà máy 1",
                  "đơn chuyển sang bước nhân sự") as r:
            s.step("Hùng mở một đơn nghỉ của công nhân và duyệt")
            pending = find(s, "Leave Application", [["name", "=", REQ["leave_team"]], ["workflow_state", "=", TO_MANAGER],
                                                    ["department", "like", "%Nhà máy 1%"]], ("name", "employee_name", "leave_type"), limit=1)
            check(pending, "không còn đơn chờ quản lý của Nhà máy 1")
            open_form(s, "Leave Application", pending[0]["name"])
            check(pending[0]["employee_name"] in body(s), body(s)[:200])
            s.step("Hùng bấm Duyệt")
            action(s, "Duyệt")
            state = doc_state(s, "Leave Application", pending[0]["name"])
            check(state == TO_HR, f"{pending[0]['name']} ở {state}")
            r["actual"] = f"{pending[0]['name']} ({pending[0]['employee_name']}): {state}"

        with case(s, "RV-33", "Duyệt giải trình chấm công của đội",
                  "Desk > Attendance Request > mở phiếu > Hành động > Duyệt", "một giải trình chờ trưởng nhà máy",
                  "giải trình chuyển sang bước nhân sự") as r:
            s.step("Hùng mở giải trình quên chấm công của công nhân")
            req = find(s, AR, [["name", "=", REQ["arq"]], ["workflow_state", "=", TO_MANAGER],
                              ["tlc_approver", "=", "hung@demo.example"]], ("name", "employee_name", "from_date"), limit=1)
            check(req, "không có giải trình chờ duyệt của Nhà máy 1")
            open_form(s, AR, req[0]["name"])
            check(req[0]["employee_name"] in body(s), body(s)[:200])
            s.step("Hùng duyệt giải trình này")
            action(s, "Duyệt")
            state = doc_state(s, AR, req[0]["name"])
            check(state == TO_HR, f"{req[0]['name']} ở {state}")
            r["actual"] = f"{req[0]['name']} ({req[0]['employee_name']}, {vn(req[0]['from_date'])}): {state}"

        with case(s, "RV-34", "Đề nghị tăng ca cho công nhân (hỏi ý kiến người lao động trước)",
                  "Desk > TLC Overtime Request > Mới > chọn công nhân, ngày, giờ, lý do > Lưu > Hành động > Đề nghị",
                  "2,5 giờ ngày thường cho Trần Văn Bình", "đề nghị tạo ra bước chờ người lao động đồng ý, chưa tính lương") as r:
            s.step("Hùng lập đề nghị tăng ca cho Bình")
            desk(s, OT)
            wait_frm(s, OT)
            pick(s, "employee", emp(s, "binh")["name"])
            check(write(s, "ot_date", working_day(27)) == working_day(27), f"ngày tăng ca không nhận: {form_value(s, 'ot_date')}")
            write_time(s, "from_time", "18:30:00")
            write_time(s, "to_time", "21:00:00")
            write(s, "reason", "Đơn hàng gấp, cần tăng ca 2,5 giờ")
            save(s)
            ot = created(s)
            check("new-tlc-overtime-request" not in ot, f"chưa lưu được đề nghị: {ot} · {body(s)[:200]}")
            s.step("Hùng gửi đề nghị để công nhân tự quyết định")
            action(s, "Đề nghị")
            state = doc_state(s, OT, ot)
            hours = field(s, OT, ot, "hours")
            check(state == TO_WORKER, f"{ot} ở {state}: {body(s)[:220]}")
            r["actual"] = f"{ot}: {hours:g} giờ, {state} — hệ thống hỏi ý kiến người lao động trước khi tính lương"

        with case(s, "RV-35", "Xác nhận bảng công tháng của nhà máy mình",
                  "Desk > TLC Attendance Period > mở kỳ Nhà máy 1 > Hành động > Xác nhận",
                  f"kỳ {M_UI} của Nhà máy 1 chờ trưởng nhà máy", "kỳ chuyển sang bước nhân sự đối soát") as r:
            s.step("Hùng đối soát và xác nhận kỳ công của Nhà máy 1")
            waiting = find(s, KC, [["name", "=", REQ["period_nm1"]], ["scope", "=", "Nhà máy 1"],
                                  ["workflow_state", "=", P_TO_HEAD], ["period_month", "=", M_UI]], ("name", "employee_count"), limit=1)
            check(waiting, f"không có kỳ công Nhà máy 1 {M_UI} chờ trưởng nhà máy")
            open_form(s, KC, waiting[0]["name"])
            check("Nhà máy 1" in body(s), body(s)[:220])
            s.step("Hùng bấm Xác nhận")
            action(s, "Xác nhận")
            state = doc_state(s, KC, waiting[0]["name"])
            check(state == P_TO_HR, f"{waiting[0]['name']} ở {state}")
            r["actual"] = f"{waiting[0]['name']}: {waiting[0]['employee_count']} người -> {state}"

        with case(s, "RV-36", "Không với tới dữ liệu của nhà máy khác",
                  "Desk > Employee > ô tìm kiếm Ctrl+K cho người Nhà máy 2 rồi cho người Nhà máy 1 > danh sách lọc theo Nhà máy 2",
                  "một công nhân Nhà máy 2", "giao diện không trả về hồ sơ nào ngoài Nhà máy 1") as r:
            other = [{"employee_name": REQ.get("nm2_worker") or ""}]
            own = [{"employee_name": REQ.get("nm1_worker") or ""}]
            check(other[0]["employee_name"] and own[0]["employee_name"], "thiếu hồ sơ để đối chứng phạm vi")
            s.step("Hùng tìm công nhân Nhà máy 2 ngay trên giao diện")
            s.page.goto(f"{BASE}/desk/employee")
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(2500)
            s.page.keyboard.press("Control+k")
            s.page.wait_for_timeout(1200)
            box = s.page.locator("#navbar-search")
            box.click()
            box.type(other[0]["employee_name"], delay=80)
            s.page.wait_for_timeout(4000)
            searched = " ".join(s.page.locator(".modal:visible").last.inner_text().split())
            s.page.keyboard.press("Escape")
            s.page.wait_for_timeout(800)
            s.step("Hùng tìm một công nhân của chính mình để đối chứng")
            s.page.keyboard.press("Control+k")
            s.page.wait_for_timeout(1000)
            box = s.page.locator("#navbar-search")
            box.click()
            box.type(own[0]["employee_name"], delay=80)
            s.page.wait_for_timeout(4000)
            found_own = " ".join(s.page.locator(".modal:visible").last.inner_text().split())
            s.page.keyboard.press("Escape")
            s.page.wait_for_timeout(800)
            s.step("Hùng mở danh sách nhân viên lọc theo phòng ban Nhà máy 2")
            s.page.goto(f"{BASE}/desk/employee?department=" + quote(json.dumps(["like", "%Nhà máy 2%"], ensure_ascii=False)))
            s.page.wait_for_load_state("networkidle")
            s.page.wait_for_timeout(4000)
            text = body(s)
            rows = s.page.locator(".data-row, .list-row, .list-row-container").count()
            check(other[0]["employee_name"] not in searched, f"tìm thấy cả người nhà máy khác: {searched[:220]}")
            check(own[0]["employee_name"] in found_own, f"hồ sơ của mình mà không tìm thấy: {found_own[:220]}")
            check(rows == 0 and other[0]["employee_name"] not in text, f"danh sách Nhà máy 2 còn {rows} dòng: {text[:240]}")
            r["actual"] = (f"tìm '{other[0]['employee_name']}' (Nhà máy 2): không có kết quả; tìm '{own[0]['employee_name']}' "
                           f"(Nhà máy 1): có kết quả; lọc danh sách theo Nhà máy 2: 0 dòng")
    finally:
        s.close()


# ------------------------------------------------------------------------------------------------------- 5. CEO

def ceo_day(browser):
    """Nguyễn Văn Thành, Tổng giám đốc: bức tranh nhân sự trên workspace, duyệt tăng ca đã có sự đồng ý của người lao động,
    ký và khoá kỳ công, ký bảng lương."""
    s = Session(browser, "R5-CEO", "thanh")
    try:
        login(s)
        with case(s, "RV-51", "Mở workspace điều hành và đọc các thẻ",
                  "Desk > TLC Điều hành > đọc thẻ nhân sự, tăng ca chờ giám đốc, kỳ công chờ ký, bảng lương chờ ký",
                  "số liệu toàn công ty", "bốn thẻ đều có số thật") as r:
            s.step("Thành mở workspace TLC Điều hành và đọc từng thẻ")
            workspace(s, "TLC Điều hành")
            staff = card_value(s.page, "Nhân sự đang làm việc")
            overtime = card_value(s.page, "Tăng ca chờ giám đốc duyệt")
            periods = card_value(s.page, "Kỳ công chờ ký")
            payroll = card_value(s.page, "Bảng lương chờ ký")
            check(staff > 0 and overtime > 0 and periods > 0 and payroll > 0,
                  f"nhân sự {staff}, tăng ca {overtime}, kỳ công {periods}, bảng lương {payroll}")
            r["actual"] = (f"TLC Điều hành: {staff} người đang làm việc, {overtime} đề nghị tăng ca chờ giám đốc, "
                           f"{periods} kỳ công chờ ký, {payroll} bảng lương chờ ký")

        with case(s, "RV-52", "Duyệt đề nghị tăng ca sau khi người lao động đã đồng ý",
                  "Desk > TLC Overtime Request > mở phiếu > đọc dấu đã đồng ý > Hành động > Duyệt",
                  "phiếu chờ giám đốc duyệt", "chỉ phiếu đã có sự đồng ý mới lên bàn giám đốc; duyệt thành Đã duyệt") as r:
            s.step("Thành mở một đề nghị tăng ca đã có sự đồng ý của công nhân")
            waiting = find(s, OT, [["name", "=", REQ["ot_director"]], ["workflow_state", "=", TO_DIRECTOR]],
                           ("name", "employee_name", "consent_at", "hours"), limit=1)
            check(waiting and waiting[0]["consent_at"], f"không có phiếu đã đồng ý chờ giám đốc: {waiting}")
            open_form(s, OT, waiting[0]["name"])
            check(waiting[0]["employee_name"] in body(s), body(s)[:220])
            s.step("Thành duyệt phiếu này")
            action(s, "Duyệt")
            state = doc_state(s, OT, waiting[0]["name"])
            check(state == APPROVED, f"{waiting[0]['name']} ở {state}")
            r["actual"] = (f"{waiting[0]['name']} ({waiting[0]['employee_name']}, {waiting[0]['hours']:g} giờ): công nhân đồng ý "
                           f"lúc {waiting[0]['consent_at']} -> {state}")

        with case(s, "RV-53", "Ký và khoá kỳ công",
                  "Desk > TLC Attendance Period > mở kỳ chờ ký > Hành động > Ký và khoá",
                  f"kỳ {M_UI} đã đối soát xong", "kỳ Đã khoá, có dấu vết người ký và thời điểm ký") as r:
            s.step("Thành ký khoá một kỳ công đã đối soát xong")
            ready = find(s, KC, [["workflow_state", "=", P_TO_CEO], ["period_month", "=", M_UI], ["scope", "=", "Hội sở"]],
                         ("name", "scope", "employee_count", "period_month"), limit=1)
            check(ready, "không có kỳ công chờ giám đốc ký")
            open_form(s, KC, ready[0]["name"])
            check(ready[0]["scope"] in body(s), body(s)[:200])
            s.step("Thành bấm Ký và khoá")
            action(s, "Ký và khoá")
            doc = api_get(s, f"/api/resource/{KC}/{quote(ready[0]['name'], safe='')}").json()["data"]
            check(doc["workflow_state"] == P_LOCKED and doc["locked_by"] == "thanh@demo.example",
                  f"{doc['workflow_state']} / {doc['locked_by']}")
            r["actual"] = f"{ready[0]['name']} ({ready[0]['scope']}, {doc['employee_count']} người): Đã khoá lúc {doc['locked_at']}"

        with case(s, "RV-54", "Ký bảng lương",
                  "Desk > Payroll Entry > mở bảng chờ ký > đọc dòng tổng > Hành động > Ký duyệt",
                  f"bảng lương {M_SIGN} đã tính", "bảng Đã ký; phiếu lương của người lao động được ghi sổ") as r:
            s.step("Thành mở bảng lương đã được gửi lên")
            ready = find(s, PE, [["name", "=", REQ["pe_sign"]], ["workflow_state", "=", P_TO_CEO]],
                         ("name", "number_of_employees"), limit=1)
            check(ready, "không có bảng lương chờ giám đốc ký")
            open_form(s, PE, ready[0]["name"])
            text = headline(s.page) or body(s)
            s.step("Thành ký duyệt bảng lương")
            action(s, "Ký duyệt")
            state = doc_state(s, PE, ready[0]["name"])
            slips = wait_slips(s, ready[0]["name"], 1, int(ready[0]["number_of_employees"]),
                               required=(emp(s, "binh")["name"], emp(s, "an")["name"]))
            check(state == SIGNED, f"{ready[0]['name']} ở {state}")
            r["actual"] = (f"{ready[0]['name']} ({ready[0]['number_of_employees']} nhân viên): {state}; {slips} phiếu đã ghi sổ · "
                           f"{' '.join(text.split())[:120]}")
    finally:
        s.close()


# -------------------------------------------------------------------------------- 6. Trưởng phòng và kế toán

def finance_day(browser):
    """Trần Minh Quang duyệt cấp một cho phòng mình; Đỗ Thị Chi trả tạm ứng bằng chứng từ ngân hàng và xác nhận đã chi lương."""
    quang = Session(browser, "R6-MANAGER", "quang")
    try:
        login(quang)
        with case(quang, "RV-61", "Trưởng phòng duyệt cấp một cho nhân viên phòng mình",
                  "Desk > Leave Application > mở đơn của nhân viên > Hành động > Duyệt", "đơn của Kinh doanh hội sở",
                  "đơn chuyển sang bước nhân sự") as r:
            quang.step("Quang mở đơn nghỉ của nhân viên kinh doanh")
            pending = find(quang, "Leave Application", [["name", "=", REQ["leave_an"]], ["workflow_state", "=", TO_MANAGER]],
                           ("name", "employee_name", "total_leave_days"), limit=1)
            check(pending, "không còn đơn chờ quản lý")
            open_form(quang, "Leave Application", pending[0]["name"])
            check(pending[0]["employee_name"] in body(quang), body(quang)[:200])
            quang.step("Quang bấm Duyệt")
            action(quang, "Duyệt")
            state = doc_state(quang, "Leave Application", pending[0]["name"])
            check(state == TO_HR, f"{pending[0]['name']} ở {state}")
            r["actual"] = f"{pending[0]['name']} ({pending[0]['employee_name']}, {pending[0]['total_leave_days']:g} ngày): {state}"
    finally:
        quang.close()

    chi = Session(browser, "R6-ACCOUNTANT", "chi")
    try:
        login(chi)
        with case(chi, "RV-62", "Kế toán chi tạm ứng bằng chứng từ ngân hàng",
                  "Desk > Employee Advance > mở phiếu chờ chi > gõ Chứng từ chi > Lưu > Hành động > Xác nhận đã chi",
                  "tạm ứng đã duyệt, chứng từ Pay đã ghi sổ", "phiếu chuyển Đã chi, số tiền đã ứng ghi đúng") as r:
            chi.step("Chi mở danh sách tạm ứng chờ chi")
            list_text(chi, EA)
            waiting = find(chi, EA, [["name", "=", REQ["advance"]], ["workflow_state", "=", "Chờ chi"]],
                           ("name", "employee_name", "advance_amount"), limit=1)
            check(waiting, "không có tạm ứng chờ chi")
            entry = REQ["advance_pe"]
            check(entry, "không có chứng từ ngân hàng để gắn vào tạm ứng")
            open_form(chi, EA, waiting[0]["name"])
            chi.step("Chi gõ số chứng từ ngân hàng vào phiếu tạm ứng")
            check(pick(chi, "tlc_payment_entry", entry) == entry, f"chứng từ không vào ô: {form_value(chi, 'tlc_payment_entry')}")
            save(chi)
            check(field(chi, EA, waiting[0]["name"], "tlc_payment_entry") == entry, "chứng từ chưa lưu vào phiếu")
            chi.step("Chi bấm Xác nhận đã chi")
            action(chi, "Xác nhận đã chi")
            doc = api_get(chi, f"/api/resource/{EA}/{quote(waiting[0]['name'], safe='')}").json()["data"]
            check(doc["workflow_state"] == "Đã chi" and doc["paid_amount"] == waiting[0]["advance_amount"],
                  f"{doc['workflow_state']} / {doc['paid_amount']}")
            r["actual"] = f"{waiting[0]['name']} ({waiting[0]['employee_name']}): Đã chi {doc['paid_amount']:,.0f} đ, chứng từ {entry}"

        with case(chi, "RV-63", "Kế toán xác nhận đã chi bảng lương",
                  "Desk > Payroll Entry > gõ Số chứng từ ngân hàng + Ngày chi > Lưu > Hành động > Xác nhận đã chi",
                  f"bảng {M_SIGN} đã ký", "bảng chuyển Đã chi và có bút toán ngân hàng mang số chứng từ") as r:
            chi.step("Chi mở bảng lương đã ký để xác nhận đã trả lương")
            ready = find(chi, PE, [["name", "=", REQ["pe_sign"]], ["workflow_state", "=", SIGNED]],
                         ("name", "number_of_employees"), limit=1)
            check(ready, "không có bảng lương đã ký chờ chi")
            open_form(chi, PE, ready[0]["name"])
            before = workflow_actions(chi.page)
            check("Xác nhận đã chi" not in before, f"chưa có chứng từ mà đã có nút chi: {before}")
            reference = f"VCB-UNC-{M_SIGN.replace('-', '')}-VIDEO"
            chi.step("Chi gõ số uỷ nhiệm chi và ngày chi ngay trên form")
            open_form(chi, PE, ready[0]["name"])
            chi.page.locator("button:visible", has_text="Nhân viên").first.click()
            chi.page.locator("input[data-fieldname='tlc_bank_reference']:visible").wait_for()
            write(chi, "tlc_bank_reference", reference)
            write(chi, "tlc_paid_on", dt.date.today().isoformat())
            chi.step("Chi đính kèm ủy nhiệm chi ngân hàng riêng tư vào bảng lương")
            attach_control = chi.page.locator("[data-fieldname='tlc_bank_proof']").first
            attach_btn = attach_control.locator("button.btn-attach:visible").last
            if not attach_btn.count():
                attach_btn = attach_control.locator("button:visible", has_text=re.compile(r"Gắn|Đính kèm|Attach")).last
            attach_btn.click()
            dialog = chi.page.locator(".modal:visible").last
            dialog.wait_for(state="visible")
            proof_file = Path("/tmp") / f"proof-roles-{ready[0]['name']}.txt"
            proof_file.write_text(f"Uỷ nhiệm chi ngân hàng {reference} cho bảng lương {ready[0]['name']}", encoding="utf-8")
            dialog.locator("input[type=file]").last.set_input_files(str(proof_file))
            dialog.get_by_role("button", name=re.compile(r"^(Tải lên|Upload)$")).last.click()
            chi.page.wait_for_timeout(3000)
            save(chi)
            saved = api_get(chi, f"/api/resource/{PE}/{quote(ready[0]['name'], safe='')}").json()["data"]
            check(saved["tlc_bank_reference"] == reference and saved["tlc_paid_on"] == dt.date.today().isoformat()
                  and saved.get("tlc_bank_proof", "").startswith("/private/files/"),
                  f"chứng từ/ngày chi/tệp chưa lưu: {saved.get('tlc_bank_reference')} / {saved.get('tlc_paid_on')}")
            chi.step("Chi bấm Xác nhận đã chi")
            action(chi, "Xác nhận đã chi")
            state = doc_state(chi, PE, ready[0]["name"])
            journals = find(chi, "Journal Entry", [["cheque_no", "=", reference], ["docstatus", "=", 1]], ("name",), limit=2)
            check(state == PAID and journals, f"{state}, bút toán {journals}")
            r["actual"] = f"{ready[0]['name']}: {state}; bút toán {journals[0]['name']} mang chứng từ {reference}"
    finally:
        chi.close()


def roles_flow(browser):
    prepare_state(browser)
    worker_day(browser)
    office_day(browser)
    hr_day(browser)
    factory_head_day(browser)
    ceo_day(browser)
    finance_day(browser)


JOURNEYS = [roles_flow]