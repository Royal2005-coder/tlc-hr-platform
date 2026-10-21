"""One self-contained HTML proposal of TLC HRM on Frappe HR, built from a real UAT run: the case for change by role, the solution
(standard Frappe UI, TLC rules and workflows declared in YAML, layered code), the 17 BRD domains mapped to modules, one slide per
role with the desktop videos of its journeys (chapters seek to each case), one slide per module with the designed process next to
the screens actually tested, results, BRD coverage, operations, roadmap, and an appendix with every case, screenshot and video.

Usage: python3 proposal_html.py out/<RUN_ID> --theme <deck.html> --diagrams <dir of slide PNGs> [--out file.html]
Nothing is loaded from the network except the web fonts (the text falls back to system fonts offline). Videos are MP4 (H.264),
decoded from the page only when their slide is opened.
"""

import argparse
import base64
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coverage  # noqa: E402

E = html.escape

# module key -> (title, BRD domains, process diagram, standard Frappe doctypes, what TLC adds)
MODULES = {
    "leave": ("Nghỉ phép", "WF", "08-leave.png", "Leave Application, Leave Allocation, Leave Type, Holiday List, báo cáo số dư phép",
              "Workflow 2 cấp TLC Nghỉ phép; lý do từ chối bắt buộc; không ai tự duyệt đơn của mình; dòng đầu form cho người duyệt: số dư sau duyệt, người nghỉ trùng"),
    "attendance": ("Chấm công và chốt kỳ công", "WF", "07-closing.png", "Employee Checkin (GPS), Shift Type/Location/Assignment, Attendance, Attendance Request",
                   "Chặn chấm ngoài ca và ngoài bán kính nhà máy; giải trình tự lấy ca; kỳ công tháng 4 bước theo nhà máy; khoá tháng, điều chỉnh sau chốt có nhật ký"),
    "overtime": ("Tăng ca", "WF", "05-overtime.png", "Overtime Type (150/200/300 %), Overtime Slip, Shift Type",
                 "Đề nghị tăng ca: người lao động đồng ý trước, CEO duyệt; trần BLLĐ 2019 điều 107 theo ngày, tháng, năm; chỉ trả giờ đã duyệt"),
    "payroll": ("Lương Việt Nam", "PAY", "10-payroll.png", "Salary Component/Structure, Payroll Entry, Salary Slip, Additional Salary, erpnextvn",
                "BHXH/BHYT/BHTN có trần theo ngày hiệu lực, thuế TNCN 5 bậc 2026, công thức sinh từ YAML; chỉ tính khi kỳ công đã khoá; CEO ký; kế toán xác nhận chi bằng chứng từ"),
    "payroll_compliance": ("Tuân thủ và quản trị lương", "PAY", None, "Salary Slip, Payroll Entry, Journal Entry",
                           "Lương đổi giữa kỳ theo quyết định; chặn gửi ký khi biến động lớn chưa giải trình; bảng lương đã ký bất biến; báo cáo thuế, BHXH, sổ lao động"),
    "travel_finance": ("Công tác, tạm ứng, quyết toán", "TRV · FIN", "09-travel.png", "Travel Request, Employee Advance, Expense Claim, Payment Entry",
                       "Chống trùng lịch, tự ghi công đi công tác; tạm ứng chi có chứng từ ngân hàng; quyết toán 3 nhánh; tạm ứng quá hạn thành khấu trừ lương"),
    "organization": ("Tổ chức và định biên", "ORG", "02-workforce.png", "Company, Department, Designation, Staffing Plan, Organizational Chart",
                     "Tuyến phê duyệt tách khỏi sơ đồ hành chính; định biên theo vị trí; thay đổi cơ cấu có ngày hiệu lực; cảnh báo dữ liệu tổ chức lệch"),
    "recruitment": ("Tuyển dụng", "TAL", None, "Job Requisition, Job Opening, Job Applicant, Interview, Job Offer",
                    "Đề nghị tuyển có JD và ngày cần người; một ứng viên nhiều hồ sơ; chỉ offer sau vòng cuối; offer qua HR rồi CEO và khoá lương"),
    "lifecycle": ("Vòng đời nhân viên", "CORE · OB · EXIT", None, "Employee, Employee Onboarding, Employee Separation, Exit Interview",
                  "Hợp đồng, người phụ thuộc có chứng từ, giấy tờ có hạn; thử việc theo luật (180/60/30/6 ngày); báo trước nghỉ việc 45/30/3 ngày, quyết toán 14 ngày"),
    "people_ops": ("Vận hành nhân sự", "AST · DEV · BEN · CMP", None, "Asset, Asset Movement, Training Event, Employee Grievance",
                   "Bàn giao tài sản hai bên xác nhận; tài khoản và license phải thu hồi trước khi nghỉ việc; xác nhận đọc chính sách; khiếu nại và kỷ luật có phạm vi xem"),
    "services": ("Dịch vụ nội bộ", "SVC", "11-services.png", "ToDo, Notification, Calendar (nền tảng Frappe)",
                 "Suất ăn tự huỷ khi nghỉ hay đi công tác; đặt phòng họp chống trùng; thư viện có hàng chờ; yêu cầu dịch vụ có SLA; văn thư đi và đến"),
    "survey": ("Khảo sát ẩn danh", "SUR", None, "Web Form (nền tảng Frappe)",
               "Phiên bản câu hỏi; phiếu trả lời không lưu danh tính; chỉ công bố kết quả khi bộ phận đủ ngưỡng người trả lời"),
    "role_experience": ("Không gian làm việc theo vai trò", "GOV · ANL", "06-approval.png", "Workspace, Number Card, Dashboard Chart, Role, User Permission",
                        "Mỗi vai trò một workspace: thẻ việc chờ, biểu đồ, lối tắt; trưởng nhà máy chỉ thấy nhà máy mình; CEO thấy gross/net và hàng đợi ký"),
    "roles": ("Hành trình liền mạch theo vai trò", "GOV", None, "Giao diện gốc của Frappe HR và desk, không màn hình tự làm",
              "Mỗi vai trò một video quay liền mạch cả ngày làm việc thật: chấm công, xin nghỉ, trả lời tăng ca, công tác – tạm ứng – quyết toán, duyệt đơn, chốt kỳ công, ký lương, khảo sát ẩn danh"),
}
# Một vai trò có thể cần nhiều tài khoản (HR = chuyên viên + trưởng phòng + tính lương); roles_stitch.sh nối các clip
# của R1..R6 thành một video ROLE-*.mp4 cho vai trò đó.
JOURNEY_CODE = {"worker": "ROLE-CONG_NHAN", "office": "ROLE-NHAN_VIEN_VP", "factory_head": "ROLE-TRUONG_NHA_MAY",
                "hr": "ROLE-HR", "ceo": "ROLE-CEO", "support": "ROLE-KE_TOAN_QUAN_LY"}
