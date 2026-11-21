"""normalize.py — แปลงผลดิบทุกแหล่งเป็น schema เดียว (brief §3) + กันซ้ำ + merge + gone

กติกาที่บังคับใช้
  · id = "<source>:<uid>" หรือ "sha1:<sha1(url)>" เมื่อไม่มี uid
  · ยุบซ้ำเมื่อ (company_normalized, title_normalized) ตรง หรือ url ตรง → sources เป็น array
    เก็บแถวที่ฟิลด์ครบกว่า, first_seen = เก่าสุด, last_seen = ใหม่สุด
    province/location ของแถวที่ยุบแล้วมาจากแถวเดียวกันเสมอ (ไม่ผสมสองแหล่ง)
  · ไม่มี salary_text → salary_min/max = null (ไม่เดาจากข้อความ)
  · work_mode/seniority/skills ไม่ชัด = null/[] (regex จาก config\\filters.json)
  · ห้ามแปล/แก้ title, company, district, location
  · location = ข้อความตำแหน่งจากแหล่งตามต้นฉบับทุกไบต์ (ไม่มี = null) — ไม่ทิ้งข้อมูล
  · province = ชื่อจังหวัดที่รู้จักเท่านั้น (config\\filters.json → provinces): จากฟิลด์
    province/state/region หรือสกัดจาก location เมื่อมีชื่อจังหวัดปรากฏจริงในสตริง;
    ไม่มีชื่อที่รู้จัก = null (ห้ามเดาจากตัวเลข หรือ \", Thailand\" ที่ไม่มีชื่อจังหวัด)
  · last_seen เกิน 14 วัน → status "gone" (ห้ามลบแถว)
  · raw_text ตัดที่ 1,500 ตัวอักษร (แหล่งที่ไม่มีฟิลด์ เช่น Facebook)

ใช้เป็น CLI:  python src\\normalize.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"
JOBS_PATH = DATA / "jobs.json"

GONE_AFTER_DAYS = 14
RAW_TEXT_LIMIT = 1500
CURRENCY_DEFAULT = "THB"

# คีย์ดิบที่ยอมรับ (ชื่อต่างกันตามบอร์ด) -------------------------------------------------
FIELD_ALIASES = {
    "uid": ("uid", "id", "job_id", "jobId", "post_id", "postId"),
    "title": ("title", "job_title", "jobTitle", "position", "name"),
    "company": ("company", "company_name", "companyName", "employer", "company_title"),
    "company_id": ("company_id", "companyId", "company_uid"),
    "district": ("district", "amphoe", "khet"),
    "province": ("province", "state", "region"),
    "location": ("location", "city", "area", "place"),
    "url": ("url", "job_url", "jobUrl", "job_url_direct", "link", "post_url", "permalink"),
    "posted_at": ("posted_at", "date_posted", "posted", "posted_date", "created_at", "time"),
    "salary_text": ("salary_text", "salary", "salary_range", "salaryText"),
    "salary_min": ("salary_min", "min_amount", "salaryMin", "min_salary"),
    "salary_max": ("salary_max", "max_amount", "salaryMax", "max_salary"),
    "currency": ("currency", "salary_currency"),
    "work_mode": ("work_mode", "work_from_home_type", "workMode", "remote_type"),
    "seniority": ("seniority", "job_level", "jobLevel", "level"),
    "job_type": ("job_type", "employment_type", "jobType", "type"),
    "skills": ("skills", "skill", "tags"),
    "description": ("description", "job_description", "detail", "details", "summary"),
    "raw_text": ("raw_text", "rawText", "text", "message", "content", "post_text"),
}

JOB_TYPE_MAP = {
    "fulltime": "fulltime",
    "full-time": "fulltime",
    "full time": "fulltime",
    "permanent": "fulltime",
    "parttime": "parttime",
    "part-time": "parttime",
    "part time": "parttime",
    "contract": "contract",
    "contractor": "contract",
    "temporary": "contract",
    "internship": "internship",
    "intern": "internship",
    "freelance": "freelance",
}

WORK_MODE_MAP = {
    "remote": "remote",
    "work from home": "remote",
    "wfh": "remote",
    "fully remote": "remote",
    "hybrid": "hybrid",
    "on-site": "onsite",
    "onsite": "onsite",
    "in person": "onsite",
    "in-person": "onsite",
}

SENIORITY_ORDER = ("intern", "junior", "mid", "senior", "lead", "manager")


# ------------------------------------------------------------------------ config
def load_filters() -> dict:
    p = CONFIG / "filters.json"
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------------- helpers
def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _text(value) -> str | None:
    if _blank(value):
        return None
    return str(value).strip()


def norm_key(value) -> str:
    """คีย์เทียบชื่อ: NFKC + casefold + ยุบช่องว่าง — ไม่แปล ไม่ตัดทิ้งคำใด."""
    if _blank(value):
        return ""
    s = unicodedata.normalize("NFKC", str(value)).casefold()
    s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def sha1_url(url: str) -> str:
    return "sha1:" + hashlib.sha1(url.strip().encode("utf-8")).hexdigest()


def _pick(raw: dict, key: str):
    for alias in FIELD_ALIASES[key]:
        if alias in raw and not _blank(raw[alias]):
            return raw[alias]
    return None


REL_DAYS = {
    "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365,
}
# จำนวนวันของหน่วยคำ (คำนวณ ไม่ใช่เดา) — บอร์ดที่ให้ "2 days ago"/"30+ days ago"
# แปลงเป็นวันที่จริง = today - N หน่วย. ที่ไม่มีข้อความวันที่เลย = null (ไม่ใส่วันนี้แทน)
REL_PATTERNS = (
    (r"(\d+)\s*\+?\s*(?:minute|hour)s?\s+ago", "minute"),
    (r"(\d+)\s*\+?\s*(?:day)s?\s+ago", "day"),
    (r"(\d+)\s*\+?\s*(?:week)s?\s+ago", "week"),
    (r"(\d+)\s*\+?\s*(?:month)s?\s+ago", "month"),
    (r"(\d+)\s*\+?\s*(?:year)s?\s+ago", "year"),
)
REL_SAME_DAY = (r"^just posted$", r"^today$", r"^เมื่อสักครู่$", r"^วันนี้$")
REL_YESTERDAY = (r"^yesterday$", r"^เมื่อวาน$")


def _relative_date(text: str, today: date) -> date | None:
    """'2 days ago' → today-2, '30+ days ago' → today-30, 'yesterday' → today-1.
    ใช้เฉพาะเมื่อเป็นข้อความสัมพัทธ์เท่านั้น; ไม่ใช่ = None."""
    low = text.strip().lower()
    for pat in REL_SAME_DAY:
        if re.match(pat, low):
            return today
    for pat in REL_YESTERDAY:
        if re.match(pat, low):
            return today - timedelta(days=1)
    for pat, unit in REL_PATTERNS:
        m = re.match(pat, low)
        if m:
            return today - timedelta(days=int(m.group(1)) * REL_DAYS[unit])
    return None


def _as_date(value, today: date | None = None) -> date | None:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    s = re.sub(r"[T ]\d{2}:\d{2}.*$", "", s)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return _relative_date(str(value), today or date.today())


def _as_number(value) -> float | None:
    if _blank(value):
        return None
    if isinstance(value, (int, float)):
        return None if float(value) == 0 else float(value)
    s = re.sub(r"[^\d.\-]", "", str(value))
    if not s:
        return None
    try:
        num = float(s)
    except ValueError:
        return None
    return None if num == 0 else num


def _as_int_or_float(value):
    num = _as_number(value)
    if num is None:
        return None
    return int(num) if float(num).is_integer() else num


def _match(rules: dict, text: str) -> str | None:
    for label, patterns in rules.items():
        if label.startswith("_"):
            continue
        for pat in patterns or []:
            if re.search(pat, text, re.IGNORECASE):
                return label
    return None


def _match_all_skills(rules: dict, text: str) -> list[str]:
    found = []
    for label, patterns in rules.items():
        if label.startswith("_"):
            continue
        for pat in patterns or []:
            if re.search(pat, text, re.IGNORECASE):
                found.append(label)
                break
    return found


# --------------------------------------------------------------- province names
def province_groups(filters: dict | None) -> dict:
    """config\\filters.json → {"bangkok": [...], "perimeter": [...], "other": [...]}.

    แต่ละค่า = รูปเขียนของชื่อจังหวัดที่รู้จัก (ไทย/อังกฤษ). นอกเหนือจากรายการนี้ = ไม่ใช่
    จังหวัด → province null (ห้ามเดา)."""
    raw = (filters or {}).get("provinces") or {}
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for group, names in raw.items():
        if str(group).startswith("_"):
            continue
        if isinstance(names, str):
            names = [names]
        out[str(group)] = [n for n in (_text(x) for x in (names or [])) if n]
    return out


_LATIN = "0-9A-Za-z"
_PROVINCE_RX: dict[str, re.Pattern] = {}


def _province_pattern(name: str) -> re.Pattern:
    """ชื่อจังหวัด → regex ที่จับในข้อความต้นฉบับ (ไม่สนตัวพิมพ์; ลาตินต้องมีขอบเขตคำ)."""
    pat = _PROVINCE_RX.get(name)
    if pat is not None:
        return pat
    body = re.escape(name)
    if name[:1].isascii() and name[:1].isalnum():
        body = "(?<![%s])" % _LATIN + body
    if name[-1:].isascii() and name[-1:].isalnum():
        body = body + "(?![%s])" % _LATIN
    pat = re.compile(body, re.IGNORECASE)
    _PROVINCE_RX[name] = pat
    return pat


def extract_province(text, groups: dict) -> str | None:
    """สกัดชื่อจังหวัดออกจากข้อความ → ข้อความตามต้นฉบับทุกไบต์ (เช่น "Bangkok") หรือ None.

    เลือกที่ตำแหน่งซ้ายสุดก่อน แล้วยาวที่สุด ("กรุงเทพมหานคร" ชนะ "กรุงเทพ").
    ไม่มีชื่อที่รู้จักในสตริง = None — ไม่เดาจากตัวเลขหรือคำลงท้าย \"Thailand\"."""
    if _blank(text) or not groups:
        return None
    raw = str(text)
    best: tuple[int, int, str] | None = None
    for names in groups.values():
        for name in names:
            m = _province_pattern(name).search(raw)
            if not m:
                continue
            key = (m.start(), -(m.end() - m.start()))
            if best is None or key < best[:2]:
                best = (key[0], key[1], m.group(0))
    return best[2] if best else None


