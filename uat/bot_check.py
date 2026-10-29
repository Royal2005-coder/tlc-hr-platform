"""Ask the assistant in Raven and judge the answer the way a person reads it."""
import json
import re
import time

from playwright.sync_api import sync_playwright

from lib import BASE, Session, api, login

HOST = re.sub(r"^https?://", "", BASE).split("/")[0]


def bot_messages(channel, after):
    return api(s, "frappe.client.get_list", doctype="Raven Message",
               filters=json.dumps([["channel_id", "=", channel], ["is_bot_message", "=", 1]]),
               fields='["name","text","creation"]', order_by="creation desc", limit_page_length=5)


def ask(page, target, channel, text, budget=170):
    """Time the wait for a message this channel had not seen yet; the greeting answers anything otherwise."""
    before = {row["name"] for row in bot_messages(channel, None)}
    box = target.locator("div[contenteditable='true']").last
    box.click()
    box.type(text)
    page.keyboard.press("Enter")
    started = time.time()
    while time.time() - started < budget:
        page.wait_for_timeout(3000)
        fresh = [row for row in bot_messages(channel, None) if row["name"] not in before]
        if fresh and (fresh[0].get("text") or "").strip():
            return round(time.time() - started, 1), fresh[0]["text"]
    return None, "(hết thời gian chờ)"


def judge(label, seconds, message):
    flat = " ".join(message.split())
    problems = []
    if "**" in flat or "](" in flat:
        problems.append("markdown-thô")
    foreign = sorted(link for link in re.findall(r"https?://([^/\s)]+)", flat) if link != HOST)
    if foreign:
        problems.append("link-lạ:" + ",".join(foreign))
    print(f"TURN-{label}", seconds, "s |", "OK" if not problems else " ".join(problems), "|", flat[:180])


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    s = Session(browser, "LG", "hoa")
    login(s)
    page = s.page
    dm = api(s, "frappe.client.get_value", doctype="Raven Channel",
             filters='{"is_direct_message": 1, "dm_user_1": "hoa@demo.example"}', fieldname='["name"]')
    channel = dm["name"]
    page.goto(f"{BASE}/raven/dm-channel/{channel}", wait_until="networkidle")
    page.wait_for_timeout(8000)
    target = page.frame_locator("iframe").first if page.locator("iframe").count() else page
    print("BANNER", "CO-LOI" if page.locator("text=/Realtime events/").count() else "khong")
    judge("DOC", *ask(page, target, channel, "Cho tôi biết mã nhân viên của tôi, trả lời ngắn gọn."))
    judge("LEAVE", *ask(page, target, channel, "Soạn đơn nghỉ phép ngày 20 và 21 tháng 12 lý do bệnh"))
    s.close()
