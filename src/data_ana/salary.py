"""Salary values from public listings, shared by crawling, ETL and display."""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

from data_ana.utils import clean_text, unaccent

UNDISCLOSED_SALARY = "Thỏa thuận (chưa nêu số tiền)"


def decimal_number(token: str) -> Decimal:
    token = token.replace(" ", "")
    if "," in token and "." in token:
        # The last separator is the decimal mark (1,000.50 / 1.000,50).
        decimal_mark = "," if token.rfind(",") > token.rfind(".") else "."
        token = token.replace("." if decimal_mark == "," else ",", "").replace(decimal_mark, ".")
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
        token = re.sub(r"[.,]", "", token)
    else:
        token = token.replace(",", ".")
    return Decimal(token)


def requires_salary_login(text: str) -> bool:
    return bool(re.search(r"sign[\s-]*in|log[\s-]*in|dang nhap", unaccent(text)))


def normalize_salary(text: str, usd_vnd_rate: Decimal) -> dict:
    result = dict(salary_currency=None, salary_period=None, salary_min_original=None,
                  salary_max_original=None, salary_min=None, salary_max=None,
                  usd_vnd_rate=usd_vnd_rate)
    value = unaccent(text)
    if not value or requires_salary_login(text) or any(w in value for w in ["thoa thuan", "negotiable", "competitive", "canh tranh"]):
        return result
    amounts = re.findall(r"\d+(?:[.,]\d+)*", value)
    if not amounts:
        return result
    usd = "$" in value or "usd" in value
    million = bool(re.search(r"trieu|million|\d\s*(?:m|tr)\b", value))
    if not usd and not million and not re.search(r"\bvnd\b|\bdong\b|₫|\d\s*k\b", value):
        return result
    multiplier = Decimal(1_000_000 if million else 1_000 if re.search(r"\d\s*k\b", value) else 1)
    if usd and (million or re.search(r"\bvnd\b|\bdong\b|₫", value)):
        return result  # Ambiguous mixed currencies: retain text without guessing.
    numbers = [decimal_number(a) * multiplier for a in amounts]
    if len(numbers) > 2 or any(n <= 0 for n in numbers):
        return result
    lower, upper = (min(numbers), max(numbers)) if len(numbers) == 2 else (numbers[0], numbers[0])
    if len(numbers) == 1:
        if any(w in value for w in ["toi ", "up to", "upto", "duoi ", "under "]):
            lower = None
        elif any(w in value for w in ["tu ", "from ", "tren ", "over "]):
            upper = None
    period = "month"
    for unit, pattern in [("hour", r"/\s*(?:h\b|hour)|per hour|moi gio|/gio"), ("day", r"/\s*(?:day|ngay)|per day|moi ngay"), ("year", r"/\s*(?:year|nam)|per year|annually|moi nam")]:
        if re.search(pattern, value):
            period = unit
            break
    currency = "USD" if usd else "VND"
    result.update(salary_currency=currency, salary_period=period, salary_min_original=lower, salary_max_original=upper)
    if period in {"month", "year"}:
        factor = (usd_vnd_rate if usd else Decimal(1)) / (12 if period == "year" else 1)
        result.update(salary_min=(lower * factor).quantize(Decimal("1")) if lower is not None else None,
                      salary_max=(upper * factor).quantize(Decimal("1")) if upper is not None else None)
    return result


def public_salary_text(base_salary) -> str:
    """Read actual baseSalary, never estimated/filter salaries or related jobs.

    Some ITviec pages label all schema salaries USD even when the value itself
    explicitly says VND. A self-contained text value takes precedence in that
    case; currency-free numbers must have valid currency and unit metadata.
    """
    if not isinstance(base_salary, dict):
        return ""
    raw = base_salary.get("value")
    quantity = raw if isinstance(raw, dict) else {"value": raw}
    unit = str(quantity.get("unitText") or base_salary.get("unitText") or "").upper()
    period = {"MONTH": "month", "YEAR": "year", "HOUR": "hour", "DAY": "day"}.get(unit)
    if not period:
        return ""
    currency = str(base_salary.get("currency") or "").upper()
    value = quantity.get("value")
    if isinstance(value, str):
        text = clean_text(value)
        if requires_salary_login(text):
            return ""
        if any(t in unaccent(text) for t in ("negotiable", "thoa thuan")):
            return text
        # Explicit units in the value also let us detect currency conflicts.
        parsed = normalize_salary(text, Decimal("25000"))
        if parsed["salary_currency"]:
            if not re.search(r"/|per (?:month|year|hour|day)|annually|moi (?:thang|nam|gio|ngay)", unaccent(text)):
                text += f"/{period}"
            return text
    if currency not in {"VND", "USD"}:
        return ""

    def number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            amount = Decimal(str(value))
            return amount if amount.is_finite() and amount > 0 else None
        except InvalidOperation:
            return None

    low, high = number(quantity.get("minValue")), number(quantity.get("maxValue"))
    if low is not None and high is not None and low > high:
        return ""
    if low is None and high is None:
        low = high = number(value)
    if low is None and high is None:
        return ""
    fmt = lambda n: f"{n:,.2f}".rstrip("0").rstrip(".")
    if low is None:
        text = "Up to " + fmt(high)
    elif high is None:
        text = "From " + fmt(low)
    elif low == high:
        text = fmt(low)
    else:
        text = f"{fmt(low)} - {fmt(high)}"
    return f"{text} {currency}/{period}"


def salary_label(text: str, low=None, high=None) -> str:
    """Prefer actual amounts; use one consistent label when no amount exists."""
    text = clean_text(text)
    try:
        parsed = normalize_salary(text, Decimal("25000"))
    except InvalidOperation:
        parsed = {}
    if parsed.get("salary_currency"):
        return text
    # Older snapshots can retain the sign-in message alongside valid numbers.
    monthly = monthly_salary_label(low, high)
    if monthly != "Chưa đủ dữ liệu quy đổi":
        return monthly
    return UNDISCLOSED_SALARY


def monthly_salary_label(low, high) -> str:
    def amount(value):
        try:
            return float(value) if math.isfinite(float(value)) and float(value) > 0 else None
        except (TypeError, ValueError):
            return None
    low, high = amount(low), amount(high)
    fmt = lambda n: f"{n:,.0f}".replace(",", ".")
    if low is not None and high is not None and low <= high:
        return (fmt(low) if low == high else f"{fmt(low)} – {fmt(high)}") + " ₫/tháng"
    if low is not None and high is None:
        return f"Từ {fmt(low)} ₫/tháng"
    if high is not None and low is None:
        return f"Tối đa {fmt(high)} ₫/tháng"
    return "Chưa đủ dữ liệu quy đổi"