# ------------------------------------------------------------------ row mapping
def detect_work_mode(text: str, explicit=None, filters: dict | None = None) -> str | None:
    if isinstance(explicit, str) and explicit.strip():
        key = explicit.strip().lower()
        if key in WORK_MODE_MAP:
            return WORK_MODE_MAP[key]
        hit = _match((filters or {}).get("work_mode") or {}, explicit)
        if hit:
            return hit
    hit = _match((filters or {}).get("work_mode") or {}, text)
    return hit or None


def detect_seniority(text: str, explicit=None, filters: dict | None = None) -> str | None:
    rules = (filters or {}).get("seniority") or {}
    if isinstance(explicit, str) and explicit.strip():
        hit = _match(rules, explicit)
        if hit:
            return hit
    hit = _match(rules, text)
    return hit or None


def detect_skills(text: str, explicit=None, filters: dict | None = None) -> list[str]:
    """skills = ค่าที่แหล่งให้มา ∪ คำที่สกัดได้จาก text (title/company/description/raw_text).

    "text" ของ normalize_row มี description อยู่แล้ว — เดิมถ้าแหล่งให้ skills มาเป็น list
    ฟังก์ชันนี้คืนแค่ list นั้นและไม่สแกน description เลย ทำให้คำสาย cloud ใน description
    (เช่น Docker) หายไป และ include ก็ไม่เห็น (ใบงาน 21 พ.ย. defect 2). ตอนนี้รวมทั้งสองทาง.
    """
    rules = (filters or {}).get("skills") or {}
    out: list[str] = []
    if isinstance(explicit, list):
        out.extend(str(s).strip().lower() for s in explicit if not _blank(s))
    elif isinstance(explicit, str) and explicit.strip():
        text = text + "\n" + explicit
    out.extend(_match_all_skills(rules, text))
    return sorted(set(out))


