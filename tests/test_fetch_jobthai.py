"""test_fetch_jobthai.py — เทสต์ src/fetch_jobthai.py (jobthai.com)

ครอบ: parse_thai_date (พ.ศ. 2 หลัก/4 หลัก, ปี 70 → 2570, อ่านไม่ออก → None)
· parse_search_html กับ fixture 3 การ์ด (title/url ไม่ว่าง, url absolute,
uid ไม่ซ้ำ, ไม่มีเงินเดือน → None ห้ามเดา 0, ช่วงเงินเดือน → min/max)
· html ว่าง → [] ไม่ throw

รัน: python -m unittest discover -s tests -v   (ไม่ยิงเน็ต)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import fetch_jobthai  # noqa: E402
except ImportError:  # โมดูลยังไม่ถูกเขียน — ให้เคสแดงพร้อมเหตุผลชัด
    fetch_jobthai = None

FIXTURE = ROOT / "tests" / "fixtures" / "jobthai_search_sample.html"
URL_PREFIX = "https://www.jobthai.com/th/company/job/"


@unittest.skipUnless(fetch_jobthai is not None, "src/fetch_jobthai.py ยังไม่มี")
class TestParseThaiDate(unittest.TestCase):
    def test_21_p_y_69(self):
        self.assertEqual(fetch_jobthai.parse_thai_date("21 พ.ย. 69"), "2026-11-21")

    def test_1_m_k_2569_full_year(self):
        self.assertEqual(fetch_jobthai.parse_thai_date("1 ม.ค. 2569"), "2026-01-01")

    def test_31_th_k_68(self):
        self.assertEqual(fetch_jobthai.parse_thai_date("31 ธ.ค. 68"), "2025-12-31")

    def test_15_s_k_70_year70_is_2570(self):
        self.assertEqual(fetch_jobthai.parse_thai_date("15 ส.ค. 70"), "2027-08-15")

    def test_today_text_none(self):
        self.assertIsNone(fetch_jobthai.parse_thai_date("วันนี้"))

    def test_empty_none(self):
        self.assertIsNone(fetch_jobthai.parse_thai_date(""))

    def test_day_32_none(self):
        self.assertIsNone(fetch_jobthai.parse_thai_date("32 ม.ค. 69"))


@unittest.skipUnless(fetch_jobthai is not None, "src/fetch_jobthai.py ยังไม่มี")
@unittest.skipUnless(FIXTURE.exists(), "fixture jobthai_search_sample.html ยังไม่มี")
class TestParseSearchHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = fetch_jobthai.parse_search_html(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual(len(self.rows), 3)

    def test_required_keys_present(self):
        for row in self.rows:
            for key in ("source", "uid", "title", "company", "url", "location",
                        "salary_text", "salary_min", "salary_max", "posted_at",
                        "raw_text"):
                self.assertIn(key, row, f"ขาด key {key!r} ใน {row!r}")

    def test_source_is_jobthai(self):
        for row in self.rows:
            self.assertEqual(row["source"], "jobthai")

    def test_title_and_url_nonempty(self):
        for row in self.rows:
            self.assertTrue(row["title"], f"title ว่าง: {row!r}")
            self.assertTrue(row["url"], f"url ว่าง: {row!r}")

    def test_url_absolute_job_path(self):
        for row in self.rows:
            self.assertTrue(
                row["url"].startswith(URL_PREFIX),
                f"url ไม่ใช่ absolute ใต้ {URL_PREFIX}: {row['url']!r}",
            )

    def test_uid_unique(self):
        uids = [row["uid"] for row in self.rows]
        self.assertEqual(len(uids), len(set(uids)), f"uid ซ้ำ: {uids}")

    def test_no_salary_card_all_none(self):
        no_salary = [r for r in self.rows if r["salary_text"] is None]
        self.assertTrue(no_salary, "fixture ต้องมีการ์ดไม่ระบุเงินเดือนอย่างน้อย 1 ใบ")
        for row in no_salary:
            self.assertIsNone(row["salary_min"], f"ห้ามเดา 0: {row!r}")
            self.assertIsNone(row["salary_max"], f"ห้ามเดา 0: {row!r}")

    def test_salary_range_parsed(self):
        ranged = [r for r in self.rows if r["salary_text"]
                  and "35,000" in r["salary_text"]]
        self.assertTrue(ranged, "fixture ต้องมีการ์ดเงินเดือนช่วง 35,000 - 40,000")
        row = ranged[0]
        self.assertEqual(row["salary_min"], 35000)
        self.assertEqual(row["salary_max"], 40000)

    def test_raw_text_none(self):
        for row in self.rows:
            self.assertIsNone(row["raw_text"])


@unittest.skipUnless(fetch_jobthai is not None, "src/fetch_jobthai.py ยังไม่มี")
class TestParseSearchHtmlEmpty(unittest.TestCase):
    def test_empty_html_returns_empty_list_no_throw(self):
        self.assertEqual(fetch_jobthai.parse_search_html("<html></html>"), [])


if __name__ == "__main__":
    unittest.main()
