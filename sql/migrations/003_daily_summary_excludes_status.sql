/* Keep read-only status samples out of daily ExternText transaction counts. */
CREATE OR ALTER VIEW inkjet.vw_DailySummary AS
SELECT p.PrinterCode, CONVERT(date, t.CompletedAt) AS SummaryDate,
       COUNT_BIG(*) AS TransactionCount,
       SUM(CASE WHEN t.Outcome='VERIFIED' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS VerifiedCount,
       SUM(CASE WHEN t.Outcome='MISMATCH' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS MismatchCount,
       SUM(CASE WHEN t.Outcome='FAILED' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS FailedCount,
       SUM(CASE WHEN t.Outcome='BLOCKED' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS BlockedCount
FROM inkjet.TransactionLog AS t
JOIN inkjet.PrinterMaster AS p ON p.PrinterId=t.PrinterId
WHERE t.Outcome <> 'STATUS_ONLY'
GROUP BY p.PrinterCode, CONVERT(date, t.CompletedAt);
GO