def job_type_of(value) -> str | None:
    if _blank(value):
        return None
    key = re.sub(r"\s+", " ", str(value).strip().lower())
    return JOB_TYPE_MAP.get(key)


def normalize_row(raw: dict, source: str, today: date, filters: dict) -> dict | None:
    """แถวดิบ 1 แถว → schema กลาง. คืน None เมื่อไม่มีทั้ง title และ url (แถวใช้ไม่ได้)."""
    if not isinstance(raw, dict):
        return None

    title = _text(_pick(raw, "title"))
    url = _text(_pick(raw, "url"))
    if not title and not url:
        return None

    company = _text(_pick(raw, "company"))
    district = _text(_pick(raw, "district"))
    location = _text(_pick(raw, "location"))  # ต้นฉบับทุกไบต์ — ไม่ทิ้ง
    declared = _text(_pick(raw, "province"))  # ฟิลด์ province/state/region ของแหล่ง
    groups = province_groups(filters)
    province = extract_province(declared, groups) if declared else None
    if province is None and location:
        province = extract_province(location, groups)  # มีชื่อจังหวัดในสตริงจริง = ไม่เดา
    if province is None and declared and not location:
        location = declared  # ค่าที่ใช้เป็นจังหวัดไม่ได้ — เก็บต้นฉบับไว้ที่ location ไม่ทิ้ง
    description = _text(_pick(raw, "description"))
    raw_text_in = _text(_pick(raw, "raw_text"))

    salary_text = _text(_pick(raw, "salary_text"))
    salary_min = _as_int_or_float(_pick(raw, "salary_min")) if salary_text else None
    salary_max = _as_int_or_float(_pick(raw, "salary_max")) if salary_text else None
    if salary_text is None:
        salary_min = salary_max = None

    body = "\n".join(p for p in (title or "", company or "", description or "",
                                 raw_text_in or "", district or "", province or "") if p)

    uid = _text(_pick(raw, "uid"))
    job_id = f"{source}:{uid}" if uid else (sha1_url(url) if url else None)

    posted = _as_date(_pick(raw, "posted_at"), today)

    raw_text = None
    if raw_text_in:
        raw_text = raw_text_in[:RAW_TEXT_LIMIT]

    row = {
        "id": job_id,
        "sources": [source],
        "title": title,
        "company": company,
        "company_id": _text(_pick(raw, "company_id")),
        "district": district,
        "province": province,
        "location": location,
        "work_mode": detect_work_mode(body, _pick(raw, "work_mode"), filters),
        "seniority": detect_seniority(body, _pick(raw, "seniority"), filters),
        "job_type": job_type_of(_pick(raw, "job_type")),
        "salary_text": salary_text,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": _text(_pick(raw, "currency")) or (CURRENCY_DEFAULT if salary_text else None),
        "skills": detect_skills(body, _pick(raw, "skills"), filters),
        "url": url,
        "posted_at": posted.isoformat() if posted else None,
        "first_seen": today.isoformat(),
        "last_seen": today.isoformat(),
        "status": "active",
        "raw_text": raw_text,
    }
    return row


