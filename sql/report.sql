-- Summary queries for the hygiene report and dashboard. Each block starts with "-- name:".
-- Tables: issues (results/issues.csv), records (every record with its table and owner),
-- users, opportunities. "Info" rows are the surviving side of a duplicate and aren't problems.

-- name: by_table
-- How many records in each table have at least one problem.
-- Count distinct records: a record with two problems joins to two issue rows.
SELECT r.tbl AS table_name,
       COUNT(DISTINCT r.record_id) AS records,
       COUNT(DISTINCT i.record_id) AS records_with_problems,
       ROUND(100.0 * (COUNT(DISTINCT r.record_id) - COUNT(DISTINCT i.record_id))
             / COUNT(DISTINCT r.record_id), 1) AS clean_pct
FROM records r
LEFT JOIN issues i ON i.record_id = r.record_id AND i.severity <> 'Info'
GROUP BY r.tbl
ORDER BY clean_pct;

-- name: by_issue
-- Every check, how often it fired, and who usually fixes it.
SELECT issue_type, "table" AS table_name, severity, fix_by, rule, COUNT(*) AS problems
FROM issues
WHERE severity <> 'Info'
GROUP BY issue_type
ORDER BY CASE severity WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, problems DESC;

-- name: by_severity
SELECT severity, COUNT(*) AS problems
FROM issues
WHERE severity <> 'Info'
GROUP BY severity
ORDER BY CASE severity WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END;

-- name: pipeline
-- Open pipeline, and how much of it sits on deals with a High problem.
WITH open_deals AS (
  SELECT opportunity_id, COALESCE(amount_num, 0) AS amount
  FROM opportunities WHERE is_closed = 0
),
flagged AS (
  SELECT DISTINCT record_id FROM issues
  WHERE "table" = 'opportunities' AND severity = 'High'
)
SELECT COUNT(*) AS open_deals,
       SUM(amount) AS open_amount,
       SUM(CASE WHEN f.record_id IS NOT NULL THEN 1 ELSE 0 END) AS flagged_deals,
       SUM(CASE WHEN f.record_id IS NOT NULL THEN amount ELSE 0 END) AS flagged_amount
FROM open_deals d
LEFT JOIN flagged f ON f.record_id = d.opportunity_id;

-- name: by_owner
-- Problems per owner, scaled by how many records they own so big books aren't punished.
WITH owned AS (
  SELECT owner_id, COUNT(*) AS records FROM records GROUP BY owner_id
),
probs AS (
  SELECT owner_id,
         COUNT(*) AS problems,
         SUM(CASE WHEN severity = 'High' THEN 1 ELSE 0 END) AS high
  FROM issues WHERE severity <> 'Info' GROUP BY owner_id
)
SELECT COALESCE(NULLIF(o.owner_id, ''), 'Unassigned') AS owner_id,
       COALESCE(u.name, 'Unassigned') AS owner,
       COALESCE(u.role, '') AS role,
       COALESCE(u.is_active, '') AS is_active,
       o.records,
       COALESCE(p.problems, 0) AS problems,
       COALESCE(p.high, 0) AS high,
       ROUND(100.0 * COALESCE(p.problems, 0) / o.records, 1) AS problems_per_100
FROM owned o
LEFT JOIN probs p ON p.owner_id = o.owner_id
LEFT JOIN users u ON u.user_id = o.owner_id
ORDER BY problems DESC;

-- name: queue
-- The clean-up queue: one row per record, worst first. Severity points add up across
-- problems, and open deal size breaks ties.
SELECT record_id,
       "table" AS table_name,
       COALESCE(u.name, 'Unassigned') AS owner,
       GROUP_CONCAT(issue_type, ', ') AS problems,
       SUM(weight) AS points,
       MAX(open_amount) AS open_amount
FROM issues i
LEFT JOIN users u ON u.user_id = i.owner_id
WHERE severity <> 'Info'
GROUP BY record_id
ORDER BY points DESC, open_amount DESC, record_id
LIMIT 50;
