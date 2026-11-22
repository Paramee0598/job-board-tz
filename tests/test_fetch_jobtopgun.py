"""test_fetch_jobtopgun.py — เทสต์ src/fetch_jobtopgun.py (jobtopgun.com)

ครอบ: fixture 3 การ์ดจริง (ตัดจากหน้าจริง 22 พ.ย. 2569)
· title/company/location/url ไม่ว่าง · uid = slug ของงาน ไม่ซ้ำ
· เงินเดือนช่วง → min/max · การ์ดไม่มีเงินเดือน → None ทั้งสาม (ห้ามเดา 0)
· วันที่บนหน้าเป็น relative ล้วน → posted_at None (ห้ามเดาเป็นวันนี้)
· ลิงก์สถานที่ /th/jobs/in-bangkok ไม่ถูกนับเป็นงาน · overlay + <a> ใน <h2> ของงานใบเดียวถูกยุบ
· url ที่สร้างมี query ตามที่เว็บใช้ (หน้าแรกไม่มี page, หน้าที่ 2 มี &page=2)

รัน: python -m unittest discover -s tests -v   (ไม่ยิงเน็ต)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import fetch_jobtopgun  # noqa: E402
except ImportError:  # โมดูลยังไม่ถูกเขียน — ให้เคสแดงพร้อมเหตุผลชัด
    fetch_jobtopgun = None

FIXTURE = ROOT / "tests" / "fixtures" / "jobtopgun_search_sample.html"
URL_PREFIX = "https://www.jobtopgun.com/th/jobs/j"

OVERLAY_HTML = """
<html><body>
<article aria-label="A at บริษัท หนึ่ง, กรุงเทพมหานคร">
  <a href="/th/jobs/j111-1" aria-hidden="true" tabindex="-1" class="absolute inset-0 z-0"></a>
  <div class="relative mb-1"><h2><a href="/th/jobs/j111-1">วิศวกรระบบ</a></h2></div>
  <div class="relative mb-2"><p><a href="/th/companies/company-c111">บริษัท หนึ่ง</a></p></div>
  <div class="relative"><a href="/th/jobs/in-bangkok">กรุงเทพมหานคร</a></div>
</article>
<article aria-label="ไม่มีชื่อ">
  <a href="/th/jobs/j222-2" aria-hidden="true" tabindex="-1"></a>
  <div class="relative mb-2"><p><a href="/th/companies/company-c222">บริษัท สอง</a></p></div>
