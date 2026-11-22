"""test_map_views.py — เทสต์มุมมองแผนที่ 3 โหมด (src/build_map.py → dist/map.html)

อ่าน dist/map.html แบบ static (ไม่เปิดเบราว์เซอร์ ไม่ยิงเน็ต):
· ปุ่ม data-view="all"|"pinned"|"mix" ครบทั้ง 3 ค่า (ขาดค่าใดค่าหนึ่ง = แดง)
· ปุ่มแต่ละปุ่มมี aria-pressed
· เก็บสถานะใน localStorage['jobboard.mapview'] + รองรับ ?view=
· ข้อความ "ยังไม่มีงานที่ปักหมุด" และ id="viewempty"

ถ้า dist/map.html ยังไม่ถูก build → skip ทั้งคลาสพร้อมเหตุผล
(ไม่รัน build_map.py เอง เพราะกติกาห้ามแตะ dist/*)

รัน: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "dist" / "map.html"

VIEWS = ("all", "pinned", "mix")
EMPTY_TEXT = "ยังไม่มีงานที่ปักหมุด"
VIEW_KEY = "jobboard.mapview"


@unittest.skipUnless(MAP.is_file(), "dist/map.html ยังไม่มี — รัน python src/build_map.py ก่อน")
class TestMapViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = MAP.read_text(encoding="utf-8")

    def test_button_all_present(self):
        self.assertIn('data-view="all"', self.html, "ปุ่ม data-view=\"all\" หายไปจาก dist/map.html")

    def test_button_pinned_present(self):
        self.assertIn('data-view="pinned"', self.html, "ปุ่ม data-view=\"pinned\" หายไปจาก dist/map.html")

    def test_button_mix_present(self):
        self.assertIn('data-view="mix"', self.html, "ปุ่ม data-view=\"mix\" หายไปจาก dist/map.html")

    def test_all_three_views_present(self):
        # เคสรวม: ขาดปุ่มใดปุ่มหนึ่งต้องแดง ไม่ใช่ผ่านเพราะเจอแค่ค่าเดียว
        missing = [v for v in VIEWS if f'data-view="{v}"' not in self.html]
        self.assertEqual(missing, [], f"ปุ่ม data-view ขาด: {missing}")

    def test_buttons_have_aria_pressed(self):
        for v in VIEWS:
            self.assertRegex(
                self.html,
                rf'data-view="{v}"[^>]*aria-pressed=',
                f'ปุ่ม data-view="{v}" ไม่มี aria-pressed')

    def test_localstorage_view_key(self):
        self.assertIn(VIEW_KEY, self.html, f"ไม่พบ localStorage key {VIEW_KEY!r}")

    def test_query_param_view_supported(self):
        self.assertRegex(self.html, r"[?&]view=", "ไม่พบการรองรับ query ?view=")

    def test_empty_state_text_and_id(self):
        self.assertIn(EMPTY_TEXT, self.html, f"ไม่พบข้อความ {EMPTY_TEXT!r}")
        self.assertRegex(self.html, r'id="viewempty"', "ไม่พบ id=\"viewempty\"")


if __name__ == "__main__":
    unittest.main()
