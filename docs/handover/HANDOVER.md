# TLC HRM — bàn giao tiếp quản 2026-10-22

## Kết luận

**BLOCKED, chưa hoàn tất UAT UI-first.** FIN-03 đã đạt; không có full run mới xanh, chưa có sáu video roles đạt, chưa đóng gói phát hành. Không có UIFIRST_DONE.md của phiên này. Owner yêu cầu chốt bàn giao; hàng đợi chạy của phiên đã dừng sạch.

## Truy cập và quyền điều khiển

- `ssh -o BatchMode=yes ai1-k3s`, VM Linux, namespace `tlc-hr`, site `tlc-hr.local`.
- Repo UAT: `/home/ai1/tlc-hr/tlc-hr-platform/uat`; app: `/home/ai1/tlc-hr/tlc_hr`.
- Service `tlc-uifirst` đã disable/stop, MainPID=0. ActiveState=failed là kết quả lần dừng timeout, không phải agent còn chạy. Không bật lại khi agent mới tiếp quản.
- Lượt compliance đang chạy đã kết thúc bình thường với exit 1. Ba lượt còn chờ bị huỷ để bàn giao; không để agent sau bị reset dữ liệu chồng.
- Kiểm cuối: không còn container `tlc-uat:1.49`, khoá `/tmp/tlc-uat.lock` lấy được với exit 0.

## Đọc theo thứ tự

1. `auto/HANDOVER.md` này.
2. `auto/UIFIRST_BLOCKED.md`: bằng chứng lệnh/output và các chặn thật.
3. `auto/UAT_UI_STANDARD.md`: đặc biệt ghi chú mới về Date và DOM wrapper.
4. `auto/UIFIRST_PROGRESS.md`, `auto/STATUS.md`.
5. `auto/UIFIRST_PROMPT.md`, `auto/NEEDS.md`, `auto/GAPS-*.md` và stories của module cần sửa.

Các đề nghị lịch sử cấp quyền tạo/sửa SSA cho CEO là sai và không được thực thi. Đề nghị submit-only cũng chưa được chứng minh đủ cho native save.

## Kết quả đã đọc độc lập từ results.json

| Run | Phân hệ | Đạt | Ca 0 UI | Ý nghĩa |
|---|---|---|---|---|
| 20261022-0936 | travel_finance kế thừa | 9/13 | FIN-07 | FIN-03 đạt, ui_ops=134 |
| 20261022-0950 | travel_finance | 12/13 | không | FIN-05, GOV-01, GOV-02 đã đạt; FIN-07 sai người thực hiện |
| 20261022-1000 | payroll_compliance | 1/12 | PC-03/04/11/12 | Lỗi selector/ngày che các lỗi sản phẩm phía sau |
| 20261022-1012 | role_experience | 0/13 | không | Wrapper `.is()` không tồn tại; ngày hạch toán chưa nhận giá trị |
| 20261022-1020 | travel_finance | 12/13 | không | Chỉ FIN-07 đỏ vì tạm ứng fixture chưa thực chi |
| 20261022-1030 | payroll_compliance hiện tại | 5/12 | PC-04 | Chặn thật PC-01/02/03/05; còn lỗi PC-04/07/09 |

Tất cả các run trên không có ca ui=False. Có thao tác UI không đồng nghĩa mọi hành vi đã đủ chuẩn; ví dụ PC-07 còn gọi gửi email qua API.

**RUN 1030 bị trùng ID:** roles chạy 10:30:11, setup lỗi và in 0/0; compliance chạy tiếp 10:30:42 cùng thư mục, ghi kết quả 12 ca. Không dùng thư mục này làm release, không gọi nó là run roles xanh. JSON hiện tại chỉ là compliance; tài sản có thể lẫn hai lượt. Không sửa bằng chứng để chữa trùng ID.

## Source đã sửa trong phiên

Chỉ sửa bốn journey, không sửa lib.py/run_uat.sh/run_uat.py/pack scripts/app:

### journeys/travel_finance.py

