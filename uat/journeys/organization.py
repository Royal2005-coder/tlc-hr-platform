"""Cơ cấu tổ chức và định biên nhân sự (W4) - toàn bộ đi trên Desk của HR Lead.

Mỗi ca là một chuỗi thao tác thật: mở cây phòng ban và nhấp từng đơn vị, mở biểu mẫu từ danh sách, điền ô, chọn trong
bảng gợi ý, bấm `Lưu`, bấm nút `Tính lại định biên`, bấm `Xuất` sơ đồ. API chỉ dùng để đọc lại dữ liệu đã được lưu sau
khi người dùng đã làm xong trên màn hình.
"""

from urllib.parse import quote

from lib import *  # noqa: F403

CHANGE, HEAD = "TLC Organization Change", "TLC Organization Headcount"
LINE, POSITION, ASSIGN = "TLC Organization Reporting Line", "TLC Organization Position", "TLC Organization Assignment"
UNIT = "Nhà máy 1 - TLC"


def user_date(s, iso):
    """Ngày viết theo đúng định dạng site đang hiển thị, để gõ vào ô bằng bàn phím."""
    format_ = s.page.evaluate("() => (window.frappe && frappe.boot.sysdefaults.date_format) || 'yyyy-mm-dd'")
    d = dt.date.fromisoformat(iso)
    return format_.replace("yyyy", f"{d.year:04d}").replace("mm", f"{d.month:02d}").replace("dd", f"{d.day:02d}")


# ---------------------------------------------------------------------------------------------------- desk helpers

def slug_of(doctype):
    return doctype.lower().replace(" ", "-")


