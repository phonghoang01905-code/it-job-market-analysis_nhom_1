"""Conservative extraction of supporting skills, spoken languages and benefits."""
from __future__ import annotations

import re

from data_ana.utils import clean_text, unaccent

ENGLISH_STATUS_LABELS = {
    "required": "Yêu cầu rõ ràng", "preferred": "Ưu tiên",
    "mentioned": "Có nhắc, chưa rõ bắt buộc", "not_required": "Không bắt buộc",
    "unknown": "Chưa có thông tin",
}
SUPPLEMENTARY = {
    "Giao tiếp": r"communication skills|communicate effectively|ky nang giao tiep|giao tiep tot",
    "Làm việc nhóm": r"teamwork|team work|work(?:ing)? (?:in|with) a team|lam viec (?:theo )?nhom",
    "Giải quyết vấn đề": r"problem.solving|giai quyet van de",
    "Tư duy phân tích": r"analytical (?:skills|thinking)|tu duy phan tich|kha nang phan tich",
    "Tư duy phản biện": r"critical thinking|tu duy phan bien",
    "Quản lý thời gian": r"time management|quan ly thoi gian",
    "Thuyết trình": r"presentation skills|thuyet trinh",
    "Lãnh đạo": r"leadership|ky nang lanh dao|dan dat (?:doi|nhom)",
    "Tự học": r"self.learning|self.study|tu hoc|ham hoc hoi|chu dong hoc",
    "Thích nghi": r"adaptability|adaptable|kha nang thich nghi",
    "Tin học văn phòng": r"microsoft office|ms office|tin hoc van phong",
    "Excel": r"\bexcel\b", "PowerPoint": r"\bpowerpoint\b",
    "Git": r"\bgit\b", "Jira": r"\bjira\b", "Confluence": r"\bconfluence\b",
}
FOREIGN = {
    "Tiếng Anh": r"\benglish\b|tieng anh|\bielts\b|\btoeic\b|\btoefl\b",
    "Tiếng Nhật": r"\bjapanese\b|tieng nhat|\bjlpt\b|日本語",
    "Tiếng Hàn": r"\bkorean\b|tieng han|\btopik\b|한국어",
    "Tiếng Trung": r"\bchinese\b|\bmandarin\b|tieng trung|tieng hoa|\bhsk\b",
    "Tiếng Pháp": r"\bfrench\b|tieng phap",
    "Tiếng Đức": r"\bgerman\b|\bdeutsch\b|tieng duc",
}
BENEFITS = {
    "Bảo hiểm": r"bao hiem|\bbhxh\b|\bbhyt\b|\bbhtn\b|\binsurance\b",
    "Thưởng": r"\bthuong\b|\bbonus\b|13th.month|thang 13",
    "Nghỉ phép": r"nghi phep|annual leave|paid leave|paid (?:sick|holiday)|vacation",
    "Khám sức khỏe": r"kham suc khoe|health check|medical check",
    "Đào tạo": r"dao tao|\btraining\b|\blearning\b|\bcourses?\b",
    "Đào tạo ngoại ngữ": r"english (?:class|training|course)|hoc tieng anh|dao tao (?:tieng anh|ngoai ngu)|language (?:class|training)",
    "Du lịch / Team building": r"du lich|company trip|team.?building|company outing",
    "Phụ cấp": r"phu cap|\ballowances?\b|lunch|meal|parking|phone charges",
    "Thiết bị làm việc": r"\blaptop\b|macbook|equipment|thiet bi lam viec",
    "Giờ làm linh hoạt": r"flexible (?:hours|time|working)|gio (?:lam )?linh hoat|thoi gian linh hoat",
    "Cổ phiếu": r"stock option|\besop\b|co phieu",
}


def clauses(text: str) -> list[str]:
    return [clean_text(part) for part in re.split(r"\n+|;|(?<=[.!?])\s+|\s+[•●]\s*", text or "") if clean_text(part)]


def excerpt(text: str, start: int, end: int) -> str:
    return text[max(0, start-90):min(len(text), end+180)]


def benefits_from_description(description: str) -> str:
    marker = re.search(r"(?:why (?:you['’]?ll|you will) love working here|benefits for you|quyền lợi(?: được hưởng)?|phúc lợi)\s*:?\s*", description or "", re.I)
    if not marker:
        return ""
    rest = description[marker.end():]
    stop = re.search(r"(?:địa điểm làm việc|thời gian làm việc|cách thức ứng tuyển|how to apply)", rest, re.I)
    return clean_text(rest[:stop.start()] if stop else rest)


