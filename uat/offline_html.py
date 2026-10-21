"""Build or validate one self-contained, navigable offline UAT evidence artifact.

python3 offline_html.py out/RUN
python3 offline_html.py --validate out/RUN/UAT_TLC_HRM_RUN_offline.html
Private catalogue text is embedded only in the generated internal artifact, never source.
"""

import argparse
import base64
import html
import json
import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path

from coverage import PASSED, compute, load_roles, load_stories, local_media, video_media

e = lambda value: html.escape(str(value), quote=True)


def data_uri(path):
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def seconds(stamp):
    parts = str(stamp).split(":")
    if len(parts) not in (2, 3) or any(not p.isdigit() for p in parts):
        return None
    result = 0
    for part in parts:
        result = result * 60 + int(part)
    return result


def badge(status):
    return f"<span class='badge {'ok' if status in ('Đạt', PASSED) else 'bad'}'>{e(status)}</span>"


def build(run_dir):
    run_dir = Path(run_dir)
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    results, videos, run_id = data["results"], data.get("videos", []), str(data["run"])
    modules, roles = load_stories(), load_roles()
    cov = compute(results, modules, evidence_root=run_dir, videos=videos)
    case_of = {}
    for row in results:
        case_of.setdefault(row["id"], []).append(row)
    story_of = {s["id"]: s for m in modules for s in m.get("stories", [])}
    media = {}
    video_html = []
    for index, video in enumerate(videos):
        vid = f"video-{index}"
        path = video_media(run_dir, video.get("file"))
        media.setdefault(video.get("file"), vid if path else None)
        player = (f"<video id='{vid}' controls preload='metadata' src='{data_uri(path)}'></video>" if path else "<p class='missing'>Thiếu tệp video đã khai báo.</p>")
        video_html.append(f"<section id='session-{index}'><h3>{e(video.get('code', ''))} · {e(video.get('role', ''))}</h3>"
                          f"<p>{e(video.get('account', ''))} · {e(video.get('device', ''))}</p>{player}</section>")
    def case_link(cid):
        rows = case_of.get(cid, [])
        status = rows[0].get("status", "Chưa chạy") if len(rows) == 1 else "Kết quả trùng" if rows else "Chưa chạy"
        return f"<a href='#case-{e(cid)}'>{e(cid)}</a> {badge(status)}"
    def seek_button(row):
        vid = media.get(row.get("video"))
        stamp = seconds(row.get("time", ""))
        return (f"<button data-video='{vid}' data-seek='{stamp}'>▶ {e(row['time'])}</button>" if vid and stamp is not None else "<span class='missing'>Thiếu video/mốc tua</span>")
    case_html = []
    all_case_ids = sorted(set(case_of) | set(cov["missing_cases"]))
    for cid in all_case_ids:
        rows = case_of.get(cid, [])
        details = []
        for row in rows:
            shot = local_media(run_dir, row.get("shot"))
            image = f"<details><summary>Ảnh màn hình</summary><img loading='lazy' alt='{e(cid)}' src='{data_uri(shot)}'></details>" if shot else "<p class='missing'>Thiếu tệp ảnh màn hình.</p>"
            issues = cov["case_issues"].get(cid, [])
            fields = (("Tài khoản", "account"), ("Thao tác", "steps"), ("Dữ liệu demo", "data"), ("Mong đợi", "expected"), ("Thực tế", "actual"), ("Thời điểm", "run_at"))
            links = " · ".join(f"<a href='#story-{e(sid)}'>{e(sid)}</a>" for sid, s in story_of.items() if cid in (s.get("cases") or []))
            details.append(f"<h4>{e(row.get('function', ''))} {badge(row.get('status', 'Chưa chạy'))} {seek_button(row)}</h4><p>{links}</p>"
                           + "<dl>" + "".join(f"<dt>{label}</dt><dd>{e(row.get(key, ''))}</dd>" for label, key in fields) + "</dl>"
                           + (f"<p class='missing'>{e('; '.join(issues))}</p>" if issues else "") + image)
        case_html.append(f"<article id='case-{e(cid)}'><h3>{e(cid)}</h3>" + ("".join(details) if rows else "<p class='missing'>Chưa chạy: không có kết quả, ảnh hoặc video.</p>") + "</article>")
    modules_html = []
    module_nav = []
    for module in modules:
        mid = module["module"]
        module_nav.append(f"<a href='#mod-{e(mid)}'>{e(module.get('title') or module.get('module') or mid)}</a>")
        stories_html = []
        for story in module.get("stories", []):
            ac_rows = []
            for index, ac in enumerate(story.get("ac", []), 1):
                cases = ac.get("cases") or []
                ac_rows.append(f"<tr id='ac-{e(story['id'])}-{index}'><td>{index}</td><td>{e(ac.get('given', ''))}</td><td>{e(ac.get('when', ''))}</td><td>{e(ac.get('then', ''))}</td><td>"
                               + ("<br>".join(case_link(c) for c in cases) if cases else "<span class='missing'>Chưa ánh xạ AC → case</span>") + "</td></tr>")
            refs = " · ".join(f"<a href='#ref-{e(ref)}'>{e(ref)}</a>" if any(r["id"] == ref for r in cov["brd"] + cov["uat"]) else f"<span class='missing'>{e(ref)} (không có catalogue)</span>" for ref in (story.get("brd") or []) + (story.get("blueprint_uat") or []))
            story_cases = " · ".join(case_link(cid) for cid in story.get("cases", []))
            stories_html.append(f"<article id='story-{e(story['id'])}'><h4>{e(story['id'])} · {e(story.get('title') or story['id'])} {badge(cov['stories'][story['id']])}</h4>"
                                f"<p>{e(story.get('story', ''))}</p><p>Vai trò: {e(story.get('role', ''))} · {refs}</p>"
                                f"<table><tr><th>AC</th><th>Given</th><th>When</th><th>Then</th><th>Cases</th></tr>{''.join(ac_rows)}</table><p>{story_cases}</p></article>")
        mapped = {s["id"] for s in module.get("stories", [])}
        executed = {cid for sid in mapped for cid in story_of[sid].get("cases", []) if cid in case_of}
        modules_html.append(f"<section id='mod-{e(mid)}'><h3>{e(module.get('title') or module.get('module') or mid)} · {e(module.get('wave', ''))}</h3><p>{e(module.get('summary', ''))}</p>"
                            f"<p>{len(executed)} case có kết quả; {sum(cov['stories'][sid] == PASSED for sid in mapped)}/{len(mapped)} story đủ bằng chứng.</p>{''.join(stories_html)}</section>")
    role_html = []
    for role in roles:
        sids = list(dict.fromkeys((role.get("journeys") or []) + [sid for sid, s in story_of.items() if role["key"] in (s.get("roles") or [s.get("role")])]))
        journey = "".join(f"<li><a href='#story-{e(sid)}'>{e(sid)} · {e(story_of[sid].get('title') or sid)}</a> {badge(cov['stories'][sid])}</li>" if sid in story_of else f"<li class='missing'>{e(sid)}: chưa khai báo story</li>" for sid in sids)
        accounts = {str(account).split()[0].split("@")[0] for account in role.get("accounts", [])}
        sessions = " · ".join(f"<a href='#session-{index}'>{e(v.get('code', ''))} · {e(v.get('account', ''))}</a>" for index, v in enumerate(videos) if str(v.get("account", "")).split("@")[0] in accounts)
        role_html.append(f"<section id='role-{e(role['key'])}'><h3>{e(role['title'])}</h3><p>{e(role.get('interface', ''))}</p><p>{e(', '.join(role.get('accounts', [])))}</p>"
                         + "".join(f"<h4>{label}</h4><ul>" + "".join(f"<li>{e(item)}</li>" for item in role.get(key, [])) + "</ul>" for key, label in (("goals", "Mục tiêu"), ("pain_points", "Vấn đề"), ("improvements", "Hỗ trợ của hệ thống")))
                         + f"<ol>{journey}</ol><p>{sessions or '<span class=missing>Chưa có phiên video cho vai trò.</span>'}</p></section>")
    coverage_html = []
    for key, label in (("brd", "Yêu cầu BRD"), ("uat", "Kịch bản blueprint")):
        rows = []
        for row in cov[key]:
            links = "<br>".join(f"<a href='#story-{e(link['story'])}'>{e(link['story'])}</a>: {e(link['assertion'] or 'Chưa xác nhận toàn bộ hành vi')} "
                                  + " · ".join(case_link(cid) for cid in link["cases"]) for link in row["evidence"])
            text = row.get("text") or (row.get("scenario", "") + " — " + row.get("assertion", ""))
            rows.append(f"<tr id='ref-{e(row['id'])}'><td>{e(row['id'])}<br>{e(row['domain'])}</td><td>{e(text)}<p>{e(row['note'])}</p></td><td>{badge(row['status'])}</td><td>{links or '<span class=missing>Chưa có story/case.</span>'}</td></tr>")
        coverage_html.append(f"<section><h3>{label}: {sum(r['status'] == PASSED for r in cov[key])}/{len(cov[key])} đủ bằng chứng</h3><table><tr><th>Mã</th><th>Hành vi đầy đủ</th><th>Kết quả</th><th>Story → cases → video</th></tr>{''.join(rows)}</table></section>")
    domain_rows = "".join(f"<tr><td>{e(d['label'])} ({e(d['domain'])})</td><td>{d['total']}</td><td>{d['passed']}</td><td>{d['partial']}</td><td>{d['total']-d['passed']-d['partial']}</td></tr>" for d in cov["domains"])
    errors = cov["errors"] + ["Chưa chạy case: " + cid for cid in cov["missing_cases"]] + [cid + ": " + "; ".join(issues) for cid, issues in cov["case_issues"].items() if issues]
    problems = "<ul>" + "".join(f"<li>{e(error)}</li>" for error in errors) + "</ul>" if errors else "<p>Không phát hiện thiếu bằng chứng theo cấu trúc khai báo; không thay thế nghiệm thu nghiệp vụ.</p>"
    attachments = []
    for pattern in ("*.xlsx", "*.pdf"):
        for path in sorted(run_dir.glob(pattern)):
            if local_media(run_dir, path.name):
                attachments.append(f"<a download='{e(path.name)}' href='{data_uri(path)}'>{e(path.name)}</a>")
    manifest = {"run": run_id, "catalog_complete": cov["catalog_complete"], "results": len(results), "videos_declared": len(videos),
                "videos_embedded": sum(bool(video_media(run_dir, v.get("file"))) for v in videos), "missing_cases": cov["missing_cases"],
                "evidence_issues": {k: v for k, v in cov["case_issues"].items() if v}, "traceability_errors": cov["errors"]}
    manifest_json = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UAT TLC HRM {e(run_id)}</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;color:#222;background:#f8f8f8;margin:0}}nav{{position:sticky;top:0;background:white;padding:12px;border-bottom:1px solid #ddd;z-index:2}}nav a{{margin-right:18px}}main{{max-width:1200px;margin:auto;padding:20px}}section,article{{background:white;border:1px solid #ddd;border-radius:6px;padding:16px;margin:12px 0}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid #ddd}}a{{color:#1765a0}}.badge{{display:inline-block;padding:1px 7px;border-radius:10px;background:#fff0ec}}.ok{{background:#e5f5e9}}.missing,.bad{{color:#a73321}}video,img{{max-width:100%}}video{{width:100%;background:#000}}dl{{display:grid;grid-template-columns:130px 1fr;gap:5px}}dd{{margin:0;white-space:pre-wrap}}:target{{scroll-margin-top:65px;outline:2px solid #1765a0}}button{{cursor:pointer}}@media(max-width:700px){{table{{display:block;overflow:auto}}main{{padding:8px}}}}</style></head><body>
