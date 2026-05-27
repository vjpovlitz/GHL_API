/*
============================================================================
vw_DailyLeadFunnel — Reporting Funnel POC

Conversion funnel by day:

    [1] Leads created           ghl.Contacts.DateAddedUtc
    [2] First contact engaged   first inbound message from contact
    [3] Appointment booked      ghl.Appointments exists for contact
    [4] Appointment showed      AppointmentStatus IN ('showed','confirmed')
    [5] Opportunity created     ghl.Opportunities exists for contact
    [6] Opportunity won         Opportunities.Status = 'won'

Each contact is counted at the EARLIEST stage they hit on a given day.
Conversion lag (lead -> X days later) is NOT included here; that's
vw_FunnelCohort (next view, after this POC validates).

Source: optional dimension. Defaults to ghl.Contacts.Source.

Assumptions:
- All dates UTC (DATETIME2(3)).
- Contact -> Opportunity join: ghl.Opportunities.ContactId.
- Contact -> Appointment join: ghl.Appointments.ContactId.
- Contact -> Inbound msg join via ghl.Conversations.ContactId then
  ghl.ConversationMessages.ConversationId.

============================================================================
*/

IF OBJECT_ID('ghl.vw_DailyLeadFunnel', 'V') IS NOT NULL
    DROP VIEW ghl.vw_DailyLeadFunnel;
GO

CREATE VIEW ghl.vw_DailyLeadFunnel AS
WITH

-- 1. Leads created per day, with source
leads AS (
    SELECT
        CAST(DateAddedUtc AS DATE) AS LeadDate,
        ISNULL(NULLIF(Source, ''), '(unknown)') AS LeadSource,
        ContactId
    FROM ghl.Contacts
    WHERE DateAddedUtc IS NOT NULL
),

-- 2. First inbound message per contact (engagement signal)
first_inbound AS (
    SELECT
        c.ContactId,
        MIN(m.DateAddedUtc) AS FirstInboundUtc
    FROM ghl.Conversations c
    JOIN ghl.ConversationMessages m
      ON m.ConversationId = c.ConversationId
    WHERE m.Direction = 'inbound'
      AND c.ContactId IS NOT NULL
    GROUP BY c.ContactId
),

-- 3+4. Appointments by contact (booked + showed)
appt_first AS (
    SELECT
        ContactId,
        MIN(DateAddedUtc) AS FirstApptBookedUtc,
        MIN(CASE
            WHEN AppointmentStatus IN ('showed','confirmed','completed')
            THEN StartTimeUtc
        END) AS FirstApptShowedUtc
    FROM ghl.Appointments
    WHERE ContactId IS NOT NULL
    GROUP BY ContactId
),

-- 5+6. Opportunities by contact (created + won)
opp_first AS (
    SELECT
        ContactId,
        MIN(DateAddedUtc) AS FirstOppUtc,
        MIN(CASE WHEN Status = 'won' THEN DateClosedUtc END) AS FirstWonUtc
    FROM ghl.Opportunities
    WHERE ContactId IS NOT NULL
    GROUP BY ContactId
)

SELECT
    L.LeadDate,
    L.LeadSource,
    COUNT_BIG(*)                                                          AS LeadsCreated,
    COUNT_BIG(FI.ContactId)                                               AS EngagedContacts,
    COUNT_BIG(AF.FirstApptBookedUtc)                                      AS ApptsBooked,
    COUNT_BIG(AF.FirstApptShowedUtc)                                      AS ApptsShowed,
    COUNT_BIG(OP.FirstOppUtc)                                             AS OppsCreated,
    COUNT_BIG(OP.FirstWonUtc)                                             AS OppsWon,
    -- Conversion percentages (cast to numeric to avoid integer division)
    CASE WHEN COUNT_BIG(*) > 0
         THEN 100.0 * COUNT_BIG(FI.ContactId) / COUNT_BIG(*)
         ELSE 0 END                                                       AS EngagedPct,
    CASE WHEN COUNT_BIG(*) > 0
         THEN 100.0 * COUNT_BIG(AF.FirstApptBookedUtc) / COUNT_BIG(*)
         ELSE 0 END                                                       AS BookedPct,
    CASE WHEN COUNT_BIG(*) > 0
         THEN 100.0 * COUNT_BIG(OP.FirstWonUtc) / COUNT_BIG(*)
         ELSE 0 END                                                       AS WonPct
FROM       leads        L
LEFT JOIN  first_inbound FI ON FI.ContactId = L.ContactId
LEFT JOIN  appt_first    AF ON AF.ContactId = L.ContactId
LEFT JOIN  opp_first     OP ON OP.ContactId = L.ContactId
GROUP BY L.LeadDate, L.LeadSource;
GO

/*
Smoke query (run after BULK INSERT lands the data):

    SELECT TOP 50 *
    FROM ghl.vw_DailyLeadFunnel
    WHERE LeadDate >= DATEADD(DAY, -90, GETUTCDATE())
    ORDER BY LeadDate DESC, LeadsCreated DESC;
*/
