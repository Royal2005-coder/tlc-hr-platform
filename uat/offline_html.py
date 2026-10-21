"""One self-contained HTML file of a UAT run, to send and open offline.

Sections: overview, roles (journeys, pain points, improvements), modules (user stories with Given/When/Then and their cases),
recorded evidence (video per session, every case with steps, result, screenshot and a button that seeks the video), and
coverage of the TLC blueprint (322 requirements, 42 blueprint UAT scenarios; see coverage.py).
Usage: python3 offline_html.py out/<RUN_ID>   ->  out/<RUN_ID>/UAT_TLC_HRM_<RUN_ID>_offline.html
Videos are the MP4 copies made by run_uat.sh (H.264, seekable), WebM when there is none. Nothing is loaded from the network.
"""

import base64
import html
import json
import re
import sys
from pathlib import Path

from coverage import PASSED, compute, load_roles, load_stories

HERE = Path(__file__).resolve().parent
SECTIONS = ["hrms", "ws_manager", "ws_hr", "ws_ceo", "approve", "company"]
SECTION_LABEL = {"hrms": "App Frappe HR (/hrms)", "ws_manager": "Workspace TLC Quản lý", "ws_hr": "Workspace TLC Nhân sự",
                 "ws_ceo": "Workspace TLC Điều hành", "approve": "Duyệt đơn", "company": "Xem toàn công ty"}
e = html.escape


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def seconds(stamp):
    m, s = (stamp or "0:0").split(":")
    return int(m) * 60 + int(s)


def badge(status):
    ok = status in ("Đạt", PASSED)
    cls = "ok" if ok else "out" if status == "Ngoài Frappe" else "plan" if status.startswith("Kế hoạch") else "bad"
    return f"<span class='b {cls}'>{e(status)}</span>"


def image_tag():
    kustomization = HERE.parent / "deploy" / "k8s" / "kustomization.yaml"
    found = re.search(r"newTag:\s*(\S+)", kustomization.read_text()) if kustomization.exists() else None
    return found.group(1) if found else "?"


def account_key(entry):
    return entry.split()[0]


