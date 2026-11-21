# SPEC — Job Board ส่วนตัวสำหรับหางาน IT กรุงเทพ (INTAKE v1)

อ้างอิง: `docs\brief-jobboard-v3.md` (FINAL v3, 21 พ.ย. 13:14) · รอบ: INTAKE · 21 พ.ย. 13:2x
สิ่งที่ตรวจแล้ว: โฟลเดอร์โปรเจกต์มีไฟล์เดียวคือ `docs\brief-jobboard-v3.md` (glob `**/*`) — ไม่มีโค้ดให้อ่าน
สภาพแวดล้อม: Python 3.14.5 + pip 26.1.1 (`C:\Python314`) · `pip download` + `pip install --dry-run python-jobspy` ผ่าน (จะได้ pandas 3.1.1, numpy 2.5.5, curl_cffi 0.17, python-jobspy 1.5.0) แต่ยังไม่ติดตั้งจริงและยังไม่ยิงจริง · ไม่มี `APIFY_TOKEN` · `%USERPROFILE%\jobboard` ยังไม่มี และเขียนนอกโฟลเดอร์โปรเจกต์ไม่ได้

## 0. คำตัดสินที่สืบทอดมา (ไม่เปิดใหม่)
- **root ของไฟล์ = `C:\Users\story\aetox-projects\job-board-tz\`** ใช้โครงเดียวกับ §2 (README.md, config\, data\, src\, dist\, runs\, tests\)
- `src\run_all.py` ตั้ง `ROOT = Path(__file__).resolve().parent.parent` → ย้ายทั้งโฟลเดอร์ไป `%USERPROFILE%\jobboard\` ได้โดยไม่แก้โค้ด · **ห้ามมี path absolute ในโค้ดใด ๆ**
- wave 1 ไม่พึ่ง Apify และไม่ใช้เงินเลย

## 1. เป้าหมาย
สร้างเครื่องมือ Python รันในเครื่อง 1 ชุด ที่ดึงประกาศงาน IT กรุงเทพจาก 4 แหล่ง → รวมเป็น schema เดียว → กรองด้วยสวิตช์ → เปิด `dist\index.html` ด้วย file:// ดูได้แบบออฟไลน์ 100%

### done-test รอบแรก (§7 ข้อ 1–3 · วัดได้จริง)
| # | done-test | คำสั่ง/วิธีวัด |
|---|---|---|
| D1 | เทสต์ผ่านทั้งหมด | `python -m pytest tests -q` → exit 0, 0 failed; ครอบ: งานซ้ำ 2 บอร์ดยุบเหลือ 1 แถวและ `sources` มี 2 ค่า · FB ไม่มีฟิลด์ไม่ทำให้ schema พัง · `id` = `<source>:<uid>` หรือ `sha1(url)` · normalize รันซ้ำบน input เดิมจำนวนแถวเท่าเดิม · `status:"gone"` เมื่อ `last_seen` เกิน 14 วัน โดยไม่ลบแถว · filters include/must_not/boost |
| D2 | ยิง JobSpy จริง 1 คำ ได้ ≥ 10 งานจริง | คำสั่งที่ใช้ต้องรายงานมาด้วย; `data\raw\<YYYY-MM-DD>\jobspy.json` มี ≥ 10 ประกาศ และทุกแถว `posted_at`/`company`/`url` ไม่ว่าง |
| D3 | หน้าเว็บทำงานออฟไลน์ | `python src\build_page.py` → มี `dist\index.html` + `dist\data.js`; เปิด file:// เห็นตาราง จำนวนแถว = จำนวน entry ใน `window.JOBS`; สลับ preset strict/balanced/wide แล้วจำนวนแถวเปลี่ยนจริง; ช่องค้น + ชิปกรองทำงาน; 0 request ออกเน็ต (script error 0, failed load 0) |
| D4 | มี log (§11) | `runs\<YYYY-MM-DD>.md` มีบรรทัดต่อแหล่ง: ยิงกี่คำ · ได้กี่งาน · เสียกี่ดอลลาร์ (wave 1 = $0) · error อะไร |

> ข้อสมมติ A1: §0 ข้อ 1 ("≥ 30 แถว") ยืนยันตอนรันเต็ม (wave 2/หลายคำค้น) — รอบแรกวัด ≥ 10 จากข้อ 2 และ "ตารางแสดงครบทุกแถวใน data.js" แทน เพราะรอบแรกยิงคำเดียว

## 2. ไฟล์ทั้งหมด (root = `C:\Users\story\aetox-projects\job-board-tz\`)
| path | หน้าที่ | wave |
|---|---|---|
| `README.md` | วิธีติดตั้ง/รัน 5 บรรทัด | 1 |
| `config\sources.json` | group URL 3 กลุ่ม (§2.1) + keywords FB + `onlyPostsNewerThan`/`resultsLimit`/`viewOption` + คำค้น JobSpy + เพดานต่อแหล่ง (§5) | 1 |
| `config\switches.json` | 12 สวิตช์ชั้น B (§4) + preset 3 ชุด | 1 (ไฟล์) / ผู้ใช้จริง wave 2 |
| `config\filters.json` | include / must_not / boost / salary_min + regex–ลิสต์คำสำหรับ work_mode, seniority, skills (§3) | 1 |
| `config\secrets.env` | `APIFY_TOKEN=...` — **Tz วางเอง** ห้ามคอมมิต ห้ามผ่านแชท | Tz / wave 2 |
| `data\jobs.json` | canonical store ตาม §3 | runtime |
| `data\raw\<YYYY-MM-DD>\<source>.json` | ผลดิบต่อแหล่ง · ลบหลัง 7 วัน | runtime |
| `src\fetch_jobspy.py` | เรียก `python-jobspy` (linkedin/indeed/jobsdb(seek)/google) | 1 |
| `src\fetch_apify.py` | actor JobThai / JobTopGun / FB groups | 2 |
| `src\normalize.py` | แปลงทุกแหล่งเป็น schema เดียว + กันซ้ำ + merge | 1 |
| `src\filters.py` | ให้คะแนน + ตัดด้วย must_not (ใช้ร่วมระหว่าง build กับเทสต์) | 1 |
| `src\build_page.py` | สร้าง `dist\index.html` + `dist\data.js` (`window.JOBS`, `window.META` รวม preset ของชั้น A + สรุป "เมื่อวานได้") | 1 |
| `src\run_all.py` | `ROOT` จาก `__file__` · ลำดับ fetch→normalize→build→log · budget guard · `--clear-session` | 1 (โครง) / 2 (budget+stop) |
| `dist\index.html` | หน้าเว็บ ไทย/อังกฤษผสม (§6) ไม่มี CDN/ฟอนต์เน็ต | 1 (ผลลัพธ์) |
| `dist\data.js` | `window.JOBS=[...]` + `window.META={...}` (ไม่ใช้ fetch บน file://) | 1 (ผลลัพธ์) |
| `runs\<YYYY-MM-DD>.md` | log ต่อรัน | 1 (ผลลัพธ์) |
| `tests\test_normalize.py` | เทสต์กันซ้ำ + schema + gone | 1 |
| `tests\test_filters.py` | เทสต์ include / must_not / boost | 1 |
| `tests\fixtures\board_full.json` | บอร์ดครบฟิลด์ | 1 |
| `tests\fixtures\fb_no_fields.json` | FB ไม่มีฟิลด์ (raw_text >1,500 ตัวอักษร เพื่อทดสอบตัด) | 1 |
| `tests\fixtures\duplicate_two_boards.json` | งานเดียวกัน 2 บอร์ด | 1 |

ไม่สร้างไฟล์นอกตารางนี้ (§2 "สร้างตามนี้เป๊ะ")

## 3. ลำดับ wave
| wave | §7 | ขอบเขต | เกณฑ์ผ่าน | ต้องมี token |
|---|---|---|---|---|
| **1 (รอบนี้)** | ข้อ 1–3 | normalize + fixtures + เทสต์ · fetch_jobspy ยิงจริง 1 คำที่กรุงเทพ · filters + build_page | D1–D4 | ไม่ |
| **2** | ข้อ 4–7 | fetch_apify: JobThai → JobTopGun → FB ทีละกลุ่ม (เริ่มกลุ่ม 1) · budget guard + stop rules | §7 ข้อ 4–7 + §0 ข้อ 2, 5–8 | **ใช่** |

**ติดที่ wave 2:** ยังไม่มี `APIFY_TOKEN` (§8) → ห้ามเริ่ม ห้ามหาทางอื่นแทน รายงานแล้วรอ Tz วาง token ใน `config\secrets.env` · T1 session ก็ยังไม่ได้รับอนุมัติ (ใช้ T0 เท่านั้น)

## 4. ซับงาน [MECH] (ทำได้โดย local-worker-code / local-worker-text · รายการละ 1 ไฟล์)
| # | action | ไฟล์เป้าหมาย |
|---|---|---|
| M1 | สร้าง JSON: group URL 3 กลุ่มจาก §2.1 verbatim + `keywords` 8 คำ + `onlyPostsNewerThan:"2 days"` + `resultsLimit:150` + `viewOption:"CHRONOLOGICAL"` + คำค้น JobSpy + เพดานต่อแหล่งตาม §5 | `config\sources.json` |
| M2 | สร้าง JSON: 12 สวิตช์ตาม §4 ตาราง (ชื่อคีย์ตรงตามตาราง) + preset `strict`/`balanced`/`wide` ค่าตามตาราง §4, default = `balanced` | `config\switches.json` |
| M3 | สร้าง JSON: include / must_not / boost / salary_min + regex–ลิสต์คำสำหรับ work_mode, seniority, skills | `config\filters.json` |
| M4 | สร้าง fixture: 1 ประกาศบอร์ดครบทุกฟิลด์ตาม §3 | `tests\fixtures\board_full.json` |
| M5 | สร้าง fixture: 1 โพสต์ FB ที่มีแค่ title/url/raw_text (raw_text >1,500 ตัวอักษร) ฟิลด์อื่น null | `tests\fixtures\fb_no_fields.json` |
| M6 | สร้าง fixture: งานเดียวกัน 2 บอร์ด (company/title ต่างช่องว่าง+ตัวพิมพ์) | `tests\fixtures\duplicate_two_boards.json` |
| M7 | เขียน README 5 บรรทัด: ติดตั้ง · รัน · เปิด `dist\index.html` · ที่วาง `APIFY_TOKEN` · `--clear-session` | `README.md` |
| M8 (wave 2) | แปลงผล actor JobThai เป็น JSON ตัวอย่างสำหรับเทสต์ (เมื่อ Tz ให้ token) | `tests\fixtures\jobthai_raw.json` |

## 5. ความเสี่ยง + วิธีตรวจ
| # | ความเสี่ยง | วิธีตรวจ | ถ้าติด |
|---|---|---|---|
| R1 | `python-jobspy` ยังไม่ยืนยันว่าใช้ได้บน Python 3.14 (ต้องการ ≥3.10) — metadata ผ่านแล้ว แต่ runtime กับ pandas 3 ยังไม่ทดสอบ | `pip install -U python-jobspy` แล้ว `python -c "import sys,jobspy;print(sys.version,jobspy.__file__)"` + ยิง 1 คำเล็ก ๆ | รายงาน traceback เต็ม **ห้ามแพตช์ไลบรารีเอง**; เสนอ venv Python 3.12/3.13 (ติดตั้ง interpreter = ต้อง Tz อนุมัติ) |
| R2 | LinkedIn 429 | 1 คำ/วัน · 100 ผล/คำ; เจอ 429 → พัก 24 ชม. + log; ห้าม retry รัว | log แล้วข้ามแหล่ง |
| R3 | เทสต์อาจแอบต่อเน็ต ทำให้ D1 เชื่อถือไม่ได้ | รัน `python -m pytest tests -q` โดยไม่ตั้ง env/token ใด ๆ + grep ใน `tests\` ว่าไม่มี requests/urllib/http/socket | แก้เทสต์ให้ใช้ fixture อย่างเดียว |
| R4 | file:// บล็อก fetch → ต้องใช้ `data.js` | เปิด headless ดู script error / failed load = 0 และ HTML ไม่มี URL ภายนอก/CDN | เปลี่ยนเป็น inline `data.js` เท่านั้น |
| R5 | ยุบซ้ำผิด (merge เกิน/ขาด) | เทสต์ M6 + normalize รันซ้ำ 2 รอบต้องได้จำนวนเท่าเดิม + `sources` มี 2 ค่า | แก้ normalize ก่อนส่ง |
| R6 | เดาเงินเดือน / แปล title (§6 ห้าม) | เทสต์: `salary_text:null` → `salary_min/max` ต้อง null; `title` ใน `data.js` ต้องเท่ากับใน fixture ทุกไบต์ | ตัดฟังก์ชันเดาออก |
| R7 | path absolute หลุดเข้าโค้ด | grep `C:\` ใน `src\ dist\ tests\` = 0 · grep `USERPROFILE` ใน `src\` = 0 | แก้เป็น `ROOT` จาก `__file__` |
| R8 | wave 2 ไม่มี token | ไม่มี `APIFY_TOKEN` → เขียน log `no_token` แล้วหยุด ห้ามยิง | รอ Tz |
| R9 | FB `login_walled` / ว่าง (wave 2) | log `login_walled` ต่อกลุ่ม; ว่าง 2 วันติด → หยุด 3 วัน | ห้าม retry รัว |
| R10 | budget guard อ่านยอดจาก `runs\` ผิด (wave 2) | เทสต์ด้วย `runs\` สังเคราะห์: ยอดสะสม ≥ $4.00 → หยุด + log "หยุดเพราะเกินงบ"; ไม่มีไฟล์ = เริ่ม 0 | แก้ parser ก่อนใช้จริง |

## 6. สิ่งที่ห้ามทำ
**§1:** ห้ามทำเว็บ public / GitHub Pages / เซิร์ฟเวอร์ · ห้ามใส่ข้อมูลส่วนตัว (โน้ตสมัครงาน/เรซูเม่/เบอร์) ลง `data\` · ห้ามใช้บัญชีหลักของ Tz กับ scraper
**§5:** T2 **ห้ามเด็ดขาด** (รวมบัญชี LinkedIn ที่ใช้สมัครงาน/Premium) · T1 ต้อง Tz อนุมัติรายครั้งก่อน · ไม่มีคีย์ `session.enabled` = ถือเป็น T0 · ห้ามใส่ session กับ JobSpy/LinkedIn jobs/Indeed/JobsDB/JobThai/JobTopGun · cookie ห้ามผ่านแชท ห้ามคอมมิต (เฉพาะ `config\secrets.env`)
**§6:** ห้ามเดาเงินเดือน (ไม่มี `salary_text` = เว้นว่าง) · ห้ามแปล `title`/`company`/`district` · ห้ามใช้ CDN/ฟอนต์จากเน็ต
**§3:** `work_mode`/`seniority`/`skills` ไม่ชัด = `null` ห้ามเดามั่ว · งานหาย >14 วัน = `status:"gone"` ห้ามลบแถว · `raw_text` ตัดที่ 1,500 ตัวอักษร · ห้ามเดา FB numeric id (ตาม share link ไม่ได้ → log `unresolved_share_link`)
**§4:** ห้าม retry รัว · หยุดทันทีเมื่อยอดสะสมเดือน ≥ $4.00
**§8/§10:** ห้ามเริ่ม Apify ก่อนมี token · ห้ามขึ้นเพดานราคา / เปลี่ยน path root / แตะบัญชี FB–LinkedIn เอง (propose-first)
**§9:** เรียกทีม/เครื่องมือที่ต้องใช้ไม่ได้ → **หยุด รายงานหลักฐาน แล้วรอ ห้ามทำแทนเอง**

## 7. สิ่งที่ codeDev ต้องส่งกลับเพื่อให้ตรวจได้
1. คำสั่งเทสต์แคบ: `python -m pytest tests\test_normalize.py -q` และ `python -m pytest tests\test_filters.py -q`
2. ชุดเต็ม: `python -m pytest tests -q` + ผลดิบ (จำนวน passed/failed + exit code)
3. path หน้าเว็บ: `C:\Users\story\aetox-projects\job-board-tz\dist\index.html` (+ `dist\data.js`)
4. คำสั่งที่ใช้ยิง JobSpy จริง, คำค้นที่ใช้, จำนวนงานที่ได้, path `data\raw\<YYYY-MM-DD>\jobspy.json`
5. `runs\<YYYY-MM-DD>.md`
6. `python --version` และ `pip show python-jobspy` (เวอร์ชันที่ติดตั้งจริง)
7. รายชื่อไฟล์ที่สร้าง/แก้ + ยืนยันว่าไม่มี `config\secrets.env` ในนั้น
8. วิธี/ผลที่ยืนยันว่าหน้าเว็บไม่มีการเรียกออกเน็ต (script error 0, failed load 0)

## 8. ข้อสมมติ (ใบงานไม่ระบุ — ระบุเหตุผล)
- **A1** รอบแรกวัด ≥10 งานจริง (ตาม §7 ข้อ 2) แทน ≥30 แถวของ §0 ข้อ 1 เพราะรอบแรกยิงคำเดียว; ≥30 วัดตอนรันเต็ม
- **A2** `src\run_all.py` อยู่ใน wave 1 แบบโครง (ยังไม่มี budget guard/Apify) เพราะ §11 ให้ส่ง log มาพร้อมรอบแรก และ §12 กำหนดให้ `ROOT` อยู่ที่ไฟล์นี้
- **A3** budget guard + stop rules = wave 2 ตาม §7 ข้อ 7 แม้ §4 จะวางไว้ใน `run_all.py`
- **A4** `config\secrets.env` เป็นไฟล์ที่ Tz สร้าง; wave 1 ต้องรันผ่านได้เมื่อไฟล์นี้ไม่มี
- **A5** ตัวรันเทสต์ = `unittest` ของ stdlib (ไม่ต้องติดตั้งอะไร) เว้นแต่ pytest มีอยู่แล้วในเครื่อง — ห้ามติดตั้งแพ็กเกจเพิ่มโดยไม่รายงาน
- **A6** คำค้น JobSpy ไม่ระบุในใบงาน → ใส่ชุดเริ่มต้นใน `config\sources.json` (developer, programmer, IT support, data, QA, devops, security) จำนวนคำต้องไม่ทำให้เกินเพดาน §5
- **A7** preset ของชั้น A ฝังใน `window.META.presets` ที่ `build_page.py` สร้าง (ไม่ fetch ไฟล์ config บน file://) ค่าตรงกับ §4
- **A8** หน้าเว็บ "แถบล่าง เมื่อวานได้" อ่านตัวเลขจาก log `runs\` วันก่อนที่ `build_page.py` ฝังใน `META` (ไม่มี log = แสดง "-")