- FIN-05 nhận đúng nhãn menu **Trả về**; đã đạt tới hoàn tất quyết toán và đối chiếu sổ tạm ứng trong run 0950/1020.
- FIN-07 dùng mã tạm ứng dạng string đúng; chuyển actor sang Hòa có quyền Additional Salary, không dùng Chi để rồi chỉ gặp lỗi phân quyền.
- GOV-01 lọc danh sách bằng ô Mã định danh, không coi chữ người dùng vừa gõ trong global-search là kết quả rò rỉ dữ liệu; vẫn mở trực tiếp hồ sơ ngoài phạm vi và đối chiếu API. Đã đạt.
- GOV-02 chuẩn bị đơn riêng còn chờ duyệt; không thử ghi lại trạng thái Đã duyệt của đơn đã được duyệt. Đã đạt.
- **Bản sửa cuối chưa chạy:** thêm setup chi thật tạm ứng quá hạn bằng workflow + Payment Entry + private proof, để native available balance không chặn trước guard chính sách/chữ ký. Mục tiêu nghiệm thu FIN-07 vẫn là lời từ chối của server, không phải việc chi fixture.

### journeys/payroll_compliance.py

- PC-01 giữ Phương lập SSA; đọc/đối chiếu company tự điền chỉ đọc thay vì click ô không tồn tại.
- type_into với Date/Datetime/Time fill trực tiếp một lần, không click mở lịch và không xoá rỗng trước. Probe trước/sau đã chứng minh model và input giữ đúng posting/start/end.
- PC-03 xoá JavaScript tự set review_fingerprint; bắt UI thật cung cấp dấu vết bắt buộc. Ca đỏ đúng chỗ thiếu UI.
- trim_grid dùng Page đúng kiểu; PC-08 lấy đúng phiếu của bảng lương hiện tại thay REQ['slip0'] chưa từng gán.
- Run 1030 đã chạy các sửa này. Additional Salary submit hoạt động; PC-02 nay đi tới gate và phát hiện ứng dụng cho gửi ký sai.

### journeys/role_experience.py

- Tab Kế toán & Thanh toán/Nhân viên đúng đường UI; control hiện trên form; đợi chính xác doctype + docname và bấm liên kết tiêu đề dòng.
- Bỏ helper body_with_inputs chưa định nghĩa, đọc ngày và lý do trên ô hiển thị thật.
- Sau run 1012: sửa wrapper từ jQuery `.is()` sang DOM `getClientRects()`, bỏ click mở lịch trước fill ngày.
- **Chưa có run mới xác nhận bản cuối.** Lượt chờ xác nhận đã huỷ khi chốt bàn giao.

### journeys/roles.py

- prepare_state dùng Employee ID nhất quán, không chọn Bình làm đồng nghiệp của chính mình; đúng actor/phạm vi cho từng bước.
- Tiếp tục workflow kỳ công tồn tại, kiểm tra tháng lương/SSA hiệu lực, phiếu của Bình/An, review fixture và private proof trước submit thanh toán.
- Người dùng trong video chọn đúng fixture IDs; thao tác ngày không mở lịch trước fill; giữ thời gian Datetime.
- Một roles_flow gọi setup rồi sáu journeys để setup lỗi không quay tiếp trên dữ liệu dở dang. Runner ngoài vẫn có bẫy 0/0 nên phải kiểm đủ 29 ca.
- **Bản sửa cuối chưa chạy:** chọn ngày vắng thật trong tháng chưa khoá cho attendance correction, thay ngày Present bị từ chối `Attendance status unchanged`.
- Chưa có run roles xanh và chưa tạo sáu ROLE-*.mp4 mới.

## Chặn sản phẩm đã chứng minh

1. **SSA approval:** mở HR-SSA-26-10-00121 bằng Phương, bấm Xác nhận → Có, response savedocs **HTTP 403 PermissionError: Không có quyền truy cập dữ liệu lương.** Form vẫn docstatus=0; modal lỗi đã nhìn thấy trực tiếp. Validator bắt Director/System Manager, trong khi người lập có DocPerm submit nhưng thiếu vai trò validator; CEO không có SSA grant. Không cấp quyền CEO để lách.
2. **Variance gate:** PC-02 run 1030 chuyển sang Chờ giám đốc ký dù còn sai lệch >20%. entry_guard chưa nối vào before_update_after_submit.
3. **Review fingerprint:** trường bắt buộc + chỉ đọc không được UI điền; không được chèn JS/API thay người dùng.
4. **Adjustment approval:** Phương không submit được; cần đường phê duyệt sản phẩm hợp lệ, không chỉ đổi actor trong journey.

