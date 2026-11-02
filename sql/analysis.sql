-- Run ETL once first: python crawler.py --skip-crawl
-- Analytics view definitions: src/data_ana/analytics.sql
-- One row in analytics_jobs = one listing, not one vacancy or applicant.

-- 1. Overview and completeness (do not join skills before counting all jobs).
SELECT count(*) AS jobs, count(DISTINCT company_id) AS companies,
       count(posted_date) AS exact_posted_dates, count(salary_midpoint) AS salary_samples,
       max(scraped_at) AS latest_observation
FROM analytics_jobs;
SELECT source, count(*) AS jobs FROM analytics_jobs GROUP BY source ORDER BY jobs DESC;

-- 2. Top skills, companies and cities. Multi-city listings count in each city.
SELECT * FROM analytics_top_skills ORDER BY job_count DESC, skill LIMIT 15;
SELECT * FROM analytics_top_companies ORDER BY job_count DESC, company LIMIT 15;
SELECT * FROM analytics_top_cities ORDER BY job_count DESC, city;

-- 3. Salary = midpoint of a complete, valid VND/month range. Always show n.
SELECT skill, job_count, salary_count, median_salary, p25_salary, p75_salary
FROM analytics_salary_by_skill WHERE salary_count >= 3 ORDER BY median_salary DESC, skill;
SELECT * FROM analytics_salary_by_level ORDER BY level;
SELECT * FROM analytics_salary_by_city ORDER BY salary_count DESC, city;

-- 4. Calendar weeks start Monday. Missing exact posted dates are excluded.
SELECT * FROM analytics_weekly_jobs ORDER BY week;
SELECT * FROM analytics_monthly_jobs ORDER BY month;
SELECT * FROM analytics_weekly_skills WHERE skill IN ('Python', 'Java', 'JavaScript') ORDER BY week, skill;
SELECT * FROM analytics_skill_changes ORDER BY share_change_pp DESC, skill;
-- growth_pct is NULL when previous_count is 0, not infinite growth.
-- These are distributions within the collected sample, not proven market trends.

-- 5. Separate observation dates: this is crawler activity, not posting activity.
SELECT date_trunc('week', observed_date)::date AS week, count(*) AS jobs
FROM analytics_jobs GROUP BY 1 ORDER BY 1;

-- 6. Featured original position titles.
SELECT title, count(*) AS job_count, count(salary_midpoint) AS salary_count,
       percentile_cont(.5) WITHIN GROUP (ORDER BY salary_midpoint) AS median_salary
FROM analytics_jobs GROUP BY title ORDER BY job_count DESC, title LIMIT 20;