# ---------------------------------------------------------------- raw envelopes
def iter_raw(obj, default_source: str | None = None):
    """ผลดิบหลายรูปแบบ → (source, raw_job) ทีละแถว
    รองรับ: {"raw":[{source,jobs}...]} · {"source","jobs"} · [ {..}|{source,jobs} ] · [raw_job...]
    """
    if obj is None:
        return
    if isinstance(obj, list):
        for item in obj:
            yield from iter_raw(item, default_source)
        return
    if not isinstance(obj, dict):
        return
    if "raw" in obj and isinstance(obj["raw"], list):
        for item in obj["raw"]:
            yield from iter_raw(item, default_source)
        return
    if "jobs" in obj and isinstance(obj["jobs"], list):
        src = obj.get("source") or default_source or "unknown"
        for job in obj["jobs"]:
            yield src, job
        return
    if "posts" in obj and isinstance(obj["posts"], list):
        src = obj.get("source") or default_source or "unknown"
        for job in obj["posts"]:
            yield src, job
        return
    src = obj.get("source") or obj.get("_source") or default_source or "unknown"
    yield src, obj


def load_raw_file(path: Path, default_source: str | None = None):
    with Path(path).open("r", encoding="utf-8-sig") as fh:
        return list(iter_raw(json.load(fh), default_source))


