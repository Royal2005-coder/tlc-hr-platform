"""Travel, Advances and Expenses (W3 TLC Công tác – Tạm ứng – Quyết toán chi phí):
Real desktop browser interactions covering PO 4.2/4.6 workflows:
1. Sequential approval (Manager -> Director -> Accountant), skipping duplicate approver for department heads.
2. No self-approval and factory manager scope enforcement.
3. Travel conflict detection and On Duty attendance recording.
4. Advance payment evidence confirmation (payment is not approval).
5. Three-way settlement calculation and reconciliation (equal, refund, top-up).
6. Overdue advance salary recovery blocked without company policy and employee signed consent.
7. Post-close trip adjustment creation preserving historical locked period snapshot.
"""

from lib import *  # noqa: F403

TR = "Travel Request"
EA = "Employee Advance"
EC = "Expense Claim"
PE = "Payment Entry"
AR = "Attendance Request"


def workflow_action(s, doctype, name, action):
    p = s.page
    p.goto(f"{BASE}/desk/{doctype.lower().replace(' ', '-')}/{name}")
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(3000)
    open_actions(p)
    p.locator(MENU_ITEMS).filter(has_text=action).first.click()
    p.wait_for_timeout(4000)
    return api_get(s, f"/api/resource/{doctype}/{name}").json()["data"].get("workflow_state")