</article>
</body></html>
"""


@unittest.skipUnless(fetch_jobtopgun is not None, "src/fetch_jobtopgun.py ยังไม่มี")
@unittest.skipUnless(FIXTURE.exists(), "fixture jobtopgun_search_sample.html ยังไม่มี")
class TestParseSearchHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = fetch_jobtopgun.parse_search_html(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual(len(self.rows), 3)

    def test_required_keys_present(self):
        for row in self.rows:
            for key in ("source", "uid", "title", "company", "url", "location",
                        "salary_text", "salary_min", "salary_max", "posted_at",
                        "raw_text", "description"):
                self.assertIn(key, row, f"ขาด key {key!r} ใน {row!r}")

    def test_source_is_jobtopgun(self):
        for row in self.rows:
            self.assertEqual(row["source"], "jobtopgun")

    def test_title_company_location_nonempty(self):
        for row in self.rows:
            self.assertTrue(row["title"], f"title ว่าง: {row!r}")
            self.assertTrue(row["company"], f"company ว่าง: {row!r}")
            self.assertTrue(row["location"], f"location ว่าง: {row!r}")

    def test_url_absolute_job_path(self):
        for row in self.rows:
            self.assertTrue(row["url"].startswith(URL_PREFIX),
                            f"url ไม่ใช่ absolute ใต้ {URL_PREFIX}: {row['url']!r}")

    def test_uid_is_job_slug_and_unique(self):
        uids = [row["uid"] for row in self.rows]
        self.assertEqual(len(uids), len(set(uids)), f"uid ซ้ำ: {uids}")
        for row in self.rows:
            self.assertEqual(row["url"].rsplit("/", 1)[-1], row["uid"])
            self.assertRegex(row["uid"], r"^j\d+-[A-Za-z0-9]+$")

    def test_card_without_salary_all_none(self):
        no_salary = [r for r in self.rows if r["salary_text"] is None]
        self.assertTrue(no_salary, "fixture ต้องมีการ์ดไม่ระบุเงินเดือนอย่างน้อย 1 ใบ")
        for row in no_salary:
            self.assertIsNone(row["salary_min"], f"ห้ามเดา 0: {row!r}")
            self.assertIsNone(row["salary_max"], f"ห้ามเดา 0: {row!r}")

    def test_salary_range_parsed(self):
        ranged = [r for r in self.rows if r["salary_min"] == 39000]
        self.assertTrue(ranged, "fixture ต้องมีการ์ดเงินเดือน 39,000 - 54,000")
        self.assertEqual(ranged[0]["salary_max"], 54000)
        self.assertIn("39,000 - 54,000", ranged[0]["salary_text"])

    def test_posted_at_none_when_page_has_no_absolute_date(self):
        # หน้านี้บอกอายุงานแบบ relative ("2 วันที่แล้ว") เท่านั้น → ห้ามเดาเป็นวันที่
        for row in self.rows:
            self.assertIsNone(row["posted_at"], f"เดาวันที่จากข้อความ relative: {row!r}")

    def test_raw_text_and_description_none(self):
        for row in self.rows:
            self.assertIsNone(row["raw_text"])
            self.assertIsNone(row["description"])


@unittest.skipUnless(fetch_jobtopgun is not None, "src/fetch_jobtopgun.py ยังไม่มี")
class TestParseSearchHtmlEdge(unittest.TestCase):
    def test_empty_html_returns_empty_list_no_throw(self):
        self.assertEqual(fetch_jobtopgun.parse_search_html("<html></html>"), [])

    def test_location_link_is_not_a_job(self):
        self.assertIsNone(fetch_jobtopgun.job_slug("/th/jobs/in-bangkok"))
        self.assertIsNone(fetch_jobtopgun.job_slug("/th/companies/company-c15793"))
        self.assertEqual(fetch_jobtopgun.job_slug("/th/jobs/j15793-68"), "j15793-68")

    def test_overlay_anchor_deduped_and_missing_title_skipped(self):
        rows, stats = fetch_jobtopgun.parse_search_html_with_stats(OVERLAY_HTML)
        self.assertEqual(len(rows), 1, f"ต้องได้ 1 แถว (overlay ถูกยุบ): {rows!r}")
        self.assertEqual(rows[0]["uid"], "j111-1")
        self.assertEqual(stats["cards"], 2)
        self.assertEqual(stats["skipped"], 1, "การ์ดไม่มีชื่อตำแหน่งต้องถูกนับว่าข้าม")


@unittest.skipUnless(fetch_jobtopgun is not None, "src/fetch_jobtopgun.py ยังไม่มี")
class TestBuildSearchUrl(unittest.TestCase):
    def test_first_page_has_no_page_param(self):
        url = fetch_jobtopgun.build_search_url("https://www.jobtopgun.com", "vmware", 1)
        self.assertEqual(url, "https://www.jobtopgun.com/th/jobs?keyword=vmware")

    def test_second_page_has_page_param(self):
        url = fetch_jobtopgun.build_search_url("https://www.jobtopgun.com", "hyper-v", 2)
        self.assertEqual(url, "https://www.jobtopgun.com/th/jobs?keyword=hyper-v&page=2")

    def test_empty_keyword_refused(self):
        with self.assertRaises(ValueError):
            fetch_jobtopgun.build_search_url("https://www.jobtopgun.com", "  ", 1)

    def test_non_origin_base_refused(self):
        with self.assertRaises(ValueError):
            fetch_jobtopgun.build_search_url("https://www.jobtopgun.com.th/jobs", "vmware", 1)


if __name__ == "__main__":
    unittest.main()
