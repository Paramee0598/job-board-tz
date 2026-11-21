# ใบงาน: Job Board ส่วนตัวสำหรับหางาน IT กรุงเทพ (รันในเครื่อง) → โต๊ะโค้ด

สถานะ: **FINAL v3 (21 พ.ย. 13:14)** — ทุกข้อตัดสินครบ พร้อมส่งโต๊ะโค้ดทันที · ผู้สั่งงาน: Tz · เอกสารนี้เป็นใบงานเดียวที่ผู้รับงานต้องอ่าน
v2 เพิ่ม: ลิงก์กลุ่ม Facebook 3 กลุ่มที่แปลงเป็น group URL แล้ว + นโยบาย session/login
v3 เพิ่ม: ปิดคำตัดสินที่เหลือ — path root `%USERPROFILE%\jobboard\` และภาษา UI ผสม ไทย/อังกฤษ (กฎใน §6)

---

## 0. สรุปสั้น

สร้างเครื่องมือรันในเครื่อง 1 ชุด: ดึงประกาศงาน IT ในกรุงเทพจาก 4 แหล่ง
→ รวมเป็น schema เดียว → กรองด้วยสวิตช์ที่เปิด/ปิดได้ → เปิดหน้า HTML ในเครื่องดูได้
**ไม่ต้องมีเซิร์ฟเวอร์ ไม่ขึ้น GitHub Pages ไม่ใช้บัญชีหลักของ Tz กับ scraper (session มีเฉพาะ T1 ที่ Tz อนุมัติ — §5)**

**เกณฑ์เสร็จ (วัดได้ ทุกข้อต้องผ่าน):**

1. `dist\index.html` เปิดด้วยดับเบิลคลิก (file://) แล้วเห็นตารางงาน ≥ 30 แถว โดยไม่ต่อเน็ต
2. งานเดียวกันที่เจอ 2 บอร์ด ยุบเหลือแถวเดียว และ `sources` มีทั้งสองค่า
3. ทุกแถวมี `title`, `company`, `url`, `posted_at` ครบ (ยกเว้นแถวจาก Facebook ที่ `raw_text` แทนได้)
4. มี preset `strict / balanced / wide` ในหน้าเว็บ กดสลับแล้วจำนวนแถวเปลี่ยนจริง
5. `runs\<วันที่>.md` มีบรรทัดสรุปต่อแหล่ง: ยิงกี่คำ ได้กี่งาน เสียกี่ดอลลาร์ error อะไร
6. จำลอง error (ตัด token) แล้วระบบ **หยุดและเขียน log** ไม่ retry รัว
7. รันครบรอบ (4 แหล่ง) ใช้เวลา < 10 นาที และยอดรวมต่อวัน < $0.25
8. ยิง FB ครบทั้ง 3 กลุ่ม และ log ระบุจำนวนโพสต์ต่อกลุ่ม หรือระบุชัดว่า `login_walled` (ห้ามค้างเงียบ)

---

## 1. บริบท (ทำไมต้องมี)

- **เพื่อใคร:** Tz คนเดียว หางานสาย IT ในกรุงเทพ เปิดดูเองบนเครื่องตัวเอง
- **ทำไม:** งาน IT ไทยกระจายอยู่หลายบอร์ด + งานในกลุ่ม Facebook หลุดง่ายและไม่มีใครเก็บ
- **ไม่ทำเด็ดขาด:** ไม่ทำเว็บ public, ไม่ใส่ข้อมูลส่วนตัว (โน้ตสมัครงาน/เรซูเม่/เบอร์) ลงในคลังข้อมูล,
  ไม่ใช้บัญชีหลักของ Tz กับ scraper ใด ๆ (นโยบาย session อยู่ใน §5)

---

## 2. เส้นทางไฟล์ทั้งหมด (สร้างตามนี้เป๊ะ)

root: `%USERPROFILE%\jobboard\`  ← ถ้าจะย้าย แก้ที่ `src\run_all.py` ตัวแปร `ROOT` ที่เดียว

| path | หน้าที่ |
|---|---|
| `%USERPROFILE%\jobboard\README.md` | วิธีติดตั้ง/รัน 5 บรรทัด |
| `%USERPROFILE%\jobboard\config\sources.json` | ลิงก์กลุ่ม FB, คำค้น, เพดานต่อแหล่ง |
| `%USERPROFILE%\jobboard\config\switches.json` | สวิตช์ทั้ง 12 ตัว + preset 3 ชุด |
| `%USERPROFILE%\jobboard\config\filters.json` | include / must_not / boost / เงินเดือนขั้นต่ำ |
| `%USERPROFILE%\jobboard\config\secrets.env` | `APIFY_TOKEN=...` (Tz วางเอง · ห้ามคอมมิต) |
| `%USERPROFILE%\jobboard\data\jobs.json` | คลังหลัก (canonical store) |
| `%USERPROFILE%\jobboard\data\raw\<YYYY-MM-DD>\<source>.json` | ผลดิบต่อแหล่ง · ลบหลัง 7 วัน |
| `%USERPROFILE%\jobboard\src\fetch_jobspy.py` | เรียก `python-jobspy` (LinkedIn/Indeed/JobsDB/Google) |
| `%USERPROFILE%\jobboard\src\fetch_apify.py` | เรียก actor JobThai / JobTopGun / FB groups |
| `%USERPROFILE%\jobboard\src\normalize.py` | แปลงทุกแหล่งเป็น schema เดียว + กันซ้ำ + merge |
| `%USERPROFILE%\jobboard\src\filters.py` | ให้คะแนน + ตัดด้วย `must_not` (ใช้ร่วมกันระหว่าง build กับเทสต์) |
| `%USERPROFILE%\jobboard\src\build_page.py` | สร้าง `dist\index.html` + `dist\data.js` |
| `%USERPROFILE%\jobboard\src\run_all.py` | ตัวคุมลำดับ: budget guard → fetch → normalize → build → log |
| `%USERPROFILE%\jobboard\dist\index.html` | หน้าเว็บ (ไม่ต่อเน็ต ไม่อ้าง CDN) |
| `%USERPROFILE%\jobboard\dist\data.js` | `window.JOBS = [...]` + `window.META = {...}` |
| `%USERPROFILE%\jobboard\runs\<YYYY-MM-DD>.md` | log ต่อรัน |
| `%USERPROFILE%\jobboard\tests\test_normalize.py` | เทสต์กันซ้ำ + schema |
| `%USERPROFILE%\jobboard\tests\test_filters.py` | เทสต์ include/must_not/boost |
| `%USERPROFILE%\jobboard\tests\fixtures\` | ไฟล์ตัวอย่าง 3 แบบ (บอร์ดครบฟิลด์ / FB ไม่มีฟิลด์ / งานซ้ำ 2 บอร์ด) |

หมายเหตุ: `dist` ใช้ `data.js` ไม่ใช่ `jobs.json` + `fetch()` เพราะเบราว์เซอร์บล็อก fetch บน file://

### 2.1 กลุ่ม Facebook ที่ใช้ (แปลงเป็น group URL แล้ว · 21 พ.ย. 13:10)

| # | กลุ่ม | group URL ที่ใช้จริง | ลิงก์ที่ Tz ให้ |
|---|---|---|---|
| 1 | หางานไอที IT Thailand | `https://www.facebook.com/groups/744726133758655/` | `https://www.facebook.com/share/g/1KBd7mGcLb/` |
| 2 | หางาน IT Security / Cybersecurity / Pentester | `https://www.facebook.com/groups/700493471102196/` | `https://www.facebook.com/share/g/1CFgDZbfSt/` |
| 3 | Job for Thai programmer / Developer | `https://www.facebook.com/groups/1096603433739674/` | `https://www.facebook.com/share/g/16b64rFWan3/` |

