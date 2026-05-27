-- GHL extraction tables (matches CSVs produced by scripts/export_to_csv.py).
-- Conventions enforced by DATA_RULES.md.
-- All NVARCHAR sizes are generous; tighten per-column once data profiles stabilize.

IF SCHEMA_ID('ghl') IS NULL EXEC('CREATE SCHEMA ghl');
GO

-- ============================================================
-- ghl.Contacts
-- ============================================================
IF OBJECT_ID('ghl.Contacts', 'U') IS NULL
CREATE TABLE ghl.Contacts (
    ContactId           VARCHAR(64)     NOT NULL  PRIMARY KEY,
    LocationId          VARCHAR(64)     NOT NULL,
    FirstName           NVARCHAR(100)   NULL,
    LastName            NVARCHAR(100)   NULL,
    FullName            NVARCHAR(200)   NULL,
    Email               NVARCHAR(254)   NULL,
    Phone               VARCHAR(20)     NULL,
    ContactType         VARCHAR(32)     NULL,
    Source              NVARCHAR(100)   NULL,
    AssignedToUserId    VARCHAR(64)     NULL,
    Address1            NVARCHAR(255)   NULL,
    City                NVARCHAR(100)   NULL,
    State               NVARCHAR(50)    NULL,
    PostalCode          VARCHAR(20)     NULL,
    Country             VARCHAR(8)      NULL,
    DateOfBirth         DATE            NULL,
    Tags                NVARCHAR(MAX)   NULL,  -- pipe-delimited
    DateAddedUtc        DATETIME2(3)    NULL,
    DateUpdatedUtc      DATETIME2(3)    NULL,
    SourceSystem        VARCHAR(32)     NOT NULL,
    SourceSystemId      VARCHAR(64)     NOT NULL,
    ExtractedAtUtc      DATETIME2(3)    NOT NULL
);
CREATE INDEX IX_Contacts_LocationId       ON ghl.Contacts(LocationId);
CREATE INDEX IX_Contacts_AssignedToUserId ON ghl.Contacts(AssignedToUserId);
CREATE INDEX IX_Contacts_DateUpdatedUtc   ON ghl.Contacts(DateUpdatedUtc);
GO

