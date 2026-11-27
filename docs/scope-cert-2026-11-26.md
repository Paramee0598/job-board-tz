# Scope ข้อมูลงานรอบ 26 พ.ย. 2026 — เพื่อวิเคราะห์ใบ Cert ต่อ

สรุปขอบเขตของข้อมูลที่มีในคลัง ณ รอบดึง 2026-11-26T22:24 ใช้เป็นโจทย์ตั้งต้นสำหรับขั้นวิเคราะห์ "ควรสอบใบ Cert อะไร"
ตัวเลขทุกตัวนับจาก `data/jobs.json` (2,012 แถว) และ `runs/2026-11-26.md` ในวันนี้

## 1. ข้อมูลที่มี

| แหล่ง | งาน (unique) | หมายเหตุ |
|---|---|---|
| linkedin | 529 | 543 tag — บางงานเจอหลายแหล่ง; บางคำค้นถูก 429 (cloud engineer, infrastructure, vmware) |
| jobsdb | 515 | ครบทุกคำค้น |
| jobtopgun | 448 + 21 (probe) | เว็บฟรี ไม่ใช้ Apify |
| jobthai | 370 | เว็บฟรี; note: no_cards |
| indeed | 150 | หลายคำค้นได้ no_rows_returned |
| google | 0 | ติด block ทั้ง 10 คำค้น → ไม่มีข้อมูล |
| facebook | 0 | ยังไม่มี APIFY_TOKEN |

- รวม **2,012 งาน** สถานะ active ทั้งหมด, โพสต์ภายใน 72 ชม.ก่อนรอบดึง (posted_at 23–26 พ.ย.)
- ทำเล: **กรุงเทพฯ+ปริมณฑล ~1,548 งาน (~77%)** (Bangkok 971, กรุงเทพมหานคร 326, กรุงเทพ 75, กทม 14, นนทบุรี 36, สมุทรปราการ 32, ปทุมธานี 31, Pathum Thani 28, Samut Prakan 24, สมุทรสาคร 11); รองลงมาเป็นกลุ่มอีอีซี/อยุธยา (ชลบุรี 39, ระยอง 38, พระนครศรีอยุธยา 39)

## 2. คำค้นที่ใช้ = กรอบตลาดที่สำรวจ

- สายงาน: `devops`, `cloud engineer`, `site reliability`, `infrastructure`, `system engineer`
- เทคโนโลยี: `aws`, `kubernetes`, `vmware`, `nutanix`, `proxmox`, `hyper-v`, `esxi`, `virtualization`

→ scope นี้มองตลาด **Cloud / DevOps / SRE / Infrastructure / Virtualization** เท่านั้น ยังไม่ครอบสาย dev ทั่วไป (สัญญาณ java/javascript ที่เจอเป็นส่วนประกอบใน JD จริงของสาย infra)

## 3. สิ่งที่วัดได้จากคลังตอนนี้

- **ระดับอาวุโส** (เฉพาะแถวที่ระบุ): manager 271 · senior 265 · lead 114 · junior 31 · intern 28 · mid 7 → ตลาดมีงานระดับกลาง-สูงมากกว่าเด็กจบใหม่ (แต่ field นี้เติมไม่ครบ ดูข้อ 4)
- **ประเภทงาน**: fulltime 582 · contract 6 · parttime 3 (ที่เหลือไม่ระบุ)
- **เงินเดือน**: มีตัวเลขแค่ 226/2,012 (11%)
- **ทักษะที่ตรวจเจอ** (เฉพาะ ~22% ของงานที่มี description ให้สกัด): security 135 · cloud 92 · infrastructure 90 · networking 82 · qa 58 · devops 43 · aws 37 · azure 14 · java/javascript/python/sre/storage 14 · kubernetes 10 · gcp 9 · docker 8 · linux 6 · terraform 5
  → ภาพรวม: กลุ่ม **network/security/infra/cloud** ใหญ่ที่สุด, ใน cloud ตัว **AWS นำ Azure/GCP**, stack devops ที่เห็นคือ **Kubernetes + Docker + Terraform**

## 4. ข้อจำกัดที่ต้องรู้ก่อนวิเคราะห์ cert

1. **ไม่มี description/raw_text ในคลังเลย (0 แถว)** — jobthai/jobtopgun (818 งาน) scrape มาแค่การ์ดหน้า list (title/company) `skills` จึงสกัดได้จาก title/company เป็นหลัก → งานทั้ง 818 แถวแทบไม่มีสัญญาณทักษะ
2. **คำค้นเทคโนโลยี ≠ สัญญาณในคลัง**: ค้น `vmware`/`nutanix`/`proxmox`/`hyper-v` ได้งาน 300+ แถว (match ผ่าน search engine ของเว็บต้นทาง) แต่ field skills = 0 เพราะเหตุผลที่แมตช์ไม่ถูกเก็บลงคลัง → ความต้องการสาย virtualization ต้องนับจาก "คำค้นได้กี่งาน" ใน runs log ไม่ใช่จาก field skills
3. **skills ถูกจำกัดด้วย dictionary** (`config/filters.json`) — เทคโนโลยีที่ไม่อยู่ในรายการจะไม่ถูกนับเลย
4. **google/facebook หายทั้งกระดาน** และ linkedin โดน 429 3 คำค้น → บางส่วนของตลาดไม่ถูกสำรวจ
5. **work_mode ระบุแค่ 65 แถว** → ยังสรุป remote/hybrid/onsite ไม่ได้
6. **jobtopgun ได้ 30 แถว/หน้าเท่ากันทุกคำค้น** → สงสัยผลค้นไม่เจาะจงคำค้น (หน้าซ้ำ/ชุดเดียวกัน) ต้องตรวจสอบก่อนเอาไปสรุปความต้องการรายเทคโนโลยี

## 5. ประเด็นที่ขั้นวิเคราะห์ cert ควรโฟกัส

- เทคโนโลยีชัดเจน: **AWS (นำ), Kubernetes/Docker/Terraform, Network, Security, Infra/Storage**
- **Virtualization (VMware/Nutanix/Proxmox/Hyper-V) เป็น niche ที่มีงานจริง** (คำค้นได้ 300+ แถว) แต่สัญญาณอ่อนในคลัง → ยืนยันด้วยข้อมูลรอบหน้าหรือแหล่งอื่นก่อนตัดสินใจ
- ตลาดโฟกัส **กรุงเทพ+ปริมณฑล ระดับ senior/lead/manager** → cert ที่สู้ตลาดนี้ควรมีคู่แข่งน้อยในระดับกลาง-สูง

## 6. ไฟล์อ้างอิง

- `data/jobs.json` — คลังรวม 2,012 งาน
- `data/raw/2026-11-26/{jobspy,jobthai,jobtopgun}.json` — ข้อมูลดิบรอบนี้
- `runs/2026-11-26.md` — log การยิง (คำค้น, ผลต่อแหล่ง, error)
- `config/filters.json` — dictionary ที่ใช้สกัด skills