def open_list(s, doctype, note):
    s.step(note)
    p = s.page
    p.goto(f"{BASE}/desk/{slug_of(doctype)}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2500)
    return p


def row_text(p, i):
    return " ".join(p.locator(".list-row-container").nth(i).inner_text().split())


def click_row(p, index=0, needle=None):
    """Nhấp vào liên kết của một dòng trong danh sách để mở biểu mẫu, như người dùng thật."""
    rows = p.locator(".list-row-container .list-subject a")
    check(rows.count() > 0, f"danh sách không có dòng nào để mở: {row_text(p, 0)[:150]}")
    target = index
    if needle:
        target = next((i for i in range(rows.count()) if needle in " ".join(rows.nth(i).inner_text().split())), None)
        check(target is not None, f"không thấy dòng chứa '{needle}' trong danh sách: "
                                  f"{[rows.nth(i).inner_text() for i in range(min(rows.count(), 6))]}")
    check(target < rows.count(), f"danh sách chỉ có {rows.count()} dòng")
    rows.nth(target).click()
    p.wait_for_function("() => window.cur_frm && !cur_frm.is_new()", timeout=25000)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(2000)


def field_value(p, field):
    """Giá trị nhìn thấy được của một ô: ô nhập liệu hay ô chỉ đọc đều đọc được trên màn hình."""
    box = p.locator(f"input[data-fieldname='{field}']:visible, textarea[data-fieldname='{field}']:visible,"
                    f" select[data-fieldname='{field}']:visible")
    if box.count():
        try:
            value = (box.last.input_value() or "").strip()
            if value:
                return value
        except Exception:
            pass
    shown = p.locator(f".frappe-control[data-fieldname='{field}'] .control-value")
    if shown.count():
        return " ".join(shown.first.inner_text().split())
    control = p.locator(f".frappe-control[data-fieldname='{field}']")
    if control.count():
        lines = [x for x in control.first.inner_text().splitlines() if x.strip()]
        return " ".join(" ".join(lines[-1:]).split())
    return ""


def type_into(p, field, value):
    """Bấm vào ô, đóng bảng lịch/bảng gợi ý đang che ô, điền rồi rời ô bằng Tab."""
    box = p.locator(f"input[data-fieldname='{field}']:visible, textarea[data-fieldname='{field}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    box.click()
    p.wait_for_timeout(500)
    p.keyboard.press("Escape")  # ô ngày mở bảng lịch che chính ô đó
    p.wait_for_timeout(500)
    if (box.get_attribute("data-fieldtype") or "") in ("Date", "Datetime", "Time"):
        box.fill(str(value))  # gõ từng ký tự làm bộ lọc ngày ghi 'Invalid date' vào form
    else:
        box.press_sequentially(str(value), delay=60)
    p.keyboard.press("Tab")
    p.wait_for_timeout(900)
    if (box.input_value() or "").strip() != str(value).strip():
        box.fill(str(value))
        p.keyboard.press("Tab")
        p.wait_for_timeout(800)
    check((box.input_value() or "").strip() == str(value).strip(),
          f"ô {field} đang hiển thị '{box.input_value() or '(trống)'}', không nhận '{value}'")


def pick_link(p, field, needle, root=None):
    """Ô liên kết: bấm vào ô (dòng lưới đang ở chế độ xem thì cú bấm mở ô nhập), gõ để lọc, chọn gợi ý đang hiện."""
    scope = root or p
    control = scope.locator(f"[data-fieldname='{field}']:visible").last
    control.wait_for(state="visible", timeout=15000)
    box = control.locator("input:visible").last
    if not box.count():
        control.click()  # a grid cell in display mode turns into an input when the user clicks it
        p.wait_for_timeout(700)
        box = scope.locator(f"input[data-fieldname='{field}']:visible").last
    box.wait_for(state="visible", timeout=15000)
    box.click()
    box.fill("")
    p.keyboard.type(needle, delay=45)
    p.wait_for_timeout(2200)
    options = p.locator(".awesomplete li, ul[role=listbox] li, .ui-menu-item, [role=option], .frappe-control-dropdown li")
    shown = [i for i in range(options.count()) if options.nth(i).is_visible()]
    target = next((i for i in shown if needle.lower() in " ".join(options.nth(i).inner_text().split()).lower()), None)
    check(target is not None,
          f"ô {field} không có gợi ý hiển thị '{needle}' (đang hiện: {[options.nth(i).inner_text() for i in shown][:4]})")
    options.nth(target).click()
    p.wait_for_timeout(1200)
    return " ".join(options.nth(target).inner_text().split())


def choose_option(p, field, label):
    select = p.locator(f"select[data-fieldname='{field}']:visible").last
    select.wait_for(state="visible", timeout=15000)
    select.click()
    try:
        select.select_option(label=label)
    except Exception:
        select.select_option(value=label)
    p.wait_for_timeout(700)


def press_save(s, note="Bấm Lưu"):
    """Nhấp nút Lưu gốc của biểu mẫu (form đã gửi thìdesk đổi thành Update)."""
    s.step(note)
    p = s.page
    button = p.locator(".page-head button:visible").filter(has_text=re.compile(r"Lưu|Save|Update|Cập nhật")).last
    button.click()
    p.wait_for_timeout(4000)
    return " ".join(p.locator(".form-message:visible").all_inner_texts())


def message_on_screen(p):
    found = []
    for sel in (".modal:visible", ".toast-message:visible", ".msgprint:visible", ".text-danger:visible",
                "[role=alert]:visible", ".form-message:visible"):
        try:
            found += [" ".join(el.inner_text().split()) for el in p.locator(sel).all()]
        except Exception:
            pass
    return " | ".join(x for x in found if x)


# ---------------------------------------------------------------------------------------------------- the journey

def organization_desk(browser):
    s = Session(browser, "ORG", "hoa")
    try:
        login(s)
        p = s.page
        with case(s, "ORG-01", "Cây tổ chức hành chính nhiều cấp",
                  "Phòng ban > dạng Cây > nhấp đơn vị cha, nhấp đơn vị con > mở biểu mẫu đơn vị, đọc mã định danh và đơn vị cha,"
                  " chọn cấp tổ chức rồi bấm Lưu", UNIT,
                  "Cây hiện phân cấp; biểu mẫu hiện mã định danh duy nhất và đơn vị cha; cấp tổ chức được ghi qua chính form") as r:
            s.step("Chị Hòa mở danh mục Phòng ban ở dạng cây")
            p.goto(f"{BASE}/desk/department/view/tree")
            p.locator(".tree-node").first.wait_for(state="visible")
            p.wait_for_timeout(1500)
            nodes = p.locator(".tree-node .tree-link")
            root = next((i for i in range(nodes.count()) if "All Departments" in nodes.nth(i).inner_text()), None)
            target = next((i for i in range(nodes.count()) if UNIT in nodes.nth(i).inner_text()), None)
            check(target is not None, f"không thấy {UNIT} trên cây: {[nodes.nth(i).inner_text() for i in range(nodes.count())]}")
            s.step("Chị Hòa nhấp đơn vị cha rồi nhấp đúng đơn vị cần xem")
            if root is not None and root != target:
                nodes.nth(root).click()
                p.wait_for_timeout(1500)
            nodes.nth(target).click()
            p.wait_for_timeout(2000)
            tree_nodes = p.locator(".tree-node").count()
            tree_text = " ".join(p.locator(".tree, .layout-main").first.inner_text().split())
            check(tree_nodes > 0, f"cây phòng ban không hiện nút nào: {tree_text[:160]}")
            check(UNIT in tree_text, f"cây không hiển thị đơn vị: {tree_text[:160]}")
            s.step("Chị Hòa mở đơn vị đó dưới dạng biểu mẫu")
            open_list(s, "Department", "Chị Hòa mở danh sách Phòng ban")
            click_row(p, needle=UNIT)
            code, parent = field_value(p, "tlc_organization_code"), field_value(p, "parent_department")
            check(code.startswith("ORG-"), f"mã định danh trên biểu mẫu: {code or '(trống)'}")
            check(parent, f"biểu mẫu không hiện đơn vị cha")
            level_before = field_value(p, "tlc_organization_level")
            if not level_before:
                s.step("Chị Hòa chọn cấp tổ chức cho đơn vị rồi bấm Lưu")
                choose_option(p, "tlc_organization_level", "Phòng ban")
                press_save(s, "Chị Hòa bấm Lưu")
            level = field_value(p, "tlc_organization_level")
            stored = api_get(s, f"/api/resource/Department/{quote(UNIT, safe='')}").json()["data"]
            check(stored["tlc_organization_code"] == code and stored["parent_department"], str(stored)[:200])
            check(level or not level_before, f"cấp tổ chức không được ghi: {level!r}")
            r["actual"] = (f"cây có {tree_nodes} đơn vị; {UNIT}: mã {code}, cha "
                           f"{stored['parent_department']}, cấp {level or '(chưa có dữ liệu demo)'}")
        with case(s, "ORG-02", "Hai đồng cấp duyệt tương đương",
                  "Danh sách Tuyến báo cáo > mở từng dòng > đọc phòng ban và người dẫn đầu", "2 dòng của Kinh doanh - TLC",
                  "Danh sách hiện 2 dòng cùng phòng ban với hai người dẫn đầu khác nhau (đọc trên màn hình, đối chiếu bằng API)") as r:
            open_list(s, LINE, "Chị Hòa mở danh sách tuyến báo cáo")
            lines = p.locator(".list-row-container .list-subject a").count()
            check(lines >= 2, f"danh sách chỉ có {lines} dòng tuyến báo cáo")
            s.step("Chị Hòa mở dòng đầu tiên và đọc người dẫn đầu")
            click_row(p, index=0)
            first = {"department": field_value(p, "department"), "leader": field_value(p, "leader")}
            p.go_back()
            p.wait_for_timeout(2500)
            s.step("Chị Hòa mở dòng thứ hai")
            click_row(p, index=1)
            second = {"department": field_value(p, "department"), "leader": field_value(p, "leader")}
            check(first["leader"] and second["leader"] and first["leader"] != second["leader"], f"{first} / {second}")
            check(first["department"] == second["department"], f"hai dòng khác phòng ban: {first['department']} / {second['department']}")
            rows = api_get(s, f"/api/resource/{LINE}?limit_page_length=20&fields=" + json.dumps(["name", "department", "leader"])).json()["data"]
            check(len(rows) >= 2, str(rows)[:160])
            r["actual"] = (f"{first['department']}: đồng cấp {first['leader']} và {second['leader']} "
                           f"(danh sách {len(rows)} dòng, mở cả hai trên màn hình)")
        with case(s, "ORG-03", "Vị trí gắn chức danh, cấp bậc và JD",
                  "Danh sách Vị trí > mở ORG-DEMO-SALES > đọc từng ô trên biểu mẫu", "ORG-DEMO-SALES",
                  "Biểu mẫu hiện mã vị trí, phòng ban, chức danh, cấp bậc và nội dung mô tả công việc") as r:
            open_list(s, POSITION, "Chị Hòa mở danh sách Vị trí")
            s.step("Chị Hòa mở vị trí bán hàng của hội sở")
            click_row(p, needle="ORG-DEMO-SALES")
            shown = {f: field_value(p, f) for f in ("position_code", "department", "designation", "grade")}
            check(all(shown.values()), f"thiếu thông tin trên biểu mẫu: {shown}")
            jd = p.locator(".frappe-control[data-fieldname='job_description']").inner_text()
            check(len(" ".join(jd.split())) > 20, f"mô tả công việc rỗng: {jd[:120]}")
            r["actual"] = (f"{shown['position_code']} · {shown['department']} · chức danh {shown['designation']} · "
                           f"cấp {shown['grade']} · JD {len(' '.join(jd.split()))} ký tự")
        with case(s, "ORG-04", "Địa điểm làm việc gắn lịch nghỉ và ca mặc định",
                  "Danh sách Vị trí ca > mở Nhà máy 1 > chọn lịch nghỉ, chọn loại ca > bấm Lưu, đọc lại trên màn hình",
                  "Nhà máy 1: Holiday List 'TLC 2026', Shift Type 'TLC Hành chính'",
                  "Hai ô tham chiếu được chọn trên form và được lưu; việc phân ca cho nhân viên vẫn qua Shift Assignment") as r:
            open_list(s, "Shift Location", "Chị Hòa mở danh sách địa điểm làm việc")
            s.step("Chị Hòa mở địa điểm Nhà máy 1")
            click_row(p, needle="Nhà máy 1")
            s.step("Chị Hòa chọn lịch nghỉ và loại ca mặc định của địa điểm")
            pick_link(p, "tlc_organization_holiday_list", "TLC 2026")
            pick_link(p, "tlc_organization_shift_type", "TLC Hành chính")
            press_save(s, "Chị Hòa bấm Lưu")
            shown = {f: field_value(p, f) for f in ("tlc_organization_holiday_list", "tlc_organization_shift_type")}
            stored = api_get(s, "/api/resource/Shift Location/" + quote("Nhà máy 1", safe="")).json()["data"]
            check(stored["tlc_organization_holiday_list"] == "TLC 2026" and stored["tlc_organization_shift_type"] == "TLC Hành chính",
                  f"màn hình {shown}, dữ liệu lưu {stored['tlc_organization_holiday_list']}/{stored['tlc_organization_shift_type']}")
            r["actual"] = f"Nhà máy 1: lịch nghỉ {shown['tlc_organization_holiday_list']}, ca mặc định {shown['tlc_organization_shift_type']}"
        with case(s, "ORG-05", "Định biên theo vị trí tự tính",
                  "Danh sách Định biên > mở bản ghi của vị trí bán hàng > bấm 'Tính lại định biên' > đọc các ô trên màn hình",
                  "capacity 2, một nhân viên đang phân công", "used 1, vacant 1, excess 0 hiện trên biểu mẫu sau khi bấm nút tính lại") as r:
            open_list(s, HEAD, "Chị Hòa mở danh sách định biên")
            s.step("Chị Hòa mở bản ghi định biên")
            click_row(p, index=0)
            before = {f: field_value(p, f) for f in ("capacity", "used", "vacant", "excess")}
            s.step("Chị Hòa bấm nút Tính lại định biên")
            button = p.locator("button:visible").filter(has_text=re.compile(r"Recalculate headcount|Tính lại định biên", re.I))
            check(button.count() > 0, f"biểu mẫu không có nút tính lại: {message_on_screen(p)[:120]}")
            button.first.click()
            p.wait_for_timeout(4000)
            after = {f: field_value(p, f) for f in ("capacity", "used", "vacant", "excess")}
            check((after["used"], after["vacant"], after["excess"]) == ("1", "1", "0"), f"trên màn hình {after} (trước đó {before})")
            doc = api_get(s, f"/api/resource/{HEAD}/{p.url.rstrip('/').split('/')[-1]}").json()["data"]
            check(doc["capacity"] == 2, f"định biên lưu {doc['capacity']}")
            r["actual"] = (f"{doc['position']}: định biên {after['capacity']}, đã dùng {after['used']}, "
                           f"còn trống {after['vacant']}, vượt {after['excess']} (bấm nút tính lại trên form)")
        with case(s, "ORG-06", "Xem và xuất sơ đồ tổ chức",
                  "Mở Sơ đồ tổ chức > bấm Mở rộng tất cả > bấm Xuất > file PNG tải về", "Employee.reports_to",
                  "Sơ đồ phân cấp hiện trên màn hình và nút Xuất tải về một file PNG không rỗng") as r:
            s.step("Chị Hòa mở sơ đồ tổ chức trên desk")
            p.goto(f"{BASE}/desk/organizational-chart")
            p.locator(".node-card").first.wait_for(state="visible")
            p.wait_for_timeout(2000)
            nodes = p.locator(".node-card").count()
            s.step("Chị Hòa bấm Mở rộng tất cả rồi bấm Xuất")
            expand = p.locator("button:visible").filter(has_text=re.compile(r"Mở rộng|Expand", re.I))
            if expand.count():
                expand.first.click()
                p.wait_for_timeout(2500)
            with p.expect_download() as download:
                p.locator("button:visible").filter(has_text=re.compile(r"^(Xuất|Export)$")).first.click()
            target = OUT / "shots" / "ORG-06-chart.png"
            download.value.save_as(str(target))
            check(nodes > 0 and target.stat().st_size > 0, f"nodes {nodes}, file {target.stat().st_size} bytes")
            r["actual"] = f"sơ đồ {nodes} nút; file PNG {target.name} {target.stat().st_size // 1024} KB tải về từ nút Xuất"
        with case(s, "ORG-07", "Sổ quyết định thay đổi cơ cấu",
                  "Danh sách Thay đổi cơ cấu > Thêm > chọn loại thay đổi, điền ngày hiệu lực và lý do, điền dòng đơn vị > Lưu",
                  "Đổi tên · Nhà máy 3 · ngày hiệu lực tháng sau",
                  "Bản nháp được lưu với loại thay đổi, ngày hiệu lực, lý do và một dòng đơn vị (đọc lại trên màn hình)") as r:
            open_list(s, CHANGE, "Chị Hòa mở sổ thay đổi cơ cấu")
            s.step("Chị Hòa bấm nút thêm quyết định mới")
            add = p.locator("button:visible").filter(has_text=re.compile(r"Thêm|New|Add", re.I))
            check(add.count() > 0, f"danh sách không có nút thêm: {message_on_screen(p)[:120]}")
            add.first.click()
            p.wait_for_timeout(2500)
            if p.locator(".modal:visible").count():
                p.keyboard.press("Escape")
                p.wait_for_timeout(800)
                p.goto(f"{BASE}/desk/{slug_of(CHANGE)}/new")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(2000)
            s.step("Chị Hòa chọn công ty, loại thay đổi, điền ngày hiệu lực và lý do")
            pick_link(p, "company", "TLC Demo")
            choose_option(p, "change_type", "Rename")
            day = (dt.date.today().replace(day=1) + dt.timedelta(days=45)).isoformat()
            type_into(p, "effective_date", user_date(s, day))
            type_into(p, "reason", "Sát nhập Nhà máy 3 về Ban điều hành theo quyết định của hội đồng quản trị")
            s.step("Chị Hòa điền dòng đơn vị bị ảnh hưởng trong bảng chi tiết")
            grid = p.locator(".frappe-control[data-fieldname='changes']")
            row = grid.locator(".grid-row:visible").last  # dòng dữ liệu thật (dòng đầu là tiêu đề lưới)
            pick_link(p, "source_department", "Nhà máy 3", root=row)
            pick_link(p, "target_department", "Nhà máy 3", root=row)
            check(p.evaluate("() => (cur_frm.doc.changes || []).length") == 1
                  and p.evaluate("() => (cur_frm.doc.changes || []).filter(r => r.source_department && r.target_department).length") == 1,
                  f"bảng chi tiết ghi {p.evaluate('() => JSON.stringify(cur_frm.doc.changes)')[:160]}")
            press_save(s, "Chị Hòa bấm Lưu để giữ quyết định nháp")
            check("/new-" not in p.url, f"quyết định không lưu được: {message_on_screen(p)[:180]}")
            name = p.url.rstrip("/").split("/")[-1]
            REQ["org_change"] = name
            doc = api_get(s, f"/api/resource/{CHANGE}/{name}").json()["data"]
            rows = [x for x in (doc.get("changes") or []) if x.get("source_department")]
            check(doc["docstatus"] == 0 and doc["change_type"] == "Rename" and doc["effective_date"] == day and rows,
                  f"{doc['change_type']} {doc['effective_date']} rows {len(doc.get('changes') or [])}")
            r["actual"] = (f"nháp {name}: {field_value(p, 'change_type')} · hiệu lực {field_value(p, 'effective_date')} · "
                           f"{len(rows)} dòng đơn vị ({rows[0]['source_department']})")
        with case(s, "ORG-08", "Kiêm nhiệm không cảnh báo oan",
                  "Danh sách Phân công > mở cả hai dòng của Nguyễn Hoài An > đọc phòng ban, vị trí, ô chính/phụ",
                  "HR-EMP-00016: một phân công chính ở Kinh doanh, một phân công kiêm nhiệm ở Nhân sự",
                  "Hai phân công là hai bản ghi riêng, cùng ngày bắt đầu, đúng một bản ghi là chính") as r:
            open_list(s, ASSIGN, "Chị Hòa mở danh sách phân công phòng ban")
            rows_on_screen = p.locator(".list-row-container .list-subject a").count()
            check(rows_on_screen >= 2, f"danh sách chỉ có {rows_on_screen} dòng phân công")
            s.step("Chị Hòa mở phân công chính")
            click_row(p, index=0)
            first = {"department": field_value(p, "department"), "position": field_value(p, "position"),
                     "primary": field_value(p, "is_primary")}
            p.go_back()
            p.wait_for_timeout(2500)
            s.step("Chị Hòa mở phân công kiêm nhiệm")
            click_row(p, index=1)
            second = {"department": field_value(p, "department"), "position": field_value(p, "position"),
                      "primary": field_value(p, "is_primary")}
            check(first["department"] != second["department"], f"hai dòng cùng phòng ban: {first} / {second}")
            rows = api_get(s, f"/api/resource/{ASSIGN}?limit_page_length=20&fields=" + json.dumps(["name", "employee", "department", "is_primary"])).json()["data"]
            check(sum(1 for x in rows if x["is_primary"]) >= 1 and len(rows) >= 2, str(rows)[:160])
            r["actual"] = (f"{rows[0]['employee']}: chính ở {next(x['department'] for x in rows if x['is_primary'])}, "
                           f"kiêm nhiệm ở {next(x['department'] for x in rows if not x['is_primary'])} - hai bản ghi riêng")
    finally:
        s.close()


JOURNEYS = [organization_desk]