def requirement_status(text: str, source: str, label="Tiếng Anh") -> str:
    text = unaccent(text)
    language = "(?:" + FOREIGN[label] + ")"
    if re.search(r"(?:khong (?:yeu cau|bat buoc)|not (?:required|mandatory|necessary)).{0,35}" + language + "|" + language + r".{0,25}(?:not (?:required|mandatory|necessary)|khong bat buoc)|no\s+(?:any\s+)?" + language + r".{0,20}required", text):
        return "not_required"
    if re.search(r"(?:uu tien|preferred|nice.to.have).{0,45}" + language + "|" + language + r".{0,45}(?:uu tien|preferred|nice.to.have|advantage|a plus|is a bonus)", text):
        return "preferred"
    if re.search(r"(?:\bmust\b|\brequire(?:d)?\b|\bmandatory\b|bat buoc|yeu cau).{0,45}" + language + "|" + language + r".{0,45}(?:\brequired\b|\bmandatory\b|bat buoc)", text):
        return "required"
    return "mentioned"


def extract_profile(title: str = "", description: str = "", requirements: str = "", skills=None, benefits: str = "") -> dict:
    if isinstance(skills, str):
        skills = skills.split(";")
    tags = "; ".join(s for s in (skills or []) if isinstance(s, str) and "..." not in s and "…" not in s)
    benefits = benefits or benefits_from_description(description)
    evidence = {"supplementary_skills": {}, "foreign_languages": {}, "benefits": {}}
    # General company and benefit text is not evidence of applicant requirements.
    sources = [("Yêu cầu ứng viên", requirements), ("Tiêu đề", title), ("Thẻ kỹ năng", tags)]
    if not requirements:
        # Legacy snapshots may only contain a flattened requirement section.
        match = re.search(r"(?:your skills (?:and|&) (?:experience|qualifications)|yêu cầu ứng viên|yêu cầu công việc|requirements)\s*:?", description, re.I)
        if match:
            text = description[match.end():]
            end = re.search(r"why you|benefits for you|quyền lợi|phúc lợi|địa điểm làm việc", text, re.I)
            sources.insert(0, ("Yêu cầu trong mô tả", text[:end.start()] if end else text))
    for source, text in sources:
        for clause in clauses(text):
            normalized = unaccent(clause)
            for label, pattern in SUPPLEMENTARY.items():
                match = re.search(pattern, normalized)
                if match and not re.search(r"khong yeu cau|not required", normalized):
                    evidence["supplementary_skills"].setdefault(label, {"source": source, "excerpt": excerpt(clause, *match.span())})
            for label, pattern in FOREIGN.items():
                match = re.search(pattern, normalized)
                if match:
                    item = {"source": source, "excerpt": excerpt(clause, *match.span()), "status": requirement_status(clause, source, label)}
                    evidence["foreign_languages"].setdefault(label, item)
    # Recognize explicit requirement phrasing in old descriptions, but reject
    # English classes, international environment, and other employment benefits.
    for clause in clauses(description):
        normalized = unaccent(clause)
        if re.search(r"english (?:class|training|course|speaking environment)|dao tao tieng anh|hoc tieng anh|moi truong .{0,20}tieng anh", normalized):
            continue
        if not re.search(r"proficien|fluent|good .{0,30}english|english .{0,30}(?:skills|communication|proficiency|required|mandatory)|must.{0,40}english|giao tiep .{0,15}tieng anh|tieng anh .{0,20}giao tiep|\bielts\b|\btoeic\b|not required|khong yeu cau", normalized):
            continue
        for label, pattern in FOREIGN.items():
            match = re.search(pattern, normalized)
            if match:
                item = {"source": "Mô tả (câu yêu cầu)", "excerpt": excerpt(clause, *match.span()), "status": requirement_status(clause, "description", label)}
                old = evidence["foreign_languages"].get(label)
                if not old or old["source"] == "Thẻ kỹ năng":
                    evidence["foreign_languages"][label] = item
    for clause in clauses(benefits):
        normalized = unaccent(clause)
        for label, pattern in BENEFITS.items():
            match = re.search(pattern, normalized)
            if match and not re.search(r"no insurance|khong co bao hiem", normalized):
                evidence["benefits"].setdefault(label, {"source": "Phúc lợi từ tin gốc", "excerpt": excerpt(clause, *match.span())})
    english = evidence["foreign_languages"].get("Tiếng Anh", {})
    return {
        "supplementary_skills": sorted(evidence["supplementary_skills"]),
        "foreign_languages": sorted(evidence["foreign_languages"]),
        "english_requirement": english.get("excerpt", ""),
        "english_status": english.get("status", "unknown"),
        "benefits": benefits,
        "benefit_tags": sorted(evidence["benefits"]),
        "profile_evidence": evidence,
    }


def refresh_profile(post) -> None:
    for key, value in extract_profile(post.title, post.description, post.requirements, post.skills, post.benefits).items():
        setattr(post, key, value)
