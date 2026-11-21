r"""test_pages_controls.py — เทสต์ปุ่มปักหมุด/ดูแล้ว บน dashboard + แผงปักหมุดบน map

อ่านไฟล์ HTML ที่ generate ไว้เท่านั้น — ไม่เปิดเบราว์เซอร์ (unittest stdlib)

สัญญาที่ตรวจ (ตามใบงาน)
  · dist\index.html มี localStorage key 'jobboard.pins' และ 'jobboard.seen'
  · dist\index.html มีลิงก์/ปุ่มที่ชี้ไป map.html
  · ทุกงานใน window.JOBS ต้องได้ปุ่มของตัวเองตอน render — ตารางสร้างฝั่ง client
    จาก dist\data.js (window.JOBS) จึงไม่มี data-pin="<id>" พิมพ์ลง HTML ตอน build;
    เทสต์จึงตรวจ "กลไกสร้างปุ่มต่อแถว" ใน dist\index.html แทนจำนวนปุ่มในไฟล์
  · dist\map.html อ่านปักหมุดได้ 2 ทาง: '?pins=' ใน URL หรือ localStorage 'jobboard.pins'
  · dist\map.html มีแผง "งานที่ปักหมุดไว้"

กติกา
  · ถ้า dist\index.html ไม่มี → สร้างใหม่ด้วย subprocess: python src\build_page.py (เขียน dist\)
  · ถ้า dist\map.html ไม่มี → skip อย่างชัดเจน (ไม่รัน build_map.py แทน — ต้องมีคีย์/ข้อมูล geocode)
  · ไม่เทสต์ค่าที่ขึ้นกับเวลา (generated_at / built_at / จำนวนนาที)
  · ไม่มี path absolute — ROOT มาจาก __file__
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
INDEX_PATH = DIST / "index.html"
DATAJS_PATH = DIST / "data.js"
MAP_PATH = DIST / "map.html"

PINS_KEY = "jobboard.pins"
SEEN_KEY = "jobboard.seen"
def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def jobs_from_datajs() -> list:
    r"""อ่าน window.JOBS จาก dist\data.js (หน้า dashboard โหลดข้อมูลจากไฟล์นี้)."""
    text = read_text(DATAJS_PATH)
    start = text.index("window.JOBS")
    eq = text.index("=", start)
    end = text.index("window.META")
    payload = text[eq + 1:end].strip()
    if payload.endswith(";"):
        payload = payload[:-1]
    rows = json.loads(payload)
    assert isinstance(rows, list), "window.JOBS ต้องเป็น array"
    return rows


def job_ids(rows: list) -> set:
    return {str(row.get("id")) for row in rows if row.get("id") is not None}


class DashboardControlsTest(unittest.TestCase):
    r"""หน้า dashboard (dist\index.html): ปุ่มปักหมุด/ดูแล้ว + ชิปนับ + ลิงก์ map."""

    @classmethod
    def setUpClass(cls):
        if not INDEX_PATH.exists():
            # เลือกสร้างใหม่ด้วย subprocess (ตามทางเลือกแรกของใบงาน) — เขียน dist\
            proc = subprocess.run(
                [sys.executable, "src/build_page.py"],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise unittest.SkipTest(
                    "dist\\index.html ไม่มีและสร้างใหม่ไม่สำเร็จ: "
                    + (proc.stderr or proc.stdout).strip()[:300]
                )
        if not INDEX_PATH.exists():
            raise unittest.SkipTest("dist\\index.html ยังไม่มี — รัน python src\\build_page.py ก่อน")
        cls.html = read_text(INDEX_PATH)

    def test_index_has_pins_localstorage_key(self):
        """สัญญา localStorage: ปุ่มปักหมุดเก็บที่ 'jobboard.pins'."""
        self.assertTrue(PINS_KEY in self.html,
                        "dist\\index.html ต้องอ้าง localStorage key 'jobboard.pins'")

    def test_index_has_seen_localstorage_key(self):
        """สัญญา localStorage: ปุ่มดูแล้วเก็บที่ 'jobboard.seen'."""
        self.assertTrue(SEEN_KEY in self.html,
                        "dist\\index.html ต้องอ้าง localStorage key 'jobboard.seen'")

    def test_index_links_to_map(self):
        """มีลิงก์/ปุ่มที่ชี้ไป map.html (href หรือการเปิดหน้า map.html)."""
        has_href = re.search(r'href=["\']map\.html', self.html) is not None
        has_nav = "map.html" in self.html
        self.assertTrue(has_nav,
                        "dist\\index.html ต้องมีลิงก์/ปุ่มไป map.html (เช่น href=\"map.html\")")
        self.assertTrue(has_href, "ควรชี้ map.html ด้วย href ตรง ๆ เพื่อเปิดได้แม้ JS พัง")

    def test_index_has_pin_attribute(self):
        """กลไกสร้าง attribute ปักหมุดต้องมีจริง: ปุ่มต่อแถวถูกเซ็ต data-pin/data-seen พร้อมผูก id.

        ตาราง render ฝั่ง client จาก dist\data.js จึงไม่มี data-pin="<id>" ใน HTML ตอน build —
        ตรวจชื่อ attribute + จุดเซ็ตต่อแถวแทน และยังแดงถ้าปุ่มถูกถอดออก (ไม่มี data-pin /
        ไม่มีจุดผูก id ต่อปุ่ม = fail ตามความหมายเดิม).
        """
        self.assertTrue('data-pin' in self.html,
                        "dist\\index.html ต้องมีชื่อ attribute 'data-pin' ที่ปุ่มปักหมุดใช้")
        self.assertTrue('data-seen' in self.html,
                        "dist\\index.html ต้องมีชื่อ attribute 'data-seen' ที่ปุ่มดูแล้วใช้")
        sets_per_row = ('dataset.jobId' in self.html
                        or re.search(r"setAttribute\([^)]*'data-pin'", self.html) is not None)
        self.assertTrue(sets_per_row,
                        "ต้องมีจุดเซ็ต attribute ต่อแถว (dataset.jobId หรือ setAttribute(... 'data-pin' ...))")
        binds_id = re.search(r"['\"]pin-['\"][^;\n]*\+\s*id", self.html) is not None
        self.assertTrue(binds_id,
                        "ต้องมีการผูก id ต่อปุ่ม (เช่น btn.id = 'pin-' + id) เพื่อให้ปุ่มชี้งานของตัวเอง")

    def test_every_job_gets_own_button_on_render(self):
        """ทุกงานใน window.JOBS ต้องได้ปุ่มของตัวเองเมื่อ render.

        เหตุผลที่ตรวจกลไกแทนจำนวนปุ่มใน HTML: ตารางสร้างฝั่ง client จาก dist\data.js
        (window.JOBS — ปัจจุบัน 61 รายการ) แถวทั้งหมดถูกสร้างตอน runtime จึงไม่มีปุ่ม
        พิมพ์ลงไฟล์ HTML ตอน build; การนับ data-pin ในไฟล์จึงเป็น 0 เสมอ ไม่ใช่โค้ดพัง.
        """
        rows = jobs_from_datajs()
        self.assertGreater(len(rows), 0, "window.JOBS ต้องมีงานอย่างน้อย 1 แถว")
        # ฟังก์ชันสร้างปุ่มต่อแถว: markButton('pin', id, ...) ต้องถูกเรียกต่องาน
        self.assertTrue(re.search(r"markButton\(\s*['\"]pin['\"]\s*,\s*id", self.html) is not None,
                        "ต้องมีการเรียก markButton('pin', id, ...) ต่อแถวงาน")
        # และปุ่มนั้นต้องเซ็ต data-pin ในฟังก์ชันเดียวกัน
        self.assertTrue(re.search(r"setAttribute\([^)]*'data-pin'", self.html) is not None,
                        "markButton ต้องเซ็ต attribute 'data-pin' ให้ปุ่ม")
        # และตารางต้องวนทุกแถวงานเพื่อสร้างปุ่ม (renderTable → rows.forEach → markCell)
        self.assertTrue(re.search(r"rows\.forEach\(function\s*\(job\)", self.html) is not None,
                        "renderTable ต้องวนสร้างแถวจากทุกงาน (rows.forEach)")
        self.assertTrue('markCell(job)' in self.html,
                        "ทุกแถวที่วนได้ต้องเรียก markCell(job) เพื่อใส่ปุ่มของงานนั้น")


class MapPinsTest(unittest.TestCase):
    r"""หน้า map (dist\map.html): อ่านปักหมุด 2 ทาง + แผงงานที่ปักหมุดไว้."""

    @classmethod
    def setUpClass(cls):
        if not MAP_PATH.exists():
            raise unittest.SkipTest(
                "dist\\map.html ยังไม่มี — ไม่รัน build_map.py แทน (ต้องมีคีย์/ข้อมูล geocode); "
                "รัน python src\\build_map.py ก่อนแล้วรันเทสต์ซ้ำ")
        cls.html = read_text(MAP_PATH)

    def test_map_reads_pins_from_url_or_storage(self):
        """รองรับ 2 ทาง: '?pins=id1,id2' ใน URL หรืออ่าน localStorage 'jobboard.pins' — อย่างน้อย 1 ทาง."""
        from_url = "?pins=" in self.html
        from_storage = PINS_KEY in self.html
        self.assertTrue(from_url or from_storage,
                        "dist\\map.html ต้องอ่านปักหมุดจาก '?pins=' หรือ localStorage 'jobboard.pins'")

    def test_map_has_both_pin_sources_and_panel(self):
        """ปิดช่องของเคส OR (เคสบน): map ต้องรองรับ 'jobboard.pins' และ '?pins=' ครบทั้ง 2 ทาง
        พร้อมแผง 'งานที่ปักหมุดไว้' — ขาดทางใดทางหนึ่งถือว่าไม่ครบสัญญา."""
        self.assertTrue(PINS_KEY in self.html,
                        "dist\\map.html ต้องอ่าน localStorage 'jobboard.pins'")
        self.assertTrue('pins=' in self.html,
                        "dist\\map.html ต้องอ่านปักหมุดจาก query '?pins='")
        self.assertTrue('งานที่ปักหมุดไว้' in self.html,
                        "dist\\map.html ต้องมีแผง 'งานที่ปักหมุดไว้'")

    def test_map_has_pinned_panel(self):
        """มีแผง "งานที่ปักหมุดไว้" บนหน้า map."""
        self.assertTrue("งานที่ปักหมุดไว้" in self.html,
                        "dist\\map.html ต้องมีแผง 'งานที่ปักหมุดไว้'")


if __name__ == "__main__":
    unittest.main()
