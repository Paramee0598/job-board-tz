# Job Board Tz — เครื่องมือหางาน IT กรุงเทพ (รันในเครื่อง 100%)

1. **ติดตั้ง:** `pip install -U python-jobspy` (Python ≥ 3.10 · เครื่องนี้ 3.14.5 ผ่าน)
2. **รัน:** `python src\run_all.py` (เติม `--preset wide` หรือ `--skip-fetch` ได้ · ทุกไฟล์อยู่ใต้โฟลเดอร์นี้ ไม่มี path absolute ในโค้ด)
3. **ดูผล:** ดับเบิลคลิก `dist\index.html` เปิดด้วย file:// ได้เลย — ออฟไลน์ ไม่มี CDN ไม่มีเซิร์ฟเวอร์
4. **`APIFY_TOKEN`:** วางเองใน `config\secrets.env` เป็นบรรทัด `APIFY_TOKEN=...` (wave 2 · ห้ามส่งทางแชท ห้ามคอมมิต) — ไม่มีไฟล์นี้ก็รัน wave 1 ได้ครบ
5. **`--clear-session`:** `python src\run_all.py --clear-session` ลบ cookie/session ทั้งหมดแล้ว **จบ** (exit 0 ไม่ดึงข้อมูล · T0 = ไม่มีอะไรให้ลบ) · ถ้าจะล้างแล้วรันต่อต้องเติม `--run`: `python src\run_all.py --clear-session --run` · ค่าเริ่มต้นไม่ใช้ session ใด ๆ
