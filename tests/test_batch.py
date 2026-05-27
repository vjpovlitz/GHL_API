"""Unit tests for BatchExtractor.

No live API calls — uses a FakeExtractor that yields scripted pages so we
can test sharding, checkpointing, resume, and max_rows behavior.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field

from ghl_api.batch import BatchExtractor, Checkpoint


class FakeThrottle:
    burst_remaining = None
    def before_request(self): return 0.0
    def observe(self, h): pass
    def stats(self): return {}


@dataclass
class FakeClient:
    throttle: FakeThrottle = field(default_factory=FakeThrottle)


class FakeExtractor(BatchExtractor):
    entity = "Fake"
    columns = ["Id", "Value"]

    def __init__(self, pages, **kwargs):
        super().__init__(client=FakeClient(), **kwargs)
        self._pages = list(pages)
        self._call_count = 0

    def fetch_page(self, cursor):
        idx = int(cursor or 0)
        self._call_count += 1
        if idx >= len(self._pages):
            return [], None
        page = self._pages[idx]
        next_cursor = idx + 1 if idx + 1 < len(self._pages) else None
        return page, next_cursor

    def map_row(self, api_row, *, extracted_at):
        return {"Id": api_row["id"], "Value": api_row["v"]}


def _read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_single_page_writes_one_shard(tmp_path):
    pages = [[{"id": "1", "v": "a"}, {"id": "2", "v": "b"}]]
    ex = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    cp = ex.run()
    assert cp.finished
    assert cp.rows_total == 2
    assert cp.shard_files == ["Fake_part_001.csv"]
    rows = _read_csv(tmp_path / "Fake_part_001.csv")
    assert len(rows) == 2
    assert rows[0]["Id"] == "1"


def test_shards_roll_at_boundary(tmp_path):
    # 12 rows across 4 pages; shard_size=5 -> shards 1,2,3
    pages = [
        [{"id": str(i), "v": "x"} for i in range(1, 4)],   # 3 rows
        [{"id": str(i), "v": "x"} for i in range(4, 9)],   # 5 rows -> straddles shard 1->2
        [{"id": str(i), "v": "x"} for i in range(9, 12)],  # 3 rows -> shard 2->3
        [{"id": "12", "v": "x"}],
    ]
    ex = FakeExtractor(pages, output_dir=tmp_path, shard_size=5)
    cp = ex.run()
    assert cp.rows_total == 12
    # 12 rows / shard_size 5 -> 3 shards (5, 5, 2)
    assert len(cp.shard_files) == 3
    assert len(_read_csv(tmp_path / "Fake_part_001.csv")) == 5
    assert len(_read_csv(tmp_path / "Fake_part_002.csv")) == 5
    assert len(_read_csv(tmp_path / "Fake_part_003.csv")) == 2


def test_checkpoint_written_and_resumable(tmp_path):
    pages = [
        [{"id": "1", "v": "a"}, {"id": "2", "v": "b"}],
        [{"id": "3", "v": "c"}, {"id": "4", "v": "d"}],
    ]
    # First run: cap at 2 rows
    ex1 = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    cp1 = ex1.run(max_rows=2)
    assert cp1.rows_total == 2
    assert not cp1.finished

    cp_data = json.loads((tmp_path / "Fake.checkpoint.json").read_text())
    assert cp_data["rows_total"] == 2
    assert cp_data["cursor"] == 1  # next page index

    # Resume: fresh extractor, same pages
    ex2 = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    cp2 = ex2.run()
    assert cp2.rows_total == 4
    assert cp2.finished
    rows = _read_csv(tmp_path / "Fake_part_001.csv")
    assert len(rows) == 4
    assert [r["Id"] for r in rows] == ["1", "2", "3", "4"]


def test_finished_checkpoint_is_noop(tmp_path):
    pages = [[{"id": "1", "v": "a"}]]
    ex1 = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    cp1 = ex1.run()
    assert cp1.finished
    calls_before = ex1._call_count

    ex2 = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    cp2 = ex2.run()
    # Should not have fetched anything
    assert ex2._call_count == 0
    assert cp2.rows_total == cp1.rows_total


def test_max_rows_caps_mid_page(tmp_path):
    pages = [[{"id": str(i), "v": "x"} for i in range(1, 11)]]  # 10 rows
    ex = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    cp = ex.run(max_rows=3)
    assert cp.rows_total == 3
    rows = _read_csv(tmp_path / "Fake_part_001.csv")
    assert len(rows) == 3


def test_csv_has_bom_and_crlf(tmp_path):
    pages = [[{"id": "1", "v": "a"}]]
    ex = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    ex.run()
    raw = (tmp_path / "Fake_part_001.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    # CRLF: at least one occurrence (header line ending)
    assert b"\r\n" in raw
    # No bare LFs (LF count == CRLF count)
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_extend_resumes_with_new_driver_list(tmp_path):
    """Simulates --extend: finished checkpoint + new driver list, append to existing shards."""
    import json

    # First batch: 2 rows -> shard 1
    pages = [[{"id": "1", "v": "a"}, {"id": "2", "v": "b"}]]
    ex1 = FakeExtractor(pages, output_dir=tmp_path, shard_size=10)
    cp1 = ex1.run()
    assert cp1.finished and cp1.rows_total == 2

    # Now: mimic the --extend flag — rewrite checkpoint cursor=0/finished=False but
    # keep shard state. Fresh extractor with different driver pages.
    cp_path = tmp_path / "Fake.checkpoint.json"
    data = json.loads(cp_path.read_text())
    data["cursor"] = 0
    data["finished"] = False
    cp_path.write_text(json.dumps(data))

    pages2 = [[{"id": "3", "v": "c"}, {"id": "4", "v": "d"}]]
    ex2 = FakeExtractor(pages2, output_dir=tmp_path, shard_size=10)
    cp2 = ex2.run()
    assert cp2.rows_total == 4  # 2 from batch1 + 2 from batch2
    rows = _read_csv(tmp_path / "Fake_part_001.csv")
    assert len(rows) == 4
    assert [r["Id"] for r in rows] == ["1", "2", "3", "4"]


def test_append_does_not_duplicate_bom_or_header(tmp_path):
    # Two pages, sharding doesn't roll — verify only one header + one BOM
    pages = [
        [{"id": "1", "v": "a"}],
        [{"id": "2", "v": "b"}],
    ]
    ex = FakeExtractor(pages, output_dir=tmp_path, shard_size=5000)
    ex.run()
    raw = (tmp_path / "Fake_part_001.csv").read_bytes()
    assert raw.count(b"\xef\xbb\xbf") == 1
    assert raw.count(b"Id,Value") == 1
