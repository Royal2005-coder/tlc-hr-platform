"""One self-contained HTML file of a UAT run, to send and open offline: cases, screenshots, videos and the Excel sheet embedded.

Usage: python3 offline_html.py out/<RUN_ID>   ->  out/<RUN_ID>/UAT_TLC_HRM_<RUN_ID>_offline.html
Videos are the MP4 copies made by run_uat.sh (H.264, seekable, plays everywhere), WebM when there is none.
Nothing is loaded from the network.
"""

import base64
import html
import json
import sys
from pathlib import Path

SECTIONS = ["hrms", "ws_manager", "ws_hr", "ws_ceo", "approve", "company"]
SECTION_LABEL = {"hrms": "App Frappe HR (/hrms)", "ws_manager": "Workspace TLC Quản lý", "ws_hr": "Workspace TLC Nhân sự",
                 "ws_ceo": "Workspace TLC Điều hành", "approve": "Duyệt đơn", "company": "Xem toàn công ty"}
MODULES = [("NV", "Nghỉ phép"), ("HT", "Nghỉ phép"), ("CN", "Nghỉ phép"), ("QL", "Nghỉ phép"), ("HR", "Nghỉ phép, tham số lương"),
           ("CEO", "Nghỉ phép, điều hành"), ("OT", "Tăng ca")]
e = html.escape


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def seconds(stamp):
    m, s = stamp.split(":")
    return int(m) * 60 + int(s)


def module_of(case_id):
    return next((name for prefix, name in MODULES if case_id.startswith(prefix)), "")


def build(run_dir):
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    results, videos, matrix, run_id = data["results"], data["videos"], data.get("matrix", {}), data["run"]
    passed = sum(r["status"] == "Đạt" for r in results)
    xlsx = next(run_dir.glob("UAT_TLC_HRM_*.xlsx"), None)
    xlsx_link = (f'<a class="btn" download="{e(xlsx.name)}" href="{data_uri(xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}">'
                 f'Tải sheet UAT (Excel)</a>') if xlsx else ""

    summary_rows = "".join(
        f"<tr><td><a href='#v{i}'>{e(v['code'])}</a></td><td>{e(v['role'])}</td><td>{e(v['account'])}@demo.example</td>"
        f"<td>{sum(r['video'] == v['file'] for r in results)}</td>"
        f"<td>{sum(r['video'] == v['file'] and r['status'] == 'Đạt' for r in results)}</td></tr>"
        for i, v in enumerate(videos))
    matrix_rows = "".join(
        f"<tr><td>{e(acc)}@demo.example</td>" + "".join(f"<td class='c'>{'✓' if k in keys else ''}</td>" for k in SECTIONS) + "</tr>"
        for acc, keys in matrix.items())
    case_rows = "".join(
        f"<tr class='{'ok' if r['status'] == 'Đạt' else 'bad'}'><td><a href='#{e(r['id'])}'>{e(r['id'])}</a></td><td>{e(module_of(r['id']))}</td>"
        f"<td>{e(r['account'])}</td><td>{e(r['function'])}</td><td><b>{e(r['status'])}</b></td></tr>" for r in results)

    sections = []
    for i, v in enumerate(videos):
        video_path = run_dir / v["file"]
        mp4 = video_path.with_suffix(".mp4")
        video_path, mime = (mp4, "video/mp4") if mp4.exists() else (video_path, "video/webm")
        cases = [r for r in results if r["video"] == v["file"]]
        items = []
        for r in cases:
            shot = run_dir / r["shot"] if r.get("shot") else None
            image = (f"<details><summary>Ảnh màn hình</summary><img loading='lazy' src='{data_uri(shot, 'image/png')}' "
                     f"alt='{e(r['id'])}'></details>") if shot and shot.exists() else ""
            items.append(f"""<article id="{e(r['id'])}" class="case {'ok' if r['status'] == 'Đạt' else 'bad'}">
<header><b>{e(r['id'])}</b> {e(r['function'])}<span class="st">{e(r['status'])}</span>
<button onclick="seek('video{i}',{seconds(r['time'])})">▶ Xem từ {e(r['time'])}</button></header>
<dl><dt>Thao tác</dt><dd>{e(r['steps'])}</dd><dt>Dữ liệu</dt><dd>{e(r['data']) or '-'}</dd>
<dt>Kết quả mong đợi</dt><dd>{e(r['expected'])}</dd><dt>Kết quả thực tế</dt><dd>{e(r['actual'])}</dd>
<dt>Thời điểm chạy</dt><dd>{e(r['run_at'])}</dd></dl>{image}</article>""")
        player = (f"<video id='video{i}' controls preload='metadata' src='{data_uri(video_path, mime)}'></video>"
                  if video_path.exists() else "<p>Không có video.</p>")
        sections.append(f"""<section id="v{i}s"><h2 id="v{i}">{e(v['code'])} · {e(v['role'])}</h2>
<p class="muted">Tài khoản {e(v['account'])}@demo.example · {e(v['device'])} · {len(cases)} trường hợp</p>
{player}{''.join(items)}</section>""")

    recorded = {v["file"] for v in videos}
    support = [r for r in results if r["video"] not in recorded]
    support_html = "".join(f"<tr><td>{e(r['id'])}</td><td>{e(r['account'])}</td><td>{e(r['function'])}</td><td>{e(r['actual'])}</td>"
                           f"<td><b>{e(r['status'])}</b></td></tr>" for r in support)

    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UAT TLC HRM {e(run_id)}</title>
