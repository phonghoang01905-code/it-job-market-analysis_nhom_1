"""Explainable salary estimates; observed salaries are never overwritten."""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from data_ana.cv_matching import minimum_experience
from data_ana.etl import extract_normalized_skills, normalized_city
from data_ana.salary import monthly_salary_label, salary_label, normalize_salary
from data_ana.utils import unaccent, infer_level

GROUP_LABELS = {"A": "A · Công khai", "B": "B · Ước tính", "C": "C · Thiếu dữ liệu"}
MIN_PEERS = 3
MAX_PEERS = 7
MAX_AGE_DAYS = 180

ROLE_PATTERNS = [
    ("Kiến trúc sư phần mềm", r"architect|kien truc"),
    ("Quản lý kỹ thuật", r"engineering manager|development manager|technical manager|head of|cto\b"),
    ("Phân tích nghiệp vụ", r"business analyst|phan tich nghiep vu|\bba\b"),
    ("Quản lý sản phẩm", r"product owner|product manager|quan ly san pham"),
    ("Quản lý dự án", r"project manager|quan ly du an|\bpm\b|scrum master"),
    ("Cầu nối / BrSE", r"\bbrse\b|bridge.*engineer|comtor|it.*interpreter"),
    ("Kiểm thử phần mềm", r"tester|testing|\bqa\b|\bqc\b|kiem thu|chat luong phan mem"),
    ("Quản trị cơ sở dữ liệu", r"\bdba\b|database admin|quan tri co so du lieu"),
    ("Kỹ sư dữ liệu", r"data engineer|ky su du lieu|data platform"),
    ("Phân tích dữ liệu", r"data analyst|data analytics|phan tich du lieu"),
    ("AI / Machine Learning", r"\bai\b|machine learning|\bml\b|tri tue nhan tao"),
    ("An toàn thông tin", r"security|an ninh|an toan thong tin|bao mat"),
    ("DevOps / Cloud", r"devops|devsecops|\bsre\b|cloud|finops"),
    ("Thiết kế UI/UX", r"ui.?ux|ux.?ui|ui designer|ux designer"),
    ("Hỗ trợ IT", r"helpdesk|help desk|it support|it generalist|ky thuat it|it technician"),
    ("Hạ tầng / Mạng", r"network|infrastructure|system admin|quan tri mang|ha tang|van hanh.*cntt"),
    ("Phát triển di động", r"android|\bios\b|mobile.*(?:developer|engineer)|flutter"),
    ("Phát triển Fullstack", r"full.?stack|phat trien web"),
    ("Phát triển Backend", r"back.?end"),
    ("Phát triển Frontend", r"front.?end"),
    ("Phát triển phần mềm", r"developer|software engineer|lap trinh|phat trien phan mem"),
]


def role_family(title: str) -> str:
    value = unaccent(title)
    # These categories can occur on IT landing pages but are not software roles.
    if re.search(r"\bcnc\b|marketing|kinh doanh|gan nhan|video editor|sales", value):
        return ""
    for name, pattern in ROLE_PATTERNS:
        if re.search(pattern, value):
            return name
    return ""


def experience(row: dict) -> tuple[str, float | None]:
    years, _ = minimum_experience(row)
    if years is None:
        # A title can explicitly state experience even if the detail was lost.
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:nam\s*(?:kn|kinh nghiem)|years?\s*(?:of\s*)?experience)", unaccent(str(row.get("title", ""))))
        years = float(match.group(1).replace(",", ".")) if match else None
    level = str(row.get("level") or "Unknown")
    if level == "Unknown":
        level = infer_level(str(row.get("title") or ""))
    if level in {"Intern", "Fresher"}:
        return "Entry", years
    if level in {"Junior", "Middle", "Senior"}:
        return level, years
    if years is not None:
        return ("Entry" if years == 0 else "Junior" if years < 2 else "Middle" if years < 5 else "Senior"), years
    return "", None


def city_key(row: dict) -> str:
    value = normalized_city(str(row.get("location") or row.get("city") or ""))
    value = unaccent(value)
    if not value or ";" in value or value in {"nhieu dia diem", "chua xac dinh", "unknown", "remote"}:
        return ""
    return re.sub(r"\s*\(moi\)", "", value).strip()


def features(row: dict) -> dict:
    title = str(row.get("title") or "")
    body = str(row.get("requirements") or row.get("description") or "")
    band, years = experience(row)
    skills = set(extract_normalized_skills(title, body, row.get("skills", "")))
    key = lambda text: re.sub(r"\W+", "", unaccent(str(text)))
    return dict(role=role_family(title), band=band, years=years, city=city_key(row),
                skills=skills, words=set(re.findall(r"[a-z]{3,}", unaccent(title))),
                company=key(row.get("company", "")), title_key=key(title))


