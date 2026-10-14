"""Load the issues and CRM tables into SQLite, run sql/report.sql, and print the summary."""

from __future__ import annotations

import argparse
import sqlite3

import pandas as pd

from common import DEFAULT_DATA, ROOT, load

ID_COLS = {"accounts": "account_id", "contacts": "contact_id", "leads": "lead_id",
           "opportunities": "opportunity_id"}


def records_table(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per record with its owner. Contacts take their account's owner."""
    acct_owner = t["accounts"].set_index("account_id").owner_id
    parts = []
    for tbl, col in ID_COLS.items():
        df = t[tbl]
        owner = (df.account_id.map(acct_owner).fillna("") if tbl == "contacts" else df.owner_id)
        parts.append(pd.DataFrame({"tbl": tbl, "record_id": df[col], "owner_id": owner.values}))
    return pd.concat(parts, ignore_index=True)


def run_queries(data_dir=DEFAULT_DATA) -> dict[str, pd.DataFrame]:
    t = load(data_dir)
    con = sqlite3.connect(":memory:")
    pd.read_csv(ROOT / "results" / "issues.csv", keep_default_na=False).to_sql("issues", con, index=False)
    records_table(t).to_sql("records", con, index=False)
    t["users"].to_sql("users", con, index=False)
    o = t["opportunities"][["opportunity_id", "is_closed", "amount_num"]].copy()
    o["is_closed"] = o.is_closed.astype(int)
    o.to_sql("opportunities", con, index=False)

    out, name, lines = {}, None, []
    for line in (ROOT / "sql" / "report.sql").read_text().splitlines() + ["-- name: end"]:
        if line.startswith("-- name:"):
            if name:
                out[name] = pd.read_sql_query("\n".join(lines), con)
            name, lines = line.split(":", 1)[1].strip(), []
        else:
            lines.append(line)
    out.pop("end", None)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    args = p.parse_args()
    res = run_queries(args.data_dir)
    text = []
    for name, df in res.items():
        show = df.head(15) if name == "queue" else df
        text.append(f"== {name}\n{show.to_string(index=False)}\n")
    report = "\n".join(text)
    (ROOT / "results" / "report.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
