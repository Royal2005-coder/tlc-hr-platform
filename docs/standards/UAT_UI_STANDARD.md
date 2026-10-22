# Chuẩn hành trình UAT theo vai trò (áp dụng từ 2026-10-21)

Kết quả 154/154 của run `20261021-2056` đúng về nghiệp vụ nhưng **không đạt về bằng chứng thao tác**:
nhiều ca hoàn thành bằng gọi API nên video chỉ chiếu trang chủ. Người xem phải thấy **đúng vai trò đó làm việc**.

## Luật cứng

1. **Hành vi được nghiệm thu phải là thao tác thật trên giao diện**: nhấp chuột, điền ô, bấm nút
   `Lưu` / `Hành động` / nút workflow, mở danh sách, mở form, bấm thẻ workspace, chọn trong dialog.
   API (`api()`, `api_get()`, `p.evaluate("frappe.new_doc(...)")`, `db_insert`) **chỉ được dùng để**:
   - dọn/khởi tạo dữ liệu nền trước ca (setup), và
   - đọc để **đối chiếu** sau khi người dùng đã làm xong (assert).
   Không bao giờ dùng API để tạo/submit/duyệt chính cái đang được nghiệm thu.
2. Harness đã chặn giùm bạn: `lib.case()` đếm sự kiện `click|keydown|change|submit` thật trong trang
   (`sessionStorage['uat-ops']`). Một ca `Đạt` mà `ui_ops == 0` sẽ tự chuyển thành
   `Không đạt: Không có thao tác nào trên giao diện`. Muốn miễn trừ thì phải viết rõ `ui=False` trong
   `case(...)` — chỉ dành cho ca mà đối tượng nghiệm thu là **trả lời của server** (403 khi đọc bảng
   ẩn danh, nội dung file xuất, API export). Số ca `ui=False` phải là tối thiểu và phải giải thích ở `expected`.
3. Mỗi ca phải **đọc được trên video**:
   - `s.step("HR mở danh sách đơn chờ duyệt")` trước mỗi thao tác có ý nghĩa (caption hiện góc màn hình),
   - kết thúc ca harness đã giữ 1,6 s ở màn hình kết quả — đừng thêm `wait_for_timeout` thừa thang,
   - không dùng `p.evaluate` để "nhảy" tới trạng thái cuối (form phải được điền từng ô thấy được).
4. Không đổi logic app để chiều UAT. Nếu UI thiếu đường làm việc thật (không có nút, không có màn hình),
   đó là **lỗi sản phẩm**: sửa app (thêm workspace shortcut, thẻ, nút, màn hình list) rồi báo trong
   `AGENT_PROGRESS.md`, không được lách bằng API.
5. Không sửa `results.json`, ảnh, video. Không dùng `--reset` của module khác khi đang chạy module mình.

## Quy trình cho mỗi phân hệ

```bash
cd ~/tlc-hr/tlc-hr-platform/uat
ONLY=<module> ./run_uat.sh            # có flock, chạy song song an toàn nhưng sẽ chờ nhau
```
- Trước khi xong: mọi ca của phân hệ `Đạt` **và** `ui_ops > 0` (trừ các ca `ui=False` có lý do).
- Xem `ui_ops` từng ca: `python3 -c "import json;[print(r['id'],r['status'],r.get('ui_ops')) for r in json.load(open('out/<RUN>/results.json'))['results']]"`
- Ghi tiến độ vào `~/tlc-hr/auto/AGENT_PROGRESS.md` theo mục `## <giờ> – <module> UI-first`.

## Việc của từng người (mỗi agent chỉ sửa đúng 1 file journeys/<module>.py)

| Phân hệ | Hiện tại | Phải làm |
|---|---|---|
| payroll_compliance | 0 bước UI / 19 API | dựng lại 11 ca trên desk: mở Payroll Entry, bấm Lấy nhân viên, Tính lương, đọc cảnh báo chặn; mở Salary Slip; màn hình review biến động; export file qua nút; kiểm tra mật khẩu PDF |
| role_experience | 4 bước UI / 13 ca | mỗi vai trò phải thật sự làm một việc: điền đơn, duyệt, mở thẻ, xem phiếu lương, đối chiếu phạm vi bằng cách mở danh sách |
| leave | 17 API | các ca duyệt cấp 1/cấp 2, trừ dư, chặn trùng: thao tác trên form + nút workflow |
| payroll | 11 API | CEO ký, kế toán xác nhận chi, xem phiếu lương trên app: tất cả qua UI |
| travel_finance | 27 API | tạo công tác/tạm ứng/chi phí bằng form desk; Payment Entry qua UI; đối chiếu 3 nhánh qua danh sách |
| overtime, attendance, organization, recruitment, lifecycle, people_ops, services, survey | khá | rà từng ca còn `ui_ops == 0`, chuyển sang UI, thêm `s.step` |

## Video journey theo vai trò (làm sau, đừng đụng vào)

`run_roles.sh` + `journeys/role_journeys.py` sẽ dựng 6 video liền mạch (công nhân, văn phòng, trưởng nhà
máy, HR, CEO, kế toán/trưởng phòng). Agent phân hệ **không** sửa file đó.
## 23:38 – bản sửa gate (đọc nếu bạn thấy ui_ops == 0 dù đã click thật)

`lib.py` bản đầu đặt bộ đếm bằng `add_init_script("() => {...}")` — Playwright **không gọi** init script dạng
arrow-function nên không sự kiện nào được đếm và MỌI ca đều bị báo "Không có thao tác nào trên giao diện".
Đã đổi sang IIFE tự chạy (`OPS_JS` dạng raw) và xác nhận đếm được thật. Nếu run của bạn chạy TRƯỚC 23:38 mà
toàn bộ ca fail vì lý do đó, đó là lỗi harness chứ không phải lỗi hành trình của bạn: **chỉ cần chạy lại**,
đừng đổi hành trình sang `ui=False` để lách.

## 23:42 – `ONLY=<module>` tự reset dữ liệu

`run_uat.sh` trước đây chỉ reset khi có `--reset`, nên chạy lẻ một module trên dữ liệu leftover của run
`20261021-2056` sẽ fail dây chuyền (vd `PD-01` timeout rồi `PD-02` KeyError). Từ 23:42, **mọi lần chạy có
`ONLY=` đều tự chạy toàn bộ `tlc seed reset-*`** (vẫn dưới flock, không ai giẫm nhau). Lệnh chuẩn:
`ONLY=<module> ./run_uat.sh` — không cần thêm `--reset`.

## 2026-10-22 – Ô ngày và wrapper của form trên build hiện tại

- Với ô Date/Datetime, dùng `input.fill(ngay_theo_dinh_dang_nguoi_dung)` rồi `input.press("Tab")`, như `payroll.py::_new_entry`. Không `click()` mở lịch trước khi fill, không `fill("")` rồi mới fill lại cùng ngày. Probe Payroll Entry cho thấy ô có thể vẫn in đúng ngày nhưng model đã thành null, hoặc lịch giữ lại ngày cũ.
- Đối chiếu cả giá trị nhìn thấy và `cur_frm.doc[field]` sau nhập. Probe trước sửa: start/end null dù input hiện 01-10-2026/31-10-2026; sau sửa: posting=2026-10-31, start=2026-10-01, end=2026-10-31 đúng cả model và input. Không sửa model bằng JavaScript để chữa ô nhập.
- `cur_frm.wrapper` trên build này là `HTMLDivElement`, không phải jQuery; kiểm tra hiển thị bằng `getClientRects().length`, không gọi `.is(":visible")`. Chờ đúng cả doctype và docname khi mở dòng của danh sách.
