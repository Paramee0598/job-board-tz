"""test_normalize.py — เทสต์ src/normalize.py (brief §3, SPEC D1/R5/R6)

ครอบ: ยุบซ้ำ 2 บอร์ด · FB ไม่มีฟิลด์ไม่พัง schema · id = <source>:<uid> / sha1(url)
· idempotent · status "gone" >14 วัน (แถวคงอยู่) · merge กับคลังเดิม (แถวหายไม่ถูกลบ)
· salary_text null → min/max null (ห้ามเดา) · title/company ผ่านมาทุกไบต์

รัน: python -m unittest tests.test_normalize -v   (หรือ discover -s tests)
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import normalize  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
TODAY = date(2026, 11, 21)

SCHEMA_KEYS = [
    "id", "sources", "title", "company", "company_id", "district", "province",
    "work_mode", "seniority", "job_type", "salary_text", "salary_min",
    "salary_max", "currency", "skills", "url", "posted_at", "first_seen",
    "last_seen", "status", "raw_text",
]


def load_fixture(name: str):
    with (FIXTURES / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def items_of(name: str):
    return normalize.load_raw_file(FIXTURES / name)


def norm_fixture(name: str, existing=None):
    return normalize.normalize(items_of(name), TODAY, normalize.load_filters(), existing=existing)


class DuplicateTwoBoards(unittest.TestCase):
    def test_duplicate_two_boards_collapse_to_one_row_two_sources(self):
        rows = norm_fixture("duplicate_two_boards.json")
        self.assertEqual(len(rows), 1, f"ต้องยุบเหลือ 1 แถว ได้ {len(rows)}")
        src = rows[0]["sources"]
        self.assertEqual(len(src), 2, f"sources ต้องมี 2 ค่า ได้ {src}")
        self.assertEqual(set(src), {"linkedin", "jobsdb"})

    def test_duplicate_merged_fields_filled_from_richer_row(self):
        rows = norm_fixture("duplicate_two_boards.json")
        row = rows[0]
        self.assertEqual(row["salary_text"], "40,000 - 60,000 บาท")
        self.assertEqual(row["salary_min"], 40000)
        self.assertEqual(row["salary_max"], 60000)


class FbNoFields(unittest.TestCase):
    def setUp(self):
        self.rows = norm_fixture("fb_no_fields.json")
        self.assertEqual(len(self.rows), 1)
        self.row = self.rows[0]

    def test_schema_keys_all_present(self):
        missing = [k for k in SCHEMA_KEYS if k not in self.row]
        self.assertEqual(missing, [], f"ขาดคีย์ schema: {missing}")

    def test_missing_fields_are_null_not_empty_string(self):
        for key in ("company", "company_id", "district", "province", "salary_text",
                    "salary_min", "salary_max", "currency", "posted_at"):
            self.assertIsNone(self.row[key], f"{key} ต้องเป็น null ไม่ใช่ {self.row[key]!r}")

    def test_raw_text_truncated_at_1500(self):
        raw = load_fixture("fb_no_fields.json")["raw"][0]["jobs"][0]["raw_text"]
        self.assertGreater(len(raw), 1500, "fixture ต้องมี raw_text > 1500 ตัวอักษร")
        self.assertEqual(len(self.row["raw_text"]), 1500)
        self.assertEqual(self.row["raw_text"], raw[:1500])

    def test_fb_id_is_sha1_of_url(self):
        url = load_fixture("fb_no_fields.json")["raw"][0]["jobs"][0]["url"]
        expected = "sha1:" + hashlib.sha1(url.encode("utf-8")).hexdigest()
        self.assertEqual(self.row["id"], expected)

    def test_fb_title_verbatim(self):
        self.assertEqual(self.row["title"], "รับสมัคร Programmer ด่วน เงินเดือนดี")

    def test_fb_no_salary_guess_from_raw_text(self):
        self.assertIsNone(self.row["salary_min"])
        self.assertIsNone(self.row["salary_max"])


class IdRules(unittest.TestCase):
    def test_id_is_source_uid_when_uid_exists(self):
        rows = norm_fixture("board_full.json")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "linkedin:3912345678")

    def test_id_falls_back_to_sha1_url_without_uid(self):
        raw = {"title": "Dev", "url": "example.test/job/1"}
        row = normalize.normalize_row(raw, "test", TODAY, normalize.load_filters())
        self.assertEqual(row["id"], normalize.sha1_url("example.test/job/1"))


class Idempotent(unittest.TestCase):
    def test_rerun_same_input_same_row_count_and_sources(self):
        first = norm_fixture("duplicate_two_boards.json")
        second = normalize.normalize(items_of("duplicate_two_boards.json"), TODAY,
                                     normalize.load_filters(), existing=copy.deepcopy(first))
        self.assertEqual(len(second), len(first))
        self.assertEqual([r["id"] for r in second], [r["id"] for r in first])
        for a, b in zip(first, second):
            self.assertEqual(sorted(b["sources"]), sorted(a["sources"]),
                             "รันซ้ำแล้ว sources ต้องไม่เพิ่มค่าซ้ำ")
            self.assertEqual(len(b["sources"]), len(set(b["sources"])))

    def test_rerun_fb_fixture_stable(self):
        first = norm_fixture("fb_no_fields.json")
        second = normalize.normalize(items_of("fb_no_fields.json"), TODAY,
                                     normalize.load_filters(), existing=copy.deepcopy(first))
        self.assertEqual(len(second), len(first))
        self.assertEqual(second[0]["raw_text"], first[0]["raw_text"])


class Gone(unittest.TestCase):
    def _row(self, last_seen):
        return {"id": "test:1", "sources": ["test"], "title": "Old Job", "company": "C",
                "url": "example.test/old", "first_seen": "2026-10-01",
                "last_seen": last_seen, "status": "active"}

    def test_last_seen_over_14_days_marks_gone_and_row_kept(self):
        rows = [self._row("2026-11-01")]  # 20 วันก่อน TODAY
        out = normalize.apply_gone(copy.deepcopy(rows), TODAY)
        self.assertEqual(len(out), 1, "ห้ามลบแถว")
        self.assertEqual(out[0]["status"], "gone")

    def test_boundary_14_days_is_active_15_is_gone(self):
        at_14 = normalize.apply_gone([self._row("2026-11-07")], TODAY)
        at_15 = normalize.apply_gone([self._row("2026-11-06")], TODAY)
        self.assertEqual(at_14[0]["status"], "active")
        self.assertEqual(at_15[0]["status"], "gone")


class MergeWithExisting(unittest.TestCase):
    def test_row_missing_from_new_round_survives(self):
        existing = [{"id": "old:1", "sources": ["old"], "title": "เก่า", "company": "เก่า จำกัด",
                     "url": "example.test/old-job", "first_seen": "2026-11-10",
                     "last_seen": "2026-11-18", "status": "active"}]
        new_raw = [{"title": "ใหม่", "url": "example.test/new-job", "uid": "n1"}]
        new_rows = [normalize.normalize_row(r, "test", TODAY, normalize.load_filters())
                    for r in new_raw]
        merged = normalize.merge_with_existing(new_rows, existing, TODAY)
        ids = [r["id"] for r in merged]
        self.assertIn("old:1", ids, "แถวที่หายจากรอบใหม่ต้องยังอยู่ ไม่ถูกลบ")
        self.assertIn("test:n1", ids)
        self.assertEqual(len(merged), 2)

    def test_carried_old_row_becomes_gone_but_stays(self):
        existing = [{"id": "old:2", "sources": ["old"], "title": "เก่าแก่", "company": "เก่าแก่ จำกัด",
                     "url": "example.test/older-job", "first_seen": "2026-10-01",
                     "last_seen": "2026-11-01", "status": "active"}]
        merged = normalize.merge_with_existing([], existing, TODAY)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["status"], "gone")


class NoSalaryGuess(unittest.TestCase):
    def test_salary_text_null_forces_min_max_null(self):
        raw = {"title": "Dev", "url": "example.test/s1",
               "min_amount": 30000, "max_amount": 60000}
        row = normalize.normalize_row(raw, "test", TODAY, normalize.load_filters())
        self.assertIsNone(row["salary_text"])
        self.assertIsNone(row["salary_min"], "ห้ามเดา salary_min เมื่อไม่มี salary_text")
        self.assertIsNone(row["salary_max"], "ห้ามเดา salary_max เมื่อไม่มี salary_text")
        self.assertIsNone(row["currency"])

    def test_board_full_salary_passthrough(self):
        rows = norm_fixture("board_full.json")
        self.assertEqual(rows[0]["salary_text"], "30,000 - 35,000 บาท")
        self.assertEqual(rows[0]["salary_min"], 30000)
        self.assertEqual(rows[0]["salary_max"], 35000)


class Verbatim(unittest.TestCase):
    def test_title_company_district_byte_exact(self):
        rows = norm_fixture("board_full.json")
        row = rows[0]
        self.assertEqual(row["title"], "Backend Developer (Python)")
        self.assertEqual(row["company"], "บริษัท ตัวอย่าง จำกัด")
        self.assertEqual(row["district"], "ดินแดง")
        self.assertEqual(row["province"], "กรุงเทพมหานคร")


if __name__ == "__main__":
    unittest.main()
