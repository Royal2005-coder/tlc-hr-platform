# Cập nhật bàn giao 2026-10-22: đọc trước lịch sử

Trạng thái hiện tại và bằng chứng ở HANDOVER.md / UIFIRST_BLOCKED.md. PC-01 đã lập SSA bằng Phương; UI xác nhận trả HTTP 403. Chặn là mâu thuẫn validator phê duyệt với quyền người lập, không phải CEO thiếu quyền tạo. **Không thực thi các đề nghị lịch sử cấp create/write/rwcs hoặc submit cho CEO bên dưới.** Submit-only cũng chưa phải giải pháp native-save đã kiểm chứng. Cần đường phê duyệt ứng dụng được owner chấp thuận, không nới quyền để làm xanh UAT.

Additional Salary đã submit qua Xác nhận → Có; PC-02 hiện đỏ do variance gate cho Gửi ký đi tiếp, không còn là lỗi nút submit. PC-03 đã bỏ chèn review_fingerprint bằng JS và đỏ đúng chỗ thiếu UI. Các đoạn mô tả workaround cũ bên dưới không phải bằng chứng nghiệm thu hợp lệ.

## Ghi nhận lịch sử, không phải lệnh thay đổi quyền hiện tại

2026-10-22 01:05 — add_button() trong journeys/payroll_compliance.py đã được sửa: bấm nút Thêm thật, nếu desk chỉ mở quick-entry (không đổi URL) thì đóng modal và mở /desk/<slug>/new. Đừng đổi lại chỗ đó; nếu hành trình của bạn vẫn fail ở bước lập bản ghi, hãy đọc hàm này trước.
2026-10-22 01:22 — PR-07 trong journeys/payroll.py đã sửa: mở danh sách Phiếu lương trên app rồi BẤM DÒNG ĐẦU TIÊN (row không hiện tên nhân viên), và chứng minh trên màn hình phiếu lương đó là của Nguyễn Hoài An; đừng quay lại kiểu filter dòng theo số tiền vì desk/app không render đúng chuỗi vnd().

2026-10-22 08:56 — cần áp quyền **submit** (không phải create/write) cho TLC Director, ngoài phạm vi journey:
- `Salary Structure Assignment`: `tlc_hr/interface/payroll_compliance.py::validate_assignment` đòi TLC Director/System Manager
  khi mức lương đổi và `docstatus = 1`, nhưng DocPerm của SSA chỉ cho TLC Payroll/TLC HR Lead/HR User/HR Manager
  quyền submit. `thanh` (TLC Director) chỉ read. Vì vậy chuyên viên lương `phuong` lập được nhưng **không gửi được**
  quyết định tăng lương (server trả PermissionError "Không có quyền truy cập dữ liệu lương."), còn CEO cũng không bấm
  Gửi được. Đây là chặn của PC-01 (không phải thiếu quyền tạo như blocker 05:45 cũ).
- `TLC Payroll Adjustment` / `TLC Payroll Bonus` / `TLC Salary Review`: cùng deadlock (`validate_award` /
  `validate_salary_review` đòi TLC Director khi submit; DocPerm chỉ cho TLC Payroll/TLC HR Lead submit), chặn PC-05.
- Đề nghị: thêm **submit** (giữ create/write = 0) cho TLC Director trên bốn doctype trong
  `customizing/payroll_access.yaml` + `customizing/payroll_compliance_records.yaml`, migrate, rồi chạy lại
  `ONLY=payroll_compliance`. Đúng vai "CEO duyệt quyết định lương" — không nới quyền lập phân bổ.
- Journey PC-01 đã đổi sang `phuong` (tạo trên desk) theo note 08:35; khi quyền submit có, cần đổi người bấm Gửi
  của PC-01 sang `thanh` nếu muốn `tlc_decision_approved_by = thanh`; hiện code để `phuong` gửi và sẽ nhận lỗi quyền.

## 2026-10-22 14:05 — điểm vào theo vai trò (đo trên site đang chạy)

- `frappe.apps.get_apps()` từ process mới cho ra **đúng hai ô**: ERPNext (`/desk/home`) và Frappe HR (`/desk/hr-setup`) — app `tlc_hr` không còn ô riêng, hết cảnh hai icon chồng nhau. thay đổi này chỉ thấy trong trình duyệt sau lần rollout kế (hooks.py đã hot-sync nhưng gunicorn đang giữ module cũ).
- Landing thật của từng tài khoản demo đo từ DB: `an`/`binh` → app `hrms` (không workspace); `phuong` → TLC Tác nghiệp lương; `thanh` → TLC Điều hành; `chi` → TLC Kế toán chi trả; `hung` → TLC Quản lý; `lan` → TLC Nhân sự; **`hoa` → TLC Quản trị kỹ thuật (SAI)**.
- Nguyên nhân `hoa`: `WORKSPACE_OF` để "System Manager" đầu bảng nên ai có cả quyền kỹ thuật bị đưa sang workspace IT. Đã sửa trong `tlc_hr/interface/role_navigation.py`: nghiệp vụ trước, kỹ thuật cuối. Có hiệu lực sau rollout.
- Việc còn mở (chưa làm, vì sẽ thay đổi quyền giữa loạt UAT đang chạy): `customizing/lifecycle_records.yaml` và `organization_records.yaml` gán **System Manager** cho nhiều tài khoản nghiệp vụ trong dữ liệu demo. Theo mô hình phân quyền đã chốt thì HR Lead không cần System Manager thường trực; cần một lượt "least privilege" rồi chạy lại toàn bộ UAT để chứng minh không vỡ ca nào. Không đổi quyền khi chưa có lượt chạy đầy đủ.

