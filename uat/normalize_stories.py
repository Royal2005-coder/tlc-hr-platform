import yaml

ROOT = "/home/ai1/tlc-hr/tlc-hr-platform/uat/stories/"
meta = {
    "lifecycle.yaml": ("Vòng đời nhân viên", "Hợp đồng, người phụ thuộc, thử việc, điều chuyển và nghỉ việc trên Desk chuẩn."),
    "people_ops.yaml": ("Vận hành nhân sự", "Tài sản, tài khoản IT, đào tạo, phúc lợi, kỷ luật, mục tiêu và đánh giá."),
}
for name, (title, summary) in meta.items():
    path = ROOT + name
    data = yaml.safe_load(open(path, encoding="utf-8"))
    data["title"] = data.get("title") or title
    data["summary"] = data.get("summary") or summary
    for story in data.get("stories", []):
        story.setdefault("title", (story.get("then") or story["id"])[:120])
        story.setdefault("story", f"{story.get('role','')}: {story.get('when','')} → {story.get('then','')}")
        story.setdefault("cases", [story["id"]])
        if not story.get("ac"):
            story["ac"] = [{"given": story.get("given", ""), "when": story.get("when", ""),
                            "then": story.get("then", ""), "cases": [story["id"]]}]
        if not story.get("blueprint_uat"):
            story["blueprint_uat"] = story.get("uat", [])
    yaml.safe_dump(data, open(path, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print(name, "normalized", len(data.get("stories", [])))
