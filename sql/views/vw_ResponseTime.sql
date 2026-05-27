/*
============================================================================
vw_ResponseTime — Per-conversation first-response latency

For each conversation, computes:
    - FirstInboundUtc       earliest inbound message
    - FirstOutboundAfterUtc  earliest outbound AFTER the first inbound
    - ResponseSeconds        delta in seconds
    - ResponseBucket         categorical:  <1min  /  <5min  /  <1hr  /  <1day  /  >=1day  /  no_reply

Aggregations downstream:
    - median by agent
    - median by conversation type (SMS vs Email)
    - distribution by day-of-week / hour-of-day

============================================================================
*/

IF OBJECT_ID('ghl.vw_ResponseTime', 'V') IS NOT NULL
    DROP VIEW ghl.vw_ResponseTime;
GO

CREATE VIEW ghl.vw_ResponseTime AS
WITH
first_inbound AS (
    SELECT
        ConversationId,
        MIN(DateAddedUtc) AS FirstInboundUtc
    FROM ghl.ConversationMessages
    WHERE Direction = 'inbound'
    GROUP BY ConversationId
),
first_outbound_after AS (
    SELECT
        M.ConversationId,
        MIN(M.DateAddedUtc) AS FirstOutboundAfterUtc
    FROM       ghl.ConversationMessages M
    INNER JOIN first_inbound             FI ON FI.ConversationId = M.ConversationId
    WHERE M.Direction = 'outbound'
      AND M.DateAddedUtc > FI.FirstInboundUtc
    GROUP BY M.ConversationId
)
SELECT
    C.ConversationId,
    C.LocationId,
    C.ContactId,
    C.ConversationType,
    FI.FirstInboundUtc,
    FO.FirstOutboundAfterUtc,
    CASE WHEN FO.FirstOutboundAfterUtc IS NULL THEN NULL
         ELSE DATEDIFF(SECOND, FI.FirstInboundUtc, FO.FirstOutboundAfterUtc)
    END AS ResponseSeconds,
    CASE
        WHEN FO.FirstOutboundAfterUtc IS NULL THEN 'no_reply'
        WHEN DATEDIFF(SECOND, FI.FirstInboundUtc, FO.FirstOutboundAfterUtc) <    60 THEN '<1min'
        WHEN DATEDIFF(SECOND, FI.FirstInboundUtc, FO.FirstOutboundAfterUtc) <   300 THEN '<5min'
        WHEN DATEDIFF(SECOND, FI.FirstInboundUtc, FO.FirstOutboundAfterUtc) <  3600 THEN '<1hr'
        WHEN DATEDIFF(SECOND, FI.FirstInboundUtc, FO.FirstOutboundAfterUtc) < 86400 THEN '<1day'
        ELSE '>=1day'
    END AS ResponseBucket
FROM       ghl.Conversations     C
LEFT JOIN  first_inbound         FI ON FI.ConversationId = C.ConversationId
LEFT JOIN  first_outbound_after  FO ON FO.ConversationId = C.ConversationId
WHERE FI.FirstInboundUtc IS NOT NULL;  -- only conversations with at least one inbound
GO

/*
Example: response-bucket distribution last 30 days
    SELECT ResponseBucket, COUNT(*) AS Convs
    FROM ghl.vw_ResponseTime
    WHERE FirstInboundUtc >= DATEADD(DAY, -30, GETUTCDATE())
    GROUP BY ResponseBucket
    ORDER BY Convs DESC;
*/