<style>
body{{font:14px/1.5 -apple-system,"Segoe UI",Inter,Roboto,sans-serif;color:#1f272e;background:#f8f8f8;margin:0}}
main{{max-width:1180px;margin:0 auto;padding:24px 20px 60px}}
h1{{font-size:24px;margin:0}} h2{{font-size:18px;margin:0}} .muted{{color:#6c7680;margin:4px 0 12px}}
.card,section{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:16px 18px;margin:0 0 16px}}
.kpi{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}} .kpi div{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:10px 16px}}
.kpi b{{display:block;font-size:22px}} .btn{{display:inline-block;background:#171717;color:#fff;border-radius:6px;padding:7px 14px;text-decoration:none}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{border-bottom:1px solid #ededed;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f3f3;font-weight:600}} td.c{{text-align:center;color:#28a745;font-weight:700}}
tr.bad td{{background:#fff0f0}} a{{color:#2490ef}} video{{width:100%;background:#000;border-radius:6px;margin:4px 0 12px}}
.case{{border:1px solid #ededed;border-left:4px solid #28a745;border-radius:6px;padding:10px 12px;margin:10px 0}} .case.bad{{border-left-color:#e24c4c}}
.case header{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} .st{{margin-left:auto;font-weight:600;color:#28a745}} .bad .st{{color:#e24c4c}}
.case button{{border:1px solid #d1d1d1;background:#fff;border-radius:6px;padding:3px 10px;cursor:pointer}}
dl{{display:grid;grid-template-columns:150px 1fr;gap:3px 12px;margin:8px 0 0}} dt{{color:#6c7680}} dd{{margin:0}}
details summary{{cursor:pointer;color:#2490ef;margin-top:6px}} details img{{max-width:100%;border:1px solid #e2e2e2;border-radius:6px;margin-top:6px}}
nav.toc a{{margin-right:12px}}
</style></head><body><main>
<h1>Bằng chứng UAT · TLC HRM trên Frappe HR v16</h1>
<p class="muted">Lần chạy {e(run_id)} · giao diện desktop web (1366×820) · dữ liệu demo · một file duy nhất, mở offline bằng trình duyệt</p>
<div class="kpi"><div>Trường hợp đạt<b>{passed}/{len(results)}</b></div><div>Vai trò / video<b>{len(videos)}</b></div>
<div>Tài khoản<b>{len(matrix)}</b></div><div>Phân hệ<b>Nghỉ phép · Tăng ca</b></div></div>
<p>{xlsx_link}</p>
<div class="card"><h2>Theo vai trò</h2><p class="muted">Mỗi vai trò là một video liền mạch; bấm "▶ Xem từ" ở từng trường hợp để tua đến đúng đoạn.</p>
<table><tr><th>Mã</th><th>Vai trò</th><th>Tài khoản</th><th>Số TH</th><th>Đạt</th></tr>{summary_rows}</table></div>
<div class="card"><h2>Ma trận chức năng theo tài khoản</h2><table><tr><th>Tài khoản</th>{''.join(f'<th>{e(SECTION_LABEL[k])}</th>' for k in SECTIONS)}</tr>{matrix_rows}</table></div>
<div class="card"><h2>Danh sách trường hợp kiểm thử</h2><table><tr><th>Mã</th><th>Phân hệ</th><th>Tài khoản</th><th>Chức năng</th><th>KQ</th></tr>{case_rows}</table></div>
{f'<div class="card"><h2>Bước hỗ trợ (qua API, không ghi hình)</h2><table><tr><th>Mã</th><th>Tài khoản</th><th>Chức năng</th><th>Thực tế</th><th>KQ</th></tr>{support_html}</table></div>' if support else ''}
{''.join(sections)}
</main><script>function seek(id,t){{const v=document.getElementById(id);v.scrollIntoView({{behavior:'smooth',block:'center'}});v.currentTime=t;v.play();}}</script>
</body></html>"""
    target = run_dir / f"UAT_TLC_HRM_{run_id}_offline.html"
    target.write_text(page, encoding="utf-8")
    return target


if __name__ == "__main__":
    path = build(Path(sys.argv[1]))
    print(path, f"{path.stat().st_size / 1e6:.1f} MB")
