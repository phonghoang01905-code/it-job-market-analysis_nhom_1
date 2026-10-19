from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


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
    posted_date: str = ""
    job_id: str = ""
    skills: list[str] = field(default_factory=list)
    url: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_row(self) -> dict[str, str | int | None]:
        row = asdict(self)
        row["skills"] = ";".join(self.skills)
        return row