ใส่ใน `config\sources.json` แบบนี้ (ใช้ group URL ไม่ใช่ share link):

```json
{
  "facebook": {
    "groups": [
      "https://www.facebook.com/groups/744726133758655/",
      "https://www.facebook.com/groups/700493471102196/",
      "https://www.facebook.com/groups/1096603433739674/"
    ],
    "keywords": ["developer","programmer","ไอที","security","pentest","devops","data","qa"],
    "onlyPostsNewerThan": "2 days",
    "resultsLimit": 150,
    "viewOption": "CHRONOLOGICAL"
  }
}
```

- 3 กลุ่ม = อยู่ในเพดาน 3–5 ของ §5 · กลุ่ม 2 แคบ (Security) → `keywords` ต้องมี security/pentest ไม่งั้นจะว่าง
- ชื่อกลุ่มอ่านได้โดยไม่ต้องล็อกอิน แต่ **โพสต์ในกลุ่มอาจต้องล็อกอิน** → ได้ 0 โพสต์ทั้ง 3 กลุ่ม
  ให้รายงาน `login_walled` แล้วหยุด รอ Tz อนุมัติ T1 (§5)

---

## 3. Schema กลาง (`data\jobs.json`)

```json
{
  "id": "linkedin:3912345678",
  "sources": ["linkedin", "jobsdb"],
  "title": "Backend Developer",
  "company": "บริษัท ตัวอย่าง จำกัด",
  "company_id": "74449",
  "district": "ดินแดง",
  "province": "กรุงเทพมหานคร",
  "work_mode": "hybrid",
  "seniority": "mid",
  "job_type": "fulltime",
  "salary_text": "30,000 - 35,000 บาท",
  "salary_min": 30000,
  "salary_max": 35000,
  "currency": "THB",
  "skills": ["python", "postgresql"],
  "url": "https://www.linkedin.com/jobs/view/3912345678",
  "posted_at": "2026-11-19",
  "first_seen": "2026-11-20",
  "last_seen": "2026-11-21",
  "status": "active",
  "raw_text": null
}
```

