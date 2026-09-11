-- Resume fit (lib/resumeFit.js): the minority share of match_score that
-- compares the skills a posting names against resume/base-resume.md.
--
-- Stored rather than computed on read, for the same reason as location_score
-- and keyword_score: the dashboard explains a ranking from these columns
-- instead of re-running the matcher over every description on every request.
-- Both stay NULL when resume fit is off or the posting names no known skill.

ALTER TABLE discovered_jobs ADD COLUMN resume_score REAL;
ALTER TABLE discovered_jobs ADD COLUMN resume_skills TEXT;  -- JSON {"have": [...], "missing": [...]}
