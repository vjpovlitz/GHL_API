/*
============================================================================
vw_LeadSourceROI — Lead source attribution & ROI

For each LeadSource (from Contacts.Source):
    - LeadsTotal             count of contacts
    - LeadsLast30
    - EngagedContacts        contacts with ≥1 inbound msg
    - ApptsBooked
    - OppsCreated
    - OppsWon
    - PipelineValueWon
    - AvgValuePerLead        PipelineValueWon / LeadsTotal
    - WinRatePct             OppsWon / LeadsTotal * 100

Use to answer:
    "Which source has the highest $/lead?"
    "Which source has the worst engagement rate?"

============================================================================
*/

IF OBJECT_ID('ghl.vw_LeadSourceROI', 'V') IS NOT NULL
    DROP VIEW ghl.vw_LeadSourceROI;
GO

CREATE VIEW ghl.vw_LeadSourceROI AS
WITH
src AS (
    SELECT
        ISNULL(NULLIF(Source, ''), '(unknown)') AS LeadSource,
        ContactId,
        DateAddedUtc
    FROM ghl.Contacts
),
engaged AS (
    SELECT DISTINCT C.ContactId
    FROM ghl.Conversations         C
    JOIN ghl.ConversationMessages  M ON M.ConversationId = C.ConversationId
    WHERE M.Direction = 'inbound' AND C.ContactId IS NOT NULL
),
appt AS (
    SELECT DISTINCT ContactId FROM ghl.Appointments WHERE ContactId IS NOT NULL
),
opp AS (
    SELECT
        ContactId,
        SUM(CASE WHEN Status = 'won' THEN 1 ELSE 0 END) AS WonCount,
        SUM(CASE WHEN Status = 'won' THEN ISNULL(MonetaryValue, 0) ELSE 0 END) AS WonValue,
        COUNT_BIG(*) AS OppsCount
    FROM ghl.Opportunities
    WHERE ContactId IS NOT NULL
    GROUP BY ContactId
)
SELECT
    S.LeadSource,
    COUNT_BIG(*) AS LeadsTotal,
    SUM(CASE WHEN S.DateAddedUtc >= DATEADD(DAY, -30, GETUTCDATE()) THEN 1 ELSE 0 END) AS LeadsLast30,
    SUM(CASE WHEN E.ContactId IS NOT NULL THEN 1 ELSE 0 END) AS EngagedContacts,
    SUM(CASE WHEN A.ContactId IS NOT NULL THEN 1 ELSE 0 END) AS ApptsBookedContacts,
    SUM(CASE WHEN O.OppsCount > 0 THEN 1 ELSE 0 END) AS OppsCreatedContacts,
    SUM(ISNULL(O.WonCount, 0)) AS OppsWon,
    SUM(ISNULL(O.WonValue, 0)) AS PipelineValueWon,
    CASE WHEN COUNT_BIG(*) > 0
         THEN CAST(SUM(ISNULL(O.WonValue, 0)) AS DECIMAL(18, 2)) / COUNT_BIG(*)
         ELSE 0 END AS AvgValuePerLead,
    CASE WHEN COUNT_BIG(*) > 0
         THEN 100.0 * SUM(ISNULL(O.WonCount, 0)) / COUNT_BIG(*)
         ELSE 0 END AS WinRatePct,
    CASE WHEN COUNT_BIG(*) > 0
         THEN 100.0 * SUM(CASE WHEN E.ContactId IS NOT NULL THEN 1 ELSE 0 END) / COUNT_BIG(*)
         ELSE 0 END AS EngagedPct
FROM       src S
LEFT JOIN  engaged E ON E.ContactId = S.ContactId
LEFT JOIN  appt    A ON A.ContactId = S.ContactId
LEFT JOIN  opp     O ON O.ContactId = S.ContactId
GROUP BY S.LeadSource;
GO

/*
Top sources by win value:

    SELECT TOP 20 *
    FROM ghl.vw_LeadSourceROI
    ORDER BY PipelineValueWon DESC;
*/
