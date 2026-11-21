"""test_area_and_description.py — regression 2 defect ที่เพิ่งแก้ (ใบงาน 21 พ.ย.)

Defect 1: src/filters.py::area_hit — เดิมตัดงาน province = null + location = "40, Thailand"
          เป็น area_outside (งาน Indeed 4 แถวหลุดจากหน้าเว็บ). ตอนนี้:
          province null/ว่าง/ไม่รู้จัก = ไม่ตัด · กรุงเทพ = ไม่ตัด ·
          ปริมณฑล = ตามสวิตช์ area.include_perimeter · จังหวัดอื่นที่รู้จัก = ตัด ·
          location/district ดิบไม่ถูกใช้ตัดสิน
Defect 2: src/filters.py::job_text + src/normalize.py::detect_skills — คำใน description
          ไม่มีผลกับ include เพราะแถวไม่มี description; ตอนนี้ job_text นับ skills ด้วย
          และ detect_skills รวมคำที่สกัดได้จาก description

รัน: python -m unittest discover -s tests -v

หมายเหตุ: ไม่ฮาร์ดโค้ดคำ include ที่อาจถูกกระชับ — ใช้ aws/docker (คำที่ยังอยู่ใน
config\filters.json แน่ ๆ ตามใบงาน) และส่ง cfg/switches ของ area เข้าฟังก์ชันตรง ๆ
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import filters  # noqa: E402
import normalize  # noqa: E402


def job(**kw):
    base = {"title": "", "company": "", "description": "", "raw_text": None,
            "district": None, "province": None, "location": None,
            "skills": [], "seniority": None, "work_mode": None, "sources": [],
            "salary_max": None}
    base.update(kw)
    return base


# cfg ของ area ส่งเข้าตรง ๆ — ไม่พึ่งไฟล์ config ที่ seat อื่นกำลังแก้ควบคู่
AREA_CFG = {
    "provinces": {
        "bangkok": ["bangkok", "กรุงเทพมหานคร"],
        "perimeter": ["nonthaburi", "นนทบุรี"],
        "other": ["chiang mai", "เชียงใหม่"],
    },
}
SW_PERIMETER_OFF = {"area.include_perimeter": False, "area.remote_anywhere": False}
SW_PERIMETER_ON = {"area.include_perimeter": True, "area.remote_anywhere": False}


class AreaHitRegression(unittest.TestCase):
    """defect 1 — province ที่ว่าง/ไม่รู้จักห้ามใช้ตัด, location ดิบไม่ใช่หลักฐาน."""

    def test_province_none_with_indeed_location_not_cut(self):
        # เคสจริงของ Indeed: province = null, location = "40, Thailand" → ไม่ตัด
        j = job(title="Cloud Support Engineer", province=None, location="40, Thailand")
        self.assertFalse(filters.area_hit(j, AREA_CFG, SW_PERIMETER_OFF),
                         "province = null ต้องไม่ถูกตัด แม้ location เป็น '40, Thailand'")
        self.assertIsNone(filters.drop_reason(j, filters.load_config(), SW_PERIMETER_OFF),
                          "แถว Indeed นี้ต้องไม่โดน area_outside")

    def test_province_bangkok_not_cut(self):
        self.assertFalse(filters.area_hit(job(province="Bangkok"), AREA_CFG, SW_PERIMETER_OFF))
        self.assertFalse(filters.area_hit(job(province="กรุงเทพมหานคร"), AREA_CFG, SW_PERIMETER_ON))

    def test_province_perimeter_follows_switch(self):
        j = job(province="Nonthaburi")
        self.assertTrue(filters.area_hit(j, AREA_CFG, SW_PERIMETER_OFF),
                        "ปริมณฑล + สวิตช์ปิด → ตัด (True)")
        self.assertFalse(filters.area_hit(j, AREA_CFG, SW_PERIMETER_ON),
                         "ปริมณฑล + สวิตช์เปิด → ไม่ตัด (False)")

    def test_province_other_known_province_cut(self):
        self.assertTrue(filters.area_hit(job(province="Chiang Mai"), AREA_CFG, SW_PERIMETER_OFF))
        self.assertTrue(filters.area_hit(job(province="เชียงใหม่"), AREA_CFG, SW_PERIMETER_ON),
                        "จังหวัดอื่นที่รู้จักตัดเสมอ ไม่สนสวิตช์ปริมณฑล")

    def test_province_garbage_value_not_cut(self):
        # ค่าขยะที่ไม่ใช่ชื่อจังหวัด = ไม่รู้จัก → ไม่ตัด (location ดิบไม่ถูกใช้ตัดสิน)
        for garbage in ["40, Thailand", "Thailand", "ระยะทาง 40 กม."]:
            with self.subTest(province=garbage):
                self.assertFalse(filters.area_hit(job(province=garbage), AREA_CFG,
                                                  SW_PERIMETER_OFF),
                                 f'province = {garbage!r} ต้องไม่ถูกตัด')


class IncludeViaSkills(unittest.TestCase):
    """defect 2 — คำใน description ถึง include ได้ทาง skills (job_text นับ skills ด้วย)."""

    def test_title_without_cloud_word_passes_via_skills(self):
        # title ไม่มีคำสาย cloud แต่ skills มี docker/aws (สกัดจาก description) → ผ่าน include
        j = job(title="Backend Developer (Python)", skills=["docker", "aws"])
        self.assertIn("docker", filters.job_text(j), "job_text ต้องรวม skills")
        self.assertIn("aws", filters.job_text(j))
        self.assertTrue(filters.matches_include(j, filters.load_config()),
                        "skills มีคำ include ต้องผ่านแม้ title ไม่มีคำสาย cloud")
        self.assertIsNone(filters.drop_reason(j, filters.load_config(), SW_PERIMETER_OFF),
                          "ต้องผ่านทุกด่าน drop_reason is None")

    def test_skills_only_row_not_include_miss(self):
        # กันถอยหลัง: ก่อนแก้ แถวแบบนี้ถูกตัดเป็น include_miss เพราะ job_text ไม่นับ skills
        j = job(title="Systems Engineer", skills=["vmware"])
        self.assertNotEqual(filters.drop_reason(j, filters.load_config(), SW_PERIMETER_OFF),
                            "include_miss")


class MustNotStillIgnoresRawText(unittest.TestCase):
    """คงพฤติกรรมเดิม: must_not ตรวจ title เท่านั้น — ห้ามตัดจาก raw_text."""

    def test_must_not_word_in_raw_text_does_not_cut(self):
        j = job(title="Programmer ด่วน", raw_text="ปิดรับ sales แล้ว ขอบคุณ")
        self.assertIsNone(filters.must_not_hit(j, filters.load_config()),
                          "คำ must_not ใน raw_text ห้ามใช้ตัด")
        self.assertNotIn("must_not", str(filters.drop_reason(j, filters.load_config(),
                                                            SW_PERIMETER_OFF) or ""))


class DetectSkillsFromDescription(unittest.TestCase):
    """defect 2 — detect_skills รวมคำที่สกัดจาก description เพิ่มจาก explicit skills."""

    def test_explicit_plus_description_words_union(self):
        # explicit มาจากแหล่ง, description มี Docker/AWS → ต้องได้ทั้งสองทาง
        got = normalize.detect_skills(
            "Responsibilities: deploy services with Docker on AWS.",
            explicit=["python"],
            filters=normalize.load_filters())
        self.assertIn("python", got, "explicit skills ต้องถูกเก็บไว้")
        self.assertIn("docker", got, "คำใน description ต้องถูกสกัดเพิ่ม")
        self.assertIn("aws", got, "คำใน description ต้องถูกสกัดเพิ่ม")
        self.assertEqual(got, sorted(set(got)), "ต้องเรียงและไม่ซ้ำ")

    def test_description_only_no_explicit(self):
        got = normalize.detect_skills("Manage VMware vSphere and Nutanix clusters.",
                                      explicit=None, filters=normalize.load_filters())
        self.assertIn("vmware", got)
        self.assertIn("nutanix", got)

    def test_explicit_list_not_lost_when_text_has_no_skills(self):
        got = normalize.detect_skills("no tech words here", explicit=["aws"],
                                      filters=normalize.load_filters())
        self.assertEqual(got, ["aws"], "explicit อย่างเดียวก็ต้องคงไว้")


if __name__ == "__main__":
    unittest.main()
