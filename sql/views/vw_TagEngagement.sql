/*
============================================================================
vw_TagEngagement — engagement & conversion by Tag

NOTE: Tags in ghl.Contacts are stored pipe-delimited in the Tags column.
This view explodes them via STRING_SPLIT and joins to engagement signals.

Useful for answering:
    - Which tag is most predictive of a reply?
    - Which tag has the highest win rate?
    - What's the volume vs. quality tradeoff per tag?

Requires SQL Server 2016+ (STRING_SPLIT).

============================================================================
*/

IF OBJECT_ID('ghl.vw_TagEngagement', 'V') IS NOT NULL
    DROP VIEW ghl.vw_TagEngagement;
GO

CREATE VIEW ghl.vw_TagEngagement AS
WITH

-- Uses materialized ghl.ContactTags (1.6M rows). If that table is missing,
-- fall back to: SELECT C.ContactId, LTRIM(RTRIM(LOWER(s.value))) AS TagSlug
-- FROM ghl.Contacts C CROSS APPLY STRING_SPLIT(ISNULL(C.Tags,''),'|') s ...
contact_tags AS (
    SELECT ContactId, TagSlug FROM ghl.ContactTags
),

engaged_contacts AS (
    SELECT DISTINCT C.ContactId
    FROM ghl.Conversations         C
    JOIN ghl.ConversationMessages  M ON M.ConversationId = C.ConversationId
    WHERE M.Direction = 'inbound' AND C.ContactId IS NOT NULL
),

opp_by_contact AS (
    SELECT
        ContactId,
        SUM(CASE WHEN Status = 'won' THEN 1 ELSE 0 END) AS WonCount,
        SUM(CASE WHEN Status = 'won' THEN ISNULL(MonetaryValue, 0) ELSE 0 END) AS WonValue,
        COUNT_BIG(*) AS OppsCount
    FROM ghl.Opportunities WHERE ContactId IS NOT NULL
    GROUP BY ContactId
)

SELECT
    CT.TagSlug,
    COUNT_BIG(DISTINCT CT.ContactId) AS Contacts,
    SUM(CASE WHEN E.ContactId IS NOT NULL THEN 1 ELSE 0 END) AS EngagedContacts,
    SUM(CASE WHEN O.OppsCount > 0 THEN 1 ELSE 0 END) AS OppsContacts,
    SUM(ISNULL(O.WonCount, 0)) AS WonOpps,
    SUM(ISNULL(O.WonValue, 0)) AS WonValue,

    CASE WHEN COUNT_BIG(DISTINCT CT.ContactId) > 0
         THEN 100.0 * SUM(CASE WHEN E.ContactId IS NOT NULL THEN 1 ELSE 0 END)
                    / COUNT_BIG(DISTINCT CT.ContactId)
         ELSE 0 END AS EngagedPct,

    CASE WHEN COUNT_BIG(DISTINCT CT.ContactId) > 0
         THEN 100.0 * SUM(ISNULL(O.WonCount, 0))
                    / COUNT_BIG(DISTINCT CT.ContactId)
         ELSE 0 END AS WinPct
FROM       contact_tags    CT
LEFT JOIN  engaged_contacts E  ON E.ContactId = CT.ContactId
LEFT JOIN  opp_by_contact   O  ON O.ContactId = CT.ContactId
GROUP BY CT.TagSlug;
GO

/*
Top performing tags by engagement (min 100 contacts):
    SELECT TOP 30 TagSlug, Contacts, EngagedPct, WinPct, WonValue
    FROM ghl.vw_TagEngagement
    WHERE Contacts >= 100
    ORDER BY EngagedPct DESC;
*/
