"""test_filters.py — เทสต์ src/filters.py (brief §3/§4, SPEC D1)

ครอบ: include (ผ่าน/ไม่ผ่าน) · must_not (ตัดจริง) · boost (คะแนนตาม config\filters.json)
· apply_filters ตัด + เรียงตามคะแนน · ใช้ fixture จริงผ่าน filters ได้

รัน: python -m unittest tests.test_filters -v   (หรือ discover -s tests)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import filters  # noqa: E402
import normalize  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
TODAY = __import__("datetime").date(2026, 11, 21)

# สวิตช์ชัดเจน ไม่พึ่ง config\switches.json (เทสต์เน้น include/must_not/boost)
SW_OFF = {"area.include_perimeter": False, "area.remote_anywhere": False}


def cfg():
    return filters.load_config()


def job(**kw):
    base = {"title": "", "company": "", "description": "", "raw_text": None,
            "district": None, "province": "กรุงเทพมหานคร", "location": None,
            "skills": [], "seniority": None, "work_mode": None, "sources": [],
            "salary_max": None}
    base.update(kw)
    return base


class MustNot(unittest.TestCase):
    def test_must_not_title_hits(self):
        for title, term in [("Sales Executive (IT Product)", "sales"),
                            ("Intern Python Developer", "intern"),
                            ("ฝึกงาน Developer", "ฝึกงาน"),
                            ("Telesale Representative", "telesale")]:
            self.assertIsNotNone(filters.must_not_hit(job(title=title), cfg()),
                                 f'title "{title}" ต้องติด must_not')

    def test_must_not_drops_row(self):
        j = job(title="Account Executive - IT Solutions")
        reason = filters.drop_reason(j, cfg(), SW_OFF)
        self.assertIsNotNone(reason)
        self.assertTrue(reason.startswith("must_not:"), f"ได้ reason = {reason!r}")
        self.assertTrue(filters.should_drop(j, cfg=cfg(), switches=SW_OFF))

    def test_clean_title_not_hit(self):
        self.assertIsNone(filters.must_not_hit(job(title="Senior Python Developer"), cfg()))

    def test_must_not_ignores_raw_text(self):
        # กติกา: ตัดจาก title เท่านั้น — raw_text ของ FB ที่มีคำต้องห้ามไม่ตัด
        j = job(title="Programmer ด่วน", raw_text="ปิดรับ sales แล้ว ขอบคุณ")
        self.assertIsNone(filters.must_not_hit(j, cfg()))


class Include(unittest.TestCase):
    def test_include_any_of_match(self):
        for title in ["Cloud Engineer", "DevOps Engineer",
                      "Senior AWS Infrastructure Engineer",
                      "VMware / Nutanix Administrator", "Proxmox VE Administrator",
                      "Site Reliability Engineer (SRE)", "รับสมัคร ผู้ดูแลระบบ ด่วน"]:
            self.assertTrue(filters.matches_include(job(title=title), cfg()),
                            f'title "{title}" ต้องผ่าน include')

    def test_include_miss(self):
        self.assertFalse(filters.matches_include(job(title="Accountant"), cfg()))
        self.assertFalse(filters.matches_include(job(title="Graphic Designer"), cfg()))

    def test_include_miss_drops_when_filter_mode(self):
        j = job(title="Accountant")
        self.assertEqual(filters.drop_reason(j, cfg(), SW_OFF, include_mode="filter"),
                         "include_miss")
        self.assertFalse(filters.passes(j, cfg=cfg(), switches=SW_OFF))

    def test_include_empty_titles_does_not_filter_by_title(self):
        c = dict(cfg())
        c["include"] = {"titles": [], "any_of": []}
        self.assertTrue(filters.matches_include(job(title="อะไรก็ได้"), c))


class Boost(unittest.TestCase):
    def test_score_follows_config_weights(self):
        c = cfg()
        j = job(title="Senior AWS Infrastructure Engineer", skills=["aws", "docker"],
                seniority="senior", work_mode="remote", sources=["linkedin"])
        expected = (int(c["boost"]["skills"]["aws"]) + int(c["boost"]["skills"]["docker"])
                    + int(c["boost"]["seniority"]["senior"])
                    + int(c["boost"]["work_mode"]["remote"])
                    + int(c["boost"]["sources"]["linkedin"]) + 2)  # +2 = ผ่าน include (title มี aws/infrastructure)
        self.assertEqual(filters.score(j, c), expected)

    def test_score_zero_base_without_boosts(self):
        # include ว่าง = ถือว่าผ่าน (docstring ของ matches_include) → ได้ +2 จาก include เท่านั้น
        c = dict(cfg())
        c["include"] = {"titles": [], "any_of": []}
        j = job(title="อื่น ๆ", skills=[], seniority=None, work_mode=None, sources=[])
        self.assertEqual(filters.score(j, c), 2)

    def test_higher_boost_sorts_first(self):
        c = cfg()
        strong = job(title="Senior DevOps Engineer", skills=["devops"],
                     seniority="senior", work_mode="remote", sources=["linkedin"])
        weak = job(title="Cloud Engineer", skills=[], seniority=None, work_mode=None,
                   sources=["google"])
        self.assertGreater(filters.score(strong, c), filters.score(weak, c))
        out = filters.apply_filters([weak, strong], c, SW_OFF)
        self.assertEqual(out, [strong, weak])

    def test_multi_source_takes_max_source_boost(self):
        c = cfg()
        j = job(title="Developer", sources=["linkedin", "facebook"])
        base = filters.score(job(title="Developer", sources=["facebook"]), c)
        self.assertEqual(filters.score(j, c),
                         base + int(c["boost"]["sources"]["linkedin"]))


class ApplyFilters(unittest.TestCase):
    def test_drops_must_not_and_sorts_by_score(self):
        c = cfg()
        dropped = job(title="Sales Executive")
        low = job(title="Cloud Engineer", skills=[], sources=["google"])
        high = job(title="Senior AWS Infrastructure Engineer", skills=["aws"],
                   seniority="senior", work_mode="remote", sources=["linkedin"])
        out = filters.apply_filters([low, dropped, high], c, SW_OFF)
        self.assertEqual(len(out), 2, "งานที่ติด must_not ต้องถูกตัด")
        self.assertNotIn(dropped, out)
        self.assertEqual(out, [high, low])

    def test_stable_order_for_equal_scores(self):
        c = dict(cfg())
        c["include"] = {"titles": [], "any_of": []}
        a = job(title="งานก")
        b = job(title="งานข")
        out = filters.apply_filters([a, b], c, SW_OFF)
        self.assertEqual(out, [a, b])


class WithFixtures(unittest.TestCase):
    """เทสต์ต้องใช้ได้จริงกับ fixture — normalize แล้วผ่าน filters."""

    def test_board_full_row_passes_and_scores(self):
        rows = normalize.normalize(normalize.load_raw_file(FIXTURES / "board_full_cloud.json"),
                                   TODAY, normalize.load_filters())
        self.assertEqual(len(rows), 1)
        self.assertTrue(filters.passes(rows[0], cfg=cfg(), switches=SW_OFF),
                        "งานบอร์ดครบฟิลด์ต้องผ่าน include/must_not")
        self.assertGreater(filters.score(rows[0], cfg()), 0)

    def test_fb_row_passes_must_not_despite_long_raw_text(self):
        rows = normalize.normalize(normalize.load_raw_file(FIXTURES / "fb_no_fields.json"),
                                   TODAY, normalize.load_filters())
        self.assertEqual(len(rows), 1)
        self.assertIsNone(filters.must_not_hit(rows[0], cfg()))
        self.assertTrue(filters.passes(rows[0], cfg=cfg(), switches=SW_OFF))

    def test_duplicate_fixture_merged_row_passes(self):
        rows = normalize.normalize(
            normalize.load_raw_file(FIXTURES / "duplicate_two_boards_cloud.json"),
            TODAY, normalize.load_filters())
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]["sources"]), {"linkedin", "jobsdb"})
        self.assertTrue(filters.passes(rows[0], cfg=cfg(), switches=SW_OFF))


class CloudScopeRegression(unittest.TestCase):
    """regression สำหรับ scope ใหม่ (cloud/devops/infra) — ใบงาน 21 พ.ย. ข้อ 2"""

    def test_include_passes_each_cloud_keyword(self):
        # อย่างละกรณี: aws / nutanix / proxmox / vmware / devops / cloud → ผ่าน include
        cases = [("aws", "Senior AWS Infrastructure Engineer"),
                 ("nutanix", "Nutanix Cluster Administrator"),
                 ("proxmox", "Proxmox VE Administrator"),
                 ("vmware", "VMware / vSphere Administrator"),
                 ("devops", "DevOps Engineer"),
                 ("cloud", "Cloud Engineer")]
        for keyword, title in cases:
            with self.subTest(keyword=keyword):
                self.assertTrue(filters.matches_include(job(title=title), cfg()),
                                f'"{keyword}" ใน title "{title}" ต้องผ่าน include')

    def test_non_cloud_titles_get_include_miss(self):
        for title in ["Accountant", "Sales Executive", "Junior Automation Engineer"]:
            self.assertFalse(filters.matches_include(job(title=title), cfg()),
                             f'title "{title}" ต้องไม่ผ่าน include')
        # Accountant / Junior Automation Engineer ไม่ติด must_not → ถูกตัดด้วย include_miss
        for title in ["Accountant", "Junior Automation Engineer"]:
            self.assertEqual(filters.drop_reason(job(title=title), cfg(), SW_OFF),
                             "include_miss", f'"{title}" ต้องถูกตัดด้วย include_miss')

    def test_intern_and_labor_titles_hit_must_not(self):
        cases = [("Intern DevOps Engineer", "intern"),
                 ("ฝึกงาน Cloud Engineer", "ฝึกงาน"),
                 ("แรงงานเทคนิค ด่วน", "แรงงาน")]
        for title, term in cases:
            with self.subTest(title=title):
                self.assertEqual(filters.must_not_hit(job(title=title), cfg()), term,
                                 f'title "{title}" ต้องติด must_not ด้วยคำ "{term}"')
                reason = filters.drop_reason(job(title=title), cfg(), SW_OFF)
                self.assertIsNotNone(reason)
                self.assertTrue(reason.startswith("must_not:"),
                                f'"{title}" ต้องถูกตัดด้วย must_not ได้ reason = {reason!r}')

    def test_fb_row_included_via_raw_text_not_title(self):
        # พฤติกรรมตามโค้ด (src/filters.py:78-92): matches_include ใช้ job_text =
        # title + company + description + raw_text → FB ที่ title ไม่มีคำสาย cloud
        # แต่ raw_text มี ต้องผ่าน include; ส่วน must_not ตรวจ title เท่านั้น
        # (src/filters.py:101-110) → raw_text มีคำ must_not ก็ห้ามตัด
        j = job(title="รับสมัครพนักงาน ด่วน",
                raw_text="ทักษะที่ต้องการ: AWS, Terraform, Kubernetes, Docker")
        self.assertTrue(filters.matches_include(j, cfg()),
                        "raw_text มีคำสาย cloud ต้องผ่าน include แม้ title ไม่มี")
        self.assertIsNone(filters.must_not_hit(j, cfg()),
                          "must_not ตรวจ title เท่านั้น ห้ามตัดจาก raw_text")
        self.assertTrue(filters.passes(j, cfg=cfg(), switches=SW_OFF))

    def test_board_row_without_cloud_title_misses_include(self):
        # แถวบอร์ด (ไม่มี raw_text) ที่ title ไม่มีคำสาย cloud → include_miss
        # (normalize ไม่เก็บ description ใน schema จึงไม่ช่วย include)
        j = job(title="Backend Developer (Python)", company="บริษัท ตัวอย่าง จำกัด")
        self.assertFalse(filters.matches_include(j, cfg()))
        self.assertEqual(filters.drop_reason(j, cfg(), SW_OFF), "include_miss")


if __name__ == "__main__":
    unittest.main()
