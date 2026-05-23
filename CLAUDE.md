# CLAUDE.md — GHL_API handoff

Project handoff for a fresh Claude Code session. Read this top-to-bottom before
making any changes. Everything in here was learned the hard way.

---

## 1. What this project is

Python client + ETL for the **GoHighLevel (LeadConnector) v2 API**, extracting
CRM data into **SQL-Server-shaped CSVs** for a downstream warehouse load.

- **Repo:** https://github.com/vjpovlitz/GHL_API
- **Owner:** vjpovlitz (Vinson Povlitz)
- **Sub-account:** Dana Capital Realty (whitelabel: `app.reireply.com`)
- **Location ID:** `hoqjFDVlAeYXKPG5xAOX`
- **Auth:** Private Integration Token (PIT). Prefix `pit-…`. Scoped to one location.
- **Working dir:** `/Users/smokestack/Projects/DCR/GHL_API`
- **Today's context window:** 2026-05-23 (Saturday). "The weekend" = today + tomorrow.

### Why CSVs and not direct DB writes?
Customer wants the data in SQL Server. CSVs let us decouple extract from load,
keep the extract idempotent, and use `BULK INSERT` for the load. We may add a
direct `pyodbc` path later; CSV-first is on purpose.

---

## 2. Current state (commit `e8f35d2`)

What's done and working:

| Component | Status |
|---|---|
| GHL v2 client with PIT auth | ✅ working |
| Resources: contacts, conversations, calendars | ✅ list/get/search/create/update/messages/free-slots/events |
| POC CSV extraction (100 contacts, 50 convos, ~200 msgs) | ✅ 0 audit issues |
| Sanitization layer (`src/ghl_api/sanitize.py`) | ✅ 23 unit tests pass |
| Audit script (`scripts/audit_csv.py`) | ✅ detects SQL-Server-hostile content |
| Self-validating extract (audit gate) | ✅ extract exits non-zero on bad data |
| SQL Server DDL (`sql/create_tables.sql`) | ✅ matches CSV shape exactly |
| Data rules doc (`DATA_RULES.md`) | ✅ enforced by code |
| Mappers extracted to `src/ghl_api/mappers.py` | ✅ shared between POC and batch |

What's NOT done (next milestone — see §8):
- `BatchExtractor` framework (sharded output + checkpoint + resume)
- Adaptive throttle on `x-ratelimit-remaining`
- 429 retry with `Retry-After`
- Manifest writer (per-file row count, sha256, schema fingerprint)
- Concurrent fan-out for messages
- `scripts/run_batch.py` orchestrator CLI

---

## 3. Critical files cheat sheet

```
GHL_API/
├── CLAUDE.md                          ← this file
├── DATA_RULES.md                      ← canonical data rules; code enforces these
├── README.md                          ← user-facing setup
├── .env                               ← LIVE credentials, gitignored
├── .env.example                       ← template, committed
├── pyproject.toml                     ← deps: httpx, pydantic, dotenv, pytest
│
├── src/ghl_api/
│   ├── client.py                      ← GHLClient.from_env(), retry-NOT-YET, basic error handling
│   ├── auth.py                        ← OAuthCredentials / APIKeyCredentials dataclasses
│   ├── exceptions.py                  ← GHLAPIError / GHLAuthError / GHLRateLimitError
│   ├── sanitize.py                    ← clean_text / clean_id / clean_phone / clean_utc_ts / …
│   ├── mappers.py                     ← *_COLUMNS lists + map_contact / map_conversation / map_message
│   └── resources/                     ← contacts.py, conversations.py, calendars.py, _base.py
│
├── scripts/
│   ├── smoke_test.py                  ← raw curl-like check that token works
│   ├── test_resources.py              ← exercises each resource read-only
│   ├── export_to_csv.py               ← POC: 100/50/~200 to data/exports/, then audits
│   ├── audit_csv.py                   ← SQL-Server-safety audit; exit=1 on failure
│   ├── preview_csv.py                 ← PII-masked CSV inspector
│   └── probe_rate_limit.py            ← empirical rate-limit probe (used once)
│
├── sql/create_tables.sql              ← ghl.Contacts, ghl.Conversations, ghl.ConversationMessages
├── tests/
│   ├── test_client.py                 ← 2 tests
│   └── test_sanitize.py               ← 23 tests
│
└── data/exports/                      ← OUTPUT, gitignored — CSVs land here
```

### How to run

```bash
# venv already exists at .venv/
source .venv/bin/activate   # optional; can call .venv/bin/python directly

# Run the POC extract + audit gate (read-only, safe to re-run)
.venv/bin/python scripts/export_to_csv.py

# Just audit existing CSVs without re-pulling
.venv/bin/python scripts/audit_csv.py

# Tests
.venv/bin/python -m pytest tests/ -v
```

---

## 4. Data rules (canonical: `DATA_RULES.md`)

Short version — read the full doc for details:

1. **Naming:** `PascalCase`. PKs are `<Entity>Id`. FKs use the same name.
2. **Types:** ISO 8601 UTC for timestamps, `1`/`0` for `BIT`, pipe-delimited for arrays.
3. **Nulls:** empty string `""`. Never `"null"`, `"None"`, `"NaN"`.
4. **Audit columns on every row:** `SourceSystem`, `SourceSystemId`, `ExtractedAtUtc`.
5. **CSV format:** UTF-8 **with BOM**, **CRLF**, `csv.QUOTE_MINIMAL`, header row, one file per table.
6. **Sanitization (Rule 2a):** every field through `ghl_api.sanitize.*`. Newlines/tabs → space. Strip C0 controls. NFC normalize. Trim. Truncate to `max_len`.
7. **PII:** `data/exports/` is gitignored. Never commit a CSV. Mask in console.
8. **Idempotency:** re-running overwrites. Natural key is the upsert key.

---

## 5. API knowledge — gotchas we learned

### Rate limits (from `x-ratelimit-*` response headers, not docs)

| Header | Value |
|---|---|
| `x-ratelimit-max` | **100 / 10 sec** burst |
| `x-ratelimit-interval-milliseconds` | `10000` |
| `x-ratelimit-limit-daily` | **200,000 / day** |
| `x-ratelimit-remaining` | per-window remaining |
| `x-ratelimit-daily-remaining` | per-day remaining |

Implication: **API is the bottleneck, not CPU**. 40-core M4 buys nothing.
Target sustained ~5-8 RPS to leave headroom.

### PIT scope quirks (Private Integration Token)

PIT is scoped to one **location**. Endpoints that expect OAuth-app scope **will**
return 401/403 — this is expected, NOT a bug:

- `GET /oauth/installedLocations` → 401
- `GET /locations/search` → 403

PIT does work on: `/locations/{id}`, `/contacts/*`, `/conversations/*`,
`/calendars/*`. Test before assuming a new endpoint works.

### Endpoint quirks

- **`/conversations/search`** returns timestamps as **epoch milliseconds**
  (`1779500080557`), NOT ISO. The Contacts and Messages endpoints return ISO.
  `clean_utc_ts` handles both — don't add a new converter.
- **`/calendars/events`** requires at least one of `userId`, `calendarId`, or
  `groupId`. Calling it bare → 422.
- **`/contacts/search`** (POST) supports `searchAfter` cursor and `pageLimit`
  up to 500. Use this for backfills, not the GET `/contacts/`.
- **`/contacts/`** (GET) caps at limit ≤ 100 and uses `startAfter`/`startAfterId`.
  Slower for backfills.

### Volumes (as of 2026-05-23)

| Entity | Total |
|---|---:|
| Contacts | 252,285 |
| Conversations | 213,347 |
| Messages | (one API call per conversation to fetch — see §7) |

---

## 6. Failures we hit (and the fixes)

### 6.1 Embedded newlines in CSV → SQL Server `BULK INSERT` won't parse
**Symptom:** POC `Conversations.csv` had only 42 readable rows when we wrote 50.
8 rows silently lost. `LastMessageBody` contained literal `\r\n` from SMS replies
that got quoted by `csv.QUOTE_MINIMAL` — RFC-compliant, but BULK-INSERT-hostile.

**Fix:** `clean_text()` in `sanitize.py` replaces all `\r`, `\n`, `\t` with single
space before write. Audit gate (`scripts/audit_csv.py`) catches regressions by
comparing **physical lines** vs **logical CSV rows** — they must match.

**Regression test:** `tests/test_sanitize.py::test_clean_text_handles_mixed_corruption`.

### 6.2 Audit script's own parser was wrong (false positive in initial run)
**Symptom:** First audit reported "1 row with 20 cols" — looked like real corruption.

**Cause:** I used `text.splitlines()` then passed to `csv.reader`, which doesn't
respect quoted multi-line fields. Reader saw a "broken" file.

**Fix:** Open with `path.open("r", encoding="utf-8-sig", newline="")` and let
`csv.reader` parse the file directly. Then compare physical line count vs row
count separately — that's the embedded-newline detector.

### 6.3 Conversations API returns epoch ms, not ISO
**Symptom:** First Conversations.csv had `LastMessageDateUtc = "1779500080557"`.

**Fix:** `clean_utc_ts` auto-detects: numeric ≥ 10^12 → ms, else seconds, else
ISO. Covered by `test_clean_utc_ts_epoch_ms`.

### 6.4 Token length looked short (40 chars vs JWT)
**Symptom:** Initial token was 40 chars — JWT-style OAuth tokens are 500+.

**Cause:** It's a Private Integration Token (`pit-…`), not OAuth.

**Fix:** None needed — bearer auth works the same way. But OAuth-scope endpoints
will reject; see §5.

---

## 7. Decisions made (and why)

