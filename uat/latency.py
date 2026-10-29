"""Measure the round trip a person actually waits for when talking to @Leo in Raven."""
import os
import time

from playwright.sync_api import sync_playwright

from lib import BASE, Session, login

CHANNEL = "/raven/dm-channel/h7hfl3do7a"


def ask(page, text, budget=200):
    composer = page.locator("textarea:visible").last
    before = page.locator(".message-container").count()
    composer.click()
    composer.fill(text)
    started = time.time()
    page.keyboard.press("Enter")
    while time.time() - started < budget:
        page.wait_for_timeout(1000)
        if page.locator(".message-container").count() > before + 1:
            body = page.locator(".message-container").last.inner_text()
            return round(time.time() - started, 1), " ".join(body.split())[:150]
    return None, "HET-GIO-CHO"


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    s = Session(browser, "LG", "hoa")
    login(s)
    page = s.page
    page.goto(f"{BASE}{CHANNEL}", wait_until="networkidle")
    page.wait_for_timeout(7000)
    print("BASE", BASE)
    print("REALTIME-BANNER", "CO-LOI" if page.locator("text=/Realtime events/").count() else "khong")
    for label, text in (("HI", "hi"),
                        ("LEAVE", "Soạn đơn nghỉ phép ngày 22 và 23 tháng 12 lý do bệnh")):
        seconds, sample = ask(page, text)
        print(f"LATENCY-{label}", seconds, "|", sample)
    s.close()
