-- Live views, not materialized: committed ETL changes appear on the next query.
CREATE OR REPLACE VIEW analytics_jobs AS
SELECT j.*, COALESCE(c.name, '') AS company,
       COALESCE((SELECT string_agg(s.name, ';' ORDER BY s.name)
                 FROM job_skills js JOIN skills s ON s.id = js.skill_id
                 WHERE js.job_id = j.id), '') AS skills,
       CASE WHEN j.salary_min > 0 AND j.salary_max >= j.salary_min
            THEN (j.salary_min + j.salary_max) / 2 END AS salary_midpoint,
       (j.scraped_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS observed_date
FROM jobs j LEFT JOIN companies c ON c.id = j.company_id;

CREATE OR REPLACE VIEW analytics_job_skills AS
SELECT f.*, x.skill
FROM analytics_jobs f CROSS JOIN LATERAL (
 SELECT s.name AS skill FROM job_skills js JOIN skills s ON s.id = js.skill_id WHERE js.job_id = f.id
 UNION SELECT unnest(f.programming_languages)
) x;

CREATE OR REPLACE VIEW analytics_job_cities AS
SELECT f.*, x.city_name
FROM analytics_jobs f
CROSS JOIN LATERAL (
    SELECT DISTINCT COALESCE(NULLIF(regexp_replace(trim(v), '\s*\(mới\)$', ''), ''), 'Chưa xác định') AS city_name
    FROM unnest(string_to_array(COALESCE(NULLIF(f.city, ''), 'Chưa xác định'), ';')) AS t(v)
) x;

CREATE OR REPLACE VIEW analytics_top_skills AS
SELECT skill, count(DISTINCT id) AS job_count,
       count(salary_midpoint) AS salary_count, avg(salary_midpoint) AS avg_salary,
       percentile_cont(.5) WITHIN GROUP (ORDER BY salary_midpoint) AS median_salary,
       percentile_cont(.25) WITHIN GROUP (ORDER BY salary_midpoint) AS p25_salary,
       percentile_cont(.75) WITHIN GROUP (ORDER BY salary_midpoint) AS p75_salary
FROM analytics_job_skills GROUP BY skill;

CREATE OR REPLACE VIEW analytics_top_companies AS
SELECT company_id, company, count(*) AS job_count,
       count(salary_midpoint) AS salary_count,
       percentile_cont(.5) WITHIN GROUP (ORDER BY salary_midpoint) AS median_salary
FROM analytics_jobs WHERE company_id IS NOT NULL GROUP BY company_id, company;

CREATE OR REPLACE VIEW analytics_top_cities AS
SELECT city_name AS city, count(DISTINCT id) AS job_count,
       count(salary_midpoint) AS salary_count, avg(salary_midpoint) AS avg_salary,
       percentile_cont(.5) WITHIN GROUP (ORDER BY salary_midpoint) AS median_salary
FROM analytics_job_cities GROUP BY city_name;

CREATE OR REPLACE VIEW analytics_salary_by_skill AS SELECT * FROM analytics_top_skills;
CREATE OR REPLACE VIEW analytics_salary_by_city AS SELECT * FROM analytics_top_cities;
CREATE OR REPLACE VIEW analytics_salary_by_level AS
SELECT level, count(*) AS job_count, count(salary_midpoint) AS salary_count,
       avg(salary_midpoint) AS avg_salary,
       percentile_cont(.5) WITHIN GROUP (ORDER BY salary_midpoint) AS median_salary,
       percentile_cont(.25) WITHIN GROUP (ORDER BY salary_midpoint) AS p25_salary,
       percentile_cont(.75) WITHIN GROUP (ORDER BY salary_midpoint) AS p75_salary
FROM analytics_jobs GROUP BY level;

CREATE OR REPLACE VIEW analytics_weekly_jobs AS
WITH bounds AS (SELECT date_trunc('week', min(posted_date)) AS lo,
                       date_trunc('week', max(posted_date)) AS hi FROM jobs),
calendar AS (SELECT generate_series(lo, hi, '1 week')::date AS week FROM bounds)
SELECT c.week, count(j.id) AS job_count
FROM calendar c LEFT JOIN jobs j ON date_trunc('week', j.posted_date)::date = c.week
GROUP BY c.week;

CREATE OR REPLACE VIEW analytics_monthly_jobs AS
WITH bounds AS (SELECT date_trunc('month', min(posted_date)) AS lo,
                       date_trunc('month', max(posted_date)) AS hi FROM jobs),
calendar AS (SELECT generate_series(lo, hi, '1 month')::date AS month FROM bounds)
SELECT c.month, count(j.id) AS job_count
FROM calendar c LEFT JOIN jobs j ON date_trunc('month', j.posted_date)::date = c.month
GROUP BY c.month;

CREATE OR REPLACE VIEW analytics_weekly_skills AS
SELECT w.week, s.name AS skill, count(DISTINCT js.id) AS job_count, w.job_count AS period_jobs,
       CASE WHEN w.job_count > 0 THEN count(DISTINCT js.id) * 100.0 / w.job_count ELSE 0 END AS share_pct
FROM analytics_weekly_jobs w CROSS JOIN (SELECT DISTINCT skill AS name FROM analytics_job_skills) s
LEFT JOIN analytics_job_skills js ON date_trunc('week', js.posted_date)::date = w.week AND js.skill = s.name
GROUP BY w.week, s.name, w.job_count;

CREATE OR REPLACE VIEW analytics_skill_changes AS
WITH compared AS (
 SELECT *, lag(job_count) OVER (PARTITION BY skill ORDER BY week) AS previous_count,
           lag(share_pct) OVER (PARTITION BY skill ORDER BY week) AS previous_share,
           lag(week) OVER (PARTITION BY skill ORDER BY week) AS previous_week
 FROM analytics_weekly_skills
)
SELECT skill, previous_week, week AS current_week, previous_count, job_count AS current_count,
       job_count - previous_count AS count_change, share_pct - previous_share AS share_change_pp,
       (job_count - previous_count) * 100.0 / NULLIF(previous_count, 0) AS growth_pct
FROM compared WHERE week = (SELECT max(week) FROM analytics_weekly_jobs) AND previous_week IS NOT NULL;