def build(run_dir):
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    results, videos, matrix, run_id = data["results"], data["videos"], data.get("matrix", {}), data["run"]
    modules, roles = load_stories(), load_roles()
    cov = compute(results, modules)
    case_of = {r["id"]: r for r in results}
    story_of_case = {c: s["id"] for m in modules for s in m["stories"] for c in s.get("cases", [])}
    stories = {s["id"]: s for m in modules for s in m["stories"]}
    video_index = {v["file"]: i for i, v in enumerate(videos)}
    passed = sum(r["status"] == "Đạt" for r in results)
    stories_ok = sum(1 for st in cov["stories"].values() if st == PASSED)
    brd_ok = sum(r["status"] == PASSED for r in cov["brd"])
    uat_ok = sum(r["status"] == PASSED for r in cov["uat"])
    xlsx = next(run_dir.glob("UAT_TLC_HRM_*.xlsx"), None)
    xlsx_link = (f'<a class="btn" download="{e(xlsx.name)}" href="{data_uri(xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}">'
                 f'Tải sheet UAT (Excel)</a>') if xlsx else ""

    def case_link(cid):
        r = case_of.get(cid)
        return f"<a href='#{e(cid)}'>{e(cid)}</a> {badge(r['status']) if r else badge('Chưa chạy')}"

    # ------------------------------------------------------------------ roles
    role_html = []
    for role in roles:
        keys = {account_key(a) for a in role.get("accounts", [])}
        role_videos = [f"<a href='#video{i}'>▶ {e(v['code'])} · {e(v['account'])}</a>" for i, v in enumerate(videos) if v["account"] in keys]
        steps = "".join(f"<li><a href='#{e(sid)}'>{e(sid)}</a> {e(stories[sid]['title'])} {badge(cov['stories'].get(sid, 'Chưa chạy'))}</li>"
                        for sid in role.get("journeys", []) if sid in stories)
        role_html.append(f"""<section class="role" id="role-{e(role['key'])}"><h3>{e(role['title'])}</h3>
<p class="muted">{e(role.get('people', ''))} · Tài khoản demo: {e(', '.join(role.get('accounts', [])))}</p>
<p><b>Làm việc ở đâu:</b> {e(role.get('interface', ''))}</p>
<div class="cols"><div><h4>Mục tiêu</h4><ul>{''.join(f'<li>{e(g)}</li>' for g in role.get('goals', []))}</ul></div>
<div><h4>Nỗi đau hiện tại</h4><ul>{''.join(f'<li>{e(p)}</li>' for p in role.get('pain_points', []))}</ul></div>
<div><h4>TLC HRM cải tiến</h4><ul>{''.join(f'<li>{e(p)}</li>' for p in role.get('improvements', []))}</ul></div></div>
<h4>Hành trình (user story)</h4><ol>{steps}</ol><p>{' · '.join(role_videos)}</p></section>""")

    # ------------------------------------------------------------------ modules and stories
    module_html = []
    for m in modules:
        cards = []
        for s in m["stories"]:
            ac = "".join(f"<tr><td>{e(a.get('given', ''))}</td><td>{e(a.get('when', ''))}</td><td>{e(a.get('then', ''))}</td></tr>"
                         for a in s.get("ac", []))
            refs = " ".join(f"<code>{e(x)}</code>" for x in (s.get("brd") or []) + (s.get("blueprint_uat") or []))
            cards.append(f"""<article class="story" id="{e(s['id'])}"><header><b>{e(s['id'])}</b> {e(s['title'])}
{badge(cov['stories'].get(s['id'], 'Chưa chạy'))}</header><p class="say">{e(s['story'])}</p>
<table class="ac"><tr><th>Cho trước (Given)</th><th>Khi (When)</th><th>Thì (Then)</th></tr>{ac}</table>
<p class="muted">Yêu cầu: {refs or '-'}</p><p>Trường hợp kiểm thử: {' · '.join(case_link(c) for c in s.get('cases', []))}</p></article>""")
        ok = sum(cov["stories"].get(s["id"]) == PASSED for s in m["stories"])
        module_html.append(f"""<section id="mod-{e(m['module'])}"><h3>{e(m['title'])} <small>{e(m.get('wave', ''))} · {ok}/{len(m['stories'])} story đạt</small></h3>
<p>{e(m.get('summary', ''))}</p>{''.join(cards)}</section>""")

    # ------------------------------------------------------------------ evidence
    evidence = []
    for i, v in enumerate(videos):
        video_path = run_dir / v["file"]
        mp4 = video_path.with_suffix(".mp4")
        video_path, mime = (mp4, "video/mp4") if mp4.exists() else (video_path, "video/webm")
        cases = [r for r in results if r["video"] == v["file"]]
        items = []
        for r in cases:
            shot = run_dir / r["shot"] if r.get("shot") else None
            image = (f"<details><summary>Ảnh màn hình</summary><img loading='lazy' src='{data_uri(shot, 'image/png')}' alt='{e(r['id'])}'>"
                     f"</details>") if shot and shot.exists() else ""
            sid = story_of_case.get(r["id"], "")
            items.append(f"""<article id="{e(r['id'])}" class="case {'ok' if r['status'] == 'Đạt' else 'bad'}">
<header><b>{e(r['id'])}</b> {e(r['function'])} {f"<a class='tag' href='#{e(sid)}'>{e(sid)}</a>" if sid else ''}<span class="st">{e(r['status'])}</span>
<button onclick="seek('video{i}',{seconds(r['time'])})">▶ Xem từ {e(r['time'])}</button></header>
<dl><dt>Thao tác</dt><dd>{e(r['steps'])}</dd><dt>Dữ liệu</dt><dd>{e(r['data']) or '-'}</dd>
<dt>Kết quả mong đợi</dt><dd>{e(r['expected'])}</dd><dt>Kết quả thực tế</dt><dd>{e(r['actual'])}</dd>
<dt>Thời điểm chạy</dt><dd>{e(r['run_at'])}</dd></dl>{image}</article>""")
        player = (f"<video id='video{i}' controls preload='metadata' src='{data_uri(video_path, mime)}'></video>"
                  if video_path.exists() else "<p>Không có video.</p>")
        evidence.append(f"""<section><h3 id="v{i}">{e(v['code'])} · {e(v['role'])}</h3>
<p class="muted">Tài khoản {e(v['account'])}@demo.example · {e(v['device'])} · {len(cases)} trường hợp</p>{player}{''.join(items)}</section>""")
    orphans = [r for r in results if r["video"] not in video_index]
    if orphans:
        evidence.append("<section><h3>Bước không ghi hình</h3><table><tr><th>Mã</th><th>Tài khoản</th><th>Chức năng</th><th>Thực tế</th><th>KQ</th></tr>"
                        + "".join(f"<tr><td id='{e(r['id'])}'>{e(r['id'])}</td><td>{e(r['account'])}</td><td>{e(r['function'])}</td>"
                                  f"<td>{e(r['actual'])}</td><td>{badge(r['status'])}</td></tr>" for r in orphans) + "</table></section>")

    # ------------------------------------------------------------------ coverage
    if cov["has_catalog"]:
        domain_rows = "".join(f"<tr><td>{e(d['label'])} <code>{e(d['domain'])}</code></td><td>{e(d['wave'])}</td><td>{d['total']}</td><td>{d['p0']}</td>"
                              f"<td>{d['passed']}</td><td>{d['partial']}</td><td>{d['outside']}</td>"
                              f"<td>{d['total'] - d['passed'] - d['partial'] - d['outside']}</td></tr>" for d in cov["domains"])
        brd_details = "".join(
            f"<details><summary>{e(d['label'])} ({d['total']})</summary><table><tr><th>Mã</th><th>Ưu tiên</th><th>Yêu cầu</th><th>Trạng thái</th><th>Story</th></tr>"
            + "".join(f"<tr><td>{e(r['id'])}</td><td>{e(r['priority'])}</td><td>{e(r['text'][:220])}{'…' if len(r['text']) > 220 else ''}"
                      f"{('<br><i>' + e(r['note']) + '</i>') if r['note'] else ''}</td><td>{badge(r['status'])}</td>"
                      f"<td>{' '.join(f'<a href=#{e(s)}>{e(s)}</a>' for s in r['stories'])}</td></tr>"
                      for r in cov["brd"] if r["domain"] == d["domain"]) + "</table></details>" for d in cov["domains"])
        uat_rows = "".join(f"<tr><td>{e(u['id'])}</td><td>{e(u['scenario'])}</td><td>{e(u['assertion'])}</td><td>{badge(u['status'])}</td>"
                           f"<td>{' '.join(f'<a href=#{e(s)}>{e(s)}</a>' for s in u['stories'])}</td></tr>" for u in cov["uat"])
        coverage_html = f"""<section><h3>Theo phân hệ (322 yêu cầu BRD)</h3><table><tr><th>Phân hệ</th><th>Đợt</th><th>Yêu cầu</th><th>P0</th>
<th>Đạt UAT</th><th>Có story, chưa đạt</th><th>Ngoài Frappe</th><th>Còn theo kế hoạch</th></tr>{domain_rows}</table></section>
<section><h3>Chi tiết từng yêu cầu</h3>{brd_details}</section>
<section><h3>42 kịch bản UAT của blueprint</h3><table><tr><th>Mã</th><th>Kịch bản</th><th>Điều kiện đạt</th><th>Trạng thái</th><th>Story</th></tr>{uat_rows}</table></section>"""
    else:
        coverage_html = "<section><p>Không có catalogue blueprint trên máy tạo báo cáo (TLC_CATALOG).</p></section>"

    matrix_rows = "".join(f"<tr><td>{e(acc)}@demo.example</td>" + "".join(f"<td class='c'>{'✓' if k in keys else ''}</td>" for k in SECTIONS) + "</tr>"
                          for acc, keys in matrix.items())
    module_rows = "".join(
        f"<tr><td><a href='#mod-{e(m['module'])}'>{e(m['title'])}</a></td><td>{e(m.get('wave', ''))}</td><td>{len(m['stories'])}</td>"
        f"<td>{sum(cov['stories'].get(s['id']) == PASSED for s in m['stories'])}</td>"
        f"<td>{sum(len(s.get('cases', [])) for s in m['stories'])}</td></tr>" for m in modules)

    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UAT TLC HRM {e(run_id)}</title>