Còn phải trace PC-04 selector form đã ký, PC-07 email ưu tiên/đường phát hành UI, PC-09 trạng thái tệp đính kèm. Không coi các ca này là đã sửa xong.

## Việc tiếp theo, không chạy song song lên cùng dữ liệu

1. Xử lý các chặn ứng dụng bằng phạm vi thay đổi được owner chấp thuận; giữ nguyên luật không cấp quyền CEO chỉ để xanh test. Nếu chưa có quyền sửa app, giữ trạng thái BLOCKED, không báo DONE.
2. Kiểm FIN-07 bản cuối; role_experience bản cuối; roles bản cuối. Mỗi lệnh ONLY tự reset toàn bộ dữ liệu demo.
3. Roles phải đủ 29 ca đạt và đủ sáu vai trò; 0/0 hoặc SCENARIO ERROR là thất bại dù exit code 0.
4. Chỉ khi các module xanh mới chạy full reset. Full mặc định không bao gồm roles; phải giải quyết việc cùng một bộ phát hành chứa đúng cả full và role evidence, không sửa JSON để ghép.
5. roles_stitch rồi finish_pack chỉ khi có clip nguồn hợp lệ. **finish_pack hiện copy đè deliverables/results.json cũ**; cần sửa đường đóng gói bảo toàn bộ cũ trước khi chạy. Phiên này chưa chạy hai bước đó.
6. Chỉ ghi UIFIRST_DONE.md khi đủ điều kiện; còn chặn ghi UIFIRST_BLOCKED.md với bằng chứng.

## Lệnh tiếp quản an toàn

```sh
ssh -o BatchMode=yes ai1-k3s
cd /home/ai1/tlc-hr/tlc-hr-platform/uat
systemctl show tlc-uifirst -p MainPID -p ActiveState -p UnitFileState
docker ps --filter ancestor=tlc-uat:1.49 --format '{{.ID}} {{.Status}}'
flock -n /tmp/tlc-uat.lock true
ONLY=travel_finance ./run_uat.sh
```

Không xếp hàng loạt lượt: RUN_ID chỉ tới phút, một lượt setup thất bại nhanh có thể đụng thư mục lượt kế tiếp ngay cùng phút. Kiểm thư mục RUN trước khi chạy, hoặc sửa định danh run trong phạm vi harness được duyệt. Không dùng ps in đầy đủ args/env.

Đọc kết quả bằng Python sau khi RUN kết thúc, kiểm số ca dự kiến, status, ui_ops, exemptions và lỗi SCENARIO; không chỉ xem exit code. Bằng chứng web: `http://100.77.166.27:30081/<RUN>/index.html`.

## An toàn và sự cố cần owner xử lý

- Không drop/tạo lại DB, namespace, site hoặc Secret; chỉ `tlc seed reset-*` qua launcher. Không migrate/rollout trong phiên này.
- Không git commit/push; không sửa thủ công results.json/ảnh/video. Không ghi vào out/20261021-2056 hoặc deliverables cũ.
- Bộ deliverables vẫn gồm bốn file cũ của 20261021-2056. Chưa có bản bàn giao sản phẩm mới.
- **Một lệnh ps liệt kê argv đã vô tình lộ demo-password trong log công cụ.** Không chép lại giá trị. Chưa đổi Secret vì bị cấm; owner cần xoay credential demo theo quy trình được phép. Từ đây chỉ xem pid/ppid/comm hoặc biến đã lọc whitelist.
- Probe tạm trên VM đã được xoá; bài học date/wrapper ghi trong UAT_UI_STANDARD.md. Không tin raw-file output bị cắt ở 50KB hoặc có footer cảnh báo là toàn bộ source; đọc theo các range đủ nhỏ trước khi ghép/sửa.
