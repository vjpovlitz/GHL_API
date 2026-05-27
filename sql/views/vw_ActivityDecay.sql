/*
============================================================================
vw_ActivityDecay — bucket contacts by days-since-last-activity

For each contact, "last activity" = latest of:
    - DateUpdatedUtc on the contact
    - LastMessageDateUtc on any of their conversations
    - DateClosedUtc / DateUpdatedUtc on any of their opportunities
    - StartTimeUtc on any of their appointments

Buckets:
    Hot         0-7 days
    Warm        8-30 days
    Cooling     31-90 days
    Cold        91-180 days
    Dormant     >180 days
    NoActivity  no signal at all

Useful for:
    - Re-engagement campaign sizing
    - Identifying agents with stale follow-ups
    - Pipeline-hygiene reports

============================================================================
*/

IF OBJECT_ID('ghl.vw_ActivityDecay', 'V') IS NOT NULL
    DROP VIEW ghl.vw_ActivityDecay;
GO

CREATE VIEW ghl.vw_ActivityDecay AS
WITH
contact_msg AS (
    SELECT C.ContactId, MAX(CV.LastMessageDateUtc) AS LastConvUtc
    FROM ghl.Contacts C
    JOIN ghl.Conversations CV ON CV.ContactId = C.ContactId
    GROUP BY C.ContactId
),
contact_opp AS (
    SELECT ContactId, MAX(ISNULL(DateUpdatedUtc, DateAddedUtc)) AS LastOppUtc
    FROM ghl.Opportunities WHERE ContactId IS NOT NULL
    GROUP BY ContactId
),
contact_appt AS (
    SELECT ContactId, MAX(StartTimeUtc) AS LastApptUtc
    FROM ghl.Appointments WHERE ContactId IS NOT NULL
    GROUP BY ContactId
),
last_activity AS (
    SELECT
        C.ContactId,
        C.AssignedToUserId,
        C.Source,
        (SELECT MAX(v) FROM (VALUES
            (C.DateUpdatedUtc), (CM.LastConvUtc),
            (CO.LastOppUtc), (CA.LastApptUtc)
        ) AS x(v)) AS LastActivityUtc
    FROM       ghl.Contacts  C
    LEFT JOIN  contact_msg   CM ON CM.ContactId = C.ContactId
    LEFT JOIN  contact_opp   CO ON CO.ContactId = C.ContactId
    LEFT JOIN  contact_appt  CA ON CA.ContactId = C.ContactId
)
SELECT
    ContactId,
    AssignedToUserId,
    Source,
    LastActivityUtc,
    CASE WHEN LastActivityUtc IS NULL THEN NULL
         ELSE DATEDIFF(DAY, LastActivityUtc, GETUTCDATE()) END AS DaysSinceActivity,
    CASE
        WHEN LastActivityUtc IS NULL                                    THEN 'NoActivity'
        WHEN DATEDIFF(DAY, LastActivityUtc, GETUTCDATE()) <=   7        THEN 'Hot'
        WHEN DATEDIFF(DAY, LastActivityUtc, GETUTCDATE()) <=  30        THEN 'Warm'
        WHEN DATEDIFF(DAY, LastActivityUtc, GETUTCDATE()) <=  90        THEN 'Cooling'
        WHEN DATEDIFF(DAY, LastActivityUtc, GETUTCDATE()) <= 180        THEN 'Cold'
        ELSE                                                                  'Dormant'
    END AS DecayBucket
FROM last_activity;
GO

/*
Bucket distribution overall:
    SELECT DecayBucket, COUNT_BIG(*) AS Contacts
    FROM ghl.vw_ActivityDecay
    GROUP BY DecayBucket
    ORDER BY CASE DecayBucket
        WHEN 'Hot' THEN 1 WHEN 'Warm' THEN 2 WHEN 'Cooling' THEN 3
        WHEN 'Cold' THEN 4 WHEN 'Dormant' THEN 5 ELSE 6 END;

Per agent — stale leads:
    SELECT AssignedToUserId, COUNT_BIG(*) AS DormantLeads
    FROM ghl.vw_ActivityDecay
    WHERE DecayBucket IN ('Cold', 'Dormant')
    GROUP BY AssignedToUserId
    ORDER BY DormantLeads DESC;
*/