กติกา:

- `id` = `<source>:<uid ของบอร์ด>` · ถ้าไม่มี uid ใช้ `sha1(url)`
- งานซ้ำข้ามบอร์ด: ยุบรวมเมื่อ `(company_normalized, title_normalized)` ตรงกัน **หรือ** `url` ตรงกัน
  → เก็บแถวที่ฟิลด์ครบกว่า และยืด `sources` เป็น array
- `work_mode` / `seniority` / `skills` = เดาจากข้อความด้วย regex/ลิสต์คำใน `config\filters.json` ถ้าไม่ชัดให้ `null` **ห้ามเดามั่ว**
- งานที่หายจากบอร์ดเกิน 14 วัน → `status: "gone"` **ห้ามลบแถว**
- `raw_text` เก็บเฉพาะแหล่งที่ไม่มีฟิลด์ (Facebook) ตัดที่ 1,500 ตัวอักษร

---

## 4. สวิตช์เงื่อนไข — สองชั้น (หัวใจของงานนี้)

**ชั้น A — สวิตช์ในหน้าเว็บ (ฟรี ทันที ไม่ต้องดึงข้อมูลใหม่):** ทุกฟิลด์ใน `jobs.json` เอามาทำตัวกรองได้
ชั้นนี้ใช้ preset `strict / balanced / wide` และเก็บสถานะลง `localStorage`
**ชั้น B — สวิตช์ใน `config\switches.json` (มีค่าใช้จ่าย):** คุมว่า *ดึงอะไรเข้ามา* ก่อนสร้างหน้า

หลักคิด: **เก็บกว้าง กรองแคบ** — จ่ายครั้งเดียวตอนดึงข้อมูลเข้ากว้าง ๆ แล้วการแคบลงทั้งหมดฟรีที่หน้าเว็บ
เพราะฉะนั้นชั้น B ควรตั้งกว้างเท่าที่งบไหว ไม่ใช่ตั้งแคบตั้งแต่ต้น

### ตารางสวิตช์ชั้น B (12 ตัว)

