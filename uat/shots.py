"""Screenshots per account for design review. Usage: python shots.py <out dir> account[:path][:phone] ...
Without a path the screenshot shows where the account lands after login."""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:30080")
PASSWORD = os.environ["DEMO_PASSWORD"]


def main(out, specs):
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for spec in specs:
            parts = spec.split(":")
            account, path, phone = parts[0], (parts[1] if len(parts) > 1 else ""), "phone" in parts[2:]
            ctx = browser.new_context(viewport={"width": 390, "height": 844} if phone else {"width": 1366, "height": 860},
                                      device_scale_factor=2 if phone else 1, is_mobile=phone, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
            page = ctx.new_page()
            page.goto(f"{BASE}/login")
            page.fill("#login_email", f"{account}@demo.example")
            page.fill("#login_password", PASSWORD)
            page.click("form.form-login button[type=submit]")
            page.wait_for_url(lambda url: "/login" not in url, timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2500)
            landed = page.url.replace(BASE, "")
            if path:
                page.goto(f"{BASE}{path}")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)
            name = f"{account}_{(path or 'landing').strip('/').replace('/', '_').replace('?', '_')}{'_phone' if phone else ''}.png"
            page.screenshot(path=os.path.join(out, name), full_page=False)
            print(name, "landed", landed, flush=True)
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
