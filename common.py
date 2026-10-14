"""Shared settings and the rule book. Every check is described here once."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT.parent / "gtm-synthetic-data" / "data"
DEFAULT_KEY = ROOT.parent / "gtm-synthetic-data" / "answer_key"

# The dataset is a snapshot. "Today" is the day it was generated.
AS_OF = pd.Timestamp("2026-10-13")

STALL_DAYS = 35                         # no activity for this long on a late-stage deal = stalled
LATE_STAGES = {"Negotiation", "Contract Review"}
BIG_DEAL = 100_000                      # open deals above this need an Economic Buyer
CANONICAL_COUNTRIES = {"United States", "United Kingdom", "Canada", "Germany"}
SEGMENT_BANDS = [(0, 199, "SMB"), (200, 1999, "Mid-Market"), (2000, 10**9, "Enterprise")]

# Each check: object, severity, who usually fixes it, and what it means.
# "Info" rows are the surviving side of a duplicate pair. They are listed so the pair can be
# found from either record, but they are not counted as problems.
RULES = {
    "missing_amount":             ("opportunities", "High",   "Rep",    "Open deal has no amount"),
    "zero_amount":                ("opportunities", "High",   "Rep",    "Open deal has an amount of 0"),
    "close_date_before_created":  ("opportunities", "High",   "Rep",    "Close date is earlier than the created date"),
    "stale_open_opportunity":     ("opportunities", "High",   "Rep",    "Open deal with a close date in the past"),
    "no_contact_roles":           ("opportunities", "High",   "Rep",    "Open deal has nobody on it"),
    "no_economic_buyer":          ("opportunities", "High",   "Rep",    "Open deal over $100K with no Economic Buyer"),
    "stalled_no_recent_activity": ("opportunities", "High",   "Rep",    "Late-stage deal with no activity in 35 days"),
    "missing_next_step":          ("opportunities", "Medium", "Rep",    "Open deal has no next step"),
    "duplicate_account":          ("accounts",      "High",   "RevOps", "Same company entered twice (the newer record)"),
    "duplicate_account_master":   ("accounts",      "Info",   "RevOps", "The older record the duplicate should merge into"),
    "shared_domain":              ("accounts",      "Medium", "RevOps", "Two different company names use the same website"),
    "owner_inactive":             ("accounts",      "Medium", "RevOps", "Account is owned by a rep who has left"),
    "segment_mismatch":           ("accounts",      "Medium", "RevOps", "Segment doesn't match employee count"),
    "inconsistent_country_value": ("accounts",      "Low",    "RevOps", "Country isn't written the standard way"),
    "missing_industry":           ("accounts",      "Low",    "Rep",    "Industry is blank"),
    "missing_employee_count":     ("accounts",      "Low",    "Rep",    "Employee count is blank"),
    "unassigned_lead":            ("leads",         "High",   "RevOps", "Lead has no owner"),
    "converted_without_account":  ("leads",         "High",   "RevOps", "Lead is Converted but links to no account or contact"),
    "duplicate_lead":             ("leads",         "Medium", "RevOps", "Same email submitted again (the newer record)"),
    "missing_company":            ("leads",         "Medium", "RevOps", "Company is blank"),
    "duplicate_contact":          ("contacts",      "Medium", "RevOps", "Same person entered twice (the newer record)"),
    "orphan_contact_no_account":  ("contacts",      "Medium", "RevOps", "Contact isn't linked to an account"),
    "invalid_email_format":       ("contacts",      "Medium", "Rep",    "Email isn't a valid address"),
    "missing_email":              ("contacts",      "Medium", "Rep",    "Email is blank"),
    "missing_title":              ("contacts",      "Low",    "Rep",    "Job title is blank"),
}
SEVERITY_WEIGHT = {"High": 3, "Medium": 2, "Low": 1, "Info": 0}


def load(data_dir: Path | str = DEFAULT_DATA) -> dict[str, pd.DataFrame]:
    """Read every table the checks need. Blanks stay as empty text so 'missing' is easy to test."""
    d = Path(data_dir)
    t = {n: pd.read_csv(d / f"{n}.csv", keep_default_na=False, dtype=str)
         for n in ["accounts", "contacts", "leads", "opportunities", "opportunity_contact_roles",
                   "activities", "users"]}
    o = t["opportunities"]
    o["is_closed"] = o["is_closed"] == "True"
    o["amount_num"] = pd.to_numeric(o["amount"], errors="coerce")
    for col in ["created_date", "close_date"]:
        o[col + "_ts"] = pd.to_datetime(o[col], errors="coerce")
    t["activities"]["activity_ts"] = pd.to_datetime(t["activities"]["activity_date"], errors="coerce")
    return t