## 2026-10-22 15:4x — sau rollout ảnh c7f391b-202610221537

- Pods đang chạy đúng ảnh bàn giao; `migrate` sạch; 5 Báo cáo VN tên ASCII tồn tại (`VN Bang Luong Thang`…), App Switcher còn ERPNext + Frappe HR; cổng asset trước lượt full: `asset_lỗi=0`.
- `tlc doctor` còn một dòng LỖI: "Kỳ công 2026-09 đã khoá: chưa khoá: Nhà máy 1/2/3, Hội sở". Đây là **mâu thuẫn giữa doctor và bước seed**: `tlc seed reset-periods` cố ý mở lại các kỳ đã khoá (tháng khoá làm lượt demo tăng ca/điều chỉnh bị chặn), còn doctor lại đòi kỳ 2026-09 phải khoá. Chưa sửa vội: muốn đúng thì doctor phải kiểm theo "kỳ nào YAML khai bố đã khoá" thay vì cứng một tháng. Việc này không làm sai số liệu UAT vì mỗi hành trình tự khoá kỳ nó cần qua màn hình thật.

## 2026-10-22 16:0x — PR-04 đỏ trong lượt full: thiếu chi phí bảo hiểm PHÍA DOANH NGHIỆP trên phiếu lương

Bằng chứng đo trên site (read-only):
- `tabSalary Detail` của 59 phiếu thuộc `HR-PRUN-2026-00064` chỉ có parentfield `earnings` (LCB, PCAT, OT, OTP) và
  `deductions` (BHXH_NLD, BHYT_NLD, BHTN_NLD, TNCN). **Không có dòng nào parentfield `employer_contributions`** →
  `payroll_summary()["employer"] = 0.0`, PR-04 chặn đúng.
- Hai cấu trúc cùng tồn tại: `TLC Lương 2026.1` → employer abbr `BHXH_DN/BHYT_DN/BHTN_DN/KPCD_DN`,
  `TLC Lương 2026.2` → `BHXH_DN_TLC/...`. `customizing/payroll.yaml` chỉ khai báo cấu trúc **2026.2** (kèm
  `employer_contributions` công thức `@contribution`), còn 2026.1 do dữ liệu demo cũ tạo ra: có 4 dòng employer
  nhưng không có công thức → HRMS tính ra 0 nên không ghi dòng nào lên phiếu.
- Vì vậy lỗi này KHÔNG phải do thứ tự module: lượt chạy nào rơi vào nhân viên đang SSA ở `TLC Lương 2026.1` là thiếu
  chi phí doanh nghiệp. Các lượt trước PR-04 xanh là do bảng lương phủ nhân viên cấu trúc 2026.2.

Hướng sửa đã chọn (không nới quyền, không đổi số liệu vàng): khai báo thêm cấu trúc `TLC Lương 2026.1` trong
`customizing/payroll.yaml` với đúng 4 dòng `employer_contributions` mang công thức `@contribution` giống 2026.2
(abbr giữ nguyên BHXH_DN… để khớp dữ liệu cũ), rồi `bench tlc config plan && apply` (chỉ ghi DB, không restart).
Kiểm chứng: `payroll_summary()` phải trả `employer > 0` cho bảng lương phủ nhân viên 2026.1, và PR-04 + tệp xuất
`employer_insurance`/`total_company_cost` có số.
Đã sửa phần đọc: `infrastructure/frappe/payroll.py::summary` và `payroll_compliance_exports.py` nay cộng theo
`parentfield == "employer_contributions"` thay vì danh sách abbr cứng (149 unit test đạt, ruff sạch) — hai file này
chưa commit, sẽ commit cùng YAML.

## 2026-10-22 16:4x — W5-ASSET-SUBMIT-BLOCKED: quyền che mất thông báo nghiệp vụ

Lượt full: ca này mong nhận cảnh báo "biên bản bàn giao chưa đủ xác nhận hai bên" nhưng lại nhận
"Không có quyền thực hiện thao tác này." → tài khoản dùng trong ca không còn quyền submit trên chứng từ bàn giao
sau các đợt áp quyền (customizing/permissions.yaml đã đổi). Đọc lại `journeys/people_ops.py` của ca này: xác định
đúng người được phép ghi sổ theo nghiệp vụ (người nhận tài sản / quản lý tài sản), sửa người tác nhân HOẶC quyền,
miễn là thông báo cuối vẫn là chặn nghiệp vụ hai bên xác nhận — không được đổi kỳ vọng cho khớp lỗi quyền.
