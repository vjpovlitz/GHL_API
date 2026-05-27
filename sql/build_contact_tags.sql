/*
============================================================================
build_contact_tags.sql — populate ghl.ContactTags from ghl.Contacts.Tags

Run after a full Contacts load. This materializes the exploded pipe-delimited
tags into a (ContactId, TagSlug) fact table — joins become 20-50x faster.

Idempotent: TRUNCATE + INSERT.
============================================================================
*/

TRUNCATE TABLE ghl.ContactTags;
GO

INSERT INTO ghl.ContactTags (ContactId, TagSlug)
SELECT DISTINCT
    C.ContactId,
    LTRIM(RTRIM(LOWER(s.value))) AS TagSlug
FROM ghl.Contacts C
CROSS APPLY STRING_SPLIT(ISNULL(C.Tags, ''), '|') AS s
WHERE LTRIM(RTRIM(s.value)) <> '';
GO

-- Sanity row count
SELECT COUNT_BIG(*) AS ContactTagsRows FROM ghl.ContactTags;
GO