def load_raw_dir(raw_dir: Path):
    """อ่านทุกไฟล์ .json ใต้ data\\raw\\<date>\\ — ชื่อไฟล์ = ชื่อแหล่ง (jobspy = หลายบอร์ด)."""
    out = []
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return out
    for path in sorted(raw_dir.glob("*.json")):
        out.extend(load_raw_file(path, path.stem))
    return out


# --------------------------------------------------------------------- dedupe
def _filled_count(row: dict) -> int:
    return sum(1 for k, v in row.items() if k not in ("id", "sources") and not _blank(v))


def _row_keys(row: dict) -> list[str]:
    keys = []
    if row.get("url"):
        keys.append("url:" + norm_key(row["url"]))
    ct = (norm_key(row.get("company")), norm_key(row.get("title")))
    if ct[0] and ct[1]:
        keys.append("ct:" + ct[0] + "|" + ct[1])
    return keys


def _merge_two(base: dict, other: dict) -> dict:
    """รวมสองแถว: เก็บแถวที่ฟิลด์ครบกว่าเป็นฐาน, เติมช่องว่างจากอีกแถว, รวม sources."""
    if _filled_count(other) > _filled_count(base):
        base, other = other, base
    out = dict(base)
    for key, value in other.items():
        if key in ("sources", "id"):
            continue
        if _blank(out.get(key)) and not _blank(value):
            out[key] = value
    if _blank(out.get("salary_max")) and not _blank(other.get("salary_max")):
        out["salary_max"] = other["salary_max"]
    if _blank(out.get("salary_min")) and not _blank(other.get("salary_min")):
        out["salary_min"] = other["salary_min"]

    # province กับ location ต้องมาจากแถวเดียวกัน: แถวฐานไม่รู้จังหวัด แต่อีกแถวรู้ →
    # ใช้คู่ province+location ของอีกแถว (ไม่ผสมจนแถวเดียวบอกสองที่ขัดกันเอง)
    if (_blank(base.get("province")) and not _blank(other.get("province"))
            and not _blank(other.get("location"))):
        out["province"] = other["province"]
        out["location"] = other["location"]

    sources = []
    for row in (base, other):
        for s in row.get("sources") or ([row["source"]] if row.get("source") else []):
            if s and s not in sources:
                sources.append(s)
    out["sources"] = sources

    firsts = [r.get("first_seen") for r in (base, other) if r.get("first_seen")]
    lasts = [r.get("last_seen") for r in (base, other) if r.get("last_seen")]
    out["first_seen"] = min(firsts) if firsts else None
    out["last_seen"] = max(lasts) if lasts else None
    out["status"] = "active" if "active" in (base.get("status"), other.get("status")) else base.get("status")
    raw_texts = [r.get("raw_text") for r in (base, other) if r.get("raw_text")]
    if raw_texts:
        out["raw_text"] = max(raw_texts, key=len)[:RAW_TEXT_LIMIT]
    if not out.get("id"):
        out["id"] = base.get("id") or other.get("id")
    return out