| # | switch | ปิด = แคบ | เปิด = กว้าง | ราคาเพิ่ม | ความเสี่ยงเพิ่ม |
|---|---|---|---|---|---|
| 1 | `boards.linkedin` | ไม่ดึง | ดึง | ฟรี | 429 (พัก 24 ชม.) |
| 2 | `boards.indeed` | ไม่ดึง | ดึง | ฟรี | ต่ำสุด (ไม่มี rate limit) |
| 3 | `boards.jobsdb` (seek) | ไม่ดึง | ดึง | ฟรี | ต่ำ |
| 4 | `boards.google` | ไม่ดึง | ดึง | ฟรี | ต่ำ |
| 5 | `boards.jobthai` | ไม่ดึง | ดึง | $1.00/1k | ไม่มี |
| 6 | `boards.jobtopgun` | ไม่ดึง | ดึง | $1.49/1k | ไม่มี |
| 7 | `boards.facebook` | ไม่ดึง | ดึง | $0.70/1k | ผลไม่ครบ/ว่าง · **บัญชีไม่เกี่ยว** |
| 8 | `area.include_perimeter` | กรุงเทพเท่านั้น | + นนทบุรี ปทุมธานี สมุทรปราการ | +20–40% | ไม่มี |
| 9 | `area.remote_anywhere` | ไม่เอา | เอางาน remote ที่ระบุ "ทั่วโลก/เอเชีย" | ฟรี (ในบอร์ดเดิม) | ไม่มี |
| 10 | `time.window_hours` | 24 | 72 → 168 → 336 | ตามผลที่ได้ | งานเก่า/ปิดรับแล้วมากขึ้น |
| 11 | `limit.per_board` | 20 | 50 → 100 → 300 | ตามผลที่ได้ | ถูกบล็อกง่ายขึ้นถ้าเยอะ |
| 12 | `details.fetch_description` | ปิด | เปิด (เพิ่ม 1 request/งาน) | ฟรีแต่ช้าลง | 429 ง่ายขึ้นที่ LinkedIn |

### Preset (ค่าเริ่มต้นใน `config\switches.json`)

| preset | เปิดอะไร | ค่าใช้จ่าย/เดือน (ประมาณ) |
|---|---|---|
| `strict` | linkedin+indeed+jobsdb · กรุงเทพ · 72 ชม. · 50/บอร์ด · ไม่มี FB | ~$0.5 |
| `balanced` (default) | ทุกบอร์ด · กรุงเทพ+ปริมณฑล · 72 ชม. · 100/บอร์ด · FB 3 กลุ่ม | ~$2–3 |
| `wide` | ทุกบอร์ด + remote · 168 ชม. · 300/บอร์ด · เปิด `fetch_description` · FB 3 กลุ่มทั้งหมด | ~$5–8 ⚠ |

