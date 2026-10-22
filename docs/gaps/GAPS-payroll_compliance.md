# Cập nhật bàn giao 2026-10-22: đọc trước lịch sử

Trạng thái hiện tại và bằng chứng ở HANDOVER.md / UIFIRST_BLOCKED.md. PC-01 đã lập SSA bằng Phương; UI xác nhận trả HTTP 403. Chặn là mâu thuẫn validator phê duyệt với quyền người lập, không phải CEO thiếu quyền tạo. **Không thực thi các đề nghị lịch sử cấp create/write/rwcs hoặc submit cho CEO bên dưới.** Submit-only cũng chưa phải giải pháp native-save đã kiểm chứng. Cần đường phê duyệt ứng dụng được owner chấp thuận, không nới quyền để làm xanh UAT.

Additional Salary đã submit qua Xác nhận → Có; PC-02 hiện đỏ do variance gate cho Gửi ký đi tiếp, không còn là lỗi nút submit. PC-03 đã bỏ chèn review_fingerprint bằng JS và đỏ đúng chỗ thiếu UI. Các đoạn mô tả workaround cũ bên dưới không phải bằng chứng nghiệm thu hợp lệ.

## Ghi nhận lịch sử, không phải lệnh thay đổi quyền hiện tại

# Khoảng trống giao diện của phân hệ Tuân thủ & Quản trị lương (UAT bàn, run `payroll_compliance`)

Mỗi mục dưới đây là một hành vi nghiệp vụ đã có trong `tlc_hr` nhưng **không có đường làm việc thật trên desk** cho đúng vai trò
sở hữu nó. Hành trình `uat/journeys/payroll_compliance.py` không lách bằng API cho phần được nghiệm thu: ca nào mắc phải vẫn
được chạy tới đúng chỗ chặn và **để đỏ**, kèm mô tả ở dưới.

## PC-01 — Không vai trò nào ghi được quyết định tăng lương có ngày hiệu lực giữa kỳ

* Vai trò: `thanh@demo.example` (Tổng giám đốc, `TLC Director`) — người duy nhất được phê quyết định lương;
  `phuong@demo.example` (chuyên viên lương, `TLC Payroll`) — người lập chứng từ.
* Người dùng muốn làm gì: mở danh sách **Salary Structure Assignment** → Thêm → chọn nhân viên, ngày hiệu lực 16 của tháng,
  mức lương cơ bản mới, lý do quyết định, đính quyết định → **Lưu** → **Gửi**.
* UI thiếu: danh sách không có nút **Thêm**, các ô đều khoá — `TLC Director` không có quyền create/write/submit trên
  `Salary Structure Assignment` (chỉ `HR User`, `HR Manager`, `TLC Payroll`, `TLC HR Lead`). Trong khi đó
  `tlc_hr/tlc_hr/interface/payroll_compliance.py::validate_assignment` lại đòi đúng vai `TLC Director`/`System Manager` khi
  mức lương đổi và khi `docstatus = 1`. **Không tài khoản demo nào thoả cả hai** (kể cả `admin@demo.example` — đăng nhập bằng
  demo-password bị 401), nên "quyết định hiệu lực giữa kỳ" không thể đưa vào hệ thống bằng desk.
* Sửa nhỏ nhất: thêm một dòng vào `tlc_hr/customizing/payroll_access.yaml`
  `- {doctype: Salary Structure Assignment, role: TLC Director, rights: rwc s}` (read/write/create + submit, không cancel/amend),
  để đúng người phê được tự tay ghi quyết định; không đổi logic.
* Hệ quả với chứng từ UAT: ca PC-01 chạy tới bước bấm Gửi thì dừng và đỏ; AC "phiếu lương phân bổ tlc_effective_base theo trung
  bình trọng số hai khoảng" không còn chứng cứ trên video vì không tồn tại khoảng lương thứ hai.

## PC-02 — Cổng chặn "Gửi ký" không bao giờ chạy (sai hook)

* Vai trò: `phuong@demo.example`.
* Người dùng muốn làm gì: bảng lương còn sai lệch chưa giải trình → **Hành động → Gửi ký** → phải thấy màn hình báo chặn.
* UI thiếu: không thiếu nút — thiếu **hành vi**. `hooks.py` gắn `entry_guard` (nơi gọi `gate_review`) vào `before_save`,
  nhưng mọi bước chuyển trạng thái của một chứng từ đã nộp (`Đã tính lương` → `Chờ giám đốc ký`, docstatus giữ nguyên 1) được
  Frappe lưu với `_action = "update_after_submit"` — chỉ `before_update_after_submit`/`on_update_after_submit` chạy.
  Vì vậy cổng rà soát biến động **im lặng cho qua**, bảng lương vẫn sang `Chờ giám đốc ký`.
* Hệ quả: nhân viên biến động >20% vẫn được trình CEO ký mà không có phiếu `TLC Payroll Review` nào — AC của ST-PC-02 chưa đạt.
* Sửa nhỏ nhất: trong `tlc_hr/tlc_hr/hooks.py`, thêm `"before_update_after_submit": f"{PCOM}.entry_guard"` cho `Payroll Entry`
  (hoặc gọi `gate_review` ngay trong `interface/payroll.py::before_update_after_submit` khi
  `before.workflow_state != doc.workflow_state`).

## PC-03 — Phiếu rà soát biến động không tự điền được dấu vết dữ liệu

* Vai trò: `phuong@demo.example` (có quyền create/submit trên `TLC Payroll Review`).
* Người dùng muốn làm gì: mở danh sách **TLC Payroll Review** → Thêm → chọn bảng lương, nhân viên, loại "Variance", diễn giải,
  đính chứng từ → **Lưu** → **Gửi**.
