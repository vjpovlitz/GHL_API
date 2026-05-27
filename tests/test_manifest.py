from __future__ import annotations

import csv
import json

from ghl_api.manifest import (
    Manifest,
    count_csv_data_rows,
    file_digest,
    schema_fingerprint,
)


def _write_csv(path, columns, rows):
    path.write_bytes(b"\xef\xbb\xbf")
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\r\n",
                           quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_schema_fingerprint_is_order_sensitive():
    a = schema_fingerprint(["A", "B", "C"])
    b = schema_fingerprint(["A", "C", "B"])
    assert a != b


def test_schema_fingerprint_is_stable():
    a = schema_fingerprint(["A", "B"])
    b = schema_fingerprint(["A", "B"])
    assert a == b
    assert len(a) == 64


def test_count_csv_data_rows(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["id", "v"], [{"id": "1", "v": "a"}, {"id": "2", "v": "b"}])
    assert count_csv_data_rows(p) == 2


def test_file_digest_changes_with_content(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["id"], [{"id": "1"}])
    a = file_digest(p)
    _write_csv(p.with_name("y.csv"), ["id"], [{"id": "2"}])
    b = file_digest(p.with_name("y.csv"))
    assert a != b
    assert len(a) == 64


def test_manifest_aggregates_shards(tmp_path):
    cols = ["ContactId", "Email"]
    s1 = tmp_path / "Contacts_part_001.csv"
    s2 = tmp_path / "Contacts_part_002.csv"
    _write_csv(s1, cols, [{"ContactId": "a", "Email": "a@x"}])
    _write_csv(s2, cols, [{"ContactId": "b", "Email": "b@x"},
                          {"ContactId": "c", "Email": "c@x"}])
    mf = Manifest(
        entity="Contacts",
        columns=cols,
        extracted_at_utc="2026-05-23T00:00:00.000Z",
        shard_size=5000,
        output_dir=tmp_path,
    )
    mf.add_shard(s1)
    mf.add_shard(s2)
    path = mf.write()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["entity"] == "Contacts"
    assert data["row_count_total"] == 3
    assert len(data["shards"]) == 2
    assert data["shards"][0]["rows"] == 1
    assert data["shards"][1]["rows"] == 2
    assert all(len(s["sha256"]) == 64 for s in data["shards"])
    assert data["schema_fingerprint"] == schema_fingerprint(cols)
