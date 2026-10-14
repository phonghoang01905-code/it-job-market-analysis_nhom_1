from __future__ import annotations

import re
from urllib.parse import urljoin

COMMON_SKILLS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "react",
    "vue",
    "angular",
    "nodejs",
    "node.js",
    "php",
    "laravel",
    "c#",
    ".net",
    "golang",
    "go",
    "sql",
    "mysql",
    "postgresql",
    "mongodb",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "devops",
    "data",
    "ai",
    "machine learning",
]

LEVEL_KEYWORDS = {
    "Intern": ["intern", "thuc tap", "thực tập"],
    "Fresher": ["fresher"],
    "Junior": ["junior"],
    "Middle": ["middle", "mid-level", "mid level"],
    "Senior": ["senior", "lead", "principal"],
}

WORK_MODEL_KEYWORDS = {
    "Remote": ["remote", "work from home", "wfh", "lam viec tu xa", "làm việc từ xa"],
    "Hybrid": ["hybrid"],
    "Onsite": ["onsite", "tai van phong", "tại văn phòng"],
}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def absolute_url(base_url: str, href: str | None) -> str:
    if not href:
        return ""
    return urljoin(base_url, href)


def infer_level(text: str) -> str:
    normalized = text.lower()
    for level, keywords in LEVEL_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return level
    return "Unknown"


def infer_work_model(text: str) -> str:
    normalized = text.lower()
    for model, keywords in WORK_MODEL_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return model
    return "Unknown"


def extract_skills(text: str, extra_skills: list[str] | None = None) -> list[str]:
    haystack = text.lower()
    skills = COMMON_SKILLS + (extra_skills or [])
    found = {skill for skill in skills if re.search(rf"(?<!\w){re.escape(skill.lower())}(?!\w)", haystack)}
    return sorted(found)


def parse_salary_vnd(salary_text: str) -> tuple[int | None, int | None]:
    text = salary_text.lower()
    if not text or any(token in text for token in ["thoa thuan", "thoả thuận", "negotiable", "canh tranh"]):
        return None, None

    numbers = [float(match.replace(",", ".")) for match in re.findall(r"\d+(?:[.,]\d+)?", text)]
    if not numbers:
        return None, None

    multiplier = 1
    if "$" in text or "usd" in text:
        multiplier = 25_000
    elif "trieu" in text or "triệu" in text or "m" in text:
        multiplier = 1_000_000
    elif "k" in text:
        multiplier = 1_000

    values = [int(number * multiplier) for number in numbers]
    if len(values) == 1:
        return values[0], values[0]
    return min(values), max(values)