DOMAINS = [("WF", "Chấm công, nghỉ, tăng ca", "leave · attendance · overtime"), ("PAY", "Lương", "payroll · payroll_compliance"),
           ("FIN", "Tạm ứng, chi phí", "travel_finance"), ("TRV", "Công tác", "travel_finance"), ("CORE", "Hồ sơ nhân sự", "lifecycle"),
           ("ORG", "Tổ chức", "organization"), ("TAL", "Tuyển dụng", "recruitment"), ("OB", "Hội nhập, thử việc", "lifecycle"),
           ("EXIT", "Nghỉ việc", "lifecycle · people_ops"), ("AST", "Tài sản, tài khoản", "people_ops"), ("DEV", "Đào tạo, phát triển", "people_ops"),
           ("BEN", "Phúc lợi", "people_ops"), ("CMP", "Tuân thủ", "people_ops"), ("SVC", "Dịch vụ nội bộ", "services"),
           ("SUR", "Khảo sát", "survey"), ("GOV", "Quản trị, phân quyền", "role_experience · mọi workflow"), ("ANL", "Báo cáo, dashboard", "role_experience")]
ROLE_ORDER = ["worker", "office", "factory_head", "hr", "ceo", "support"]


def b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def img_uri(path):
    kind = "jpeg" if str(path).lower().endswith((".jpg", ".jpeg")) else "png"
    return f"data:image/{kind};base64,{b64(path)}"


def seconds(stamp):
    parts = [int(p) for p in str(stamp or "0").split(":") if p.isdigit()]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def load(run_dir):
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    stories = coverage.load_stories()
    roles = coverage.load_roles()
    module_of = {}
    for m in stories:
        for s in m.get("stories", []):
            for c in s.get("cases") or []:
                module_of.setdefault(c, m["module"])
    for r in data["results"]:
        if r["id"].startswith("RV-"):  # the role journeys are not a story module: they belong to the role slides
            module_of[r["id"]] = "roles"
    cov = coverage.compute(data["results"], evidence_root=run_dir, videos=data.get("videos", []))
    return data, stories, roles, module_of, cov


