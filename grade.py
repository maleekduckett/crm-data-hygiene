"""Compare results/issues.csv to the planted answer key. This is the only file that reads the key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common import DEFAULT_KEY, ROOT


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key-dir", default=DEFAULT_KEY)
    args = p.parse_args()

    key = pd.read_csv(Path(args.key_dir) / "planted_issues.csv", keep_default_na=False, dtype=str)
    found = pd.read_csv(ROOT / "results" / "issues.csv", keep_default_na=False, dtype=str)
    k = set(zip(key.table, key.record_id, key.issue_type))
    f = set(zip(found.table, found.record_id, found.issue_type))

    rows = []
    for issue in sorted(set(key.issue_type) | set(found.issue_type)):
        kk = {x for x in k if x[2] == issue}
        ff = {x for x in f if x[2] == issue}
        rows.append({"issue_type": issue, "planted": len(kk), "found": len(kk & ff),
                     "missed": len(kk - ff), "extra": len(ff - kk)})
    g = pd.DataFrame(rows)
    print(g.to_string(index=False))
    print(f"\nPlanted problems found: {g.found.sum()} of {g.planted.sum()}. "
          f"Missed: {g.missed.sum()}. Extra flags: {g.extra.sum()}.")

    # Duplicates must point at the right record, not just be flagged.
    dup_types = ["duplicate_account", "duplicate_contact", "duplicate_lead"]
    kp = key[key.issue_type.isin(dup_types)].set_index(["issue_type", "record_id"]).related_record_id
    fp = found[found.issue_type.isin(dup_types)].set_index(["issue_type", "record_id"]).related_record_id
    both = kp.index.intersection(fp.index)
    right = int((kp[both] == fp[both]).sum())
    print(f"Duplicates linked to the right original: {right} of {len(kp)}")

    extra = sorted(f - k)
    pd.DataFrame(extra, columns=["table", "record_id", "issue_type"]).to_csv(
        ROOT / "results" / "extra_flags.csv", index=False)
    g.to_csv(ROOT / "results" / "grade.csv", index=False)
    (ROOT / "results" / "grade_summary.json").write_text(json.dumps({
        "planted": int(g.planted.sum()), "found": int(g.found.sum()), "extra": int(g.extra.sum()),
        "dup_right": right, "dup_total": int(len(kp))}, indent=2))


if __name__ == "__main__":
    main()
