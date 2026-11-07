"""Classify salary availability while preserving every collected job."""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation

import pandas as pd

from data_ana.salary_estimation import add_salary_estimates, GROUP_LABELS
from data_ana.salary import normalize_salary


def qualify_posts(posts):
    assessed = add_salary_estimates(pd.DataFrame([asdict(post) for post in posts]))
    low = pd.to_numeric(assessed.salary_comparison_min, errors="coerce")
    high = pd.to_numeric(assessed.salary_comparison_max, errors="coerce")
    def non_monthly(post):
        try:
            return normalize_salary(post.salary_text, Decimal("25000"))["salary_period"] in {"hour", "day"}
        except InvalidOperation:
            return True
    unsupported = pd.Series([non_monthly(post) for post in posts], index=assessed.index, dtype=bool)
    invalid = (low.notna() & high.notna() & low.gt(high)) | ~(low.gt(0) | high.gt(0)) | unsupported
    newly_invalid = invalid & assessed.salary_group.ne("C")
    assessed.loc[newly_invalid, "salary_estimate_reason"] = "Khoảng lương không hợp lệ hoặc chưa quy đổi được sang VND/tháng."
    assessed.loc[invalid, "salary_group"] = "C"
    assessed.loc[invalid, "salary_group_label"] = GROUP_LABELS["C"]
    assessed.loc[invalid, ["salary_display", "salary_vnd"]] = "NaN · Chưa đủ dữ liệu"
    assessed.loc[invalid, ["salary_comparison_min", "salary_comparison_max", "salary_comparison_midpoint", "salary_estimate_min", "salary_estimate_max", "salary_estimate_midpoint"]] = float("nan")
    return [post for post, accepted in zip(posts, assessed.salary_group.isin(["A", "B"])) if accepted], assessed


def update_salary_dataset(posts, main_path):
    from data_ana.crawl import merge_posts, write_csv

    archive_path = main_path.with_name(main_path.stem + "_archive" + main_path.suffix)
    archive = merge_posts(merge_posts(posts, main_path), archive_path)
    write_csv(archive, archive_path)
    _, assessed = qualify_posts(archive)
    write_csv(archive, main_path)
    return archive, assessed
