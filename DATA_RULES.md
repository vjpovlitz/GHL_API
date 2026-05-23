# Data extraction rules

Rules for turning GHL API responses into SQL-Server-shaped CSVs.
Every extraction script must follow these — no exceptions.

## 1. Naming

- **Columns**: `PascalCase`. No spaces, no special chars. SQL Server convention.
- **Primary keys**: `<Entity>Id` (e.g. `ContactId`, `ConversationId`).
- **Foreign keys**: same name as the PK in the referenced table.
- **Booleans**: prefix `Is`/`Has` (e.g. `IsUnread`, `HasAttachment`).
- **Timestamps**: suffix `Utc` if stored in UTC (e.g. `DateAddedUtc`).

## 2. Types & format

| Logical type | CSV value             | SQL Server type      |
| ------------ | --------------------- | -------------------- |
| String       | UTF-8, quoted         | `NVARCHAR(n)`        |
| Identifier   | source-system string  | `VARCHAR(64)`        |
| Integer      | digits, no commas     | `INT` / `BIGINT`     |
| Boolean      | `1` / `0`             | `BIT`                |
| Timestamp    | ISO 8601 UTC `Z`      | `DATETIME2(3)`       |
| Date         | `YYYY-MM-DD`          | `DATE`               |
| Phone        | E.164 (`+1...`)       | `VARCHAR(20)`        |
| Multi-value  | `\|`-delimited string | `NVARCHAR(MAX)`      |
| JSON blob    | stringified, quoted   | `NVARCHAR(MAX)`      |

## 3. Nulls

- Missing values → empty string `""`, **never** the literal `"null"`, `"None"`, or `"NaN"`.
- Empty arrays → empty string, not `[]`.

## 4. Required audit columns (every table)

- `SourceSystem` — constant string (`"GoHighLevel"`).
- `SourceSystemId` — the row's natural ID in the source.
- `ExtractedAtUtc` — ISO 8601 timestamp of the extraction run.

## 5. CSV file format

- Encoding: **UTF-8 with BOM** (so SQL Server `BULK INSERT` and Excel both work).
- Line endings: `CRLF` (`\r\n`).
- Delimiter: comma.
- Quoting: `QUOTE_MINIMAL` — quote any value containing `,`, `"`, `\r`, or `\n`.
- Header row required.
- One file per logical table. Filename = `<TableName>.csv`.

## 6. Relationships

- Always emit the FK column even if the parent table isn't in this batch.
- Never invent surrogate keys at extract time. Use the source system's IDs.
- Junction tables (many-to-many) get their own CSV: `<Parent><Child>.csv`.

## 7. PII & security

- Exports go to `data/exports/` which is `.gitignore`d.
- Never log raw email/phone in console output — mask after the 4th char.
- Never commit a CSV that contains real customer data.

## 8. Idempotency

- Re-running an extraction overwrites the prior CSV.
- The natural key (`<Entity>Id`) is the upsert key in the warehouse.
