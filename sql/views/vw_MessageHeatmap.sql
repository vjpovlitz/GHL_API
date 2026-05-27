/*
============================================================================
vw_MessageHeatmap — hour-of-day × day-of-week message counts

For each (Direction, DayOfWeek, HourOfDay) bucket:
    - MsgCount
    - DistinctConvs
    - DistinctContacts

Use as a heatmap source for the dashboard "best time to send" tile.

Day-of-week: 1=Sunday ... 7=Saturday (SQL Server DATEPART default).
Hour-of-day: 0..23 in UTC. Convert to local TZ in the BI tool.

============================================================================
*/

IF OBJECT_ID('ghl.vw_MessageHeatmap', 'V') IS NOT NULL
    DROP VIEW ghl.vw_MessageHeatmap;
GO

CREATE VIEW ghl.vw_MessageHeatmap AS
SELECT
    Direction,
    DATEPART(WEEKDAY, DateAddedUtc) AS DayOfWeek,    -- 1=Sun..7=Sat (default)
    DATEPART(HOUR, DateAddedUtc)    AS HourOfDay,    -- 0..23
    MessageType,
    COUNT_BIG(*) AS MsgCount,
    COUNT(DISTINCT ConversationId) AS DistinctConvs,
    COUNT(DISTINCT ContactId)      AS DistinctContacts
FROM ghl.ConversationMessages
WHERE DateAddedUtc IS NOT NULL
  AND Direction IS NOT NULL
GROUP BY
    Direction,
    DATEPART(WEEKDAY, DateAddedUtc),
    DATEPART(HOUR, DateAddedUtc),
    MessageType;
GO

/*
Outbound SMS heat (filter MessageType in your viz):

    SELECT DayOfWeek, HourOfDay, MsgCount
    FROM ghl.vw_MessageHeatmap
    WHERE Direction = 'outbound' AND MessageType = 'TYPE_SMS'
    ORDER BY DayOfWeek, HourOfDay;
*/