<nav><a href='#overview'>Tổng quan</a><a href='#roles'>Vai trò</a><a href='#modules'>Phân hệ</a><a href='#evidence'>Bằng chứng</a><a href='#coverage'>Traceability</a><a href='#gaps'>Thiếu bằng chứng</a></nav><main>
<h1 id='overview'>TLC HRM — UAT desktop theo vai trò</h1><p>Lần chạy {e(run_id)}. Báo cáo nội bộ: chứa dữ liệu demo và nội dung catalogue; không đưa lên kho công khai.</p>
<p>{sum(r.get('status') == 'Đạt' for r in results)}/{len(results)} kết quả được ghi Đạt; {sum(s == PASSED for s in cov['stories'].values())}/{len(story_of)} story đủ AC và bằng chứng. {len(modules)} module được khai báo — không phải số module đã đạt.</p>
<p>Catalogue: {len(cov['brd'])}/322 yêu cầu; {len(cov['uat'])}/42 blueprint cases. Liên kết story không tự chứng minh toàn bộ yêu cầu; mọi nghĩa vụ đã ánh xạ phải đạt. Ngoài Frappe vẫn cần bằng chứng, không miễn nghiệm thu.</p><p>{' · '.join(attachments)}</p>
<section><h3>Phân hệ và bằng chứng</h3><p>{' · '.join(module_nav)}</p><table><tr><th>Phân hệ</th><th>BRD</th><th>Đủ bằng chứng</th><th>Có story, chưa đủ</th><th>Chưa có story</th></tr>{domain_rows}</table></section>
<h2 id='gaps'>Thiếu bằng chứng / lỗi ánh xạ</h2><section>{problems}</section><h2 id='roles'>Vai trò và hành trình</h2>{''.join(role_html)}
<h2 id='modules'>Phân hệ, story và AC</h2>{''.join(modules_html)}<h2 id='evidence'>Phiên video và từng case</h2>{''.join(video_html)}{''.join(case_html)}
<h2 id='coverage'>322 yêu cầu / 42 blueprint cases</h2>{''.join(coverage_html)}</main><script id='evidence-manifest' type='application/json'>{manifest_json}</script>
<script>document.querySelectorAll('button[data-video]').forEach(b=>b.addEventListener('click',()=>{{const v=document.getElementById(b.dataset.video);if(!v)return;v.scrollIntoView({{behavior:'smooth',block:'center'}});const go=()=>{{v.currentTime=Number(b.dataset.seek);v.play().catch(()=>{{}})}};if(v.readyState)go();else{{v.addEventListener('loadedmetadata',go,{{once:true}});v.load()}}}}));</script></body></html>"""
    # Run IDs are metadata, not paths.
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    target = run_dir / f"UAT_TLC_HRM_{safe_id}_offline.html"
    target.write_text(page, encoding="utf-8")
    return target


class ArtifactParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.seeks, self.errors = set(), [], [], []
        self.manifest, self.in_manifest = "", False
        self.videos = 0

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            if attrs["id"] in self.ids:
                self.errors.append("Duplicate anchor: " + attrs["id"])
            self.ids.add(attrs["id"])
        self.in_manifest = tag == "script" and attrs.get("id") == "evidence-manifest"
        if attrs.get("data-video"):
            self.seeks.append(attrs["data-video"])
        for key in ("src", "href", "poster"):
            value = attrs.get(key, "")
            if not value:
                continue
            if value.startswith("#"):
                self.refs.append(value[1:])
            elif value.startswith("data:"):
                try:
                    header, encoded = value.split(",", 1)
                    raw = base64.b64decode(encoded, validate=True)
                    if not raw:
                        raise ValueError("empty media")
                    if tag == "video":
                        if not (("video/mp4" in header and raw[4:8] == b"ftyp") or ("video/webm" in header and raw[:4] == b"\x1aE\xdf\xa3")):
                            raise ValueError("invalid MP4/WebM signature")
                        self.videos += 1
                    if tag == "img" and not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff") or raw.startswith((b"GIF87a", b"GIF89a", b"RIFF"))):
                        raise ValueError("invalid image signature")
                except (ValueError, base64.binascii.Error) as exc:
                    self.errors.append("Invalid embedded media: " + str(exc))
            else:
                self.errors.append("Non-self-contained resource: " + value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_manifest = False

    def handle_data(self, text):
        if self.in_manifest:
            self.manifest += text


def validate(path):
    parser = ArtifactParser()
    parser.feed(Path(path).read_text(encoding="utf-8"))
    parser.errors.extend("Missing target: " + ref for ref in parser.refs + parser.seeks if ref not in parser.ids)
    try:
        manifest = json.loads(parser.manifest)
        if manifest["videos_embedded"] != parser.videos or manifest["videos_declared"] != parser.videos:
            parser.errors.append("Declared/embedded video counts differ")
        if not manifest["catalog_complete"]:
            parser.errors.append("Catalogue does not contain exactly 322 BRD and 42 blueprint cases")
        if manifest["missing_cases"] or manifest["evidence_issues"] or manifest["traceability_errors"]:
            parser.errors.append("Report visibly contains missing/invalid evidence or traceability gaps; inspect gaps section")
    except (ValueError, KeyError):
        parser.errors.append("Missing/invalid evidence manifest")
    return sorted(set(parser.errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        errors = validate(args.path)
        print(json.dumps({"artifact": str(args.path), "valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return int(bool(errors))
    target = build(args.path)
    print(target, f"{target.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
