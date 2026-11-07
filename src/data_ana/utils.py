from __future__ import annotations

import re
import unicodedata
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
    "reactjs", "vuejs", "linux", "git", "agile", "scrum", "c++", "flutter",
    "tensorflow", "pytorch", "spark", "redis", "qa", "business analyst",
    "product owner", "tester", "excel", "power bi", "tableau",
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
    normalized = unaccent(text)
    if "hybrid" in normalized:
        return "Hybrid"
    if "truc tiep" in normalized or "at office" in normalized:
        return "Onsite"
    for model, keywords in WORK_MODEL_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return model
    return "Unknown"


def unaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").replace("đ", "d")


def extract_skills(text: str, extra_skills: list[str] | None = None) -> list[str]:
    haystack = text.lower()
    skills = COMMON_SKILLS + (extra_skills or [])
    found = {skill for skill in skills if re.search(rf"(?<!\w){re.escape(skill.lower())}(?!\w)", haystack)}
    return sorted(found)


def parse_salary_vnd(salary_text: str) -> tuple[int | None, int | None]:
    from decimal import Decimal
    from data_ana.salary import normalize_salary

    salary = normalize_salary(salary_text, Decimal("25000"))
    return tuple(int(salary[key]) if salary[key] is not None else None
                 for key in ("salary_min", "salary_max"))