-- ============================================================
-- ghl.Conversations
-- ============================================================
IF OBJECT_ID('ghl.Conversations', 'U') IS NULL
CREATE TABLE ghl.Conversations (
    ConversationId       VARCHAR(64)    NOT NULL  PRIMARY KEY,
    LocationId           VARCHAR(64)    NOT NULL,
    ContactId            VARCHAR(64)    NULL,
    ContactName          NVARCHAR(200)  NULL,
    ContactEmail         NVARCHAR(254)  NULL,
    ContactPhone         VARCHAR(20)    NULL,
    LastMessageType      VARCHAR(64)    NULL,
    LastMessageBody      NVARCHAR(MAX)  NULL,
    LastMessageDateUtc   DATETIME2(3)   NULL,
    LastMessageDirection VARCHAR(16)    NULL,
    IsUnread             BIT            NULL,
    IsStarred            BIT            NULL,
    UnreadCount          INT            NULL,
    ConversationType     VARCHAR(32)    NULL,
    DateAddedUtc         DATETIME2(3)   NULL,
    DateUpdatedUtc       DATETIME2(3)   NULL,
    SourceSystem         VARCHAR(32)    NOT NULL,
    SourceSystemId       VARCHAR(64)    NOT NULL,
    ExtractedAtUtc       DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_Conversations_ContactId         ON ghl.Conversations(ContactId);
CREATE INDEX IX_Conversations_LocationId        ON ghl.Conversations(LocationId);
CREATE INDEX IX_Conversations_LastMessageDateUtc ON ghl.Conversations(LastMessageDateUtc);
GO

-- ============================================================
-- ghl.ConversationMessages
-- ============================================================
IF OBJECT_ID('ghl.ConversationMessages', 'U') IS NULL
CREATE TABLE ghl.ConversationMessages (
    MessageId         VARCHAR(64)    NOT NULL  PRIMARY KEY,
    ConversationId    VARCHAR(64)    NOT NULL,
    ContactId         VARCHAR(64)    NULL,
    LocationId        VARCHAR(64)    NOT NULL,
    Direction         VARCHAR(16)    NULL,
    MessageType       VARCHAR(64)    NULL,
    Status            VARCHAR(32)    NULL,
    Body              NVARCHAR(MAX)  NULL,
    HasAttachment     BIT            NULL,
    DateAddedUtc      DATETIME2(3)   NULL,
    SourceSystem      VARCHAR(32)    NOT NULL,
    SourceSystemId    VARCHAR(64)    NOT NULL,
    ExtractedAtUtc    DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_Messages_ConversationId ON ghl.ConversationMessages(ConversationId);
CREATE INDEX IX_Messages_ContactId      ON ghl.ConversationMessages(ContactId);
CREATE INDEX IX_Messages_DateAddedUtc   ON ghl.ConversationMessages(DateAddedUtc);
GO

-- ============================================================
-- ghl.Users  (dim — agents/team members)
-- ============================================================
IF OBJECT_ID('ghl.Users', 'U') IS NULL
CREATE TABLE ghl.Users (
    UserId            VARCHAR(64)    NOT NULL  PRIMARY KEY,
    LocationId        VARCHAR(64)    NULL,
    FirstName         NVARCHAR(100)  NULL,
    LastName          NVARCHAR(100)  NULL,
    FullName          NVARCHAR(200)  NULL,
    Email             NVARCHAR(254)  NULL,
    Phone             VARCHAR(20)    NULL,
    Role              VARCHAR(50)    NULL,
    RoleType          VARCHAR(50)    NULL,
    IsActive          BIT            NULL,
    DateAddedUtc      DATETIME2(3)   NULL,
    SourceSystem      VARCHAR(32)    NOT NULL,
    SourceSystemId    VARCHAR(64)    NOT NULL,
    ExtractedAtUtc    DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_Users_LocationId ON ghl.Users(LocationId);
GO

-- ============================================================
-- ghl.Pipelines  (dim) + ghl.PipelineStages (dim)
-- ============================================================
IF OBJECT_ID('ghl.Pipelines', 'U') IS NULL
CREATE TABLE ghl.Pipelines (
    PipelineId        VARCHAR(64)    NOT NULL  PRIMARY KEY,
    LocationId        VARCHAR(64)    NOT NULL,
    Name              NVARCHAR(200)  NULL,
    DateAddedUtc      DATETIME2(3)   NULL,
    DateUpdatedUtc    DATETIME2(3)   NULL,
    SourceSystem      VARCHAR(32)    NOT NULL,
    SourceSystemId    VARCHAR(64)    NOT NULL,
    ExtractedAtUtc    DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_Pipelines_LocationId ON ghl.Pipelines(LocationId);
GO

IF OBJECT_ID('ghl.PipelineStages', 'U') IS NULL
CREATE TABLE ghl.PipelineStages (
    PipelineStageId   VARCHAR(64)    NOT NULL  PRIMARY KEY,
    PipelineId        VARCHAR(64)    NOT NULL,
    LocationId        VARCHAR(64)    NULL,
    Name              NVARCHAR(200)  NULL,
    Position          INT            NULL,
    ShowInFunnel      BIT            NULL,
    ShowInPieChart    BIT            NULL,
    SourceSystem      VARCHAR(32)    NOT NULL,
    SourceSystemId    VARCHAR(64)    NOT NULL,
    ExtractedAtUtc    DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_PipelineStages_PipelineId ON ghl.PipelineStages(PipelineId);
GO

-- ============================================================
-- ghl.Opportunities  (fact — lead/deal pipeline)
-- ============================================================
IF OBJECT_ID('ghl.Opportunities', 'U') IS NULL
CREATE TABLE ghl.Opportunities (
    OpportunityId           VARCHAR(64)    NOT NULL  PRIMARY KEY,
    LocationId              VARCHAR(64)    NOT NULL,
    PipelineId              VARCHAR(64)    NULL,
    PipelineStageId         VARCHAR(64)    NULL,
    ContactId               VARCHAR(64)    NULL,
    AssignedToUserId        VARCHAR(64)    NULL,
    Name                    NVARCHAR(255)  NULL,
    Status                  VARCHAR(32)    NULL,   -- open|won|lost|abandoned
    MonetaryValue           DECIMAL(18, 2) NULL,
    Source                  NVARCHAR(100)  NULL,
    LostReasonId            VARCHAR(64)    NULL,
    DateAddedUtc            DATETIME2(3)   NULL,
    DateUpdatedUtc          DATETIME2(3)   NULL,
    DateLastStageChangeUtc  DATETIME2(3)   NULL,
    DateClosedUtc           DATETIME2(3)   NULL,
    SourceSystem            VARCHAR(32)    NOT NULL,
    SourceSystemId          VARCHAR(64)    NOT NULL,
    ExtractedAtUtc          DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_Opportunities_PipelineId        ON ghl.Opportunities(PipelineId);
CREATE INDEX IX_Opportunities_PipelineStageId   ON ghl.Opportunities(PipelineStageId);
CREATE INDEX IX_Opportunities_ContactId         ON ghl.Opportunities(ContactId);
CREATE INDEX IX_Opportunities_AssignedToUserId  ON ghl.Opportunities(AssignedToUserId);
CREATE INDEX IX_Opportunities_Status            ON ghl.Opportunities(Status);
CREATE INDEX IX_Opportunities_DateAddedUtc      ON ghl.Opportunities(DateAddedUtc);
GO

-- ============================================================
-- ghl.Appointments  (fact — calendar bookings)
-- ============================================================
IF OBJECT_ID('ghl.Appointments', 'U') IS NULL
CREATE TABLE ghl.Appointments (
    AppointmentId          VARCHAR(64)    NOT NULL  PRIMARY KEY,
    LocationId             VARCHAR(64)    NOT NULL,
    CalendarId             VARCHAR(64)    NULL,
    ContactId              VARCHAR(64)    NULL,
    AssignedToUserId       VARCHAR(64)    NULL,
    Title                  NVARCHAR(255)  NULL,
    AppointmentStatus      VARCHAR(32)    NULL,    -- new|confirmed|cancelled|showed|noshow
    Source                 NVARCHAR(100)  NULL,
    StartTimeUtc           DATETIME2(3)   NULL,
    EndTimeUtc             DATETIME2(3)   NULL,
    DateAddedUtc           DATETIME2(3)   NULL,
    DateUpdatedUtc         DATETIME2(3)   NULL,
    SourceSystem           VARCHAR(32)    NOT NULL,
    SourceSystemId         VARCHAR(64)    NOT NULL,
    ExtractedAtUtc         DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_Appointments_ContactId         ON ghl.Appointments(ContactId);
CREATE INDEX IX_Appointments_AssignedToUserId  ON ghl.Appointments(AssignedToUserId);
CREATE INDEX IX_Appointments_StartTimeUtc      ON ghl.Appointments(StartTimeUtc);
CREATE INDEX IX_Appointments_AppointmentStatus ON ghl.Appointments(AppointmentStatus);
GO

-- ============================================================
-- ghl.ContactTags  (fact — exploded Contact.Tags for fast tag joins)
-- Populated by: scripts/build_contact_tags.sql (or post-load step)
-- ============================================================
IF OBJECT_ID('ghl.ContactTags', 'U') IS NULL
CREATE TABLE ghl.ContactTags (
    ContactId  VARCHAR(64)    NOT NULL,
    TagSlug    VARCHAR(128)   NOT NULL,
    CONSTRAINT PK_ContactTags PRIMARY KEY (ContactId, TagSlug)
);
CREATE INDEX IX_ContactTags_TagSlug ON ghl.ContactTags(TagSlug);
GO

-- ============================================================
-- ghl.CustomFields  (dim — custom field DEFINITIONS for contacts/opps)
-- ============================================================
IF OBJECT_ID('ghl.CustomFields', 'U') IS NULL
CREATE TABLE ghl.CustomFields (
    CustomFieldId     VARCHAR(64)    NOT NULL  PRIMARY KEY,
    LocationId        VARCHAR(64)    NOT NULL,
    Model             VARCHAR(32)    NULL,                     -- contact|opportunity
    FieldKey          VARCHAR(128)   NULL,                     -- e.g. "contact.exact_age"
    Name              NVARCHAR(255)  NULL,                     -- display name
    DataType          VARCHAR(32)    NULL,                     -- TEXT|NUMERICAL|MONETORY|...
    Placeholder       NVARCHAR(255)  NULL,
    Position          INT            NULL,
    IsRequired        BIT            NULL,
    DateAddedUtc      DATETIME2(3)   NULL,
    SourceSystem      VARCHAR(32)    NOT NULL,
    SourceSystemId    VARCHAR(64)    NOT NULL,
    ExtractedAtUtc    DATETIME2(3)   NOT NULL
);
CREATE INDEX IX_CustomFields_Model ON ghl.CustomFields(Model);
GO

-- ============================================================
-- ghl.Tags  (dim — derived from Contacts.Tags pipe-delimited column)
-- ============================================================
IF OBJECT_ID('ghl.Tags', 'U') IS NULL
CREATE TABLE ghl.Tags (
    TagId             VARCHAR(128)   NOT NULL  PRIMARY KEY,    -- slug
    TagName           NVARCHAR(255)  NULL,                     -- display
    ContactsCount     INT            NULL,
    FirstSeenAtUtc    DATETIME2(3)   NULL,
    LastSeenAtUtc     DATETIME2(3)   NULL,
    SourceSystem      VARCHAR(32)    NOT NULL,
    SourceSystemId    VARCHAR(128)   NOT NULL,
    ExtractedAtUtc    DATETIME2(3)   NOT NULL
);
GO

-- ============================================================
-- Loading the CSVs (BULK INSERT example)
-- ============================================================
-- Run from a SQL Server instance that can read the CSV path.
-- Adjust the file paths for your environment.
/*
BULK INSERT ghl.Contacts
FROM 'C:\path\to\Contacts.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0d0a',
    CODEPAGE = '65001',  -- UTF-8
    TABLOCK
);
*/
