# Trạng thái mới nhất: BLOCKED — 2026-10-22 10:51:03

Owner yêu cầu chốt bàn giao. Đọc HANDOVER.md và UIFIRST_BLOCKED.md trước phần lịch sử bên dưới. FIN-03 đã đạt; travel_finance 12/13 (1020), payroll_compliance 5/12 (JSON hiện tại 1030), role_experience chưa có run xanh; roles chưa chạy đủ ca. Các sửa cuối finance/roles và wrapper/date của role_experience chưa có lượt xác nhận mới.

Service uifirst disabled, MainPID=0; UAT container và hàng đợi phiên đã hết, lock lấy được. Không chạy full cuối, roles_stitch hoặc finish_pack, không tạo UIFIRST_DONE. Run 1030 trùng phút giữa roles và compliance, không dùng làm release. Không thay app/quyền CEO/Secret, không migrate/rollout/commit/push. Một lệnh ps argv đã lộ demo-password trong log công cụ; owner cần xử lý credential, không chép lại giá trị.

## Lịch sử trước lần bàn giao này

# TLC HRM – trạng thái (2026-10-22 00:08, giờ VN)

## Chủ đề đang chạy: UAT phải quay được THAO TÁC THẬT của từng vai trò

Owner xem video và bác: 154/154 đúng nghiệp vụ nhưng nhiều ca chạy bằng API nên video chỉ chiếu trang chủ
(`payroll_compliance` 0 bước UI/19 API, `role_experience` 4 bước UI/13 ca). Mọi ca phải làm trên UI.

## Harness đã đổi (`tlc-hr-platform/uat/`)

- `lib.py`: `OPS_JS` đếm sự kiện `click|keydown|change|submit` thật trong trang vào `sessionStorage['uat-ops']`
  (phải là IIFE tự chạy — arrow-function Playwright không gọi, bản đầu sai chỗ này nên mọi ca bị báo 0).
  `Session.step(text)` caption + nghỉ 0,7 s; `Session.ops()` cộng dồn mọi tab; `case(..., ui=True)` tự chuyển
  `Không đạt` khi ca `Đạt` mà `ui_ops == 0`; cuối ca giữ 1,6 s ở màn hình kết quả.
- `run_uat.sh`: `flock /tmp/tlc-uat.lock` (nhiều agent không giẫm dữ liệu demo) và **mọi chạy `ONLY=` tự reset**.
- `roles_stitch.sh`: nối clip per-account thành một video ROLE-*.mp4 cho mỗi vai trò.
- Chuẩn + 2 ghi chú sửa lỗi: `auto/UAT_UI_STANDARD.md`.
- Kiểm chứng: `ONLY=attendance` → `20261021-2326` 15/16, bắt đúng `PD-08` (sửa kỳ đã khoá bằng API).

## Ai đang làm gì (01:10)

6 agent chạy từ laptop đã chết vì hết 150 lượt khi chờ hàng đợi `flock` (không phải hết việc).
Toàn bộ 13 journeys + `roles.py` giờ do MỘT agent chạy trên VM đảm nhiệm, không phụ thuộc laptop:

- service `tlc-uifirst` (unit `/etc/systemd/system/tlc-uifirst.service`, script `auto/run_uifirst.sh`),
  mỗi vòng là phiên mới đọc `auto/UIFIRST_PROMPT.md` → bộ nhớ là tệp trên đĩa.
- Phạm vi: 13 `journeys/*.py` (attendance, overtime, leave, payroll, payroll_compliance, travel_finance,
  organization, recruitment, lifecycle, people_ops, services, survey, role_experience) + `roles.py`.
  Cấm sửa `lib.py`, `run_uat.sh`, app, evidence.
- Tiến độ ghi `auto/UIFIRST_PROGRESS.md`; kết thúc `auto/UIFIRST_DONE.md`; kẹt thật `auto/UIFIRST_BLOCKED.md`.
- Bài học đã ghi vào prompt để không khám phá lại: nút Thêm của list mở quick-entry (form thật ở
  `/desk/<slug>/new`); phải gõ ngày theo định dạng người dùng = **dd-mm-yyyy** (trường rỗng bị
  `frappe.client.get` lược bỏ nên nhìn như KeyError); label select bằng tiếng Việt; bấm vào tiêu đề dòng
  trong list, chờ form bằng `cur_frm.doctype` chứ không chờ networkidle.

Việc của tôi (laptop): kiểm chứng chéo kết quả từng module, xử lý GAPS cần sửa app/customizing (phải migrate
nên chỉ làm khi hàng đợi trống), đóng gói deck + offline HTML, W7 Raven+Mistral, build image, Plane/Outline.

