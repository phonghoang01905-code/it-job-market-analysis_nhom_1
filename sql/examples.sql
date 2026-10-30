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

-- Explicit programming language mentions by website (one occurrence/job).
SELECT j.source, language.name, count(*) AS job_count
FROM jobs j
CROSS JOIN LATERAL unnest(j.programming_languages) AS language(name)
GROUP BY j.source, language.name ORDER BY j.source, job_count DESC;

-- Inspect the original requirement and evidence for Python jobs.
SELECT source, title, programming_languages, requirements, language_evidence, url
FROM jobs WHERE 'Python' = ANY(programming_languages);

-- Supporting skills, spoken languages and the original benefits text.
SELECT source, title, supplementary_skills, foreign_languages,
       english_status, english_requirement, benefit_tags, benefits, url
FROM jobs ORDER BY source, id;

-- Training in English is not a mandatory English requirement.
SELECT source, english_status, count(*) AS job_count
FROM jobs GROUP BY source, english_status ORDER BY source, english_status;

SELECT source, benefit.name, count(*) AS job_count
FROM jobs CROSS JOIN LATERAL unnest(benefit_tags) AS benefit(name)
GROUP BY source, benefit.name ORDER BY source, job_count DESC;

-- Compare salaries only for closed ranges, in VND/month.
SELECT source, city, level, count(*) AS disclosed_jobs,
       round(avg((salary_min + salary_max) / 2)) AS average_midpoint_vnd
FROM jobs
WHERE salary_min IS NOT NULL AND salary_max IS NOT NULL
GROUP BY source, city, level;
