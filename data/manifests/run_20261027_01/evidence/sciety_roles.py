import yaml
d = yaml.safe_load(open("config/platforms.yaml", encoding="utf-8"))
rows = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list) and v and "row_id" in v[0])
in_index = {"prereview","prelights","arcadia-science","rapid-reviews-covid-19","peerj","ncrc","asapbio-crowd-review","biophysics-colab","life-science-editors-foundation","asapbio-scielo-preprint-crowd-review","life-science-editors"}
for r in rows:
    sel = r.get("extraction_selector") or {}
    if "sciety" not in sel:
        continue
    s = sel["sciety"]
    slug = s.get("group_slug", "?")
    other = [k for k in sel if k != "sciety"]
    cls = "OK_in_index" if slug in in_index else ("harmless_zero" if s.get("role") == "cross_check" or other else "NOT_MEASURABLE")
    print(f"{r['row_id']:42s} {slug:40s} {s.get('role','?'):12s} other={other!s:14s} {cls}")
