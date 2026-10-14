"""Build the dashboard from results/issues.csv and the SQL report.

Writes two copies of the same page:
  docs/index.html     a full HTML file (opens in a browser, works on GitHub Pages)
  dashboard/page.html the page body only, for publishing as a hosted page
Run run_checks.py and grade.py first."""

from __future__ import annotations

import argparse
import json

import pandas as pd

from common import AS_OF, DEFAULT_DATA, ROOT, RULES, load
from report import records_table, run_queries


def build_data(data_dir=DEFAULT_DATA) -> dict:
    t = load(data_dir)
    q = run_queries(data_dir)
    issues = pd.read_csv(ROOT / "results" / "issues.csv", keep_default_na=False)
    issues = issues[issues.severity != "Info"]
    grade = json.loads((ROOT / "results" / "grade_summary.json").read_text())
    extra = pd.read_csv(ROOT / "results" / "extra_flags.csv")

    rec = records_table(t)
    rec["owner_id"] = rec.owner_id.replace("", "Unassigned")
    by_table = rec.groupby(["owner_id", "tbl"]).size().unstack(fill_value=0)
    o = t["opportunities"]
    open_ids = set(o.loc[~o.is_closed, "opportunity_id"])
    open_amt = o[~o.is_closed].groupby("owner_id").amount_num.sum()
    users = t["users"].set_index("user_id")
    owners = []
    for oid, row in by_table.iterrows():
        u = users.loc[oid] if oid in users.index else None
        owners.append({
            "id": oid,
            "name": u["name"] if u is not None else "Unassigned",
            "role": u["role"] if u is not None else "",
            "active": u["is_active"] if u is not None else "",
            "records": int(row.sum()),
            "byTable": {k: int(v) for k, v in row.items() if v},
            "openAmount": float(open_amt.get(oid, 0)),
        })

    p = q["pipeline"].iloc[0]
    return {
        "asOf": AS_OF.strftime("%Y-%m-%d"),
        "tables": [{"name": r.table_name, "records": int(r.records)} for r in q["by_table"].itertuples()],
        "owners": owners,
        "rules": {k: list(v) for k, v in RULES.items()},
        "issues": [[r.record_id, r.issue_type, r.owner_id, float(r.open_amount), int(r.record_id in open_ids)]
                   for r in issues.itertuples()],
        "pipeline": {k: float(p[k]) for k in ["open_deals", "open_amount", "flagged_deals", "flagged_amount"]},
        "grade": {
            "planted": grade["planted"], "found": grade["found"], "extra": grade["extra"],
            "extraNote": ("two different companies on one website"
                          if len(extra) == 1 and extra.issue_type.iloc[0] == "shared_domain"
                          else "see results/extra_flags.csv"),
            "dupRight": grade["dup_right"], "dupTotal": grade["dup_total"],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=DEFAULT_DATA)
    args = ap.parse_args()
    data = build_data(args.data_dir)
    page = (ROOT / "dashboard" / "template.html").read_text()
    page = page.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    (ROOT / "dashboard" / "page.html").write_text(page)
    full = ('<!doctype html>\n<html lang="en" data-theme="dark">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + page.replace("<div class=\"wrap\">", "</head>\n<body>\n<div class=\"wrap\">", 1)
            + "\n</body>\n</html>\n")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(full)
    print(f"Wrote docs/index.html and dashboard/page.html ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