def observed_salary(row: dict) -> tuple[float, float, str, str]:
    low, high = row["salary_min"], row["salary_max"]
    text = str(row.get("salary_text") or "")
    if pd.notna(low) or pd.notna(high):
        return low, high, salary_label(text, low, high), "Mức lương đã thu thập từ tin gốc"
    candidates = [(text, "Trường lương của tin gốc")]
    title = unaccent(str(row.get("title") or ""))
    # Extract only a salary phrase, so experience years/bonuses cannot become pay.
    if "bonus" not in title:
        amount = r"\$?\s*\d+(?:[.,]\d+)*(?:\s*[-–]\s*\$?\s*\d+(?:[.,]\d+)*)?\s*(?:trieu|tr\b|m\b|usd\b|vnd\b|\$)"
        match = re.search(r"\b(?:luong|thu nhap|salary|up\s*to|upto|len den|toi da|tu|from)\s*(?:cung\s*)?(?:up\s*to\s*|upto\s*)?" + amount, title)
        if match:
            phrase = re.sub(r"len den|toi da", "up to", match.group())
            candidates.append((phrase, "Tiêu đề tin gốc: " + str(row.get("title", ""))))
    try:
        rate = Decimal(str(row.get("usd_vnd_rate") or "25000"))
        if not rate.is_finite() or rate <= 0:
            rate = Decimal("25000")
    except InvalidOperation:
        rate = Decimal("25000")
    for value, source in candidates:
        try:
            parsed = normalize_salary(value, rate)
        except InvalidOperation:
            continue
        if parsed["salary_min"] is not None or parsed["salary_max"] is not None:
            low = float(parsed["salary_min"]) if parsed["salary_min"] is not None else np.nan
            high = float(parsed["salary_max"]) if parsed["salary_max"] is not None else np.nan
            return low, high, salary_label(value, low, high), source
    return np.nan, np.nan, "", ""


