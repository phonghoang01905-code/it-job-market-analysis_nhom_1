from decimal import Decimal
import json

from data_ana.languages import extract_languages
from data_ana.etl import normalize_job
from data_ana.models import JobPost
from data_ana.crawl import merge_posts, write_csv


def test_languages_do_not_confuse_cpp_csharp_java_javascript_or_nodejs():
    languages, evidence = extract_languages("C++ / C# Developer", "JavaScript, TypeScript, Python. Node.js and R&D.", ["React"])
    assert languages == ["C#", "C++", "JavaScript", "Python", "TypeScript"]
    assert "Java" not in evidence and "C" not in evidence and "R" not in evidence
    assert extract_languages(description="Node.js, React and .NET")[0] == []
    assert extract_languages(description="Go to the office")[0] == []
    assert extract_languages(title="C++17 / Python3.10 / Java17 Developer")[0] == ["C++", "Java", "Python"]


def test_requirements_evidence_takes_priority_and_go_c_tags_are_supported():
    languages, evidence = extract_languages("Python dev", "Python is optional", ["Go", "C"], "Required: Python and Java.")
    assert languages == ["C", "Go", "Java", "Python"]
    assert evidence["Python"]["source"] == "Yêu cầu ứng viên"
    assert "Required: Python" in evidence["Python"]["excerpt"]


def test_language_fields_survive_raw_csv_and_etl(tmp_path):
    post = JobPost(source="topcv", title="Developer", requirements="Python, JavaScript, C++", url="https://example.com/job/1")
    path = tmp_path / "raw.csv"
    write_csv([post], path)
    merged = merge_posts([], path)
    write_csv(merged, path)
    loaded = merge_posts([], path)[0]
    assert loaded.programming_languages == ["C++", "JavaScript", "Python"]
    assert loaded.requirements == post.requirements
    normalized = normalize_job(loaded.to_row(), Decimal("25000"))
    assert normalized["programming_languages"] == loaded.programming_languages
    assert normalized["language_evidence"]["Python"]["source"] == "Yêu cầu ứng viên"
    assert json.loads(loaded.to_row()["language_evidence"]) == loaded.language_evidence