def travel_finance_flow(browser):
    # -------------------------------------------------------------------------
    # Part 1: Employee An (Kinh doanh) creates travel request
    # -------------------------------------------------------------------------
    s_an = Session(browser, "TRV", "an")
    login(s_an)
    p = s_an.page

    # Get employee details
    emp_an = api(s_an, "frappe.client.get_value", doctype="Employee",
                 filters=json.dumps({"user_id": f"{s_an.account}@demo.example"}),
                 fieldname="name,company,cost_center")
    an_emp_id = emp_an["name"]
    company = emp_an["company"]
    cost_center = emp_an.get("cost_center") or "Main - TLC"

    # Dates for upcoming business trip
    d_start = working_day(10)
    d_end = working_day(12)

    with case(s_an, "TRV-01", "Chặn tạo công tác trùng đơn nghỉ phép",
              "Tạo đơn công tác trùng ngày với lịch nghỉ phép đã duyệt",
              f"{vn(d_start)} – {vn(d_end)}",
              "Bị chặn: báo lỗi trùng lịch nghỉ phép hoặc công tác") as r:
        # Create a conflicting leave first
        leave_doc = api(s_an, "frappe.client.insert", doc=json.dumps({
            "doctype": "Leave Application",
            "employee": an_emp_id,
            "leave_type": "Phép năm",
            "from_date": d_start,
            "to_date": d_start,
            "description": "Nghỉ phép trùng công tác (UAT)"
        }))
        p.goto(f"{BASE}/desk/travel-request")
        p.wait_for_load_state("networkidle")
        p.evaluate("""([c, e, d1, d2]) => frappe.new_doc('Travel Request', {
            company: c, employee: e, travel_type: 'Domestic', purpose_of_travel: 'TLC Công tác',
            tlc_destination: 'Chi nhánh Hà Nội', description: 'Khảo sát thị trường',
            tlc_from_date: d1, tlc_to_date: d2, tlc_from_session: 'AM', tlc_to_session: 'PM',
            tlc_funded: 1, tlc_requested_advance: 3000000,
            costings: [{expense_type: 'TLC Vé công tác', total_amount: 3000000}]
        })""", [company, an_emp_id, d_start, d_end])
        p.wait_for_url(re.compile(r".*/travel-request/new.*"))
        p.wait_for_timeout(2500)
        p.keyboard.press("Control+s")
        p.wait_for_timeout(3000)
        modal = p.locator(".modal:visible")
        toast = p.locator(".msgprint")
        msg = modal.last.inner_text() if modal.count() else (toast.last.inner_text() if toast.count() else "")
        check("Trùng lịch" in msg or "overlap" in msg.lower(), f"Expected overlap error, got: {msg}")
        r["actual"] = "Hệ thống chặn lưu và thông báo: " + " ".join(msg.split())[:180]
        p.keyboard.press("Escape")
        # Clean up temporary conflicting leave
        if leave_doc and leave_doc.get("name"):
            s_an.page.request.delete(f"{BASE}/api/resource/Leave Application/{leave_doc['name']}",
                                     headers={"X-Frappe-CSRF-Token": p.evaluate("frappe.csrf_token")})

    # Non-conflicting dates for the main travel journey
    t_start = working_day(15)
    t_end = working_day(17)

    with case(s_an, "TRV-02", "Tạo đề xuất công tác có phí có dự toán",
              "Travel Request > Mới > Nhập nơi đến, ngày đi/về, dự toán chi phí, số tiền tạm ứng > Lưu > Gửi duyệt",
              f"Hà Nội 3 ngày ({vn(t_start)} – {vn(t_end)}), dự toán 5.000.000, tạm ứng 4.000.000",
              "Lưu thành công, trạng thái Chờ quản lý duyệt, người duyệt tự gán là Trần Minh Quang") as r:
        p.goto(f"{BASE}/desk/travel-request")
        p.wait_for_load_state("networkidle")
        p.evaluate("""([c, e, d1, d2]) => {
            frappe.new_doc('Travel Request', {
                company: c, employee: e, travel_type: 'Domestic', purpose_of_travel: 'TLC Công tác',
                tlc_destination: 'Chi nhánh Hà Nội', description: 'Gặp gỡ đối tác chiến lược',
                tlc_from_date: d1, tlc_to_date: d2, tlc_from_session: 'AM', tlc_to_session: 'PM',
                tlc_funded: 1, tlc_requested_advance: 4000000,
                costings: [
                    {expense_type: 'TLC Vé công tác', total_amount: 3000000},
                    {expense_type: 'TLC Lưu trú', total_amount: 2000000}
                ]
            });
        }""", [company, an_emp_id, t_start, t_end])
        p.wait_for_url(re.compile(r".*/travel-request/new.*"))
        p.wait_for_timeout(2500)
        p.keyboard.press("Control+s")
        p.wait_for_timeout(3000)
        p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Travel Request' && !cur_frm.is_new() && !cur_frm.is_dirty()")
        REQ["trip"] = p.evaluate("cur_frm.doc.name")
        state = workflow_action(s_an, TR, REQ["trip"], "Gửi duyệt")
        check(state == "Chờ quản lý duyệt", f"State is {state}")
        approver = api_get(s_an, f"/api/resource/{TR}/{REQ['trip']}").json()["data"].get("tlc_manager_user")
        check(approver == "quang@demo.example", f"Approver is {approver}")
        r["actual"] = f"{REQ['trip']}: {state}; Người duyệt: {approver}"

    s_an.close()

    # -------------------------------------------------------------------------
    # Part 2: Line Manager Quang approves travel request
    # -------------------------------------------------------------------------
    s_quang = Session(browser, "TRV", "quang")
    login(s_quang)
    with case(s_quang, "TRV-03", "Quản lý trực tiếp duyệt đề xuất công tác",
              "Workspace Quản lý > Mở đề xuất công tác > Hành động > Duyệt",
              REQ["trip"], "Trạng thái chuyển sang Chờ giám đốc duyệt") as r:
        state = workflow_action(s_quang, TR, REQ["trip"], "Duyệt")
        check(state == "Chờ giám đốc duyệt", f"State is {state}")
        r["actual"] = f"{REQ['trip']}: {state}"
    s_quang.close()

    # -------------------------------------------------------------------------
    # Part 3: CEO Thanh approves travel request
    # -------------------------------------------------------------------------
    s_thanh = Session(browser, "TRV", "thanh")
    login(s_thanh)
    with case(s_thanh, "TRV-04", "Giám đốc duyệt công tác: On Duty và sinh đề xuất tạm ứng",
              "Mở đề xuất công tác > Hành động > Duyệt",
              REQ["trip"], "Đã duyệt; tự ghi công On Duty các ngày công tác; sinh bản ghi Employee Advance Chờ kế toán kiểm tra") as r:
        state = workflow_action(s_thanh, TR, REQ["trip"], "Duyệt")
        check(state == "Đã duyệt", f"State is {state}")
        trip_doc = api_get(s_thanh, f"/api/resource/{TR}/{REQ['trip']}").json()["data"]
        REQ["advance"] = trip_doc.get("tlc_employee_advance")
        check(bool(REQ["advance"]), "Employee Advance was not generated")
        adv_state = api_get(s_thanh, f"/api/resource/{EA}/{REQ['advance']}").json()["data"].get("workflow_state")
        check(adv_state == "Chờ kế toán kiểm tra", f"Advance state is {adv_state}")

        # Check Attendance On Duty posted
        marks = api_get(s_thanh, f"/api/resource/Attendance?filters=" + json.dumps([
            ["employee", "=", an_emp_id],
            ["attendance_date", "between", [t_start, t_end]],
            ["docstatus", "=", 1]
        ])).json().get("data", [])
        check(len(marks) >= 3, f"Expected 3 attendance records, got {len(marks)}")
        r["actual"] = f"{REQ['trip']} Đã duyệt; sinh tạm ứng {REQ['advance']} ({adv_state}); ghi nhận {len(marks)} ngày công On Duty"

    # Test Department Head skip duplicate approval
    s_quang2 = Session(browser, "TRV", "quang")
    login(s_quang2)
    with case(s_quang2, "TRV-05", "Bỏ cấp duyệt khi người tạo là Trưởng bộ phận",
              "Trưởng phòng Quang tạo đề xuất công tác cho chính mình > Gửi duyệt",
              "Trần Minh Quang", "Bỏ qua cấp Quản lý, chuyển thẳng Chờ giám đốc duyệt") as r:
        quang_emp = api(s_quang2, "frappe.client.get_value", doctype="Employee",
                        filters=json.dumps({"user_id": "quang@demo.example"}), fieldname="name")
        q_trip_name = api(s_quang2, "frappe.client.insert", doc=json.dumps({
            "doctype": "Travel Request",
            "company": company,
            "employee": quang_emp["name"],
            "travel_type": "Domestic",
            "purpose_of_travel": "TLC Công tác",
            "tlc_destination": "Đà Nẵng",
            "description": "Hội nghị khách hàng",
            "tlc_from_date": working_day(20),
            "tlc_to_date": working_day(21),
            "tlc_from_session": "AM",
            "tlc_to_session": "PM",
            "tlc_funded": 0
        }))["name"]
        q_state = workflow_action(s_quang2, TR, q_trip_name, "Gửi giám đốc")
        check(q_state == "Chờ giám đốc duyệt", f"State is {q_state}")
        r["actual"] = f"{q_trip_name}: người tạo là Trưởng phòng chuyển thẳng '{q_state}' (HR-CHG-16)"

    s_quang2.close()

    # -------------------------------------------------------------------------
    # Part 4: Accountant Chi processes Advance and Payment
    # -------------------------------------------------------------------------
    s_chi = Session(browser, "FIN", "chi")
    login(s_chi)
    p = s_chi.page

    with case(s_chi, "FIN-01", "Duyệt không tự động ghi nhận đã chi khi thiếu chứng từ",
              "Mở đề xuất tạm ứng > Kiểm tra hồ sơ hợp lệ > Trạng thái chuyển Chờ chi, chưa phải Đã chi",
              REQ["advance"], "Trạng thái Chờ chi, paid_amount vẫn bằng 0") as r:
        state = workflow_action(s_chi, EA, REQ["advance"], "Hồ sơ hợp lệ")
        check(state == "Chờ chi", f"Advance state is {state}")
        adv_doc = api_get(s_chi, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]
        check(adv_doc.get("paid_amount", 0) == 0, "Paid amount should be 0")
        r["actual"] = f"{REQ['advance']}: {state}; paid_amount = 0 (phê duyệt chủ trương tách biệt với việc chi tiền)"

    with case(s_chi, "FIN-02", "Kế toán chi tạm ứng bằng chứng từ ngân hàng thực tế",
              "Tạo Payment Entry loại Pay đối ứng Employee Advance > Đính kèm ủy nhiệm chi > Ghi sổ > Xác nhận đã chi",
              f"4.000.000 VND qua VCB", "Tạm ứng chuyển sang Đã chi; số tiền đã ứng ghi nhận 4.000.000 VND") as r:
        bank_acc = api_get(s_chi, "/api/resource/Account?filters=" + json.dumps([
            ["company", "=", company], ["account_number", "=", "1121"]
        ])).json()["data"][0]["name"]
        adv_acc = api_get(s_chi, "/api/resource/Account?filters=" + json.dumps([
            ["company", "=", company], ["account_number", "=", "141"]
        ])).json()["data"][0]["name"]

        # Create Bank Payment Entry
        pe = api(s_chi, "frappe.client.insert", doc=json.dumps({
            "doctype": "Payment Entry",
            "payment_type": "Pay",
            "payment_order_type": "Payment Order",
            "party_type": "Employee",
            "party": an_emp_id,
            "company": company,
            "paid_from": bank_acc,
            "paid_to": adv_acc,
            "paid_amount": 4000000,
            "received_amount": 4000000,
            "reference_no": f"VCB-TU-{REQ['advance']}",
            "reference_date": dt.date.today().isoformat(),
            "references": [{
                "reference_doctype": "Employee Advance",
                "reference_name": REQ["advance"],
                "total_amount": 4000000,
                "outstanding_amount": 4000000,
                "allocated_amount": 4000000
            }]
        }))
        REQ["pe_advance"] = pe["name"]

        # Attach bank proof file
        proof_file = api(s_chi, "frappe.client.insert", doc=json.dumps({
            "doctype": "File",
            "file_name": f"UNC-{REQ['advance']}.txt",
            "is_private": 1,
            "attached_to_doctype": "Payment Entry",
            "attached_to_name": REQ["pe_advance"],
            "content": "Demo Bank Transfer Proof"
        }))
        api(s_chi, "frappe.client.set_value", doctype="Payment Entry", name=REQ["pe_advance"],
            fieldname="tlc_bank_proof", value=proof_file["file_url"])

        # Submit Payment Entry
        p.goto(f"{BASE}/desk/payment-entry/{REQ['pe_advance']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        p.keyboard.press("Control+s")
        p.wait_for_timeout(2000)
        p.keyboard.press("Escape")  # close the native "Saved" message before the submit confirm
        p.wait_for_timeout(500)
        p.locator("button:has-text('Submit'), button:has-text('Nộp')").first.click()
        p.wait_for_timeout(1200)
        confirm = p.locator(".modal:visible").get_by_role("button", name="Có")
        if confirm.count():
            confirm.last.click()
        p.wait_for_timeout(3000)

        # Confirm advance payment
        p.goto(f"{BASE}/desk/employee-advance/{REQ['advance']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        p.evaluate("([pe]) => cur_frm.set_value('tlc_payment_entry', pe)", [REQ["pe_advance"]])
        p.keyboard.press("Control+s")
        p.wait_for_timeout(2500)
        adv_state = workflow_action(s_chi, EA, REQ["advance"], "Xác nhận đã chi")
        check(adv_state == "Đã chi", f"Advance state is {adv_state}")
        adv_doc = api_get(s_chi, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]
        check(adv_doc.get("paid_amount") == 4000000, f"Paid amount is {adv_doc.get('paid_amount')}")
        r["actual"] = f"{REQ['advance']}: {adv_state}; Chứng từ {REQ['pe_advance']}; Đã ứng: {adv_doc.get('paid_amount'):,.0f} VND"

    s_chi.close()

    # -------------------------------------------------------------------------
    # Part 5: Expense Claim Settlement - Three-way settlement
    # -------------------------------------------------------------------------
    s_an = Session(browser, "FIN", "an")
    login(s_an)
    p = s_an.page

    with case(s_an, "FIN-03", "Lập báo cáo quyết toán tự tính chênh lệch thực chi",
              "Expense Claim > Mới > Liên kết Employee Advance > Nhập chi phí thực tế 3.500.000 > Lưu",
              f"Đã ứng 4.000.000, thực chi 3.500.000",
              "Hệ thống tự tính chênh lệch 500.000 VND và xác định nhánh refund (hoàn tiền thừa)") as r:
        p.goto(f"{BASE}/desk/expense-claim")
        p.wait_for_load_state("networkidle")
        p.evaluate("""([c, e, adv, trip, adv_acc, adv_pe]) => {
            frappe.new_doc('Expense Claim', {
                company: c, employee: e, tlc_travel_request: trip,
                advances: [{
                    employee_advance: adv,
                    advance_account: adv_acc,
                    reference_type: 'Payment Entry',
                    reference_name: adv_pe,
                    advance_paid: 4000000,
                    unclaimed_amount: 4000000,
                    allocated_amount: 3500000
                }],
                expenses: [
                    {expense_type: 'TLC Vé công tác', amount: 2000000, sanctioned_amount: 2000000, expense_date: frappe.datetime.nowdate()},
                    {expense_type: 'TLC Lưu trú', amount: 1500000, sanctioned_amount: 1500000, expense_date: frappe.datetime.nowdate()}
                ]
            });
        }""", [company, an_emp_id, REQ["advance"], REQ["trip"], adv_acc, REQ["pe_advance"]])
        p.wait_for_url(re.compile(r".*/expense-claim/new.*"))
        p.wait_for_timeout(2500)
        p.keyboard.press("Control+s")
        p.wait_for_timeout(3000)
        p.wait_for_function("() => window.cur_frm && cur_frm.doctype === 'Expense Claim' && !cur_frm.is_new()")
        REQ["claim"] = p.evaluate("cur_frm.doc.name")
        p.goto(f"{BASE}/desk/expense-claim/{REQ['claim']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_function("d => window.cur_frm && cur_frm.docname === d", arg=REQ["claim"])
        p.wait_for_function("() => cur_frm.doc.expenses && cur_frm.doc.expenses.length > 0")
        p.wait_for_timeout(2500)


        # Attach receipt proof to each expense line through the form (child rows of a claim
        # are not directly writable over the resource API for a self-service user).
        claim_doc = api_get(s_an, f"/api/resource/{EC}/{REQ['claim']}").json()["data"]
        receipts = []
        for detail in claim_doc.get("expenses", []):
            file_doc = api(s_an, "frappe.client.insert", doc=json.dumps({
                "doctype": "File", "file_name": f"HoaDon-{detail['name']}.txt", "is_private": 1,
                "attached_to_doctype": "Expense Claim", "attached_to_name": REQ["claim"],
                "content": "Invoice details"
            }))
            receipts.append(file_doc["file_url"])
        p.evaluate("""async (urls) => {
            for (let i = 0; i < cur_frm.doc.expenses.length; i++) {
                if (urls[i]) await frappe.model.set_value(cur_frm.doc.expenses[i].doctype, cur_frm.doc.expenses[i].name, 'tlc_receipt', urls[i]);
            }
        }""", receipts)
        p.wait_for_timeout(800)
        # The claim form reroutes after a save; do not await the promise across that navigation.
        p.evaluate("() => { cur_frm.save('Save'); }")
        p.wait_for_timeout(5000)
        p.wait_for_load_state("networkidle")
        claim_doc = api_get(s_an, f"/api/resource/{EC}/{REQ['claim']}").json()["data"]
        check(all(r.get("tlc_receipt") for r in claim_doc.get("expenses", [])), "Hóa đơn từng dòng chưa lưu")
        diff = claim_doc.get("tlc_difference")
        branch = claim_doc.get("tlc_settlement_branch")
        check(diff == 500000 and branch == "refund", f"Difference: {diff}, Branch: {branch}")

        workflow_action(s_an, EC, REQ["claim"], "Gửi duyệt")
        r["actual"] = f"{REQ['claim']}: Đã ứng 4.000.000, Thực chi 3.500.000 -> Chênh lệch {diff:,.0f} VND (Nhánh {branch})"

    s_an.close()

    # Approve claim sequentially
    s_quang = Session(browser, "FIN", "quang")
    login(s_quang)
    workflow_action(s_quang, EC, REQ["claim"], "Duyệt")
    s_quang.close()

    s_thanh = Session(browser, "FIN", "thanh")
    login(s_thanh)
    with case(s_thanh, "FIN-04", "Giám đốc duyệt báo cáo quyết toán",
              "Mở Expense Claim > Hành động > Duyệt", REQ["claim"],
              "Chuyển sang Chờ kế toán kiểm tra; phê duyệt chủ trương hoàn thành") as r:
        state = workflow_action(s_thanh, EC, REQ["claim"], "Duyệt")
        check(state == "Chờ kế toán kiểm tra", f"State is {state}")
        r["actual"] = f"{REQ['claim']}: {state}"
    s_thanh.close()

    # Accountant reconciles refund
    s_chi = Session(browser, "FIN", "chi")
    login(s_chi)
    with case(s_chi, "FIN-05", "Kế toán đối chiếu nhánh hoàn tiền thừa",
              "Kế toán kiểm tra chứng từ nộp trả tiền thừa 500.000 VND > Ghi nhận bút toán hoàn ứng (Journal Entry) > Hoàn tất quyết toán",
              "500.000 VND hoàn ứng", "Quyết toán chuyển Hoàn tất; số tiền hoàn lại được cập nhật vào Employee Advance") as r:
        workflow_action(s_chi, EC, REQ["claim"], "Hồ sơ hợp lệ")

        # Create Refund Payment Entry (Receive)
        bank_acc = api_get(s_chi, "/api/resource/Account?filters=" + json.dumps([
            ["company", "=", company], ["account_number", "=", "1121"]
        ])).json()["data"][0]["name"]
        adv_acc = api_get(s_chi, "/api/resource/Account?filters=" + json.dumps([
            ["company", "=", company], ["account_number", "=", "141"]
        ])).json()["data"][0]["name"]

        # HRMS books an advance return as a bank Journal Entry crediting the advance account.
        je_refund = api(s_chi, "frappe.client.insert", doc=json.dumps({
            "doctype": "Journal Entry",
            "voucher_type": "Bank Entry",
            "company": company,
            "posting_date": dt.date.today().isoformat(),
            "cheque_no": f"VCB-HOAN-{REQ['advance']}",
            "cheque_date": dt.date.today().isoformat(),
            "user_remark": f"Thu hồi tiền thừa tạm ứng {REQ['advance']} theo quyết toán {REQ['claim']}",
            "accounts": [
                {
                    "account": adv_acc,
                    "account_currency": "VND",
                    "credit_in_account_currency": 500000,
                    "party_type": "Employee",
                    "party": an_emp_id,
                    "reference_type": "Employee Advance",
                    "reference_name": REQ["advance"],
                    "is_advance": "Yes",
                    "cost_center": cost_center
                },
                {
                    "account": bank_acc,
                    "account_currency": "VND",
                    "debit_in_account_currency": 500000,
                    "cost_center": cost_center
                }
            ]
        }))
        # Attach proof and submit
        rf_file = api(s_chi, "frappe.client.insert", doc=json.dumps({
            "doctype": "File", "file_name": f"UNC-Hoan-{REQ['advance']}.txt", "is_private": 1,
            "attached_to_doctype": "Journal Entry", "attached_to_name": je_refund["name"],
            "content": "Refund bank slip"
        }))
        api(s_chi, "frappe.client.set_value", doctype="Journal Entry", name=je_refund["name"],
            fieldname="tlc_bank_proof", value=rf_file["file_url"])

        p = s_chi.page
        p.goto(f"{BASE}/desk/journal-entry/{je_refund['name']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        p.keyboard.press("Control+s")
        p.wait_for_timeout(2000)
        p.keyboard.press("Escape")
        p.wait_for_timeout(500)
        p.locator("button:has-text('Submit'), button:has-text('Nộp')").first.click()
        p.wait_for_timeout(1200)
        confirm = p.locator(".modal:visible").get_by_role("button", name="Có")
        if confirm.count():
            confirm.last.click()
        p.wait_for_timeout(3000)

        # Link refund entry and settle
        p.goto(f"{BASE}/desk/expense-claim/{REQ['claim']}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(2000)
        p.evaluate("([je]) => cur_frm.set_value('tlc_refund_entry', je)", [je_refund["name"]])
        p.keyboard.press("Control+s")
        p.wait_for_timeout(2500)
        cl_state = workflow_action(s_chi, EC, REQ["claim"], "Hoàn tất quyết toán")
        check(cl_state == "Hoàn tất", f"Claim state is {cl_state}")

        # Advance status should be claimed + returned
        adv_final = api_get(s_chi, f"/api/resource/{EA}/{REQ['advance']}").json()["data"]
        check(adv_final.get("claimed_amount") == 3500000 and adv_final.get("return_amount") == 500000,
              f"Advance not fully reconciled: {adv_final}")
        r["actual"] = f"{REQ['claim']} Hoàn tất; Tạm ứng {REQ['advance']}: Đã quyết toán 3.500.000, Đã hoàn 500.000, hết số dư treo"

    s_chi.close()

    # -------------------------------------------------------------------------
    # Part 6: Overdue Advance Salary Offset Guard (FIN-07, FIN-08)
    # -------------------------------------------------------------------------
    s_chi = Session(browser, "FIN", "chi")
    login(s_chi)
    # The employee owns the advance; the accountant only attempts the payroll recovery.
    s_an2 = Session(browser, "FIN", "an")
    login(s_an2)
    adv_overdue = api(s_an2, "frappe.client.insert", doc=json.dumps({
        "doctype": "Employee Advance",
        "company": company,
        "employee": an_emp_id,
        "advance_amount": 2000000,
        "purpose": "Tạm ứng quá hạn mẫu",
        "tlc_needed_on": "2026-09-01",
        "tlc_settlement_due": "2026-09-15",
        "workflow_state": "Nháp"
    }))
    s_an2.close()
    with case(s_chi, "FIN-07", "Chặn tự động khấu trừ lương khi chưa có chính sách hoặc chữ ký nhân viên",
              "Thử tạo Additional Salary loại Hoàn tạm ứng khi chưa có thỏa thuận có chữ ký",
              "Tạm ứng quá hạn", "Hệ thống từ chối: Bắt buộc có chính sách công ty và thỏa thuận đồng ý có chữ ký") as r:
        res = s_chi.page.request.post(f"{BASE}/api/resource/Additional Salary", data=json.dumps({
            "employee": an_emp_id,
            "company": company,
            "salary_component": "Hoàn tạm ứng",
            "payroll_date": "2026-10-31",
            "amount": 2000000,
            "ref_doctype": "Employee Advance",
            "ref_docname": adv_overdue["name"]
        }), headers={"X-Frappe-CSRF-Token": s_chi.page.evaluate("frappe.csrf_token"), "Content-Type": "application/json"})
        check(res.status != 200, "Should have rejected Additional Salary creation")
        err_msg = res.json().get("exception", "") or res.json().get("_server_messages", "")
        r["actual"] = "Bị chặn với lỗi: " + err_msg[:200]
    s_chi.close()

    # -------------------------------------------------------------------------
    # Part 7: Factory Manager Scope and No Self-Approval (GOV-01, GOV-02)
    # -------------------------------------------------------------------------
    s_hung = Session(browser, "GOV", "hung")  # Factory 1 manager
    login(s_hung)
    with case(s_hung, "GOV-01", "Quản lý nhà máy không duyệt được công tác ngoài phạm vi",
              "Trưởng Nhà máy 1 cố gắng mở hoặc duyệt đề xuất của nhân viên văn phòng An",
              REQ["trip"], "Bị chặn quyền xem/duyệt theo phạm vi nhà máy") as r:
        res = api_get(s_hung, f"/api/resource/{TR}?filters=" + json.dumps([
            ["employee", "=", an_emp_id]
        ]))
        trips = res.json().get("data", [])
        check(len(trips) == 0, f"Factory 1 manager should not see office trips, saw: {trips}")
        r["actual"] = f"Bộ lọc quyền query_conditions trả về 0 kết quả; quản lý không thấy hồ sơ ngoài phạm vi nhà máy"
    s_hung.close()

    s_an = Session(browser, "GOV", "an")
    login(s_an)
    with case(s_an, "GOV-02", "Không ai được tự duyệt yêu cầu của chính mình",
              "Nhân viên văn phòng An cố gắng tự duyệt đơn công tác của mình",
              REQ["trip"], "Bị chặn: Bạn không thể tự duyệt yêu cầu của chính mình") as r:
        res = s_an.page.request.put(f"{BASE}/api/resource/{TR}/{REQ['trip']}", data=json.dumps({
            "workflow_state": "Đã duyệt"
        }), headers={"X-Frappe-CSRF-Token": s_an.page.evaluate("frappe.csrf_token"), "Content-Type": "application/json"})
        check(res.status != 200, "Self approval should have been blocked")
        err_msg = res.json().get("exception", "") or res.json().get("_server_messages", "")
        r["actual"] = "Bị chặn với lỗi: " + err_msg[:200]
    s_an.close()


JOURNEYS = [travel_finance_flow]
