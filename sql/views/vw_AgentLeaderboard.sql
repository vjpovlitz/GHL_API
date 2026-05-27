/*
============================================================================
vw_AgentLeaderboard — Per-agent activity rollup

Metrics:
    LeadsAssigned        contacts where AssignedToUserId = User
    MsgsOutbound         ConversationMessages joined via conv.ContactId
    MsgsInbound          (replies received on convs they own)
    ReplyRate            inbound / outbound
    ApptsBooked          appointments where AssignedToUserId = User
    OppsWon              opportunities won assigned to User
    PipelineValueOpen    sum of monetaryValue for open opps assigned to User
    PipelineValueWon     sum of monetaryValue for won opps assigned to User

Window: parameterize via WHERE clause when querying.
Optionally LEFT JOIN ghl.Users U to get FullName/Email.

============================================================================
*/

IF OBJECT_ID('ghl.vw_AgentLeaderboard', 'V') IS NOT NULL
    DROP VIEW ghl.vw_AgentLeaderboard;
GO

CREATE VIEW ghl.vw_AgentLeaderboard AS
WITH

agent_contacts AS (
    SELECT
        AssignedToUserId AS UserId,
        COUNT_BIG(*) AS LeadsAssigned,
        SUM(CASE WHEN DateAddedUtc >= DATEADD(DAY, -7,  GETUTCDATE()) THEN 1 ELSE 0 END) AS LeadsLast7,
        SUM(CASE WHEN DateAddedUtc >= DATEADD(DAY, -30, GETUTCDATE()) THEN 1 ELSE 0 END) AS LeadsLast30
    FROM ghl.Contacts
    WHERE AssignedToUserId IS NOT NULL AND AssignedToUserId <> ''
    GROUP BY AssignedToUserId
),

-- Resolve agent for a message via the conversation's contact's AssignedToUserId
agent_msgs AS (
    SELECT
        C.AssignedToUserId AS UserId,
        SUM(CASE WHEN M.Direction = 'outbound' THEN 1 ELSE 0 END) AS MsgsOutbound,
        SUM(CASE WHEN M.Direction = 'inbound'  THEN 1 ELSE 0 END) AS MsgsInbound,
        SUM(CASE WHEN M.Direction = 'outbound'
                 AND M.DateAddedUtc >= DATEADD(DAY, -7, GETUTCDATE())
                 THEN 1 ELSE 0 END) AS MsgsOutLast7
    FROM ghl.Contacts C
    JOIN ghl.Conversations         CV ON CV.ContactId = C.ContactId
    JOIN ghl.ConversationMessages  M  ON M.ConversationId = CV.ConversationId
    WHERE C.AssignedToUserId IS NOT NULL AND C.AssignedToUserId <> ''
    GROUP BY C.AssignedToUserId
),

agent_appts AS (
    SELECT
        AssignedToUserId AS UserId,
        COUNT_BIG(*) AS ApptsBooked,
        SUM(CASE WHEN AppointmentStatus IN ('showed','confirmed','completed') THEN 1 ELSE 0 END) AS ApptsShowed
    FROM ghl.Appointments
    WHERE AssignedToUserId IS NOT NULL AND AssignedToUserId <> ''
    GROUP BY AssignedToUserId
),

agent_opps AS (
    SELECT
        AssignedToUserId AS UserId,
        COUNT_BIG(*) AS OppsTotal,
        SUM(CASE WHEN Status = 'won'  THEN 1 ELSE 0 END) AS OppsWon,
        SUM(CASE WHEN Status = 'lost' THEN 1 ELSE 0 END) AS OppsLost,
        SUM(CASE WHEN Status NOT IN ('won','lost','abandoned') OR Status IS NULL
                 THEN ISNULL(MonetaryValue, 0) ELSE 0 END) AS PipelineValueOpen,
        SUM(CASE WHEN Status = 'won' THEN ISNULL(MonetaryValue, 0) ELSE 0 END) AS PipelineValueWon
    FROM ghl.Opportunities
    WHERE AssignedToUserId IS NOT NULL AND AssignedToUserId <> ''
    GROUP BY AssignedToUserId
)

SELECT
    ISNULL(AC.UserId, ISNULL(AM.UserId, ISNULL(AA.UserId, AO.UserId))) AS UserId,
    ISNULL(AC.LeadsAssigned, 0)        AS LeadsAssigned,
    ISNULL(AC.LeadsLast7, 0)           AS LeadsLast7,
    ISNULL(AC.LeadsLast30, 0)          AS LeadsLast30,
    ISNULL(AM.MsgsOutbound, 0)         AS MsgsOutbound,
    ISNULL(AM.MsgsInbound, 0)          AS MsgsInbound,
    ISNULL(AM.MsgsOutLast7, 0)         AS MsgsOutLast7,
    CASE WHEN ISNULL(AM.MsgsOutbound, 0) > 0
         THEN 100.0 * AM.MsgsInbound / AM.MsgsOutbound ELSE 0 END AS ReplyRatePct,
    ISNULL(AA.ApptsBooked, 0)          AS ApptsBooked,
    ISNULL(AA.ApptsShowed, 0)          AS ApptsShowed,
    ISNULL(AO.OppsTotal, 0)            AS OppsTotal,
    ISNULL(AO.OppsWon, 0)              AS OppsWon,
    ISNULL(AO.OppsLost, 0)             AS OppsLost,
    ISNULL(AO.PipelineValueOpen, 0)    AS PipelineValueOpen,
    ISNULL(AO.PipelineValueWon, 0)     AS PipelineValueWon
FROM       agent_contacts AC
FULL JOIN  agent_msgs     AM ON AM.UserId = AC.UserId
FULL JOIN  agent_appts    AA ON AA.UserId = ISNULL(AC.UserId, AM.UserId)
FULL JOIN  agent_opps     AO ON AO.UserId = ISNULL(AC.UserId, ISNULL(AM.UserId, AA.UserId));
GO

/*
Example: top-10 by leads-last-30:

    SELECT TOP 10
        U.FullName, LB.LeadsLast30, LB.MsgsOutLast7,
        LB.ReplyRatePct, LB.ApptsShowed, LB.OppsWon, LB.PipelineValueWon
    FROM ghl.vw_AgentLeaderboard LB
    LEFT JOIN ghl.Users U ON U.UserId = LB.UserId
    ORDER BY LB.LeadsLast30 DESC;
*/