* UI thiếu: trường `review_fingerprint` là `reqd` + `read_only` (xem `customizing/payroll_compliance_records.yaml`), nên form
  không cho người dùng điền; hàm `interface/payroll_compliance.py::new_review` sinh đúng giá trị này nhưng **không có nút nào
  gọi nó**. Hành trình phải đặt giá trị do server tính (`inspect_reviews`) vào form để người dùng làm được phần còn lại.
* Sửa nhỏ nhất: trong `tlc_hr/public/js/payroll_entry.js`, thêm `frm.add_custom_button("Lập phiếu rà soát biến động", ...)`
  gọi `new_review` rồi `frappe.new_doc("TLC Payroll Review", message)`; hoặc thêm thẻ "Sai lệch lương chờ giải trình"
  (Number Card/Report) trên workspace `TLC Tác nghiệp lương`.

## PC-05 — Không thể Gửi phiếu điều chỉnh/thưởng/đợt xét lương (deadlock quyền, giống PC-01)

* Vai trò: `phuong@demo.example` (chuyên viên lương) và `thanh@demo.example` (CEO).
* Người dùng muốn làm gì: mở **TLC Payroll Adjustment** → Thêm → phiếu lương gốc đã ký, cấu phần, chiều Increase, số tiền,
  ngày trả ở kỳ sau, lý do, đính chứng từ → **Lưu** → **Gửi** (AC: "phiếu điều chỉnh được ghi nhận và bù trừ vào kỳ tiếp theo").
* UI thiếu: `validate_award` (và `validate_salary_review`) đòi `TLC Director` khi `docstatus = 1`, nhưng DocPerm của
  `TLC Payroll Adjustment`, `TLC Payroll Bonus`, `TLC Salary Review` chỉ cho `TLC Payroll`/`TLC HR Lead` quyền submit —
  `TLC Director` chỉ read. Chuyên viên lương thì bị chặn bởi `require_roles`, CEO bị chặn bởi quyền gửi chứng từ.
* Sửa nhỏ nhất: trong `tlc_hr/customizing/payroll_compliance_records.yaml`, đặt `"submit": 1` cho role `TLC Director`
  trên ba doctype đó (giữ `write: 0`, `create: 0`) — đúng người ký sẽ tự tay gửi được phiếu.

## PC-06, PC-08, PC-11, PC-12 — Số liệu ngân hàng, luật định, mô phỏng và quét bất thường không có nút trên desk

* Vai trò: `chi@demo.example` (kế toán chi), `phuong@demo.example` (chuyên viên lương).
* Người dùng muốn làm gì: trên form **Payroll Entry** đã ký, bấm "Xuất file chuyển khoản ngân hàng"; ở kỳ quyết toán bấm
  "Xuất PIT / BHXH D02-LT / Sổ quản lý lao động"; trên màn hình quỹ lương nhập `+10%` và chạy mô phỏng; bấm "Quét bất thường".
* UI thiếu: `tlc_hr/interface/payroll_compliance.py` có `export_bank_batch`, `export_accounting`, `export_pit`,
  `export_bhxh_d02lt`, `export_labor_register`, `simulate_salary`, `cost_report`, `payroll_anomalies` (đã `@frappe.whitelist`)
  nhưng **không một client script, nút, trang hay workspace nào gọi chúng**. Hành trình hiện nghiệm thu phần nội dung file/kết
  quả tính qua API (đã ghi rõ trong `expected` của từng ca) và cho người dùng bấm thứ thật nhất mà desk có:
  báo cáo `VN Bảng Lương Tháng` (kế toán) và `VN Báo Cáo Thuế TNCN` (chuyên viên lương), cùng dòng tổng hợp ở đầu form
  Payroll Entry do `tlc_hr/public/js/payroll_entry.js` vẽ.
* Sửa nhỏ nhất: thêm vào `tlc_hr/public/js/payroll_entry.js` (khi `workflow_state` là `Đã ký`/`Đã chi`)
  các `frm.add_custom_button("Xuất file ngân hàng (VCB)", ... → export_bank_batch, tải about:blank href)`,
  `"Xuất PIT"`, `"Xuất BHXH D02-LT"`, `"Xuất sổ quản lý lao động"`, `"Quét bất thường lương"`; thêm shortcut
  "Chi phí & mô phỏng lương" trỏ tới một trang `TLC Payroll Budget` (hoặc ít nhất một Workspace Card `cost_report`)
  trong `customizing/workspaces.yaml` / `role_native_workspaces.yaml`.
* Ghi chú thêm cho PC-06: báo cáo gốc `Bank Remittance` của HRMS luôn trả bảng trống với dữ liệu demo vì nhân viên
  chỉ có `bank_ac_no = TLC-DEMO-<mã NV>` và `bank_name = NULL`; cần cho nhân viên demo tên ngân hàng thật (seed) thì kế toán
  mới có một màn hình ngân hàng đúng nghĩa.

## PC-07 — Chuyên viên lương không mở được Payroll Settings

* Quan sát (không chặn ca): `Payroll Settings` chỉ cho `System Manager` (rw) và `HR Manager` (rw) —
  `TLC Payroll` (phuong) bị từ chối. Hành trình để `hoa@demo.example` (HR Manager, `TLC HR Lead`) cấu hình mã hoá PDF trên desk,
  đúng vai có quyền. Nếu muốn chuyên viên lương tự làm, thêm quyền read + `write` có chọn lọc cho `TLC Payroll` trong
  `customizing/payroll_access.yaml`.
