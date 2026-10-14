"""Small checks on the matching rules. Run with: python tests/test_rules.py"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_checks import EMAIL_OK, account_pairs, clean_name, domain_root, pairs_by_key, same_company, segment_for  # noqa: E402


def accounts(rows):
    return pd.DataFrame(rows, columns=["account_id", "name", "domain", "created_date"])


def test_domain_root():
    assert domain_root("www.CalmLark.com") == "calmlark"
    assert domain_root("calmlark.io") == "calmlark"


def test_clean_name():
    assert clean_name("Calm Lark, Inc.") == "calm lark"
    assert clean_name("CALM LARK") == "calm lark"


def test_typo_counts_as_same_company():
    assert same_company("Brightstead", "Brihgtstead")
    assert not same_company("Pinehaven", "Pinehaven Home")


def test_segment_bands():
    assert segment_for(199) == "SMB"
    assert segment_for(200) == "Mid-Market"
    assert segment_for(2000) == "Enterprise"


def test_email_format():
    assert EMAIL_OK.match("ana@calmlark.com")
    assert not EMAIL_OK.match("anacalmlark.com")   # no @
    assert not EMAIL_OK.match("ana@calmlark")      # no ending


def test_oldest_record_survives():
    df = pd.DataFrame({"lead_id": ["L-2", "L-1"], "created_date": ["2025-03-01", "2025-01-01"]})
    assert pairs_by_key(df, "lead_id", pd.Series(["a@x.com", "a@x.com"])) == [("L-2", "L-1")]


def test_duplicate_account_needs_matching_name():
    df = accounts([
        ("A-1", "Pinehaven", "pinehaven.com", "2024-01-01"),
        ("A-2", "Pinehaven Home", "pinehaven.net", "2024-02-01"),   # different company
        ("A-3", "PINEHAVEN", "www.pinehaven.com", "2024-03-01"),    # same company, new record
    ])
    dups, conflicts = account_pairs(df)
    assert dups == [("A-3", "A-1")]
    assert conflicts == []


def test_same_website_different_name_is_a_conflict():
    df = accounts([
        ("A-1", "Amber Valley Energy", "ambervalley.io", "2024-01-01"),
        ("A-2", "Amber Valley Cargo", "ambervalley.io", "2024-05-01"),
    ])
    dups, conflicts = account_pairs(df)
    assert dups == []
    assert conflicts == [("A-2", "A-1")]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests passed")