| Decision | Reason |
|---|---|
| CSV-first, not direct SQL writes | Decouple extract from load; idempotent re-runs; easier debugging |
| `csv.QUOTE_MINIMAL` + UTF-8 BOM + CRLF | Works with both BULK INSERT and Excel |
| PascalCase columns | Matches SQL Server convention the user requested |
| Replace newlines with single space (not `\n` literal) | KISS; SMS bodies don't need preserved formatting; reversible decision |
| Pipe-delimited arrays (Tags) | CSV-safe, easy to `STRING_SPLIT` in SQL Server |
| Audit gate runs after every extract | User wants machine-enforced quality, not visual review |
| 90-day message backfill scope | User confirmed; fits daily API cap; older data can be backfilled later |
| Sustained throttle ~5-8 RPS, not 10 | Headroom for other API users on this PIT |
| Shard files instead of one big CSV (planned) | Failure-isolation; SQL Server can BULK INSERT shards in parallel |

---

## 8. Next steps — the weekend plan (the build that was paused)

User is loading data over the weekend (2026-05-23/24). Plan gated by audit checks
between steps — script enforces, do NOT skip gates.

| Step | What | Expected calls | Time @ ~5 RPS | Gate |
|---|---|---:|---:|---|
| **A** | Contacts: 1,000 (test) | 2 | 1 sec | Audit 0 issues, row count == 1000, **checkpoint resume test** |
| **B** | Contacts: full ~252,285 | 505 | ~2 min | Audit 0 issues, manifest, row count ≈ API total (±0.1%) |
| **C** | Conversations: 1,000 (test) | 10 | 2 sec | Audit 0 issues, row count == 1000 |
| **D** | Conversations: full ~213,347 | 2,134 | ~7 min | Audit 0 issues, manifest |
| **E** | Messages: convs w/ `lastMessageDate ≥ now-90d` | ~30-60k | ~30-90 min | Audit 0 issues, per-conv reconcile |
| **F** | Final manifest + checksums for all shards | 0 | 1 sec | All present, hashes stable on re-run |

### Code to write before Step A (paused mid-build at commit `e8f35d2`)

1. **`src/ghl_api/mappers.py`** — ✅ DONE (committed below the line, see git status)
   - Holds `*_COLUMNS` lists + `map_contact` / `map_conversation` / `map_message`
   - Already extracted from `scripts/export_to_csv.py`
2. **`src/ghl_api/throttle.py`** — adaptive throttle
   - Watches `x-ratelimit-remaining` from responses
   - If < 20 remaining, sleep `(20 - remaining) / 20 * 0.5s`
   - If 0, sleep until `x-ratelimit-interval-milliseconds` resets
3. **`src/ghl_api/client.py` updates** — 429 retry
   - Catch 429, read `Retry-After`, sleep, retry up to 3 times
   - Integrate throttle: after each response, call `throttle.observe(headers)`
4. **`src/ghl_api/batch.py`** — `BatchExtractor` base class
   - Subclasses: `ContactsExtractor`, `ConversationsExtractor`, `MessagesExtractor`
   - `fetch_page(cursor) -> (rows, next_cursor)`
   - `map_row(api_row) -> dict`
   - `run(max_rows=None, resume=True)` — paginates, shards (5k rows/file), checkpoints after each page
   - Output: `<Entity>_part_NNN.csv`, `<Entity>.checkpoint.json`
5. **`src/ghl_api/manifest.py`** — manifest writer
   - Per-file: row count, sha256, columns, size bytes
   - Schema fingerprint = sha256 of column list
6. **`scripts/run_batch.py`** — CLI orchestrator
   - `--entity contacts --max-rows 1000` etc.
   - Runs extract → audit → manifest → exit code
   - Default behavior: load checkpoint, resume

### Open questions for the user (none pressing — these can be revisited later)

- **SQL Server target**: where is the data landing? Azure SQL? On-prem? Local
  Docker for testing? Affects whether we add a `pyodbc` direct-load step.
- **Incremental cadence after backfill**: daily? hourly? webhook-driven?
- **Pipelines/opportunities**: not in current scope but commonly wanted next.

---

## 9. Memory references (auto-memory persists across sessions)

Stored under `~/.claude/projects/-Users-smokestack-Projects-DCR-GHL-API/memory/`:

- `MEMORY.md` — index
- `project_ghl_api.md` — sub-account/location/PIT specifics
- `feedback_validate_before_scale.md` — user requires audit gates between batches

---

## 10. Don't do these things

- **Don't** add new fields to CSVs without updating `mappers.py`, the SQL DDL,
  and the audit's expected columns.
- **Don't** call `csv.writer` directly with raw data — always sanitize first.
- **Don't** assume any API field is non-null. PIT tokens have produced rows
  with missing `email`, `phone`, `assignedTo`, `source`. The mappers handle this.
- **Don't** commit `.env` or anything under `data/exports/`.
- **Don't** ship code that doesn't pass `pytest tests/ -v`.
- **Don't** skip the audit gate — it exists because of the 8-lost-rows bug.
- **Don't** raise concurrency above ~5 workers — at sustained 10 RPS we'd
  exhaust the burst window in 2 seconds.
- **Don't** use `git rebase -i`, `--amend`, or force-push without explicit
  user permission. Create new commits.
