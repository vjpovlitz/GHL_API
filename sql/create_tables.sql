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
