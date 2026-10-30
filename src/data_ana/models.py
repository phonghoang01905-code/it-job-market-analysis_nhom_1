from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json


@dataclass(slots=True)
class JobPost:
    source: str
    title: str
    company: str = ""
    location: str = ""
    level: str = "Unknown"
    work_model: str = "Unknown"
    salary_text: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    description: str = ""
    requirements: str = ""
    programming_languages: list[str] = field(default_factory=list)
    language_evidence: dict = field(default_factory=dict)
    supplementary_skills: list[str] = field(default_factory=list)
    foreign_languages: list[str] = field(default_factory=list)
    english_requirement: str = ""
    english_status: str = "unknown"
    benefits: str = ""
    benefit_tags: list[str] = field(default_factory=list)
    profile_evidence: dict = field(default_factory=dict)
    posted_date: str = ""
    job_id: str = ""
    skills: list[str] = field(default_factory=list)
    url: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_row(self) -> dict[str, str | int | None]:
        row = asdict(self)
        row["skills"] = ";".join(self.skills)
        row["programming_languages"] = ";".join(self.programming_languages)
        row["language_evidence"] = json.dumps(self.language_evidence, ensure_ascii=False)
        for key in ("supplementary_skills", "foreign_languages", "benefit_tags"):
            row[key] = ";".join(row[key])
        row["profile_evidence"] = json.dumps(self.profile_evidence, ensure_ascii=False)
        return row