def add_salary_estimates(frame: pd.DataFrame, *, as_of=None) -> pd.DataFrame:
    """A=observed, B=peer estimate, C=NaN. Fit once before dashboard filters.

    Only complete observed ranges are references. Three deduplicated listings,
    two employers, exact role/city/experience band, overlapping skills and a
    bounded dispersion are required. Estimated rows never become references.
    """
    df = frame.copy()
    for field in ("salary_min", "salary_max"):
        df[field] = pd.to_numeric(df.get(field, pd.Series(np.nan, index=df.index)), errors="coerce")
        df[field] = df[field].where(np.isfinite(df[field]) & df[field].gt(0))
    records = df.to_dict("records")
    feats = [features(row) for row in records]
    observed_values = [observed_salary(row) for row in records]
    now = pd.Timestamp(as_of if as_of is not None else pd.Timestamp.now(tz="UTC"))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    donors = []
    seen = set()
    stamps = pd.to_datetime(df.get("scraped_at", pd.Series("", index=df.index)), utc=True, errors="coerce")
    for i in sorted(range(len(records)), key=lambda n: str(records[n].get("scraped_at", "")), reverse=True):
        row, f = records[i], feats[i]
        low, high, _, _ = observed_values[i]
        stamp = stamps.iloc[i]
        if not (pd.notna(low) and pd.notna(high) and 0 < low <= high):
            continue
        if not all(f[k] for k in ("role", "band", "city", "company", "skills")):
            continue
        if pd.isna(stamp) or not -7 <= (now-stamp).total_seconds()/86400 <= MAX_AGE_DAYS:
            continue
        identity = (f["company"], f["title_key"], f["city"], f["band"])
        if identity in seen:
            continue
        seen.add(identity)
        donors.append(i)
    outputs = []
    for i, (row, f) in enumerate(zip(records, feats)):
        low, high, observed_text, evidence = observed_values[i]
        result = dict(salary_group="C", salary_estimate_min=np.nan, salary_estimate_max=np.nan,
                      salary_estimate_midpoint=np.nan, salary_peer_count=0, salary_peers=[],
                      salary_role=f["role"], salary_experience_band=f["band"], salary_estimate_reason="",
                      salary_observed_min=low, salary_observed_max=high, salary_observed_evidence=evidence)
        observed = pd.notna(low) or pd.notna(high)
        if observed:
            result.update(salary_group="A", salary_estimate_reason="Mức lương từ tin gốc; giữ nguyên số tiền và giới hạn trần/sàn.")
        else:
            missing = [label for key, label in (("role", "nhóm vị trí"), ("city", "địa điểm cụ thể"), ("band", "kinh nghiệm/cấp bậc"), ("skills", "kỹ năng chuyên môn")) if not f[key]]
            if missing:
                result["salary_estimate_reason"] = "Thiếu " + ", ".join(missing) + "."
            else:
                matches = []
                for j in donors:
                    peer = feats[j]
                    if j == i or any(f[k] != peer[k] for k in ("role", "city", "band")):
                        continue
                    if f["years"] is not None and peer["years"] is not None and abs(f["years"]-peer["years"]) > 2:
                        continue
                    skill_score = len(f["skills"] & peer["skills"])/len(f["skills"] | peer["skills"])
                    if skill_score < .2:
                        continue
                    title_score = len(f["words"] & peer["words"])/max(1, len(f["words"] | peer["words"]))
                    matches.append((.8*skill_score + .2*title_score, j))
                matches.sort(key=lambda pair: (-pair[0], str(records[pair[1]].get("url", ""))))
                chosen, companies = [], {}
                for score, j in matches:
                    company = feats[j]["company"]
                    if companies.get(company, 0) >= 2:
                        continue
                    companies[company] = companies.get(company, 0)+1
                    chosen.append((score, j))
                    if len(chosen) == MAX_PEERS:
                        break
                result["salary_peer_count"] = len(chosen)
                if len(chosen) < MIN_PEERS or len(companies) < 2:
                    result["salary_estimate_reason"] = f"Chỉ có {len(chosen)} tin tương tự từ {len(companies)} công ty; cần ít nhất 3 tin / 2 công ty."
                else:
                    lows = np.array([observed_values[j][0] for _, j in chosen])
                    highs = np.array([observed_values[j][1] for _, j in chosen])
                    mids = (lows+highs)/2
                    median = float(np.median(mids))
                    if (np.quantile(mids, .75)-np.quantile(mids, .25))/median > .6 or max(mids)/min(mids) > 3:
                        result["salary_estimate_reason"] = "Lương các tin tương tự chênh lệch quá lớn; chưa đủ nhất quán để ước tính."
                    else:
                        estimate_low, estimate_high = float(np.median(lows)), float(np.median(highs))
                        result.update(salary_group="B", salary_estimate_min=estimate_low,
                                      salary_estimate_max=estimate_high, salary_estimate_midpoint=(estimate_low+estimate_high)/2,
                                      salary_estimate_reason="Trung vị từng đầu khoảng lương của các tin đối chiếu; không phải mức lương nhà tuyển dụng công bố.")
                        result["salary_peers"] = [dict(title=records[j].get("title", ""), company=records[j].get("company", ""),
                            source=records[j].get("source", ""), url=records[j].get("url", ""), similarity=round(score*100, 1),
                            salary_min=observed_values[j][0], salary_max=observed_values[j][1],
                            scraped_at=records[j].get("scraped_at", "")) for score, j in chosen]
        comparison_low = low if observed else result["salary_estimate_min"]
        comparison_high = high if observed else result["salary_estimate_max"]
        valid = pd.notna(comparison_low) and pd.notna(comparison_high) and comparison_low <= comparison_high
        result.update(salary_comparison_min=comparison_low, salary_comparison_max=comparison_high,
                      salary_comparison_midpoint=(comparison_low+comparison_high)/2 if valid else np.nan)
        if result["salary_group"] == "A":
            result["salary_display"] = observed_text
            result["salary_vnd"] = monthly_salary_label(low, high)
        elif result["salary_group"] == "B":
            result["salary_display"] = "Ước tính ≈ " + monthly_salary_label(comparison_low, comparison_high)
            result["salary_vnd"] = result["salary_display"]
        else:
            result["salary_display"] = result["salary_vnd"] = "NaN · Chưa đủ dữ liệu"
        result["salary_group_label"] = GROUP_LABELS[result["salary_group"]]
        outputs.append(result)
    for field in (outputs[0] if outputs else ["salary_group", "salary_group_label", "salary_display", "salary_vnd", "salary_peer_count", "salary_peers", "salary_role", "salary_experience_band", "salary_estimate_reason", "salary_estimate_min", "salary_estimate_max", "salary_estimate_midpoint", "salary_comparison_min", "salary_comparison_max", "salary_comparison_midpoint", "salary_observed_min", "salary_observed_max", "salary_observed_evidence"]):
        df[field] = pd.Series([row[field] for row in outputs], index=df.index, dtype=object if field in {"salary_peers"} else None)
    return df