⚠ `wide` เกินเครดิตฟรี $5 → ต้องมี **budget guard**: `run_all.py` หยุดทันทีเมื่อยอดสะสมเดือนนี้ ≥ $4.00
และเขียน log ว่า "หยุดเพราะเกินงบ" · ตัวเลขยอดสะสมอ่านจาก `runs\` ของเดือนนั้น (ไม่มีก็เริ่ม 0)

---

## 5. นโยบาย session / login (Tz ล็อกอินได้ทุกแพลตฟอร์ม — ไล่ตามลำดับนี้เท่านั้น)

Tz ล็อกอินได้ทุกแพลตฟอร์มหางาน แต่ระบบนี้ **ไม่ใช้การล็อกอินเป็นค่าเริ่มต้น** เพราะถ้าบัญชีถูกจำกัด
ราคาที่จ่ายคือบัญชีจริงของ Tz ไม่ใช่ค่าสแครปไม่กี่ดอลลาร์ — ให้ไล่ตาม tier:

| tier | ใช้เมื่อ | เงื่อนไข | สถานะ |
|---|---|---|---|
| **T0 cookieless** | ทุกกรณีแรก (ค่าเริ่มต้น) | ไม่มี cookie/session ในระบบเลย | ✅ ใช้ก่อนเสมอ |
| **T1 บัญชีแยก** | T0 ได้ผลไม่ครบ 2 รันติด **และ Tz อนุมัติรายครั้ง** | บัญชีแยกที่สร้างเพื่องานนี้ล้วน ๆ (FB: ไม่มีเพื่อน/ไม่ผูกเบอร์หลัก · LinkedIn: บัญชีที่ 2) · cookie อยู่ `config\secrets.env` · เปิด `session.enabled=true` · log ทุกครั้ง | ⚠️ ต้องอนุมัติก่อน |
| **T2 บัญชีหลัก Tz** | — | — | ❌ **ห้ามเด็ดขาด** รวมบัญชี LinkedIn ที่ใช้สมัครงาน/Premium |

กติกาเสริม:

- cookie/session **ห้ามผ่านแชท ห้ามคอมมิต** — วางใน `config\secrets.env` เท่านั้น
- ต้องมี `python src\run_all.py --clear-session` ลบ cookie ออกได้ทันที และรันก่อนส่งงานทุกครั้ง
- ไม่มีคีย์ `session.enabled` ใน config → ถือเป็น **T0 เสมอ** (ห้ามเดา)
- บอร์ดที่ไม่ต้องล็อกอินอยู่แล้ว (JobSpy/LinkedIn jobs, Indeed, JobsDB, JobThai, JobTopGun) → **ห้ามใส่ session**
  การล็อกอินมีประโยชน์เฉพาะข้อมูลที่ปิดจริง: โปรไฟล์/HR บน LinkedIn, กลุ่ม FB ที่เห็นเฉพาะสมาชิก

### ความจริงที่ต้องยอมรับ (ไม่ใช่ bug)

- Facebook: actor cookieless เริ่มได้เฉพาะกลุ่ม public · Meta บังคับล็อกอินบางกลุ่ม
  → **ว่างบางวันหรือว่างทั้งกลุ่มถือว่าปกติ และไม่คิดเงิน**
- LinkedIn: ค้นประกาศงานผ่าน JobSpy ได้โดยไม่ต้องล็อกอิน · Tz **ไม่ต้อง** สมัคร Premium เพื่องานนี้
- ถ้างานต้องใช้ข้อมูลหลังล็อกอินและยังไม่ได้รับอนุมัติ T1 → **หยุด รายงาน แล้วรอ**

### กติกาการรันต่อแหล่ง

| แหล่ง | ความถี่ | เพดาน | เมื่อไม่ปกติ |
|---|---|---|---|
| Facebook | 1 รัน/วัน เวลาไม่ซ้ำเดิม | 3 กลุ่ม (§2.1) · 150 โพสต์ · 2 วันย้อนหลัง · `keywords` เปิด | ว่าง 2 วันติด → หยุด 3 วัน + log · ห้าม retry รัว |
| LinkedIn | 1 ครั้ง/คำ/วัน | 100 ผล/คำ | `429` → พัก 24 ชม. · ใส่ proxy ถ้ามีใน `secrets.env` |
| Indeed / JobsDB / Google | 1 ครั้ง/วัน | 100/บอร์ด | error 2 ครั้งติด → ข้ามวัน |
| JobThai / JobTopGun | 1–2 รัน/วัน | 300/รัน | error 2 ครั้งติด → ข้ามวัน |

---

## 6. หน้า dashboard (`dist\index.html`)

- **หัวบน:** ชื่อ + `generated_at` + preset select (`strict/balanced/wide`) + ช่องค้นข้อความ
- **แถบกรอง (chip กดเปิด/ปิดได้ทุกตัว):** แหล่ง · เขต/จังหวัด · work mode · seniority · ช่วงเงินเดือน · อายุประกาศ · ซ่อน `gone`
- **ตารางคอลัมน์:** คะแนน · ตำแหน่ง · บริษัท · เขต · เงินเดือน · โหมด · แหล่ง (ป้ายเล็ก ๆ) · วันที่โพสต์
- **แถวกดได้:** เปิด `url` แท็บใหม่
- **แถบล่าง:** "เมื่อวานได้: linkedin 42 · indeed 31 · jobthai 88 · fb 12" — เห็นทันทีว่าแหล่งไหนตาย
- **สถานะว่าง/error:** ถ้า `jobs.json` ว่าง ให้ขึ้นข้อความ "ยังไม่เคยรัน" ไม่ใช่ตารางเปล่าเงียบ ๆ
- **ภาษา (ผสม ไทย/อังกฤษ):** ป้าย หัวตาราง ปุ่ม ตัวกรอง เป็นไทย · คำเทคนิคที่ติดปาก (backend, remote, hybrid, QA) คงอังกฤษ
- **ห้ามแปล `title` / `company` / `district`** ที่มาจากบอร์ด — แสดงตามต้นฉบับ (ถ้าอยากได้คำไทย ให้เพิ่มคอลัมน์แยก)
- **เงินเดือน:** แสดง `salary_text` ตามต้นฉบับ · ถ้าไม่มีให้เว้นว่าง **ห้ามเดาเป็นตัวเลข**
- ต้องทำงานออฟไลน์ 100% (ไม่มี CDN ไม่มี font จากเน็ต)

---

## 7. ลำดับงาน + เกณฑ์ผ่านย่อย

1. `normalize.py` + `tests\fixtures\` (3 แบบ) → **ผ่านเมื่อ** เทสต์ผ่าน: งานซ้ำยุบเหลือแถวเดียว, FB ที่ไม่มีฟิลด์ไม่ทำให้ schema พัง
2. `fetch_jobspy.py` ยิงจริง 1 คำที่กรุงเทพ → **ผ่านเมื่อ** ได้ ≥ 10 งานจริง มี `posted_at`/`company`/`url` ครบ
3. `filters.py` + `build_page.py` → **ผ่านเมื่อ** เปิด `dist\index.html` ด้วย file:// แล้วกรอง/เรียง/preset ได้
4. `fetch_apify.py` ต่อ JobThai → **ผ่านเมื่อ** ได้งาน IT กรุงเทพ และ `runs\` ระบุต้นทุนจริงต่อรัน
5. ต่อ JobTopGun → **ผ่านเมื่อ** ยอดรวมต่อวันยัง < $0.25
6. ต่อ Facebook ทีละกลุ่ม เริ่มที่กลุ่ม 1 (§2.1) → **ผ่านเมื่อ** ได้โพสต์จริง **หรือ** ได้ผลชัดว่า `login_walled`/อ่านไม่ได้ (ทั้งสองผล = ผ่าน) แล้วทำซ้ำครบ 3 กลุ่ม
7. ใส่ budget guard + stop rules → **ผ่านเมื่อ** จำลอง error แล้วระบบหยุดจริงและ log ครบ

ส่งงานตรวจรอบแรกเมื่อข้อ **1–3** ผ่าน (ยังไม่ต้องใช้ Apify/ไม่ต้องใช้เงิน)

---

## 8. Preflight — บริการ บัญชี และขั้นที่ Tz ต้องกดเอง

| ต้องมี | สถานะ | ใครทำ |
|---|---|---|
| Python 3.10+ และ `pip install -U python-jobspy` (JobSpy บังคับ ≥3.10) | ต้องติดตั้ง | โต๊ะโค้ดติดตั้งได้เอง |
| บัญชี Apify (ฟรี **ไม่ต้องผูกบัตร** · เครดิต $5/เดือน) | ยังไม่มี | **Tz สมัครเอง** |
| `APIFY_TOKEN` ใน `config\secrets.env` | ยังไม่มี | **Tz วางเอง ห้ามส่งทางแชท** |
| บัญชี Facebook | **ไม่ต้องใช้ใน T0** · Tz ล็อกอินได้ (เก็บเป็น T1) | Tz อนุมัติรายครั้งถ้าจะขึ้น T1 |
| LinkedIn Premium | **ไม่ต้องสมัครเพื่องานนี้** | — |
| ลิงก์กลุ่ม Facebook 3 กลุ่ม | ✅ ได้แล้ว 3 กลุ่ม แปลงเป็น group URL แล้ว (§2.1) | Tz ให้แล้ว 21 พ.ย. 13:09 |

**ถ้าอะไรในตารางนี้ยังไม่มี → ห้ามเดา ห้ามใช้ทางอื่นแทน ทำส่วนที่ไม่ต้องใช้ก่อน แล้วรายงานว่าติดอะไร**

---

## 9. กติกาการทำงาน (ตามที่ Tz กำหนดไว้)

- รันเทสต์ก่อนคอมมิตทุกครั้ง
- เอกสาร/คอมมิต แยกจากโค้ด แล้วค่อย push
- **ถ้าเรียกทีม/เครื่องมือที่ต้องใช้ไม่ได้ → หยุด รายงานหลักฐาน แล้วรอคำสั่ง ห้ามลงมือทำแทนเอง**
- งานนี้เป็นงานใหม่ทั้งชุด แผนคือเอกสารนี้ ไม่ต้องถามแผนซ้ำ

---

## 10. อำนาจตัดสินใจ (autonomy)

- **decide-and-do:** โครงไฟล์, ชื่อฟิลด์, library, รูปแบบการ implement, การเขียนเทสต์
- **decide-and-tell:** ปรับ schema, เพิ่ม/ถอดแหล่งข้อมูล, เปลี่ยนรูปแบบหน้าเว็บ
- **propose-first (ห้ามทำเอง):** อะไรที่ต้องใช้บัญชี/คีย์/จ่ายเงิน · อะไรที่แตะบัญชี FB/LinkedIn ·
  การขึ้นเพดานราคา · การเปลี่ยน path root

---

## 11. Check-in และ read-back

- **อ่านกลับก่อนเริ่ม:** ผู้รับงานต้องตอบได้ว่า done-test คืออะไร และก้าวแรกคือไฟล์ไหน (ถ้าตอบไม่ได้ = ใบงานยังขาด)
- **ตรวจรอบแรก:** เมื่อข้อ 1–3 ผ่าน ส่ง `dist\index.html` + ผลเทสต์ + log มาให้ Tz ดู 1 รอบก่อนไปต่อ Apify
- ถามได้ตลอด · ถามเร็วไม่ใช่ความผิดพลาด

---

## 12. คำตัดสินสุดท้าย (ครบแล้ว — ไม่มีอะไรค้าง)

| เรื่อง | คำตัดสินของ Tz | สถานะ |
|---|---|---|
| path root | `%USERPROFILE%\jobboard\` · ถ้าจะย้ายแก้ `ROOT` ที่เดียวใน `src\run_all.py` | ✅ 21 พ.ย. 13:13 |
| ภาษาในหน้าเว็บ | **ผสม ไทย/อังกฤษ** (กฎอยู่ใน §6) | ✅ 21 พ.ย. 13:13 |
| กลุ่ม Facebook | 3 กลุ่ม แปลงเป็น group URL แล้ว (§2.1) | ✅ 21 พ.ย. 13:10 |
| session / login | T0 ค่าเริ่มต้น · T1 ต้อง Tz อนุมัติรายครั้ง · T2 ห้าม | ✅ §5 |
| จะขึ้น T1 หรือไม่ | ไม่ต้องตอบตอนนี้ — done-test ครบด้วย T0 | ⏸ รอ Tz |

**ไม่มีคำถามค้างให้ผู้รับงานถามกลับ นอกจากเรื่องที่ §8 ยังไม่มี (Apify token) — เริ่มงานได้เลยที่ §7 ข้อ 1**

---

## 13. แหล่งอ้างอิงที่ตรวจแล้ว (ไม่ต้องตรวจซ้ำ)

- JobSpy รองรับ `linkedin, indeed, seek(JobsDB/JobStreet), google, glassdoor` — Glassdoor **ไม่มีไทย**
  · `country_indeed="thailand"` ใช้กับ Indeed และ SEEK · LinkedIn 429 เคลียร์ใน ~1 นาที
- `mcp-jobspy` / `python-jobspy` = ของ speedyapply (MIT) · Python ≥ 3.10
- `dami_studio/facebook-groups-scraper`: ไม่ต้องล็อกอิน/ไม่มีคุกกี้ · $0.70/1k โพสต์ · ≤50 กลุ่ม/รัน ·
  มี `keywords` + `onlyPostsNewerThan` · โพสต์ที่ไม่ผ่านตัวกรองไม่คิดเงิน · กลุ่มที่ไม่มีโพสต์คืน free note
- share link `facebook.com/share/g/<id>/` **ตาม redirect ได้โดยไม่ต้องล็อกอิน** — ทดสอบแล้ว 21 พ.ย. 13:10
  ทั้ง 3 ลิงก์ → `fetch_apify.py` ใช้ `allow_redirects=True` แล้วเก็บ `facebook.com/groups/<numeric-id>/`
  · ตามไม่ได้ให้ log `unresolved_share_link` **ห้ามเดา id**
- `mai_amm/jobthai-scraper`: $1.00/1k ผล · กรอง `jobTypes` IT ได้ · ผลมีจังหวัด/อำเภอ/ช่วงเงินเดือน
- `unfenced-group/jobtopgun-scraper`: $1.49/1k ผล
- Apify Free plan: $0 · เครดิต $5/เดือน · **ไม่ต้องใช้บัตร** · หมดแล้วบล็อกจนรอบบิลถัดไป
