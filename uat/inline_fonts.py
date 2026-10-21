"""Make a self-contained HTML really offline: replace the Google Fonts <link> with @font-face rules whose woff2 are base64 data URIs.

The deck and the evidence pack embed every screenshot and video, but the theme links Google Fonts. Running this on the
file that goes to the customer means it opens with the intended typeface on a machine with no network.

Usage: python3 inline_fonts.py <file.html>
"""

import base64
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
LINK = re.compile(r'<link[^>]*href="(https://fonts\.googleapis\.com/css2[^"]*)"[^>]*>')


def faces(stylesheet_url):
    css = urllib.request.urlopen(urllib.request.Request(stylesheet_url, headers=UA), timeout=60).read().decode()
    cache, out = {}, []
    for block in re.findall(r"@font-face\s*{[^}]*}", css):
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        if not url:
            continue
        src = url.group(1)
        if src not in cache:
            cache[src] = base64.b64encode(urllib.request.urlopen(urllib.request.Request(src, headers=UA), timeout=60).read()).decode()
        out.append(block.replace(src, "data:font/woff2;base64," + cache[src]))
    return out, len(cache)


def main(path):
    html = open(path, encoding="utf-8").read()
    link = LINK.search(html)
    if not link:
        print(f"{path}: không có liên kết Google Fonts, giữ nguyên")
        return
    rules, files = faces(link.group(1))
    open(path, "w", encoding="utf-8").write(html.replace(link.group(0), "<style>" + "\n".join(rules) + "</style>"))
    print(f"{path}: đã nhúng {len(rules)} @font-face từ {files} tệp woff2")


if __name__ == "__main__":
    main(sys.argv[1])