class Deck:
    def __init__(self, run_dir, data, stories, roles, module_of, cov, diagrams):
        self.run_dir, self.data, self.stories, self.roles, self.module_of, self.cov = run_dir, data, stories, roles, module_of, cov
        self.diagrams = diagrams
        self.results = data["results"]
        self.slides, self.blobs = [], []
        self.video_id = {}
        self.role_of_account = {}
        for r in roles:
            for a in r.get("accounts", []):
                self.role_of_account[str(a).split(" ")[0]] = r["key"]
        self.by_module = defaultdict(list)
        for r in self.results:
            self.by_module[self.module_of.get(r["id"], "khác")].append(r)
        self.passed = sum(r["status"] == "Đạt" for r in self.results)
        self.tests = {}

    # ---------------------------------------------------------------- media registry
    def blob(self, path, mime):
        self.blobs.append((len(self.blobs), mime, b64(path)))
        return len(self.blobs) - 1

    def video(self, v):
        if v["file"] not in self.video_id:
            mp4 = coverage.video_media(self.run_dir, v["file"])
            if not mp4 or not Path(mp4).is_file():
                return None
            self.video_id[v["file"]] = self.blob(mp4, "video/mp4")
        return self.video_id[v["file"]]

    def shot(self, row, width=None):
        path = self.run_dir / (row.get("shot") or "")
        if not row.get("shot") or not path.is_file():
            return ""
        style = f' style="width:{width}px"' if width else ""
        return f'<img class="p-shot" loading="lazy" src="{img_uri(path)}" alt="{E(row["id"])}" title="{E(row["id"])}: {E(row["function"])}"{style}>'

    # ---------------------------------------------------------------- slide frame
    def add(self, title, sec, body, kind="paper", foot=("TLC HRM trên Frappe HR · MVP", ""), extra=""):
        n = len(self.slides) + 1
        self.slides.append(f'<section class="slide {kind}{extra}" data-title="{E(title)}"><div class="rail"><span class="num">{n:02d}</span>'
                           f'<span class="sec">{E(sec)}</span><span class="num tot"></span></div><div class="frame">{body}</div>'
                           f'<div class="foot"><span>{foot[0]}</span><span>{foot[1] or "Run " + E(self.data["run"])}</span></div></section>')

    @staticmethod
    def head(kicker, title):
        return f'<div class="kicker">{kicker}</div><h2 class="sm">{title}</h2>'

    def video_player(self, videos):
        """A player for one or more videos with a case chapter list per video."""
        tabs, panes = [], []
        for v in videos:
            vid = self.video(v)
            if vid is None:
                continue
            cases = [r for r in self.results if r.get("video") == v["file"]]
            chapters = "".join(f'<button class="p-ch {"ok" if r["status"] == "Đạt" else "ko"}" data-t="{seconds(r.get("time"))}">'
                               f'<b>{E(r["id"])}</b> {E(r["function"])}<span>{E(r.get("time") or "")}</span></button>' for r in cases)
            module = MODULES.get(self.module_of.get(cases[0]["id"]) if cases else "", (v.get("code", ""),))[0]
            tabs.append((len(panes), f'{v["account"]} · {module} ({len(cases)} ca)'))
            panes.append(f'<div class="p-pane{" on" if not panes else ""}"><video class="p-video" controls preload="none" data-blob="{vid}"></video>'
                         f'<div class="p-chapters">{chapters or "<i>Không có ca gắn video</i>"}</div></div>')
        if not panes:
            return '<p class="lead">Không có video cho vai trò này trong lượt chạy.</p>'
        if len(tabs) > 5:
            picker = '<select class="p-pick">' + "".join(f'<option value="{i}">{E(t)}</option>' for i, t in tabs) + '</select>'
        else:
            picker = "".join(f'<button class="p-tab{" on" if i == 0 else ""}" data-i="{i}">{E(t)}</button>' for i, t in tabs)
        return f'<div class="p-player"><div class="p-tabs">{picker}</div>{"".join(panes)}</div>'

    # ---------------------------------------------------------------- slides
    def cover(self):
        modules = len({self.module_of.get(r["id"]) for r in self.results})
        brd = sum(bool(r["stories"]) for r in self.cov["brd"])
        body = (f'<div class="p-cover"><div class="brand">Đề xuất triển khai · Bằng chứng nghiệm thu · {E(self.data["run"][:8])}</div>'
                '<h1>TLC HRM<br>trên Frappe HR:<br><span>quy trình thật của từng vai trò.</span></h1>'
                '<p class="sub">Giao diện chuẩn Frappe cho mọi người. TLC chỉ thêm luật Việt Nam, tuyến duyệt và số liệu đúng việc. '
                'Mọi thứ trong tài liệu này được quay lại trên hệ thống đang chạy.</p>'
                f'<div class="p-meta"><div>NGHIỆM THU<b>{self.passed}/{len(self.results)} ca đạt</b></div><div>PHÂN HỆ UAT<b>{modules} phân hệ, 17 nhóm BRD</b></div>'
                f'<div>VIDEO<b>{len(self.data.get("videos", []))} phiên theo vai trò</b></div>'
                f'<div>THAO TÁC THẬT<b>{sum(1 for r in self.results if r.get("ui_ops"))}/{len(self.results)} ca có cú nhấp/phím</b></div>'
                f'<div>YÊU CẦU BRD<b>{brd}/{len(self.cov["brd"])} đã gắn story</b></div></div></div>')
        self.add("Trang bìa", "TLC HRM", body, kind="night", foot=("Frappe 16 · ERPNext 16 · HRMS 16 · erpnextvn · tlc_hr", "Dữ liệu demo hư cấu, 60 nhân sự"))

    def pains(self):
        rows = "".join(f'<tr><td><b>{E(r["title"])}</b><small>{E(r.get("people", ""))}</small></td><td><ul>{"".join(f"<li>{E(p)}</li>" for p in r.get("pain_points", [])[:4])}</ul></td>'
                       f'<td><ul>{"".join(f"<li>{E(p)}</li>" for p in r.get("improvements", [])[:4])}</ul></td></tr>' for r in self.roles)
        body = self.head("VÌ SAO THAY ĐỔI", "Mỗi vai trò có <em>nỗi đau riêng</em>; giải pháp đi theo việc hằng ngày của họ.") + \
            f'<div class="p-scroll"><table class="p-table"><thead><tr><th>Vai trò</th><th>Hôm nay</th><th>Trên hệ thống mới</th></tr></thead><tbody>{rows}</tbody></table></div>'
        self.add("Nỗi đau theo vai trò", "Bối cảnh", body, foot=("Nguồn: phỏng vấn vai trò và roles.yaml của bộ UAT", ""))

    def principles(self):
        cards = [("Giao diện chuẩn Frappe", "Nhân viên dùng app Frappe HR (/hrms). Quản lý, HR, CEO dùng desk với workspace theo vai trò. Không có portal tự làm, nên nâng cấp Frappe không vỡ giao diện."),
                 ("TLC chỉ thêm phần riêng", "Luật Việt Nam (BLLĐ 2019, thuế TNCN 2026, BHXH), tuyến duyệt của TLC, chốt công theo nhà máy. Phần còn lại dùng nguyên tính năng HRMS."),
                 ("Cấu hình là khai báo", "Vai trò, trường, quyền, workflow, thẻ, workspace, ca, tham số lương nằm trong YAML. Lệnh `bench tlc config plan` cho thấy khác biệt trước khi ghi, giống customizing SAP."),
                 ("Code có lớp, test được", "Luật nghiệp vụ là Python thuần (domain), không phụ thuộc Frappe; test chạy không cần cơ sở dữ liệu. Frappe chỉ là lớp giao tiếp và lưu trữ.")]
        body = self.head("NGUYÊN TẮC GIẢI PHÁP", "Dùng tối đa <em>chuẩn Frappe</em>, tuỳ biến đúng chỗ, và tuỳ biến nào cũng kiểm chứng được.") + \
            '<div class="grid g4">' + "".join(f'<div class="card"><h3>{E(t)}</h3><p>{E(d)}</p></div>' for t, d in cards) + '</div>'
        self.add("Nguyên tắc", "Giải pháp", body)

    def architecture(self):
        layers = [("interface", "Controller DocType, doc_events, API, lệnh bench tlc", "Đổi tài liệu Frappe thành lệnh, đổi lỗi nghiệp vụ thành thông báo"),
                  ("application", "Use case: Leave, Overtime, Attendance, Payroll…", "Chỉ gọi port, không biết Frappe"),
                  ("domain", "Luật: trần tăng ca, máy trạng thái kỳ công, PIT/BHXH theo ngày hiệu lực", "Python thuần, unit test không cần DB"),
                  ("infrastructure", "Repository Frappe cài port; applier customizing YAML", "Chỗ duy nhất đọc ghi Frappe"),
                  ("customizing/*.yaml", "Vai trò, quyền, 8 workflow, thẻ, workspace, ca, lương", "validate · plan · apply · export")]
        rows = "".join(f'<tr><td><code>{E(a)}</code></td><td>{E(b)}</td><td>{E(c)}</td></tr>' for a, b, c in layers)
        ops = ("<pre class='p-code'>bench --site tlc-hr.local tlc config validate   # kiểm YAML theo data contract\n"
               "bench --site tlc-hr.local tlc config plan       # khác biệt site ↔ YAML\n"
               "bench --site tlc-hr.local tlc config apply      # ghi phần khác biệt\n"
               "bench --site tlc-hr.local tlc doctor            # ca, địa điểm, người duyệt, tài khoản, kỳ công\n"
               "bench --site tlc-hr.local run-tests --app tlc_hr</pre>")
        body = self.head("KIẾN TRÚC", "App <em>tlc_hr</em> theo Clean Architecture, chạy trên k3s cùng Frappe chuẩn.") + \
            f'<div class="grid g2"><div><table class="p-table"><thead><tr><th>Lớp</th><th>Chứa gì</th><th>Quy tắc</th></tr></thead><tbody>{rows}</tbody></table></div>' \
            f'<div><div class="card"><h3>Bảo trì như SAP</h3><p>Sửa YAML hoặc sửa trên desk rồi export về git; plan → commit → build image → migrate tự apply.</p>{ops}</div></div></div>'
        self.add("Kiến trúc", "Giải pháp", body, kind="paper", foot=("docs/ARCHITECTURE.md · docs/CONFIGURATION.md · docs/OPERATIONS.md trong repo tlc_hr", ""))

    def domain_map(self):
        counts = {d["domain"]: d for d in self.cov["domains"]}
        rows = ""
        for code, label, modules in DOMAINS:
            d = counts.get(code, {})
            rows += (f'<tr><td><b>{code}</b></td><td>{E(label)}</td><td>{E(modules)}</td><td class="n">{d.get("total", "")}</td>'
                     f'<td class="n">{d.get("passed", "")}</td></tr>')
        mod_rows = ""
        for key, (title, dom, _dg, native, tlc) in MODULES.items():
            rs = self.by_module.get(key, [])
            ok = sum(r["status"] == "Đạt" for r in rs)
            mod_rows += (f'<tr><td><b>{E(title)}</b><small>{E(dom)}</small></td><td>{E(native)}</td><td>{E(tlc)}</td>'
                         f'<td class="n {"ok" if rs and ok == len(rs) else "ko"}">{ok}/{len(rs)}</td></tr>')
        body = self.head("17 NHÓM YÊU CẦU → 13 PHÂN HỆ", "Phần nào <em>Frappe có sẵn</em>, phần nào TLC thêm, và đã nghiệm thu đến đâu.") + \
            f'<div class="p-scroll"><table class="p-table"><thead><tr><th>Phân hệ</th><th>Chuẩn Frappe / HRMS dùng nguyên</th><th>TLC tuỳ biến</th><th>UAT</th></tr></thead><tbody>{mod_rows}</tbody></table>' \
            f'<h3 style="margin:26px 0 10px">Nhóm yêu cầu BRD</h3><table class="p-table"><thead><tr><th>Mã</th><th>Nhóm</th><th>Phân hệ đáp ứng</th><th>Số YC</th><th>Có bằng chứng đạt</th></tr></thead><tbody>{rows}</tbody></table></div>'
        self.add("Bản đồ phân hệ", "Phạm vi", body, foot=("Đạt = yêu cầu có story, AC và ca UAT đạt trong lượt chạy này", ""))

    def journey_video(self, role_key):
        """The continuous video of one role's whole day, joined by roles_stitch.sh from that role's sessions."""
        name = JOURNEY_CODE.get(role_key)
        if not name:
            return None
        for candidate in (self.run_dir / "videos" / f"{name}.mp4", self.run_dir / f"{name}.mp4"):
            if candidate.is_file():
                return {"file": f"videos/{name}.mp4", "account": name, "code": "NGAY-LAM-VIEC"}
        return None

    def journey_player(self, v, cases):
        vid = self.video(v)
        if vid is None:
            return ""
        steps = "".join(f'<li><b>{E(r["id"])}</b> {E(r["function"])}</li>' for r in cases)
        return (f'<div class="p-journey"><div class="p-jhead">Cả ngày làm việc của vai trò này, quay liền mạch '
                f'<span>{len(cases)} việc</span></div><video class="p-video" controls preload="none" data-blob="{vid}"></video>'
                f'<ol class="p-jsteps">{steps}</ol></div>')

    def role_slides(self):
        videos_by_role = defaultdict(list)
        for v in self.data.get("videos", []):
            videos_by_role[self.role_of_account.get(v["account"], "khác")].append(v)
        all_stories = {s["id"]: s for m in self.stories for s in m.get("stories", [])}
        for key in ROLE_ORDER + sorted(set(videos_by_role) - set(ROLE_ORDER)):
            role = next((r for r in self.roles if r["key"] == key), None)
            vids = videos_by_role.get(key, [])
            if not role and not vids:
                continue
            title = role["title"] if role else "Tài khoản khác"
            accounts = {v["account"] for v in vids}
            cases = [r for r in self.results if r["account"].split("@")[0] in accounts]
            ok = sum(r["status"] == "Đạt" for r in cases)
            journey = self.journey_video(key)
            jcases = [r for r in self.results if r["id"].startswith("RV-")] if journey else []
            acts = ""
            for sid in (role or {}).get("journeys", []):
                s = all_stories.get(sid)
                if s:
                    acts += f'<li><b>{E(sid)}</b> {E(s.get("title", ""))}</li>'
            side = (f'<div class="p-side"><div class="card"><h3>{E(title)}</h3><p class="muted">{E((role or {}).get("interface", ""))}</p>'
                    f'<p><span class="p-pill ok">{ok}/{len(cases)} ca đạt</span> <span class="p-pill">{len(vids)} video</span>'
                    f'<span class="p-pill">{sum(1 for r in cases if r.get("ui_ops"))} ca có thao tác thật</span></p>'
                    f'<h4>Hoạt động trên hệ thống</h4><ul class="p-acts">{acts or "".join(f"<li>{E(c)}</li>" for c in sorted({r["function"] for r in cases})[:12])}</ul></div></div>')
            left = (self.journey_player(journey, jcases) if journey else "") + self.video_player(vids)
            body = self.head("QUY TRÌNH THEO VAI TRÒ", f'{E(title)}: <em>làm việc thật</em> trên giao diện chuẩn.') + \
                f'<div class="p-rolegrid">{left}{side}</div>'
            self.add(f"Vai trò · {title}", "Vai trò", body,
                     foot=("Trên: cả ngày làm việc quay liền mạch · Dưới: từng ca, bấm để tua đến đúng đoạn · desktop 1366×820", ""))

    def module_slides(self):
        for key, (title, dom, dg, native, tlc) in MODULES.items():
            rs = self.by_module.get(key, [])
            if not rs:
                continue
            ok = sum(r["status"] == "Đạt" for r in rs)
            picks = [r for r in rs if r.get("shot")]
            picks = [picks[i] for i in sorted({0, len(picks) // 2, len(picks) - 1})] if picks else []
            diagram = self.diagrams / dg if dg and self.diagrams else None
            left = (f'<figure class="p-dg"><img src="{img_uri(diagram)}" alt="Sơ đồ {E(title)}"><figcaption>Quy trình thiết kế</figcaption></figure>'
                    if diagram and diagram.is_file() else
                    f'<div class="card"><h3>Chuẩn Frappe</h3><p>{E(native)}</p><h3 style="margin-top:18px">TLC thêm</h3><p>{E(tlc)}</p></div>')
            shots = "".join(f'<figure class="p-fig">{self.shot(r)}<figcaption><span class="p-pill {"ok" if r["status"] == "Đạt" else "ko"}">{E(r["status"])}</span> '
                            f'<b>{E(r["id"])}</b> {E(r["function"])}<small>{E(r["role"])}</small></figcaption></figure>' for r in picks)
            body = self.head(f"PHÂN HỆ · {E(dom)}", f'{E(title)}: <em>{ok}/{len(rs)} ca đạt</em> trên hệ thống thật.') + \
                f'<div class="p-modgrid"><div>{left}</div><div class="p-shots">{shots}</div></div>' \
                f'<p class="p-note"><b>Chuẩn Frappe:</b> {E(native)} · <b>TLC:</b> {E(tlc)}</p>'
            self.add(f"Phân hệ · {title}", "Phân hệ", body, foot=("Trái: quy trình thiết kế · Phải: màn hình thật trong lượt UAT (bấm để phóng to)", ""))

    def results_slide(self):
        rows = ""
        for key, (title, *_rest) in MODULES.items():
            rs = self.by_module.get(key, [])
            if not rs:
                continue
            ok = sum(r["status"] == "Đạt" for r in rs)
            real = sum(1 for r in rs if r.get("ui_ops"))
            pct = ok * 100 // len(rs)
            rows += (f'<tr><td>{E(title)}</td><td class="n">{len(rs)}</td><td class="n">{ok}</td>'
                     f'<td class="n {"ok" if real == len(rs) else "ko"}">{real}/{len(rs)}</td>'
                     f'<td><div class="p-bar"><i style="width:{pct}%"></i></div></td></tr>')
        roles = Counter(r["role"] for r in self.results)
        body = self.head("KẾT QUẢ NGHIỆM THU", f'<em>{self.passed}/{len(self.results)} ca đạt</em> — mỗi ca phải là '
                                               f'<em>thao tác thật trên giao diện</em> (đếm cú nhấp và phím trong trang), '
                                               f'quay video desktop, dữ liệu reset trước khi chạy.') + \
            f'<div class="grid g2"><div class="p-scroll"><table class="p-table"><thead><tr><th>Phân hệ</th><th>Ca</th><th>Đạt</th><th>Thao tác UI</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>' \
            f'<div class="card"><h3>Ca theo người thực hiện</h3><table class="p-table">{"".join(f"<tr><td>{E(k)}</td><td class=n>{v}</td></tr>" for k, v in roles.most_common(14))}</table></div></div>'
        self.add("Kết quả UAT", "Nghiệm thu", body, foot=(f"Lượt {E(self.data['run'])} · image {E(str(self.data.get('image', '')))}", ""))

    def coverage_slide(self):
        states = self.cov["stories"]
        traced = lambda r: r["stories"] and all(states.get(s) == coverage.PASSED for s in r["stories"])  # noqa: E731
        rows = ""
        for d in self.cov["domains"]:
            reqs = [r for r in self.cov["brd"] if r["domain"] == d["domain"]]
            if not reqs:
                continue
            linked = sum(bool(r["stories"]) for r in reqs)
            rows += (f'<tr><td><b>{E(d["domain"])}</b></td><td>{E(d["label"])}</td><td class="n">{len(reqs)}</td><td class="n">{linked}</td>'
                     f'<td class="n">{sum(bool(traced(r)) for r in reqs)}</td><td class="n">{d["passed"]}</td>'
                     f'<td><div class="p-bar"><i style="width:{linked * 100 // len(reqs)}%"></i></div></td></tr>')
        brd = self.cov["brd"]
        linked = sum(bool(r["stories"]) for r in brd)
        full = sum(v == coverage.PASSED for v in states.values())
        body = self.head("PHỦ YÊU CẦU", f'<em>{linked}/{len(brd)}</em> yêu cầu BRD đã gắn với story; hồ sơ truy vết từng AC là việc còn lại.') + \
            f'<div class="p-scroll"><table class="p-table"><thead><tr><th>Nhóm</th><th>Tên</th><th>YC</th><th>Có story</th><th>Story đủ AC↔ca, ca đạt</th>' \
            f'<th>Đạt chuẩn kiểm toán</th><th>Có story</th></tr></thead><tbody>{rows}</tbody></table></div>' \
            f'<p class="p-note">Hệ thống: {self.passed}/{len(self.results)} ca UAT đạt. Hồ sơ: {full}/{len(states)} story đã ánh xạ đủ mọi AC tới ca. ' \
            '"Đạt chuẩn kiểm toán" chỉ tính khi yêu cầu có câu xác nhận hành vi gắn với ca cụ thể và mọi ca đạt; chưa yêu cầu nào được khai báo theo cách này. ' \
            'Việc của đợt kế tiếp: bổ sung ánh xạ AC↔ca và câu xác nhận cho từng yêu cầu, rồi chạy lại để con số này phản ánh đúng.</p>'
        self.add("Phủ BRD", "Nghiệm thu", body, foot=("Đo bằng uat/coverage.py trên catalogue BRD 322 yêu cầu (không phát hành trong repo)", ""))

    def operations(self):
        items = [("Triển khai", "Một image cho mọi pod (backend, worker, scheduler, frontend); `bench migrate` áp YAML; rollback bằng tag image trước."),
                 ("Kiểm thử", "Unit (luật, không cần DB) + tích hợp trên site demo + UAT Playwright có video. CI GitHub chạy ruff và unit test mỗi lần push."),
                 ("Thay đổi cấu hình", "HR đề xuất, IT sửa YAML hoặc export từ desk; `tlc config plan` trên site thử; commit; build; migrate; `tlc doctor`."),
                 ("Bàn giao", "docs/ARCHITECTURE.md (lớp, cách thêm phân hệ), CONFIGURATION.md (tham chiếu YAML, đối chiếu SAP), OPERATIONS.md (vận hành, sự cố đã gặp).")]
        body = self.head("VẬN HÀNH VÀ BẢO TRÌ", "Ai cũng <em>tiếp cận được</em>: cấu hình, test, sự cố đều có chỗ và có lệnh.") + \
            '<div class="grid g4">' + "".join(f'<div class="card"><h3>{E(t)}</h3><p>{E(d)}</p></div>' for t, d in items) + '</div>' + \
            self.stats_row()
        self.add("Vận hành", "Bảo trì", body)

    def stats_row(self):
        stats = [(self.tests.get("unit"), "unit test thuần, không cần DB"), (self.tests.get("integration"), "test tích hợp trên site demo"),
                 (f"{self.passed}/{len(self.results)}", "ca UAT đạt, có video"), (self.tests.get("workflows"), "workflow duyệt khai báo YAML")]
        return '<div class="p-stats">' + "".join(f'<div><b>{E(str(v))}</b><span>{E(t)}</span></div>' for v, t in stats if v) + '</div>'

    def roadmap(self):
        steps = [("Đã xong (MVP)", "13 phân hệ trên Frappe HR, workflow TLC, lương VN 2026, UAT theo vai trò có video, kiến trúc lớp + YAML + CLI"),
                 ("Cần TLC quyết định", "Toạ độ và bán kính thật của 3 nhà máy; danh sách người duyệt thật; mẫu file ngân hàng và VNPT BHXH; dữ liệu nhân sự thật để chuyển đổi"),
                 ("Pilot 1 nhà máy + hội sở", "Nhập dữ liệu thật, chạy song song 1 kỳ công và 1 kỳ lương với Excel, so từng phiếu"),
                 ("Mở rộng", "Trợ lý AI chỉ đọc và tạo nháp (Raven + Mistral, cần duyệt pháp lý dữ liệu), máy chấm công, SSO Keycloak, sao lưu và giám sát production")]
        body = self.head("LỘ TRÌNH", "Từ <em>MVP đã chứng minh</em> đến pilot có kiểm soát.") + \
            '<div class="p-steps">' + "".join(f'<div class="card"><span class="p-n">{i + 1}</span><h3>{E(t)}</h3><p>{E(d)}</p></div>' for i, (t, d) in enumerate(steps)) + '</div>'
        self.add("Lộ trình", "Đề xuất", body, kind="night")

    def appendix(self):
        for key, (title, *_rest) in list(MODULES.items()) + [("khác", ("Khác",))]:
            rs = self.by_module.get(key, [])
            if not rs:
                continue
            rows = ""
            for r in rs:
                vid = self.video_id.get(r.get("video")) if r.get("video") else None
                if vid is None and r.get("video"):
                    v = next((v for v in self.data.get("videos", []) if v["file"] == r["video"]), None)
                    vid = self.video(v) if v else None
                play = (f'<button class="p-play" data-blob="{vid}" data-t="{seconds(r.get("time"))}">▶ {E(r.get("time") or "")}</button>'
                        if vid is not None else "")
                ops = r.get("ui_ops")
                opscell = "—" if ops is None else (f'<span class="p-pill ok">{ops}</span>' if ops else '<span class="p-pill ko">0</span>')
                rows += (f'<tr><td><b>{E(r["id"])}</b><small>{E(r["account"])}</small></td><td>{E(r["function"])}<small>{E(r.get("steps", ""))}</small></td>'
                         f'<td>{E(r.get("expected", ""))}</td><td>{E(r.get("actual", ""))}</td>'
                         f'<td><span class="p-pill {"ok" if r["status"] == "Đạt" else "ko"}">{E(r["status"])}</span>{play}</td>'
                         f'<td class="n">{opscell}</td><td>{self.shot(r, 150)}</td></tr>')
            body = self.head(f"PHỤ LỤC · {E(title)}", f'Toàn bộ <em>{len(rs)} ca</em>: bước, kết quả mong đợi, thực tế, '
                                                      f'<em>số cú nhấp/phím thật trong trang</em>, ảnh, video.') + \
                f'<div class="p-scroll tall"><table class="p-table p-cases"><thead><tr><th>Ca</th><th>Chức năng / bước</th><th>Mong đợi</th><th>Thực tế</th><th>KQ</th><th>Thao tác UI</th><th>Ảnh</th></tr></thead><tbody>{rows}</tbody></table></div>'
            self.add(f"Phụ lục · {title}", "Phụ lục", body, foot=("Cuộn trong bảng · bấm ▶ để xem đúng đoạn video · bấm ảnh để phóng to", ""))

    def build(self):
        self.cover()
        self.pains()
        self.principles()
        self.architecture()
        self.domain_map()
        self.role_slides()
        self.module_slides()
        self.results_slide()
        self.coverage_slide()
        self.operations()
        self.roadmap()
        self.appendix()


EXTRA_CSS = """
.slide .rail .tot:empty{display:none}
.p-cover{position:absolute;inset:0;padding:150px 132px 0;color:#F6EEF3}
.p-cover .brand{font-family:var(--font-mono);letter-spacing:.16em;text-transform:uppercase;color:#7FD3D6;font-size:20px;margin-bottom:34px}
.p-cover h1{font-family:var(--font-display);font-size:104px;line-height:1.02;font-weight:800}
.p-cover h1 span{color:#E7B9D9}
.p-cover .sub{font-size:30px;line-height:1.5;max-width:1300px;margin-top:34px;color:rgba(246,238,243,.82)}
.p-meta{position:absolute;left:132px;right:132px;bottom:120px;display:grid;grid-template-columns:repeat(5,1fr);gap:24px}
.p-meta div{border-top:2px solid rgba(255,255,255,.25);padding-top:16px;font-family:var(--font-mono);font-size:17px;letter-spacing:.12em;color:#7FD3D6}
.p-meta b{display:block;font-family:var(--font-body);letter-spacing:0;font-size:30px;color:#fff;margin-top:8px}
.g2{grid-template-columns:1fr 1fr}.g4{grid-template-columns:repeat(4,1fr)}
.card h3{font-size:26px;margin-bottom:12px;color:var(--plum)}.night .card h3{color:#E7B9D9}.card p{font-size:20px;line-height:1.5}
.card h4{font-size:18px;margin:18px 0 8px;font-family:var(--font-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--teal)}
.p-table{width:100%;border-collapse:collapse;font-size:18px;line-height:1.35;background:#fff}
.p-table th{text-align:left;font-family:var(--font-mono);font-size:14px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);padding:10px 12px;border-bottom:2px solid var(--line);position:sticky;top:0;background:#fff;z-index:1}
.p-table td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
.p-table td small{display:block;color:var(--muted);font-size:14px;margin-top:3px}
.p-table td.n{text-align:right;font-family:var(--font-mono)}.p-table td.ok{color:#1d7a3a;font-weight:700}.p-table td.ko{color:var(--rose);font-weight:700}
.p-table ul{margin:0;padding-left:18px}.p-table li{margin:2px 0}
.p-scroll{overflow:auto;max-height:800px;margin-top:20px;border:1px solid var(--line);border-radius:12px}
.p-scroll.tall{max-height:820px}
.p-code{background:#241A22;color:#F3E9EF;font-family:var(--font-mono);font-size:16px;padding:18px;border-radius:12px;margin-top:16px;white-space:pre-wrap}
.p-rolegrid{display:grid;grid-template-columns:1.55fr 1fr;gap:28px;margin-top:22px;height:790px}
.p-player{display:flex;flex-direction:column;min-height:0}
.p-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.p-tab{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 14px;font-size:15px;cursor:pointer;font-family:var(--font-mono)}
.p-tab.on{background:var(--plum);color:#fff;border-color:var(--plum)}
.p-pick{font-size:18px;padding:8px 12px;border-radius:10px;border:1px solid var(--line);width:100%;font-family:var(--font-body)}
.p-pane{display:none;flex:1;min-height:0;flex-direction:column}.p-pane.on{display:flex}
.p-video{width:100%;max-height:500px;background:#111;border-radius:12px}
.p-rolegrid>div:first-child{overflow:auto;min-height:0;display:flex;flex-direction:column;padding-right:4px}
.p-journey{border:1px solid var(--teal);border-radius:14px;padding:12px 14px;background:#fff;margin-bottom:14px;flex:none}
.p-jhead{font-family:var(--font-mono);font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:var(--teal);margin-bottom:8px}
.p-jhead span{color:var(--muted);text-transform:none;letter-spacing:0}
.p-jsteps{margin:8px 0 0;padding-left:20px;font-size:15px;line-height:1.4;max-height:160px;overflow:auto}
.p-jsteps b{font-family:var(--font-mono);font-size:12px;color:var(--teal)}
.p-chapters{overflow:auto;margin-top:10px;flex:1;display:flex;flex-direction:column;gap:4px}
.p-ch{text-align:left;border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 10px;font-size:15px;cursor:pointer;display:flex;gap:8px;align-items:baseline}
.p-ch span{margin-left:auto;font-family:var(--font-mono);color:var(--muted)}.p-ch.ok b{color:#1d7a3a}.p-ch.ko b{color:var(--rose)}
.p-ch:hover{border-color:var(--teal)}
.p-side .card{height:790px;overflow:auto}
.p-acts{padding-left:20px;font-size:17px;line-height:1.45}.p-acts b{font-family:var(--font-mono);font-size:13px;color:var(--teal)}
.p-pill{display:inline-block;border-radius:999px;padding:3px 12px;font-size:15px;font-weight:700;background:var(--plum-soft);color:var(--plum)}
.p-pill.ok{background:#DDF1E3;color:#1d7a3a}.p-pill.ko{background:var(--rose-soft);color:var(--rose)}
.p-modgrid{display:grid;grid-template-columns:1fr 1.15fr;gap:28px;margin-top:20px;height:700px}
.p-dg{margin:0;height:100%;display:flex;flex-direction:column}.p-dg img{width:100%;height:640px;object-fit:contain;background:#fff;border:1px solid var(--line);border-radius:14px}
.p-dg figcaption,.p-fig figcaption{font-size:15px;color:var(--muted);margin-top:6px}
.p-shots{display:flex;flex-direction:column;gap:12px;overflow:auto}
.p-fig{margin:0}.p-fig figcaption small{display:block}
.p-shot{width:100%;border:1px solid var(--line);border-radius:10px;cursor:zoom-in;display:block;background:#fff}
.p-cases .p-shot{width:150px}
.p-note{font-size:18px;color:var(--muted);margin-top:14px;line-height:1.45}
.p-bar{height:14px;background:var(--paper-2);border-radius:7px;overflow:hidden;min-width:160px}.p-bar i{display:block;height:100%;background:var(--teal)}
.p-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:28px;margin-top:60px}.p-stats div{border-top:3px solid var(--teal);padding-top:16px}
.p-stats b{display:block;font-family:var(--font-display);font-size:84px;color:var(--plum);line-height:1}.p-stats span{font-size:20px;color:var(--muted)}
.p-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;margin-top:40px}.p-n{font-family:var(--font-display);font-size:64px;color:#E7B9D9;display:block}
.p-play{display:block;margin-top:8px;border:1px solid var(--teal);background:#fff;color:var(--teal);border-radius:8px;padding:4px 10px;cursor:pointer;font-family:var(--font-mono);font-size:14px}
.p-modal{position:fixed;inset:0;background:rgba(20,10,18,.88);z-index:2000;display:none;align-items:center;justify-content:center;padding:30px}
.p-modal.on{display:flex}.p-modal img,.p-modal video{max-width:96vw;max-height:92vh;border-radius:10px;background:#fff}
.p-modal .x{position:absolute;top:14px;right:22px;color:#fff;font-size:34px;cursor:pointer}
.deck-nav{position:fixed;right:18px;bottom:14px;z-index:1500;display:flex;gap:8px;align-items:center;font-family:var(--font-mono);font-size:13px;color:#fff;background:rgba(20,10,18,.6);padding:6px 10px;border-radius:999px}
.deck-nav button{background:none;border:0;color:#fff;cursor:pointer;font-size:16px}
.deck-nav select{max-width:280px;font-size:13px}
.progress{position:fixed;left:0;top:0;height:4px;background:var(--teal);z-index:1500;transition:width .3s}
"""

NAV_JS = r"""
const BLOBS = {};
function blobUrl(i){ if(BLOBS[i]) return BLOBS[i]; const el=document.getElementById('b'+i); const bin=atob(el.textContent.trim());
  const a=new Uint8Array(bin.length); for(let k=0;k<bin.length;k++) a[k]=bin.charCodeAt(k);
  BLOBS[i]=URL.createObjectURL(new Blob([a],{type:el.dataset.mime})); return BLOBS[i]; }
const slides=[...document.querySelectorAll('.slide')], stage=document.getElementById('deckStage');
const counter=document.getElementById('counter'), progress=document.getElementById('progress'), jump=document.getElementById('jump');
slides.forEach((s,i)=>{ s.querySelectorAll('.rail .tot').forEach(t=>t.textContent='/'+slides.length); const o=document.createElement('option'); o.value=i; o.textContent=(i+1)+'. '+s.dataset.title; jump.appendChild(o); });
let cur=0;
function scale(){ const f=Math.min(innerWidth/1920,innerHeight/1080); stage.style.transform=`translate(${(innerWidth-1920*f)/2}px,${(innerHeight-1080*f)/2}px) scale(${f})`; }
function show(i){ cur=Math.max(0,Math.min(i,slides.length-1));
  slides.forEach((s,k)=>{ const on=k===cur; s.classList.toggle('active',on); s.classList.toggle('visible',on); if(!on) s.querySelectorAll('video').forEach(v=>v.pause()); });
  counter.textContent=(cur+1)+' / '+slides.length; progress.style.width=((cur+1)/slides.length*100)+'%'; jump.value=cur;
  history.replaceState(null,'','#'+(cur+1));
  slides[cur].querySelectorAll('.p-pane.on video[data-blob], .p-journey video[data-blob]').forEach(v=>{ if(!v.src) v.src=blobUrl(v.dataset.blob); }); }
addEventListener('resize',scale); scale();
document.getElementById('prev').onclick=()=>show(cur-1); document.getElementById('next').onclick=()=>show(cur+1); jump.onchange=()=>show(+jump.value);
addEventListener('keydown',e=>{ if(['INPUT','SELECT','TEXTAREA','VIDEO'].includes(e.target.tagName)) return; if(document.querySelector('.p-modal.on')){ if(e.key==='Escape') closeModal(); return; }
  if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(cur+1);} if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(cur-1);}
  if(e.key==='Home')show(0); if(e.key==='End')show(slides.length-1); });
let lock=false; addEventListener('wheel',e=>{ if(lock||Math.abs(e.deltaY)<30||e.target.closest('.p-scroll,.p-chapters,.p-shots,.p-side .card,.p-modal')) return; lock=true; show(cur+(e.deltaY>0?1:-1)); setTimeout(()=>lock=false,700); },{passive:true});
function pick(p,i){ p.querySelectorAll('.p-tab').forEach(x=>x.classList.toggle('on',+x.dataset.i===i));
  p.querySelectorAll('.p-pane').forEach((x,k)=>{ const on=k===i; x.classList.toggle('on',on); const v=x.querySelector('video'); if(on&&!v.src) v.src=blobUrl(v.dataset.blob); if(!on) v.pause(); }); }
document.querySelectorAll('.p-player').forEach(p=>{ p.querySelectorAll('.p-tab').forEach(t=>t.onclick=()=>pick(p,+t.dataset.i));
  const sel=p.querySelector('.p-pick'); if(sel) sel.onchange=()=>pick(p,+sel.value);
  p.querySelectorAll('.p-ch').forEach(c=>c.onclick=()=>{ const v=c.closest('.p-pane').querySelector('video'); if(!v.src) v.src=blobUrl(v.dataset.blob); v.currentTime=+c.dataset.t; v.play(); }); });
const modal=document.getElementById('modal'), mbody=document.getElementById('mbody');
function closeModal(){ modal.classList.remove('on'); mbody.innerHTML=''; }
document.getElementById('mx').onclick=closeModal; modal.onclick=e=>{ if(e.target===modal) closeModal(); };
document.addEventListener('click',e=>{ const img=e.target.closest('.p-shot, .p-dg img'); if(img){ mbody.innerHTML=`<img src="${img.src}">`; modal.classList.add('on'); return; }
  const b=e.target.closest('.p-play'); if(b){ mbody.innerHTML=`<video controls autoplay src="${blobUrl(b.dataset.blob)}"></video>`; const v=mbody.querySelector('video'); v.addEventListener('loadedmetadata',()=>{v.currentTime=+b.dataset.t;}); modal.classList.add('on'); } });
const h=parseInt((location.hash||'').slice(1),10); show(Number.isFinite(h)?h-1:0);
"""


def theme_css(theme_path):
    text = Path(theme_path).read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", text, re.S).group(1)
    tlc = Path(theme_path).parent / "assets" / "hrm-tlc.css"
    return css + ("\n" + tlc.read_text(encoding="utf-8") if tlc.is_file() else "")


def render(deck, css, xlsx):
    blobs = "".join(f'<script type="text/plain" id="b{i}" data-mime="{m}">{d}</script>' for i, m, d in deck.blobs)
    download = (f'<a download="{E(xlsx.name)}" href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64(xlsx)}" '
                'style="color:#fff">⬇ Excel</a>') if xlsx else ""
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TLC HRM trên Frappe HR · Đề xuất và nghiệm thu · {E(deck.data['run'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,700;9..144,800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{css}{EXTRA_CSS}</style></head><body>
<div class="progress" id="progress"></div>
<div class="deck-viewport"><main class="deck-stage" id="deckStage">{''.join(deck.slides)}</main></div>
<div class="deck-nav"><button id="prev">◀</button><span id="counter"></span><button id="next">▶</button><select id="jump"></select>{download}</div>
<div class="p-modal" id="modal"><span class="x" id="mx">×</span><div id="mbody"></div></div>
{blobs}<script>{NAV_JS}</script></body></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--theme", type=Path, required=True, help="deck HTML whose <style> (and assets/hrm-tlc.css) gives the look")
    parser.add_argument("--diagrams", type=Path, help="directory of the process diagram PNGs")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tests", default="", help="facts for the operations slide, e.g. unit=147,integration=69,workflows=8")
    args = parser.parse_args()
    data, stories, roles, module_of, cov = load(args.run_dir)
    deck = Deck(args.run_dir, data, stories, roles, module_of, cov, args.diagrams)
    deck.tests = dict(kv.split("=", 1) for kv in args.tests.split(",") if "=" in kv)
    deck.build()
    xlsx = next(iter(sorted(args.run_dir.glob("*.xlsx"))), None)
    out = args.out or args.run_dir / f"TLC_HRM_Proposal_UAT_{data['run']}.html"
    out.write_text(render(deck, theme_css(args.theme), xlsx), encoding="utf-8")
    print(f"{out} {out.stat().st_size / 1e6:.1f} MB · {len(deck.slides)} slides · {len(deck.video_id)} videos · {deck.passed}/{len(deck.results)} cases")


if __name__ == "__main__":
    main()