<style>
body{{font:14px/1.5 -apple-system,"Segoe UI",Inter,Roboto,sans-serif;color:#1f272e;background:#f8f8f8;margin:0}}
nav{{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #e2e2e2;padding:10px 20px}} nav a{{margin-right:18px;color:#1f272e;font-weight:600;text-decoration:none}}
main{{max-width:1180px;margin:0 auto;padding:20px 20px 60px}} h1{{font-size:24px;margin:0}} h2{{font-size:20px;margin:32px 0 12px}}
h3{{font-size:17px;margin:0 0 8px}} h3 small{{color:#6c7680;font-weight:400;font-size:13px}} h4{{font-size:14px;margin:10px 0 4px}}
.muted{{color:#6c7680;margin:4px 0 10px}} section{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:16px 18px;margin:0 0 16px}}
.kpi{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}} .kpi div{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:10px 16px;min-width:130px}}
.kpi b{{display:block;font-size:22px}} .btn{{display:inline-block;background:#171717;color:#fff;border-radius:6px;padding:7px 14px;text-decoration:none}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0}} th,td{{border-bottom:1px solid #ededed;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f3f3;font-weight:600}} td.c{{text-align:center;color:#28a745;font-weight:700}} a{{color:#2490ef}} code{{background:#f3f3f3;border-radius:4px;padding:0 4px;font-size:12px}}
.b{{display:inline-block;border-radius:10px;padding:0 8px;font-size:12px;font-weight:600;white-space:nowrap}} .b.ok{{background:#e4f5e9;color:#16794c}}
.b.bad{{background:#fff0f0;color:#c0392b}} .b.plan{{background:#f3f3f3;color:#6c7680}} .b.out{{background:#fff5e0;color:#a0610c}}
.cols{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}} .cols ul{{margin:0;padding-left:18px}}
.story,.case{{border:1px solid #ededed;border-left:4px solid #2490ef;border-radius:6px;padding:10px 12px;margin:10px 0}}
.case{{border-left-color:#28a745}} .case.bad{{border-left-color:#e24c4c}} .say{{font-style:italic;margin:6px 0}}
.story header,.case header{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} .st{{margin-left:auto;font-weight:600;color:#28a745}} .bad .st{{color:#e24c4c}}
.tag{{font-size:12px;background:#eef6fe;border-radius:4px;padding:0 6px;text-decoration:none}}
.case button{{border:1px solid #d1d1d1;background:#fff;border-radius:6px;padding:3px 10px;cursor:pointer}}
dl{{display:grid;grid-template-columns:150px 1fr;gap:3px 12px;margin:8px 0 0}} dt{{color:#6c7680}} dd{{margin:0}}
details summary{{cursor:pointer;color:#2490ef;margin:6px 0}} details img{{max-width:100%;border:1px solid #e2e2e2;border-radius:6px;margin-top:6px}}
video{{width:100%;background:#000;border-radius:6px;margin:4px 0 12px}}
</style></head><body>
<nav><a href="#tong-quan">Tổng quan</a><a href="#vai-tro">Vai trò &amp; hành trình</a><a href="#phan-he">Phân hệ &amp; story</a>
<a href="#bang-chung">Bằng chứng video</a><a href="#phu">Phủ yêu cầu</a></nav><main>
<h1 id="tong-quan">TLC HRM trên Frappe HR – UAT theo hành trình người dùng</h1>
<p class="muted">Lần chạy {e(run_id)} · image tlc-hr:{e(image_tag())} · giao diện desktop web 1366×820 · dữ liệu demo (người và số liệu giả lập) · một file, mở offline bằng trình duyệt</p>
<div class="kpi"><div>Trường hợp đạt<b>{passed}/{len(results)}</b></div><div>User story đạt<b>{stories_ok}/{len(stories)}</b></div>
<div>Phân hệ đã UAT<b>{len(modules)}</b></div><div>Video<b>{len(videos)}</b></div>
<div>Yêu cầu BRD đạt UAT<b>{brd_ok}/{len(cov['brd']) or '?'}</b></div><div>Kịch bản blueprint đạt<b>{uat_ok}/{len(cov['uat']) or '?'}</b></div></div>
<p>{xlsx_link}</p>
<section><h3>Phân hệ trong lần chạy</h3><table><tr><th>Phân hệ</th><th>Đợt</th><th>Story</th><th>Story đạt</th><th>Trường hợp</th></tr>{module_rows}</table></section>
<section><h3>Ma trận chức năng theo tài khoản</h3><table><tr><th>Tài khoản</th>{''.join(f'<th>{e(SECTION_LABEL[k])}</th>' for k in SECTIONS)}</tr>{matrix_rows}</table></section>
<h2 id="vai-tro">Vai trò &amp; hành trình</h2>{''.join(role_html)}
<h2 id="phan-he">Phân hệ &amp; user story</h2>{''.join(module_html)}
<h2 id="bang-chung">Bằng chứng video</h2><p class="muted">Mỗi phiên là một video liền mạch; "▶ Xem từ" tua đến đúng trường hợp.</p>{''.join(evidence)}
<h2 id="phu">Phủ yêu cầu blueprint TLC</h2>{coverage_html}
</main><script>function seek(id,t){{const v=document.getElementById(id);v.scrollIntoView({{behavior:'smooth',block:'center'}});v.currentTime=t;v.play();}}</script>
</body></html>"""
    target = run_dir / f"UAT_TLC_HRM_{run_id}_offline.html"
    target.write_text(page, encoding="utf-8")
    return target


if __name__ == "__main__":
    path = build(Path(sys.argv[1]))
    print(path, f"{path.stat().st_size / 1e6:.1f} MB")
