/*
============================================================================
vw_FunnelCohort — Lead cohort conversion at +N days

For each lead-creation WEEK, count what % of those leads had reached each
stage within 7, 14, 30, 60, 90 days of lead creation.

Stages (same as vw_DailyLeadFunnel):
    Engaged      — at least one inbound message
    Booked       — at least one appointment
    OppsCreated  — at least one opportunity
    OppsWon      — at least one won opportunity

Cohort = ISO-week of lead creation.

============================================================================
*/

IF OBJECT_ID('ghl.vw_FunnelCohort', 'V') IS NOT NULL
    DROP VIEW ghl.vw_FunnelCohort;
GO

CREATE VIEW ghl.vw_FunnelCohort AS
WITH

leads AS (
    SELECT
        ContactId,
        DateAddedUtc AS LeadAtUtc,
        DATEADD(DAY, 1 - DATEPART(WEEKDAY, CAST(DateAddedUtc AS DATE)), CAST(DateAddedUtc AS DATE)) AS LeadWeek
        -- Week boundary: Sunday by default. Use SET DATEFIRST 1 for Monday.
    FROM ghl.Contacts
    WHERE DateAddedUtc IS NOT NULL
),

eng AS (
    SELECT
        C.ContactId,
        MIN(M.DateAddedUtc) AS EngagedAtUtc
    FROM ghl.Conversations         C
    JOIN ghl.ConversationMessages  M ON M.ConversationId = C.ConversationId
    WHERE M.Direction = 'inbound' AND C.ContactId IS NOT NULL
    GROUP BY C.ContactId
),

appt AS (
    SELECT ContactId, MIN(DateAddedUtc) AS ApptAtUtc
    FROM ghl.Appointments
    WHERE ContactId IS NOT NULL
    GROUP BY ContactId
),

opp AS (
    SELECT
        ContactId,
        MIN(DateAddedUtc) AS OppAtUtc,
        MIN(CASE WHEN Status = 'won' THEN DateClosedUtc END) AS WonAtUtc
    FROM ghl.Opportunities
    WHERE ContactId IS NOT NULL
    GROUP BY ContactId
),

joined AS (
    SELECT
        L.ContactId,
        L.LeadWeek,
        L.LeadAtUtc,
        CASE WHEN E.EngagedAtUtc IS NOT NULL
             THEN DATEDIFF(DAY, L.LeadAtUtc, E.EngagedAtUtc) END AS DaysToEngaged,
        CASE WHEN A.ApptAtUtc IS NOT NULL
             THEN DATEDIFF(DAY, L.LeadAtUtc, A.ApptAtUtc) END AS DaysToBooked,
        CASE WHEN O.OppAtUtc IS NOT NULL
             THEN DATEDIFF(DAY, L.LeadAtUtc, O.OppAtUtc) END AS DaysToOpp,
        CASE WHEN O.WonAtUtc IS NOT NULL
             THEN DATEDIFF(DAY, L.LeadAtUtc, O.WonAtUtc) END AS DaysToWon
    FROM       leads L
    LEFT JOIN  eng   E ON E.ContactId = L.ContactId
    LEFT JOIN  appt  A ON A.ContactId = L.ContactId
    LEFT JOIN  opp   O ON O.ContactId = L.ContactId
)

SELECT
    LeadWeek,
    COUNT_BIG(*) AS LeadsInCohort,

    SUM(CASE WHEN DaysToEngaged IS NOT NULL AND DaysToEngaged <=  7 THEN 1 ELSE 0 END) AS Engaged_7d,
    SUM(CASE WHEN DaysToEngaged IS NOT NULL AND DaysToEngaged <= 30 THEN 1 ELSE 0 END) AS Engaged_30d,
    SUM(CASE WHEN DaysToEngaged IS NOT NULL AND DaysToEngaged <= 90 THEN 1 ELSE 0 END) AS Engaged_90d,

    SUM(CASE WHEN DaysToBooked IS NOT NULL AND DaysToBooked <= 14 THEN 1 ELSE 0 END) AS Booked_14d,
    SUM(CASE WHEN DaysToBooked IS NOT NULL AND DaysToBooked <= 30 THEN 1 ELSE 0 END) AS Booked_30d,
    SUM(CASE WHEN DaysToBooked IS NOT NULL AND DaysToBooked <= 90 THEN 1 ELSE 0 END) AS Booked_90d,

    SUM(CASE WHEN DaysToOpp IS NOT NULL AND DaysToOpp <= 30 THEN 1 ELSE 0 END) AS Opp_30d,
    SUM(CASE WHEN DaysToOpp IS NOT NULL AND DaysToOpp <= 90 THEN 1 ELSE 0 END) AS Opp_90d,

    SUM(CASE WHEN DaysToWon IS NOT NULL AND DaysToWon <= 30 THEN 1 ELSE 0 END) AS Won_30d,
    SUM(CASE WHEN DaysToWon IS NOT NULL AND DaysToWon <= 90 THEN 1 ELSE 0 END) AS Won_90d,

    -- Pct columns
    CASE WHEN COUNT_BIG(*) > 0 THEN 100.0 *
        SUM(CASE WHEN DaysToEngaged IS NOT NULL AND DaysToEngaged <= 7 THEN 1 ELSE 0 END) / COUNT_BIG(*)
        ELSE 0 END AS Engaged_7d_Pct,

    CASE WHEN COUNT_BIG(*) > 0 THEN 100.0 *
        SUM(CASE WHEN DaysToWon IS NOT NULL AND DaysToWon <= 90 THEN 1 ELSE 0 END) / COUNT_BIG(*)
        ELSE 0 END AS Won_90d_Pct
FROM joined
GROUP BY LeadWeek;
GO

/*
Recent cohort performance:

    SELECT TOP 20 *
    FROM ghl.vw_FunnelCohort
    WHERE LeadWeek >= DATEADD(DAY, -180, GETUTCDATE())
    ORDER BY LeadWeek DESC;
*/