Đã phát hiện và cần quyết định nghiệp vụ: `phuong` (TLC Payroll) KHÔNG có quyền đọc `TLC Attendance Period`,
nên không tự xem được vì sao bảng lương bị chặn — cân nhắc mở read cho vai trò này trong
`tlc_hr/customizing/permissions.yaml`.

## Deck `uat/proposal_html.py` — đã sửa xong, chờ lượt UAT mới để dựng lại

- Thêm module `roles` + `JOURNEY_CODE`: slide vai trò có **video journey liền mạch** ở trên, clip per-case ở dưới.
- Cột **"Thao tác UI"** (`ui_ops`) ở bảng kết quả và phụ lục; ô "THAO TÁC THẬT x/y ca" ở trang bìa.
- Regression với run cũ `20261021-2056`: vẫn 43 slide · 106 video · 154/154 (fallback `—`).
- Bản phát hành phải offline tuyệt đối: chạy `python3 /tmp/inline_fonts.py <file>` (inline Google Fonts) —
  bản đang giao ở `~/tlc-hr/deliverables/TLC_HRM_Proposal_UAT_20261021-2056.html` đã inline (58.148.100 B).

## Plane

Board `HRM` = project `f1d730ff-ec07-4869-a1d8-13490fb29516` (workspace `ba-ailab`), API qua
`tools/plane_client.py`. Đã tạo cụm **HRM-576..584** bằng `tools/plane_frp_sync.py` (idempotent theo tên):
FRP-00 chương trình (In Progress) · FRP-01 13 phân hệ (Done) · FRP-02 UAT 154/154 (Done) ·
FRP-03 cổng ui_ops (In Progress) · FRP-04 6 video journey (In Progress) · FRP-05 AI Raven+Mistral (Todo) ·
FRP-06 build image (Todo) · FRP-07 deck+Outline+Plane (In Progress) · FRP-08 GAPS giao diện (Todo).

## Việc còn lại của tôi

1. Gộp kết quả 8 agent; xử lý `auto/GAPS-*.md` (thiếu đường UI thật = sửa `tlc_hr/customizing/*.yaml`/app, migrate).
2. Một lượt full `./run_uat.sh --reset` + `roles_stitch.sh <RUN>`; dựng lại deck và offline HTML;
   copy `~/tlc-hr/deliverables/` + `Z:\New folder (7)\` (nhớ inline font); cập nhật Outline
   `d56f3c60-4259-4b5e-a276-7b98196986fe` (dùng `tools/publish_tlc_frappe_outline.py <run-dir> --apply`,
   ảnh thật lấy từ `out/<RUN>/shots`).
3. FRP-05: Raven (pin) vào `apps.json` + Mistral qua Secret `tlc-hr-ai` (không in key) + UAT an toàn
   "chỉ đọc theo quyền + tạo nháp". `journeys/assistant.py` cũng phải theo chuẩn UI mới.
4. FRP-06: build image chứa code mới, rollout backend/worker/scheduler/frontend, migrate, chạy lại full UAT.
5. Commit/push khi xanh; cập nhật Plane + tài liệu này sau mỗi bước.

## Bất di dịch

Không drop/tạo lại MariaDB, namespace `tlc-hr`, site `tlc-hr.local`, Secret nào. Không xoá/sửa
`out/20261021-2056/` và `~/tlc-hr/deliverables/` (bằng chứng đang chia sẻ). Không sửa `results.json`/ảnh/video.
Chỉ dùng `tlc seed reset-*`. Không in bí mật. Không build/clone trên laptop (ổ C: còn 4,2 GB).

## W7 — Trợ lý Raven + Mistral (2026-10-24)

- Raven v3.0.0 pin trong ; image  (nền , thêm shim message Mistral).
- Secret ;  và  trong backend/worker/scheduler;  chỉ dùng cho lần configure.
- Bot **TLC Demo HR Assistant**: Mistral  (key demo bị 0 req/phút với ), tool  và , 13 kênh DM cho các persona demo.
- Provider smoke đã gọi Mistral thật và thực thi tool. Chat Raven thật trả hồ sơ HR-EMP-00019 của binh. UAT trợ lý **6/6** (run ).
- An toàn: chỉ đọc dữ liệu của chính mình và tạo nháp nghỉ phép; không có tool duyệt, lương, đóng kỳ, đổi quyền; chỉ DM AI, chặn file/kênh chung; job AI được ghi thread của chính nó sau khi message gốc đã qua guard.
- UAT hồi quy các module từng lỗi ngày 22/10 đang chạy trên image mới; kết quả đầy đủ sẽ thay dòng này khi hoàn tất.
