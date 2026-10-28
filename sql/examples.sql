-- Total jobs from each website.
SELECT source, count(*) AS job_count
FROM jobs GROUP BY source ORDER BY job_count DESC;

-- Most frequently mentioned skills, counting each job once.
SELECT s.name, count(*) AS job_count
FROM job_skills js JOIN skills s ON s.id = js.skill_id
GROUP BY s.id, s.name ORDER BY job_count DESC LIMIT 20;

-- Companies and their job counts.
SELECT c.name, count(*) AS job_count
FROM jobs j JOIN companies c ON c.id = j.company_id
GROUP BY c.id, c.name ORDER BY job_count DESC;

-- Compare salaries only for closed ranges, in VND/month.
SELECT source, city, level, count(*) AS disclosed_jobs,
       round(avg((salary_min + salary_max) / 2)) AS average_midpoint_vnd
FROM jobs
WHERE salary_min IS NOT NULL AND salary_max IS NOT NULL
GROUP BY source, city, level;
