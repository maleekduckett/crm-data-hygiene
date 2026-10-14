"""Run every hygiene check and write one row per problem to results/issues.csv."""

from __future__ import annotations

import argparse
import re
from difflib import SequenceMatcher

import pandas as pd

from common import (AS_OF, BIG_DEAL, CANONICAL_COUNTRIES, DEFAULT_DATA, LATE_STAGES, ROOT, RULES,
                    SEGMENT_BANDS, SEVERITY_WEIGHT, STALL_DAYS, load)

EMAIL_OK = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SUFFIXES = {"inc", "llc", "ltd", "corp", "co", "company", "corporation"}


def segment_for(employees: float) -> str | None:
    for low, high, seg in SEGMENT_BANDS:
        if low <= employees <= high:
            return seg
    return None


def domain_root(domain: str) -> str:
    """'www.calmlark.com' and 'calmlark.io' both become 'calmlark'."""
    d = domain.lower().strip()
    d = d[4:] if d.startswith("www.") else d
    return d.rsplit(".", 1)[0]


def clean_name(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    while words and words[-1] in SUFFIXES:
        words.pop()
    return " ".join(words)


def same_company(n1: str, n2: str) -> bool:
    """Names match once case, punctuation and 'Inc.' are ignored, or differ by a typo."""
    a, b = clean_name(n1), clean_name(n2)
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.9


def account_pairs(a: pd.DataFrame) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Duplicates: same website name (ignoring 'www.' and .com vs .io) AND a near-identical
    company name. Sharing only a website name isn't enough: Pinehaven and Pinehaven Home are
    different companies. Two different names on the exact same website are returned
    separately as conflicts, because someone has to decide which record is right."""
    d = a.assign(root_key=a.domain.map(domain_root),
                 dom_key=a.domain.str.lower().str.replace(r"^www\.", "", regex=True))
    d = d.sort_values(["created_date", "account_id"])
    dups, conflicts = [], []
    for _, grp in d.groupby("root_key"):
        recs = list(grp.itertuples())
        for i, r in enumerate(recs):
            match = next((e for e in recs[:i] if same_company(r.name, e.name)), None)
            if match is not None:
                dups.append((r.account_id, match.account_id))
                continue
            clash = next((e for e in recs[:i] if e.dom_key == r.dom_key), None)
            if clash is not None:
                conflicts.append((r.account_id, clash.account_id))
    return dups, conflicts


def pairs_by_key(df: pd.DataFrame, id_col: str, key: pd.Series) -> list[tuple[str, str]]:
    """Group records that share a key. The oldest record survives; each newer one is a duplicate.
    Returns (duplicate_id, survivor_id) pairs."""
    d = df.assign(_key=key).query("_key != ''").sort_values(["created_date", id_col])
    out = []
    for _, grp in d.groupby("_key"):
        if len(grp) > 1:
            keep = grp[id_col].iloc[0]
            out += [(dup, keep) for dup in grp[id_col].iloc[1:]]
    return out


def run(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict] = []

    def flag(issue: str, ids, detail: str = "", related=None):
        ids = list(ids)
        related = related if related is not None else [""] * len(ids)
        for rid, rel in zip(ids, related):
            rows.append({"issue_type": issue, "record_id": rid, "detail": detail, "related_record_id": rel})

    # ---- Accounts
    a = t["accounts"]
    flag("missing_industry", a.loc[a.industry == "", "account_id"])
    flag("missing_employee_count", a.loc[a.employee_count == "", "account_id"])
    emp = pd.to_numeric(a.employee_count, errors="coerce")
    expected = emp.map(lambda e: segment_for(e) if pd.notna(e) else None)
    bad_seg = expected.notna() & (expected != a.segment)
    for _, r in a[bad_seg].iterrows():
        flag("segment_mismatch", [r.account_id],
             f"{int(float(r.employee_count)):,} employees should be {segment_for(float(r.employee_count))}, not {r.segment}")
    bad_country = ~a.country.isin(CANONICAL_COUNTRIES)
    for _, r in a[bad_country].iterrows():
        flag("inconsistent_country_value", [r.account_id], f"'{r.country}'")
    gone = set(t["users"].loc[t["users"].is_active == "False", "user_id"])
    flag("owner_inactive", a.loc[a.owner_id.isin(gone), "account_id"])
    dups, conflicts = account_pairs(a)
    for rid, other in conflicts:
        flag("shared_domain", [rid], f"same website as {other}, different company name", [other])
    for dup, keep in dups:
        n1 = a.loc[a.account_id == dup, "name"].iloc[0]
        n2 = a.loc[a.account_id == keep, "name"].iloc[0]
        flag("duplicate_account", [dup], f"'{n1}' looks like '{n2}'", [keep])
        flag("duplicate_account_master", [keep], f"duplicated as {dup}", [dup])

    # ---- Contacts
    c = t["contacts"]
    flag("orphan_contact_no_account", c.loc[c.account_id == "", "contact_id"])
    flag("missing_email", c.loc[c.email == "", "contact_id"])
    bad_email = (c.email != "") & ~c.email.str.match(EMAIL_OK)
    for _, r in c[bad_email].iterrows():
        flag("invalid_email_format", [r.contact_id], f"'{r.email}'")
    flag("missing_title", c.loc[c.title == "", "contact_id"])
    for dup, keep in pairs_by_key(c, "contact_id", c.email.str.lower().where(~bad_email, "")):
        flag("duplicate_contact", [dup], "same email", [keep])

    # ---- Leads
    l = t["leads"]
    flag("unassigned_lead", l.loc[l.owner_id == "", "lead_id"])
    flag("missing_company", l.loc[l.company == "", "lead_id"])
    flag("converted_without_account",
         l.loc[(l.status == "Converted") & (l.converted_account_id == ""), "lead_id"])
    for dup, keep in pairs_by_key(l, "lead_id", l.email.str.lower()):
        flag("duplicate_lead", [dup], "same email", [keep])

    # ---- Opportunities
    o = t["opportunities"]
    op = o[~o.is_closed]
    flag("missing_amount", op.loc[op.amount_num.isna(), "opportunity_id"])
    flag("zero_amount", op.loc[op.amount_num == 0, "opportunity_id"])
    for _, r in o[o.close_date_ts < o.created_date_ts].iterrows():
        flag("close_date_before_created", [r.opportunity_id], f"created {r.created_date}, closes {r.close_date}")
    stale = op[(op.close_date_ts < AS_OF) & (op.close_date_ts >= op.created_date_ts)]
    for _, r in stale.iterrows():
        flag("stale_open_opportunity", [r.opportunity_id], f"close date {r.close_date} has passed")
    flag("missing_next_step", op.loc[op.next_step == "", "opportunity_id"])
    roles = t["opportunity_contact_roles"]
    has_roles = set(roles.opportunity_id)
    flag("no_contact_roles", op.loc[~op.opportunity_id.isin(has_roles), "opportunity_id"])
    has_eb = set(roles.loc[roles.role == "Economic Buyer", "opportunity_id"])
    big = op[(op.amount_num > BIG_DEAL) & op.opportunity_id.isin(has_roles) & ~op.opportunity_id.isin(has_eb)]
    flag("no_economic_buyer", big.opportunity_id)
    acts = t["activities"]
    last_touch = acts[acts.opportunity_id != ""].groupby("opportunity_id").activity_ts.max()
    late = op[op.stage.isin(LATE_STAGES)]
    cutoff = AS_OF - pd.Timedelta(days=STALL_DAYS)
    for _, r in late.iterrows():
        last = last_touch.get(r.opportunity_id)
        if last is not None and last <= cutoff:
            flag("stalled_no_recent_activity", [r.opportunity_id], f"last activity {last.date()}")

    issues = pd.DataFrame(rows)
    return enrich(issues, t)


def enrich(issues: pd.DataFrame, t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Add table, severity, owner and dollars so the report and dashboard can slice the list."""
    issues["table"] = issues.issue_type.map(lambda x: RULES[x][0])
    issues["severity"] = issues.issue_type.map(lambda x: RULES[x][1])
    issues["fix_by"] = issues.issue_type.map(lambda x: RULES[x][2])
    issues["rule"] = issues.issue_type.map(lambda x: RULES[x][3])

    a = t["accounts"].set_index("account_id")
    owner = {}
    owner.update(a.owner_id.to_dict())
    owner.update(t["leads"].set_index("lead_id").owner_id.to_dict())
    owner.update(t["opportunities"].set_index("opportunity_id").owner_id.to_dict())
    c = t["contacts"]
    owner.update(dict(zip(c.contact_id, c.account_id.map(a.owner_id).fillna(""))))
    issues["owner_id"] = issues.record_id.map(owner).fillna("")

    o = t["opportunities"].set_index("opportunity_id")
    open_amt = o.loc[~o.is_closed, "amount_num"]
    issues["open_amount"] = issues.record_id.map(open_amt).fillna(0)
    issues["weight"] = issues.severity.map(SEVERITY_WEIGHT)
    cols = ["table", "record_id", "issue_type", "severity", "fix_by", "owner_id", "open_amount",
            "detail", "related_record_id", "rule", "weight"]
    return issues[cols].sort_values(["table", "issue_type", "record_id"]).reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    args = p.parse_args()
    issues = run(load(args.data_dir))
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    issues.to_csv(out / "issues.csv", index=False)
    real = issues[issues.severity != "Info"]
    print(f"{len(real):,} problems on {real.record_id.nunique():,} records")
    print(real.groupby(["table", "severity"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
