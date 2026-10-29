from playwright.sync_api import sync_playwright

from lib import BASE, PASSWORD

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    calls, errors = [], []
    page.on("request", lambda r: calls.append((r.method, r.url[:96])) if "/api/" in r.url else None)
    page.on("console", lambda m: errors.append(m.text[:120]) if m.type in ("error", "warning") else None)
    page.goto(f"{BASE}/login", wait_until="networkidle")
    calls.clear()
    page.locator("#login_email").fill("hoa@demo.example")
    page.locator("#login_password").fill(PASSWORD)
    page.locator('button:has-text("Tiếp tục")').first.click()
    page.wait_for_timeout(8000)
    print("CALLS", calls[:6])
    print("ALERT", " | ".join(" ".join(x.inner_text().split()) for x in page.locator("[role=alert], .alert").all() if x.inner_text().strip())[:200])
    print("CONSOLE", errors[:3])
    browser.close()
