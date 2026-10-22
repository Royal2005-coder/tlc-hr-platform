# Cập nhật bàn giao 2026-10-22: đọc trước lịch sử

Trạng thái hiện tại và bằng chứng ở HANDOVER.md / UIFIRST_BLOCKED.md. PC-01 đã lập SSA bằng Phương; UI xác nhận trả HTTP 403. Chặn là mâu thuẫn validator phê duyệt với quyền người lập, không phải CEO thiếu quyền tạo. **Không thực thi các đề nghị lịch sử cấp create/write/rwcs hoặc submit cho CEO bên dưới.** Submit-only cũng chưa phải giải pháp native-save đã kiểm chứng. Cần đường phê duyệt ứng dụng được owner chấp thuận, không nới quyền để làm xanh UAT.

Additional Salary đã submit qua Xác nhận → Có; PC-02 hiện đỏ do variance gate cho Gửi ký đi tiếp, không còn là lỗi nút submit. PC-03 đã bỏ chèn review_fingerprint bằng JS và đỏ đúng chỗ thiếu UI. Các đoạn mô tả workaround cũ bên dưới không phải bằng chứng nghiệm thu hợp lệ.

## Ghi nhận lịch sử, không phải lệnh thay đổi quyền hiện tại

# GAPS giao diện – chiến dịch UAT UI-first (2026-10-22)

Ghi nhận những chỗ giao diện chưa đủ đường làm việc thật. Ca tương ứng vẫn phải xanh bằng một đường UI thật;
nếu không có đường nào thì ca để đỏ và ghi rõ ở đây.

## Employee Grievance – cảnh báo "Không đủ quyền cho Designation" ngay sau khi chọn người nêu

- Ai gặp: nhân viên (an@demo.example) tạo khiếu nại trên Desk.
- Chọn `Người nêu` (Link Employee) → form tự nạp `Designation` của nhân viên và hiện hộp thoại
  “Lỗi phân quyền / Không đủ quyền cho Designation”; hộp thoại che form cho tới khi người dùng bấm X.
- Người dùng vẫn lập và lưu được khiếu nại sau khi đóng thông báo; `journeys/people_ops.py` (W5-GRIEVANCE-SUBMIT)
  đóng thông báo bằng nút Đóng trên giao diện rồi tiếp tục. Đây là lỗi quyền/khoảng trắng trải nghiệm, không phải
  thiếu đường nghiệp vụ, nên ca vẫn chạy và xanh bằng thao tác thật.
- Đề nghị (cần migrate nên không tự sửa): cấp read `Designation` cho vai trò nhân viên hoặc bỏ trường Designation
  khỏi phần fetch của form khi người dùng không có quyền.

## Salary Structure Assignment – CEO không có quyền tạo, không thể ghi quyết định tăng lương (PC-01)

- Ai gặp: `thanh@demo.example` (TLC Director) mở `Phân công cấu trúc lương` trên desk. Danh sách chỉ có
  nút `Tải thêm`, **không có nút Thêm**; đường `/desk/salary-structure-assignment/new` vẫn mở nhưng các ô
  `employee`, `salary_structure`, `from_date`, `base`, `tlc_decision_evidence` đều bị ẩn (chỉ hiện Company và
  TLC Decision Reason). Ảnh: `out/20261022-0511/shots/PC-01.png`; probe DOM: các ô `is_visible=False`.
- Nguyên nhân: bảng quyền của `Salary Structure Assignment` (Custom DocPerm) chỉ có System Manager, Employee,
  HR Manager, HR User, TLC Payroll, TLC HR Lead — **không có TLC Director**. Vì vậy ca PC-01
  (CEO ghi quyết định tăng lương hiệu lực giữa kỳ) không có đường thao tác thật trên giao diện.
- Đề nghị (cần migrate, ngoài phạm vi file UAT): thêm quyền read/create/write (và submit nếu quyết định phải gửi)
  cho TLC Director trên `Salary Structure Assignment` trong `tlc_hr/customizing/permissions.yaml`, migrate, rồi chạy lại
  `ONLY=payroll_compliance`. Ca PC-01 để đỏ cho tới khi có quyền.

## Báo cáo VN (erpnextvn) không import được trên build này (PC-06, PC-08)

- Mở `VN Bảng Lương Tháng` hoặc `VN Báo Cáo Thuế TNCN` trên desk: hộp thoại
  `ModuleNotFoundError: No module named 'erpnextvn.erpnext_vietnam.report.vn_bảng_lương_tháng'`.
- Nguyên nhân: thư mục report trong app là ASCII (`vn_bang_luong_thang`, `vn_bao_cao_thue_tncn`) nhưng `tabReport.name`
  (và `report_name`) là tiếng Việt có dấu; Frappe suy ra module path theo tên có dấu nên import hỏng.
- Ảnh: `out/20261022-0525/shots/PC-06.png`.
- Journey dùng báo cáo chuẩn `Salary Register` (cùng dữ liệu phiếu lương/thực lĩnh/cột Thuế TNCN trên desk) cho phần
  màn hình của PC-06/PC-08; file xuất luật định vẫn đối chiếu qua API như khai báo `ui=False` trong expected.
  Đề nghị (app/packaging, cần migrate/redeploy): đặt `report_name` ASCII hoặc đổi tên thư mục theo tên có dấu.
