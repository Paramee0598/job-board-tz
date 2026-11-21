# Job Board Tz — เครื่องมือหางาน IT กรุงเทพ (รันในเครื่อง 100%)

1. **ติดตั้ง:** `pip install -U python-jobspy` (Python ≥ 3.10 · เครื่องนี้ 3.14.5 ผ่าน)
2. **รัน:** `python src\run_all.py` (เติม `--preset wide` หรือ `--skip-fetch` ได้ · ทุกไฟล์อยู่ใต้โฟลเดอร์นี้ ไม่มี path absolute ในโค้ด)
3. **ดูผล:** ดับเบิลคลิก `dist\index.html` เปิดด้วย file:// ได้เลย — ออฟไลน์ ไม่มี CDN ไม่มีเซิร์ฟเวอร์
4. **`APIFY_TOKEN`:** วางเองใน `config\secrets.env` เป็นบรรทัด `APIFY_TOKEN=...` (wave 2 · ห้ามส่งทางแชท ห้ามคอมมิต) — ไม่มีไฟล์นี้ก็รัน wave 1 ได้ครบ
5. **หน้า dashboard (GitHub Pages):** https://paramee0598.github.io/job-board-tz/ — ตารางงาน (`dist\index.html` · ออฟไลน์ 100%)
6. **หน้า map:** https://paramee0598.github.io/job-board-tz/map.html — บริษัทในประกาศงานปักหมุดบนแผนที่กรุงเทพ (`dist\map.html` · แยกหน้าจาก dashboard แต่ repo เดียวกัน · มีลิงก์ "แผนที่บริษัท →" บน dashboard)
7. **คีย์แผนที่:** วาง `GOOGLE_MAPS_API_KEY=...` ใน `config\secrets.env` (อยู่ใน `.gitignore` — ห้ามคอมมิต) แล้วรัน `python src\geocode_companies.py` → `python src\build_map.py` · ไม่มีคีย์ก็ build ได้ (ได้หน้าแบนเนอร์บอกวิธี ไม่เรียก Google) · คีย์ถูกฝังใน `dist\map.html` ตอน build เพราะ Maps JS ต้องใช้ฝั่ง client → **จำกัดคีย์ด้วย HTTP referrer ของ Pages**
8. **`--clear-session`:** `python src\run_all.py --clear-session` ลบ cookie/session ทั้งหมดแล้ว **จบ** (exit 0 ไม่ดึงข้อมูล · T0 = ไม่มีอะไรให้ลบ) · ถ้าจะล้างแล้วรันต่อต้องเติม `--run`: `python src\run_all.py --clear-session --run` · ค่าเริ่มต้นไม่ใช้ session ใด ๆ
