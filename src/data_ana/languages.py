"""Extract explicit programming language mentions and a short source excerpt."""
from __future__ import annotations

import re


ALIASES = {
    "C++": ["c++", "cpp"], "C#": ["c#", "c sharp"],
    "Python": ["python"], "Java": ["java"], "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"], "PHP": ["php"], "Go": ["golang"],
    "Rust": ["rust"], "Ruby": ["ruby"], "Kotlin": ["kotlin"], "Swift": ["swift"],
    "Dart": ["dart"], "Scala": ["scala"], "Perl": ["perl"], "Lua": ["lua"],
    "Objective-C": ["objective-c", "objective c"], "SQL": ["sql"],
    "Bash": ["bash", "shell scripting"], "R": ["r"],
}
PATTERNS = {name: re.compile(r"(?<![\w+#.&])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![\w+#&])", re.I) for name, aliases in ALIASES.items()}
PATTERNS["C++"] = re.compile(r"(?<![\w+#.])(?:c\+\+(?:\d{2})?|cpp)(?![\w+#])", re.I)
PATTERNS["Python"] = re.compile(r"(?<![\w.])python(?:\d+(?:\.\d+)*)?(?!\w)", re.I)
PATTERNS["Java"] = re.compile(r"(?<![\w.])java(?:\d+)?(?!\w)", re.I)
PATTERNS["C"] = re.compile(r"(?<![\w+#.])(?:ngôn ngữ\s+c|\bc\s+(?:programming|language|developer)|\bc(?=\s*[,/]\s*c\+\+))(?![\w+#])", re.I)
PATTERNS["Go"] = re.compile(r"(?<![\w.])(?:golang|go\s+(?:developer|engineer|programming|language))(?!\w)", re.I)


def extract_languages(title: str = "", description: str = "", skills=None, requirements: str = "") -> tuple[list[str], dict]:
    if isinstance(skills, str):
        skills = skills.split(";")
    skills = [s for s in (skills or []) if isinstance(s, str) and "..." not in s and "…" not in s]
    sources = [("Yêu cầu ứng viên", requirements), ("Tiêu đề", title), ("Mô tả", description), ("Thẻ kỹ năng", "; ".join(skills))]
    evidence = {}
    for language, pattern in PATTERNS.items():
        for source, text in sources:
            text = re.sub(r"\s+", " ", text or "").strip()
            match = pattern.search(text)
            if match:
                evidence[language] = {"source": source, "excerpt": text[max(0, match.start()-70):match.end()+100]}
                break
    # C and Go are ambiguous prose; standalone tags are explicit enough.
    for language in ("C", "Go"):
        if any(s.strip().casefold() == language.casefold() for s in skills):
            evidence.setdefault(language, {"source": "Thẻ kỹ năng", "excerpt": language})
    return sorted(evidence), evidence


def refresh_languages(post) -> None:
    post.programming_languages, post.language_evidence = extract_languages(post.title, post.description, post.skills, post.requirements)
