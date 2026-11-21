"""test_word_boundary.py — regression สัญญาใหม่ของการแมตช์คำ (defect 21 พ.ย.)

สัญญา: คำลาติน/ASCII มี word boundary ทั้งสองข้าง (\b…\b, case-insensitive) ·
คำไทย/ไม่ใช่ ASCII ยังแมตช์ substring · วลีหลายคำมีขอบเขตปลายทั้งสองข้าง ·
พฤติกรรมอื่น (boost, area, salary, job_text) ไม่เปลี่ยน

คำที่ใช้มาจาก config\filters.json จริง: include.any_of มี "cloud", "network engineer",
"network engineering", "คลาวด์" · must_not.titles มี "intern", "ฝึกงาน" (ไม่มี "internship")

รัน: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import filters  # noqa: E402


def cfg():
    return filters.load_config()


def job(**kw):
    base = {"title": "", "company": "", "description": "", "raw_text": None,
            "district": None, "province": "กรุงเทพมหานคร", "location": None,
            "skills": [], "seniority": None, "work_mode": None, "sources": [],
            "salary_max": None}
    base.update(kw)
    return base


class CloudVsCompanySubstring(unittest.TestCase):
    """(ก) cloud ห้ามแมตช์ชื่อบริษัทที่มี cloud ฝังอยู่"""

    def test_cloud_does_not_match_gushcloud(self):
        j = job(title="Media Buyer", company="Gushcloud")
        self.assertFalse(filters.matches_include(j, cfg()),
                         '"cloud" ห้ามแมตช์ company "Gushcloud" (ต้องมี word boundary)')

    def test_cloud_does_not_match_cloudbeds(self):
        j = job(title="Advanced Support Coach- Thailand", company="Cloudbeds")
        self.assertFalse(filters.matches_include(j, cfg()),
                         '"cloud" ห้ามแมตช์ company "Cloudbeds" (ต้องมี word boundary)')

    def test_cloud_matches_cloud_operations_engineer(self):
        self.assertTrue(filters.matches_include(job(title="Cloud Operations Engineer"), cfg()),
                        '"cloud" ต้องยังแมตช์ title ที่มีคำ cloud เต็มคำ')


class InternMustNotBoundary(unittest.TestCase):
    """(ข) intern ห้ามแมตช์ internal"""

    def test_internal_audit_manager_not_cut(self):
        self.assertIsNone(filters.must_not_hit(job(title="Internal Audit Manager"), cfg()),
                          '"intern" ห้ามแมตช์ "Internal" (ต้องมี word boundary)')

    def test_branch_internal_auditor_not_cut(self):
        self.assertIsNone(filters.must_not_hit(job(title="Branch Internal Auditor"), cfg()),
                          '"intern" ห้ามแมตช์ "Internal" ใน "Branch Internal Auditor"')

    def test_devops_intern_still_cut(self):
        self.assertEqual(filters.must_not_hit(job(title="DevOps Intern"), cfg()), "intern",
                         '"intern" เต็มคำต้องยังติด must_not')

    def test_internship_follows_config_terms(self):
        # config\filters.json must_not.titles มี "intern" เท่านั้น (ไม่มี "internship")
        # → ตามสัญญา \bintern\b ไม่แมตช์ "Internship"; ถ้า config เติม "internship"
        #   เทสต์จะคาดหวังการตัดแทนตามความจริงของ config (ไม่ hardcode)
        titles = [t for t in (cfg().get("must_not") or {}).get("titles") or [] if t]
        has_internship = any(t.strip().casefold() == "internship" for t in titles)
        j = job(title="Cloud Engineer (Internship)")
        hit = filters.must_not_hit(j, cfg())
        if has_internship:
            self.assertIsNotNone(hit, 'config มีคำ "internship" → ต้องตัด')
        else:
            self.assertIsNone(hit,
                              'config ไม่มีคำ "internship" และ \\bintern\\b ไม่ครอบ "Internship"')


class ThaiStillSubstring(unittest.TestCase):
    """คำไทย/ไม่ใช่ ASCII ยังแมตช์แบบ substring (ไม่มี \b มาบัง)"""

    def test_thai_must_not_substring_no_spaces(self):
        # "ฝึกงาน" ฝังในคำไทยติดกัน → ต้องยังตัด (ถ้าใส่ \b กับคำไทยจะพลาดเคสนี้)
        self.assertEqual(filters.must_not_hit(job(title="สมัครฝึกงานด่วน"), cfg()), "ฝึกงาน",
                         'คำไทยต้องแมตช์ substring แม้ติดกับคำอื่น')

    def test_thai_include_substring_no_spaces(self):
        # "คลาวด์" ฝังในคำไทยติดกัน → ต้องผ่าน include
        self.assertTrue(filters.matches_include(job(title="ระบบคลาวด์ครบวงจร"), cfg()),
                        'คำไทย "คลาวด์" ต้องแมตช์ substring')

    def test_thai_include_standalone_word(self):
        self.assertTrue(filters.matches_include(job(title="วิศวกร คลาวด์"), cfg()),
                        '"คลาวด์" เป็นคำโดดต้องผ่าน include ตามเดิม')


class LatinPhraseBoundary(unittest.TestCase):
    """วลีหลายคำ (ลาติน) มีขอบเขตปลายทั้งสองข้าง"""

    def test_phrase_matches_whole_words(self):
        c = {"include": {"titles": [], "any_of": ["network engineer"]}}
        self.assertTrue(filters.matches_include(job(title="Senior Network Engineer"), c),
                        'วลี "network engineer" ต้องแมตช์คำเต็มทั้งสองคำ')

    def test_phrase_does_not_match_inside_longer_word(self):
        # "Network Engineering Manager": "engineer" ไม่มีขอบขวา (ตามด้วย -ing)
        c = {"include": {"titles": [], "any_of": ["network engineer"]}}
        self.assertFalse(filters.matches_include(job(title="Network Engineering Manager"), c),
                         'วลี "network engineer" ห้ามแมตช์กลางคำ "Engineering"')

    def test_real_config_cloudonomics_excluded(self):
        # config มีทั้ง "cloud" และ "network engineering" → ใช้ตัวอย่างไม่กำกวม:
        # "Cloudonomics" ไม่มีคำ cloud เต็มคำ → ไม่ผ่าน include
        self.assertFalse(filters.matches_include(job(title="Cloudonomics Specialist"), cfg()),
                         '"cloud" ห้ามแมตช์กลางคำ "Cloudonomics"')

    def test_real_config_network_engineering_manager_still_included(self):
        # ความจริงของ config: any_of มี "network engineering" ด้วย → title นี้ผ่านอยู่ดี
        self.assertTrue(filters.matches_include(job(title="Network Engineering Manager"), cfg()),
                        'config มีคำ "network engineering" → ต้องผ่าน include')


if __name__ == "__main__":
    unittest.main()
