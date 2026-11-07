import numpy as np
import pandas as pd
import pytest

from data_ana.salary_estimation import add_salary_estimates

NOW = "2026-11-07T00:00:00Z"


def listing(i, **overrides):
    return {"source": "topcv", "url": f"https://example.com/{i}", "title": "Backend Developer Python",
            "company": f"Company {i}", "location": "Hà Nội", "level": "Middle",
            "requirements": "At least 3 years of experience. Python Django SQL.", "skills": "Python;Django;SQL",
            "scraped_at": "2026-11-01T00:00:00Z", "salary_text": "Negotiable",
            "salary_min": np.nan, "salary_max": np.nan, **overrides}


def sample():
    return [listing(i, salary_text=f"{18+2*i} - {28+2*i} triệu", salary_min=(18+2*i)*1e6, salary_max=(28+2*i)*1e6) for i in range(1, 4)] + [listing(4, source="itviec")]


def estimate(rows):
    return add_salary_estimates(pd.DataFrame(rows), as_of=NOW)


def test_group_median_has_traceable_public_peers_and_preserves_original_values():
    original = pd.DataFrame(sample())
    result = add_salary_estimates(original, as_of=NOW)
    assert result.salary_group.tolist() == ["A", "A", "A", "B"]
    target = result.iloc[-1]
    assert target.salary_estimate_min == 22e6 and target.salary_estimate_max == 32e6
    assert target.salary_comparison_midpoint == 27e6
    assert target.salary_peer_count == 3
    assert len({peer["company"] for peer in target.salary_peers}) == 3
    assert target.salary_display.startswith("Ước tính ≈")
    assert pd.isna(target.salary_min) and pd.isna(target.salary_max)
    pd.testing.assert_series_equal(original.salary_min, result.salary_min)
    assert original.salary_text.equals(result.salary_text)


@pytest.mark.parametrize("changes", [{"location": "Hồ Chí Minh"}, {"level": "Senior"}, {"title": "Data Engineer Python"}, {"title": "Backend Developer Java", "skills": "Java;React", "requirements": "3 years of experience. Java React."}])
def test_mismatched_city_experience_role_or_skills_are_not_used(changes):
    rows = sample()
    rows[2].update(changes)
    target = estimate(rows).iloc[-1]
    assert target.salary_group == "C"
    assert pd.isna(target.salary_comparison_midpoint)


def test_same_employer_and_cross_site_duplicates_do_not_inflate_peer_count():
    rows = sample()
    for r in rows[:3]:
        r["company"] = "Same employer"
    assert estimate(rows).iloc[-1].salary_group == "C"
    rows = sample()
    duplicate = {**rows[0], "source": "topdev", "url": "https://other.example/same-job"}
    target = estimate([rows[0], rows[1], duplicate, rows[-1]]).iloc[-1]
    assert target.salary_group == "C" and target.salary_peer_count == 2


def test_estimates_are_never_donors_and_recomputing_cannot_create_feedback():
    rows = sample()[:2] + [listing(4, salary_group="B", salary_estimate_min=25e6, salary_estimate_max=35e6), listing(5)]
    result = estimate(rows)
    assert result.salary_group.tolist() == ["A", "A", "C", "C"]
    again = add_salary_estimates(result, as_of=NOW)
    assert again.salary_group.equals(result.salary_group)


def test_sparse_stale_or_highly_variable_reference_groups_keep_nan():
    assert estimate(sample()[1:]).iloc[-1].salary_group == "C"
    rows = sample()
    rows[2].update(salary_min=150e6, salary_max=200e6)
    assert estimate(rows).iloc[-1].salary_group == "C"
    rows = sample()
    for row in rows[:3]:
        row["scraped_at"] = "2025-01-01T00:00:00Z"
    assert estimate(rows).iloc[-1].salary_group == "C"


@pytest.mark.parametrize("changes", [{"level": "Unknown", "requirements": "Python Django SQL"}, {"location": ""}, {"location": "Hà Nội; Hồ Chí Minh"}])
def test_missing_important_target_fields_keep_nan(changes):
    rows = sample()
    rows[-1].update(changes)
    target = estimate(rows).iloc[-1]
    assert target.salary_group == "C"
    assert pd.isna(target.salary_estimate_min) and pd.isna(target.salary_estimate_max)


def test_advertised_ceiling_in_title_is_preserved_instead_of_estimated_above_it():
    rows = sample()
    rows[-1]["title"] = "Backend Developer - Upto 25tr - 3 năm kinh nghiệm"
    target = estimate(rows).iloc[-1]
    assert target.salary_group == "A"
    assert pd.isna(target.salary_comparison_min)
    assert target.salary_comparison_max == 25e6
    assert pd.isna(target.salary_estimate_max)
    assert "Tiêu đề" in target.salary_observed_evidence


def test_observed_ceiling_is_not_filled_with_an_estimated_floor():
    rows = sample()
    rows[-1].update(salary_text="Up to 30 triệu", salary_max=30e6)
    target = estimate(rows).iloc[-1]
    assert target.salary_group == "A" and pd.isna(target.salary_comparison_midpoint)
    assert pd.isna(target.salary_estimate_min)


def test_empty_dataset_has_estimate_schema():
    result = estimate([])
    assert result.empty
    assert {"salary_group", "salary_estimate_min", "salary_comparison_midpoint", "salary_peers"}.issubset(result.columns)


def test_point_estimate_is_the_center_of_displayed_median_bounds():
    rows = sample()
    for row, low, high in zip(rows, [20e6, 26e6, 28e6], [35e6, 30e6, 42e6]):
        row.update(salary_min=low, salary_max=high)
    target = estimate(rows).iloc[-1]
    assert target.salary_group == "B"
    assert target.salary_estimate_midpoint == (target.salary_estimate_min+target.salary_estimate_max)/2
    assert target.salary_comparison_midpoint == target.salary_estimate_midpoint
