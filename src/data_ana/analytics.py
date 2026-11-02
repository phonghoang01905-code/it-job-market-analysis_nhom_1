"""Shared EDA definitions. One observation is a (source, job ID/link) listing."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from data_ana.etl import extract_normalized_skills, normalized_city
from data_ana.languages import extract_languages

UNKNOWN = "Chưa xác định"


def prepare_jobs(frame: pd.DataFrame) -> pd.DataFrame:
    authoritative = frame.attrs.get("skills_normalized", False) or {"salary_currency", "usd_vnd_rate"}.issubset(frame.columns)
    df = frame.copy()
    fields = ["source", "job_id", "url", "title", "company", "city", "location", "level", "work_model",
              "skills", "requirements", "description", "posted_date", "scraped_at"]
    for field in fields:
        if field not in df:
            df[field] = ""
        df[field] = df[field].fillna("").astype(str)
    identity = df.url.str.replace(r"[?#].*$", "", regex=True)
    identity = identity.where(identity.ne(""), df.job_id)
    identity = identity.where(identity.ne(""), pd.Series([f"row:{i}" for i in range(len(df))], index=df.index))
    df["_key"] = df.source.str.lower().str.strip() + "|" + identity
    df = df.drop_duplicates("_key", keep="last").reset_index(drop=True)
    df["company_key"] = df.company.str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()
    names = df.drop_duplicates("company_key").set_index("company_key").company.to_dict()
    df["company"] = df.company_key.map(names)
    for field in ["level", "work_model"]:
        df[field] = df[field].replace("", "Unknown")
    def skills(row):
        if authoritative:
            # BI and Python use exactly the persisted normalized labels. Do not
            # silently re-infer newer requirements over historical DB skills.
            languages = getattr(row, "programming_languages", "")
            language_labels = languages.split(";") if isinstance(languages, str) else (languages or [])
            return sorted({s.strip() for s in row.skills.split(";") + language_labels if s.strip()})
        body = row.requirements or row.description
        languages, _ = extract_languages(row.title, body, row.skills)
        return sorted(set(extract_normalized_skills(row.title, body, row.skills)) | set(languages))
    df["_skills"] = df["_analysis_skills"] if "_analysis_skills" in df else pd.Series([skills(row) for row in df.itertuples()], dtype=object)
    city_values = df["_analysis_city"] if "_analysis_city" in df else df["city"].replace("Nhiều địa điểm", "")
    df["_cities"] = pd.Series([sorted({re.sub(r"\s*\(mới\)$", "", city.strip()) for city in (value or normalized_city(location)).split(";") if city.strip()}) or [UNKNOWN]
                               for value, location in zip(city_values, df.location)], dtype=object)
    for field in ["salary_min", "salary_max"]:
        df[field] = pd.to_numeric(df.get(field, pd.Series(index=df.index, dtype=float)), errors="coerce")
    both = df.salary_min.gt(0) & df.salary_max.gt(0) & df.salary_min.le(df.salary_max)
    # A lower/upper bound alone is not an estimate of the actual salary.
    df["salary_midpoint"] = ((df.salary_min + df.salary_max) / 2).where(both)
    df["_date_posted"] = pd.to_datetime(df.posted_date.where(df.posted_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")), errors="coerce")
    df["_date_observed"] = pd.to_datetime(df.scraped_at, utc=True, errors="coerce").dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None).dt.normalize()
    return df


def explode(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension == "skill":
        return df.explode("_skills").rename(columns={"_skills": "skill"}).dropna(subset=["skill"])
    if dimension == "city":
        return df.drop(columns=["city"]).explode("_cities").rename(columns={"_cities": "city"})
    if dimension == "company":
        return df[df.company_key.ne("")]
    return df


def summary(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    data = explode(df, dimension)
    result = data.groupby(dimension, as_index=False).agg(
        job_count=("_key", "nunique"), salary_count=("salary_midpoint", "count"),
        median_salary=("salary_midpoint", "median"), avg_salary=("salary_midpoint", "mean"),
        p25_salary=("salary_midpoint", lambda s: s.quantile(.25)),
        p75_salary=("salary_midpoint", lambda s: s.quantile(.75)))
    result["share_pct"] = (result.job_count / len(df) * 100).round(2) if len(df) else 0
    return result.sort_values(["job_count", dimension], ascending=[False, True]).reset_index(drop=True)


def dated_jobs(df: pd.DataFrame, basis="posted", frequency="week") -> pd.DataFrame:
    if basis not in {"posted", "observed"} or frequency not in {"week", "month"}:
        raise ValueError("basis: posted/observed; frequency: week/month")
    result = df[df[f"_date_{basis}"].notna()].copy()
    result["period"] = result[f"_date_{basis}"].dt.to_period("W-SUN" if frequency == "week" else "M").dt.start_time
    return result


def periods(data: pd.DataFrame, frequency: str) -> pd.DatetimeIndex:
    if data.empty:
        return pd.DatetimeIndex([])
    return pd.date_range(data.period.min(), data.period.max(), freq="W-MON" if frequency == "week" else "MS")


def time_summary(df: pd.DataFrame, basis="posted", frequency="week") -> pd.DataFrame:
    data = dated_jobs(df, basis, frequency)
    result = data.groupby("period")._key.nunique().reindex(periods(data, frequency), fill_value=0)
    return result.rename_axis("period").rename("job_count").reset_index()


def skill_timeseries(df: pd.DataFrame, basis="posted", frequency="week") -> pd.DataFrame:
    data = dated_jobs(df, basis, frequency)
    skills = sorted({skill for values in data._skills for skill in values})
    index = pd.MultiIndex.from_product([periods(data, frequency), skills], names=["period", "skill"])
    counts = explode(data, "skill").groupby(["period", "skill"])._key.nunique().reindex(index, fill_value=0)
    result = counts.rename("job_count").reset_index()
    totals = data.groupby("period")._key.nunique()
    result["period_jobs"] = result.period.map(totals).fillna(0).astype(int)
    result["share_pct"] = (result.job_count / result.period_jobs.replace(0, np.nan) * 100).fillna(0)
    return result


def skill_changes(df: pd.DataFrame, basis="posted") -> pd.DataFrame:
    series = skill_timeseries(df, basis)
    columns = ["skill", "previous_week", "current_week", "previous_count", "current_count", "count_change", "share_change_pp", "growth_pct"]
    weeks = sorted(series.period.unique())
    if len(weeks) < 2:
        return pd.DataFrame(columns=columns)
    before = series[series.period.eq(weeks[-2])].set_index("skill")
    after = series[series.period.eq(weeks[-1])].set_index("skill")
    result = pd.DataFrame({"skill": after.index, "previous_week": weeks[-2], "current_week": weeks[-1],
        "previous_count": before.job_count.to_numpy(), "current_count": after.job_count.to_numpy(),
        "count_change": (after.job_count-before.job_count).to_numpy(),
        "share_change_pp": (after.share_pct-before.share_pct).round(2).to_numpy(),
        "growth_pct": ((after.job_count-before.job_count) / before.job_count.replace(0, np.nan)*100).round(2).to_numpy()})
    return result[columns].sort_values(["share_change_pp", "skill"], ascending=[False, True]).reset_index(drop=True)


def cluster_jobs(df: pd.DataFrame, k: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfTransformer
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import MultiLabelBinarizer

    assignments = df[["_key", "source", "title", "company", "url"]].copy()
    assignments["cluster"] = pd.Series(pd.NA, index=assignments.index, dtype="Int64")
    summary_columns = ["cluster", "job_count", "top_skills", "median_salary", "salary_count"]
    valid = df[df._skills.map(bool)]
    distinct = len({tuple(s) for s in valid._skills})
    if len(valid) < 3 or distinct < 2:
        return assignments, pd.DataFrame(columns=summary_columns), {"status": "insufficient", "reason": "Cần ít nhất 3 tin có kỹ năng và 2 bộ kỹ năng khác nhau", "excluded": len(df)-len(valid)}
    encoder = MultiLabelBinarizer()
    binary = encoder.fit_transform(valid._skills)
    features = TfidfTransformer().fit_transform(binary).toarray()
    maximum = min(6, distinct, len(valid)-1)
    candidates = [k] if k is not None else list(range(2, maximum+1))
    if any(value < 2 or value > maximum for value in candidates):
        raise ValueError(f"Số cụm phải từ 2 đến {maximum} với dữ liệu này")
    trials = []
    for value in candidates:
        model = KMeans(n_clusters=value, n_init=20, random_state=42).fit(features)
        if len(set(model.labels_)) > 1:
            score = silhouette_score(features, model.labels_, metric="cosine")
            trials.append((score, value, model))
    if not trials:
        return assignments, pd.DataFrame(columns=summary_columns), {"status": "insufficient", "excluded": len(df)-len(valid)}
    score, selected, model = max(trials, key=lambda item: (item[0], -item[1]))
    assignments.loc[valid.index, "cluster"] = model.labels_
    rows = []
    for label in sorted(set(model.labels_)):
        subset = valid.iloc[np.flatnonzero(model.labels_ == label)]
        common = summary(subset, "skill").head(6)
        rows.append({"cluster": int(label), "job_count": len(subset), "top_skills": "; ".join(common.skill),
            "median_salary": subset.salary_midpoint.median() if subset.salary_midpoint.notna().any() else np.nan,
            "salary_count": int(subset.salary_midpoint.count())})
    return assignments, pd.DataFrame(rows, columns=summary_columns), {
        "status": "ok", "k": selected, "silhouette_cosine": round(float(score), 4), "random_state": 42,
        "excluded": len(df)-len(valid), "n_features": len(encoder.classes_),
        "trials": [{"k": value, "silhouette_cosine": round(float(s), 4)} for s, value, _ in trials]}