def dedupe(rows: list[dict]) -> list[dict]:
    """ยุบซ้ำด้วย union-find: (company_norm,title_norm) ตรง หรือ url ตรง."""
    rows = [r for r in rows if isinstance(r, dict)]
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    seen: dict[str, int] = {}
    for idx, row in enumerate(rows):
        for key in _row_keys(row):
            if key in seen:
                union(seen[key], idx)
            else:
                seen[key] = idx

    groups: dict[int, list[dict]] = {}
    for idx, row in enumerate(rows):
        groups.setdefault(find(idx), []).append(row)

    merged: list[dict] = []
    for root in sorted(groups):
        acc = groups[root][0]
        for other in groups[root][1:]:
            acc = _merge_two(acc, other)
        merged.append(acc)
    return merged


# ---------------------------------------------------------------- gone + merge
def apply_gone(rows: list[dict], today: date, days: int = GONE_AFTER_DAYS) -> list[dict]:
    """last_seen เกิน N วัน → status "gone" (ไม่ลบแถว)."""
    cutoff = today - timedelta(days=days)
    for row in rows:
        last = _as_date(row.get("last_seen")) or _as_date(row.get("first_seen"))
        if last is None:
            row["status"] = row.get("status") or "active"
            continue
        if last < cutoff:
            row["status"] = "gone"
        elif row.get("status") != "gone":
            row["status"] = "active"
    return rows


def merge_with_existing(new_rows: list[dict], existing: list[dict], today: date) -> list[dict]:
    """รวมของใหม่กับคลังเดิม: คง first_seen เดิม, last_seen ของเดิมไม่ถูกทับถ้าไม่ได้เจอวันนี้."""
    touched = set()
    for row in new_rows:
        for key in _row_keys(row):
            touched.add(key)

    carried = []
    for row in existing or []:
        keys = _row_keys(row)
        if any(k in touched for k in keys):
            continue
        carried.append(row)

    merged = dedupe(new_rows + carried)
    return apply_gone(merged, today)


# ---------------------------------------------------------------------- driver
def load_existing(path: Path = JOBS_PATH) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        data = data.get("jobs") or data.get("raw") or []
    return [r for r in data if isinstance(r, dict)]


def normalize(raw_items, today: date | None = None, filters: dict | None = None,
              existing: list[dict] | None = None) -> list[dict]:
    """รายการ (source, raw_job) → คลังที่ยุบซ้ำแล้ว + merge กับ existing (ถ้าให้มา)."""
    today = today or date.today()
    filters = filters if filters is not None else load_filters()
    rows = []
    for source, raw in raw_items:
        row = normalize_row(raw, source, today, filters)
        if row:
            rows.append(row)
    merged = dedupe(rows)
    if existing is not None:
        merged = merge_with_existing(rows, existing, today)
    return merged


def run(day: date | None = None, raw_dir: Path | None = None, out_path: Path | None = None,
        existing_path: Path | None = None) -> dict:
    day = day or date.today()
    raw_dir = raw_dir or (RAW / day.isoformat())
    out_path = out_path or JOBS_PATH
    existing_path = existing_path or JOBS_PATH
    raw_items = load_raw_dir(raw_dir)
    existing = load_existing(existing_path)
    jobs = normalize(raw_items, day, load_filters(), existing=existing)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "jobs": jobs}
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return {
        "raw_rows": len(raw_items),
        "jobs": len(jobs),
        "gone": sum(1 for j in jobs if j.get("status") == "gone"),
        "raw_dir": str(raw_dir),
        "out": str(out_path),
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    day = date.today()
    if "--date" in argv:
        day = _as_date(argv[argv.index("--date") + 1]) or day
    summary = run(day)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
