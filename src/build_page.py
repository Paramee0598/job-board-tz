"""build_page.py — สร้าง dist\\index.html + dist\\data.js (brief §6 · SPEC D3)

อ่าน: data\\jobs.json · config\\switches.json · config\\filters.json · runs\\<เมื่อวาน>.md
เขียน: dist\\data.js (window.JOBS + window.META) · dist\\index.html (หน้าเดียว ออฟไลน์ 100%)

กติกา
  · ห้าม fetch/XHR — หน้าเว็บโหลดข้อมูลด้วย <script src="data.js"> เท่านั้น (file:// บล็อก fetch)
  · ห้าม URL ภายนอก/CDN/ฟอนต์เน็ตใน dist\\index.html — ใช้ฟอนต์ระบบ
  · ห้ามแปล/แก้ title/company/district/location · ห้ามเดาเงินเดือน (แสดง salary_text ตามต้นฉบับ, ไม่มี = เว้นว่าง)
  · คอลัมน์ "เขต/จังหวัด" = province ถ้ามี + location ต้นฉบับต่อท้ายเมื่อต่างกัน (ไม่ให้ข้อมูลหาย)
  · ย่านพื้นที่ใช้ province เท่านั้น: null = "unknown" (ไม่ระบุ) แยกจาก "other" (จังหวัดอื่นที่รู้จัก)
  · แถว status "gone" ไม่ถูกลบ — ซ่อนได้ด้วยชิปในหน้าเว็บ
  · แถวที่ส่งลงหน้าเว็บ = เฉพาะที่ผ่าน src\filters.py (drop_reason = None): ไม่ติด must_not · ผ่าน include · อยู่ในพื้นที่
    แถวที่ถูกตัดไม่ถูกส่ง แต่ยอด 684 → include_pass → kept → dropped (แยกตามเหตุผล) อยู่ใน window.META.filters ตรวจย้อนได้
  · preset ชั้น A = ตัวกรองฝั่ง client (พื้นที่ · อายุประกาศ · เงินเดือน · โหมด · ซ่อน gone)
    ไม่ใช่ค่าชั้น B ใน config\\switches.json (limit.per_board 100/300 = wave 2) — switches.json ใช้แค่ชื่อ preset ที่ active
  · ไม่มี path absolute ในไฟล์นี้: ROOT มาจาก __file__

ใช้: python src\\build_page.py   → พิมพ์สรุป JSON (จำนวนแถวต่อ preset + ขนาดไฟล์)
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import filters as filters_mod  # noqa: E402  (อยู่ src\ เดียวกัน — ใช้ให้คะแนนแถว)

DATA = ROOT / "data"
CONFIG = ROOT / "config"
DIST = ROOT / "dist"
RUNS = ROOT / "runs"
JOBS_PATH = DATA / "jobs.json"
SWITCHES_PATH = CONFIG / "switches.json"
FILTERS_PATH = CONFIG / "filters.json"

SOURCE_ORDER = ("linkedin", "indeed", "jobsdb", "google", "jobthai", "jobtopgun", "facebook")
SOURCE_LABEL = {"facebook": "fb"}
SALARY_STEPS = (30000, 50000)

# ---------------------------------------------------------------- preset ชั้น A
# ค่าที่ใช้จริงบนข้อมูล 111 แถว (21 พ.ย.): กรุงเทพ 91 · ปริมณฑล 8 · other 0 · ไม่ระบุ 12
# (12 แถว Indeed: location "40, Thailand" = ไม่มีชื่อจังหวัด → province null → ย่าน unknown)
# อายุประกาศไม่มีผล (ทุกแถว ≤ 72 ชม.) · salary ว่างทั้งคลัง (0 แถว) — จึงใช้ "พื้นที่" เป็นมิติที่ทำให้จำนวนต่างจริง
PRESET_SPEC = {
    "strict": {
        "label": "เข้ม",
        "desc": "กรุงเทพเท่านั้น · 72 ชม.",
        "areas": ["bangkok"],
        "max_age_hours": 72,
        "salary": "any",
        "hide_gone": True,
    },
    "balanced": {
        "label": "สมดุล",
        "desc": "กรุงเทพ + ปริมณฑล · 168 ชม.",
        "areas": ["bangkok", "perimeter"],
        "max_age_hours": 168,
        "salary": "any",
        "hide_gone": True,
    },
    "wide": {
        "label": "กว้าง",
        "desc": "ทุกพื้นที่ (รวมพื้นที่ไม่ระบุ) · 336 ชม. · แสดง gone ด้วย",
        "areas": [],
        "max_age_hours": 336,
        "salary": "any",
        "hide_gone": False,
    },
}
PRESET_ORDER = ("strict", "balanced", "wide")


# ------------------------------------------------------------------------ utils
def load_json(path: Path, default=None):
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def load_jobs():
    """→ (rows, data_generated_at, note). ไฟล์ไม่มี/ว่าง = rows [] + note 'ยังไม่เคยรัน'."""
    raw = load_json(JOBS_PATH)
    if raw is None:
        return [], None, "ยังไม่เคยรัน — ไม่พบ data\\jobs.json (รัน python src\\run_all.py ก่อน)"
    rows = raw.get("jobs") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    gen = raw.get("generated_at") if isinstance(raw, dict) else None
    note = None if rows else "ยังไม่เคยรัน — data\\jobs.json ไม่มีแถวงาน"
    return rows, gen, note


def page_default_preset(switches) -> str:
    """ชื่อ preset ที่ active ใน config\\switches.json (ใช้แค่ชื่อ ไม่ใช้ค่าชั้น B)."""
    active = (switches or {}).get("active")
    if active in PRESET_SPEC:
        return active
    if active and active not in PRESET_SPEC:
        return "balanced"
    return "balanced"


def scored_rows(rows, cfg) -> list:
    """คัดลอกแถวแล้วเติม "score" จาก src\\filters.py — ไม่แก้ค่าต้นฉบับของ title/company/district."""
    out = []
    for row in rows:
        job = dict(row)
        try:
            job["score"] = int(filters_mod.score(row, cfg))
        except Exception:  # ให้คะแนนไม่ได้ = 0 ไม่ทำให้ build ล้ม
            job["score"] = 0
        out.append(job)
    return out


def filter_rows(rows, cfg, sw_map) -> tuple[list, dict]:
    """กรองด้วย src\filters.py (ตรรกะเดียวกับเทสต์) → (แถวที่ผ่าน, ยอดที่ถูกตัดแยกตามเหตุผล).

    ยอด dropped เป็น disjoint: ผลรวม dropped + kept = จำนวนแถวใน data\\jobs.json
    (drop_reason คืนเหตุผลแรกที่เจอ: must_not → salary_below_min → area_outside → include_miss).
    """
    kept = []
    dropped = {"must_not": 0, "salary_below_min": 0, "area_outside": 0, "include_miss": 0}
    for row in rows:
        reason = filters_mod.drop_reason(row, cfg, sw_map)
        if reason is None:
            kept.append(row)
        else:
            key = reason.split(":", 1)[0]
            dropped[key] = dropped.get(key, 0) + 1
    return kept, dropped


def include_pass_count(rows, cfg) -> int:
    """จำนวนแถวที่ผ่าน include อย่างเดียว (ไม่คิด must_not/พื้นที่) — ตัวหาร M บนหัวหน้าเว็บ."""
    return sum(1 for row in rows if filters_mod.matches_include(row, cfg))


def parse_runs_log(path: Path) -> dict:
    """อ่านตาราง '| แหล่ง | ยิงกี่คำ | ได้กี่งาน | cost_usd | error |' → {source: got}."""
    counts: dict[str, int] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return counts
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        source = cells[0].lower()
        if source not in SOURCE_ORDER or source in counts:
            continue
        try:
            counts[source] = int(cells[2].replace(",", "").strip())
        except ValueError:
            continue
    return counts


def yesterday_summary(today: date) -> dict:
    """ตัวเลขต่อแหล่งของ runs\\<เมื่อวาน>.md — ไม่มี log = {} (หน้าเว็บแสดง '-')."""
    day = today - timedelta(days=1)
    path = RUNS / f"{day.isoformat()}.md"
    found = path.is_file()
    return {
        "date": day.isoformat(),
        "log": path.name if found else None,
        "counts": parse_runs_log(path) if found else {},
    }


# -------------------------------------------- ตัวกรองฝั่ง client (สำเนา 1:1 ของ JS)
# ตรรกะชุดเดียวกับ JOBVIEW ใน dist\\index.html — ใช้พิมพ์ตัวเลขพิสูจน์ตอน build
def area_of(job: dict, rules: dict) -> str:
    """ย่านพื้นที่ (ตรรกะชุดเดียวกับ areaOf ใน dist\\index.html).

    province ว่าง/null → "unknown" (ไม่ระบุ) · ชื่อจังหวัดกรุงเทพ → "bangkok" ·
    ปริมณฑล → "perimeter" · ชื่อจังหวัดอื่นที่รู้จัก → "other".
    ใช้ province เท่านั้น — ไม่เดาย่านจาก location."""
    province = str(job.get("province") or "").strip().casefold()
    if not province:
        return "unknown"
    for token in rules.get("bangkok") or []:
        t = str(token).casefold()
        if t and t in province:
            return "bangkok"
    for token in rules.get("perimeter") or []:
        t = str(token).casefold()
        if t and t in province:
            return "perimeter"
    return "other"


def area_counts(rows, rules) -> dict:
    """จำนวนแถวต่อย่าน (ทุกแถว ไม่ผ่านตัวกรอง) — ใช้โชว์ป้าย "พื้นที่ไม่ระบุ" บนหน้าเว็บ."""
    counts = {"bangkok": 0, "perimeter": 0, "other": 0, "unknown": 0}
    for row in rows:
        counts[area_of(row, rules)] += 1
    return counts


def age_hours(job: dict, today: date) -> float | None:
    posted = job.get("posted_at")
    if not posted:
        return None
    try:
        day = date.fromisoformat(str(posted)[:10])
    except ValueError:
        return None
    hours = (today - day).days * 24
    return 0 if hours < 0 else hours


def has_salary(job: dict) -> bool:
    return bool(job.get("salary_text")) or salary_best(job) is not None


def salary_best(job: dict):
    for key in ("salary_max", "salary_min"):
        value = job.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def matches(job: dict, state: dict, rules: dict, today: date, skip: str | None = None) -> bool:
    if state.get("hide_gone") and job.get("status") == "gone" and skip != "hide_gone":
        return False
    query = (state.get("q") or "").strip().lower()
    if query and skip != "q":
        hay = " ".join(
            str(job.get(k) or "") for k in ("title", "company", "district", "province", "salary_text")
        ).lower()
        hay += " " + " ".join(str(s) for s in (job.get("skills") or []))
        for token in query.split():
            if token not in hay:
                return False
    chosen = state.get("sources") or []
    if chosen and skip != "sources":
        if not any(s in chosen for s in (job.get("sources") or [])):
            return False
    chosen = state.get("areas") or []
    if chosen and skip != "areas":
        if area_of(job, rules) not in chosen:
            return False
    chosen = state.get("work_modes") or []
    if chosen and skip != "work_modes":
        if (job.get("work_mode") or "unknown") not in chosen:
            return False
    chosen = state.get("seniorities") or []
    if chosen and skip != "seniorities":
        if (job.get("seniority") or "unknown") not in chosen:
            return False
    salary = state.get("salary") or "any"
    if salary != "any" and skip != "salary":
        if salary == "unspecified":
            if has_salary(job):
                return False
        else:
            best = salary_best(job)
            if best is None or float(best) < float(salary):
                return False
    window = state.get("max_age_hours") or 0
    if window and skip != "max_age_hours":
        hours = age_hours(job, today)
        if hours is not None and hours > window:  # ไม่รู้วันโพสต์ = ไม่ตัด (ไม่เดา)
            return False
    return True


def apply_view(rows, state, rules, today) -> list:
    return [r for r in rows if matches(r, state, rules, today)]


def state_for(name: str) -> dict:
    spec = PRESET_SPEC[name]
    return {
        "preset": name,
        "q": "",
        "sources": [],
        "areas": list(spec["areas"]),
        "work_modes": [],
        "seniorities": [],
        "salary": spec["salary"],
        "max_age_hours": spec["max_age_hours"],
        "hide_gone": spec["hide_gone"],
    }


def build_meta(rows, kept, filters_info, data_generated_at, note, default_preset, cfg,
               switches) -> dict:
    """rows = ทุกแถวในคลัง (684) · kept = แถวที่ผ่าน filters (ส่งลงหน้าเว็บ)."""
    provinces_cfg = (cfg or {}).get("provinces") or {}
    area_rules = {
        "bangkok": [str(t) for t in provinces_cfg.get("bangkok") or []],
        "perimeter": [str(t) for t in provinces_cfg.get("perimeter") or []],
        "other": [str(t) for t in provinces_cfg.get("other") or []],
    }
    present = [s for s in SOURCE_ORDER if any(s in (r.get("sources") or []) for r in kept)]
    return {
        "generated_at": data_generated_at or datetime.now().isoformat(timespec="seconds"),
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "data_file": "data\\jobs.json",
        "total": len(rows),          # แถวทั้งหมดในคลัง (ไม่ใช่จำนวนที่แสดง)
        "kept": len(kept),            # แถวที่ส่งลง window.JOBS
        "include_total": filters_info.get("include_pass", len(kept)),  # M บนหัวหน้าเว็บ
        "filters": filters_info,
        "active_preset": default_preset,
        "presets": {name: dict(PRESET_SPEC[name], order=i)
                    for i, name in enumerate(PRESET_ORDER)},
        "salary_steps": list(SALARY_STEPS),
        "area_rules": area_rules,
        "area_counts": area_counts(kept, area_rules),
        "source_order": list(SOURCE_ORDER),  # ทั้ง 7 แหล่ง — แหล่งที่ไม่มีงานต้องเห็นเป็น 0 ไม่ใช่หายไป
        "sources_present": present,
        "source_label": dict(SOURCE_LABEL),
        "yesterday": yesterday_summary(date.today()),
        "note": note,
        "layer_b": {
            "note": "สวิตช์ชั้น B (ดึงข้อมูล/ค่าใช้จ่าย) อยู่ใน config\\switches.json — ไม่เกี่ยวกับตัวกรองหน้านี้",
            "active": (switches or {}).get("active"),
        },
    }


def write_outputs(rows, meta) -> dict:
    DIST.mkdir(parents=True, exist_ok=True)
    data_js = DIST / "data.js"
    index_html = DIST / "index.html"
    body = (
        "// สร้างโดย src\\build_page.py — ห้ามแก้ด้วยมือ\n"
        f"window.JOBS = {json.dumps(rows, ensure_ascii=False, separators=(',', ':'))};\n\n"
        f"window.META = {json.dumps(meta, ensure_ascii=False, separators=(',', ':'))};\n"
    )
    data_js.write_text(body, encoding="utf-8")
    index_html.write_text(INDEX_TEMPLATE, encoding="utf-8")
    return {
        "index_html": "dist\\index.html",
        "data_js": "dist\\data.js",
        "index_html_bytes": index_html.stat().st_size,
        "data_js_bytes": data_js.stat().st_size,
    }


# ------------------------------------------------------------------------ main
def main() -> int:
    rows, data_generated_at, note = load_jobs()
    switches = load_json(SWITCHES_PATH, {}) or {}
    cfg = load_json(FILTERS_PATH, {}) or {}
    sw_map = switches.get("switches") or {}
    default_preset = page_default_preset(switches)

    kept, dropped = filter_rows(rows, cfg, sw_map)
    include_pass = include_pass_count(rows, cfg)
    filters_info = {
        "total": len(rows),
        "include_pass": include_pass,
        "kept": len(kept),
        "dropped": dropped,
        "note": ("kept = แถวที่ผ่าน drop_reason (ไม่ติด must_not · ผ่าน include · อยู่ในพื้นที่) "
                 "· dropped นับแยกตามเหตุผลแรกที่ drop_reason คืน (รวมกันได้ = total) "
                 "· include_pass = ผ่าน include อย่างเดียว (ตัวหาร M บนหัวหน้าเว็บ)"),
    }
    jobs = scored_rows(kept, cfg)
    meta = build_meta(rows, jobs, filters_info, data_generated_at, note,
                      default_preset, cfg, switches)
    rules = meta["area_rules"]
    today = date.today()

    # preset_rows คิดจากชุดที่กรองแล้วเท่านั้น (ไม่ใช่ 684 หรือ 47)
    preset_rows = {}
    for name in PRESET_ORDER:
        preset_rows[name] = len(apply_view(jobs, state_for(name), rules, today))

    sizes = write_outputs(jobs, meta)
    report = {
        "jobs": len(jobs),
        "filters": {"total": filters_info["total"], "include_pass": include_pass,
                    "kept": len(kept), "dropped": dropped},
        "generated_at": meta["generated_at"],
        "active_preset": default_preset,
        "preset_rows": preset_rows,
        "area_rows": meta["area_counts"],
        "yesterday": meta["yesterday"],
        "note": note,
        **sizes,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>หางาน IT กรุงเทพ — Job Board (ในเครื่อง)</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1c2128;--muted:#6b7280;--line:#e3e6ea;--accent:#1f6feb;--chip:#eef1f5;--warn:#b45309}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-size:14px;line-height:1.45;padding-bottom:44px;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Leelawadee UI","Noto Sans Thai",Tahoma,Arial,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px 8px}
.title-row{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h1{font-size:18px;margin:0}
.tag{font-size:12px;color:var(--muted);font-weight:400}
.meta{margin-left:auto;font-size:12px;color:var(--muted)}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:13px}
.controls label{display:flex;align-items:center;gap:6px;color:var(--muted)}
select,input[type=search]{font:inherit;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink)}
input[type=search]{width:280px}
button{font:inherit;cursor:pointer}
#reset{padding:4px 8px;border:1px solid var(--line);background:#fff;border-radius:6px;color:var(--muted)}
.filters{margin-top:8px;display:flex;flex-direction:column;gap:4px}
.grp{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.gname{font-size:12px;color:var(--muted);flex:0 0 104px}
.chip{border:1px solid var(--line);background:var(--chip);color:var(--ink);border-radius:999px;padding:2px 9px;
 font-size:12.5px;display:inline-flex;gap:5px;align-items:center}
.chip b{font-weight:600;color:var(--muted);font-size:11.5px}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.chip.on b{color:#dbe7ff}
.chip.zero{opacity:.45}
main{padding:10px 16px 40px}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line)}
thead th{position:sticky;top:0;background:#f1f3f7;text-align:left;font-size:12px;color:var(--muted);
 padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
tbody td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr{cursor:pointer}
tbody tr:hover{background:#f2f7ff}
td.num{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap;width:56px}
td.title{font-weight:600;max-width:430px}
td.small{color:var(--muted);font-size:12.5px}
.gone{font-size:11px;color:var(--warn);font-weight:600;margin-left:4px}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:999px;background:var(--chip);color:#374151;margin-right:3px}
.badge.linkedin{background:#dbeafe;color:#1e40af}
.badge.jobsdb{background:#dcfce7;color:#166534}
.badge.indeed{background:#ede9fe;color:#5b21b6}
.badge.google{background:#fee2e2;color:#991b1b}
.badge.facebook{background:#dbeafe;color:#1d4ed8}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
 padding:8px 16px;font-size:12.5px;color:var(--muted);z-index:6}
.empty{margin:24px 16px;padding:20px;background:var(--card);border:1px dashed var(--line)}
.empty h2{margin:0 0 6px;font-size:16px}
.empty p{margin:4px 0;color:var(--muted)}
#noresult{padding:16px;color:var(--muted)}
.warnbox{margin-top:8px;padding:6px 8px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;font-size:12.5px}
.areacounts{margin-top:6px;font-size:12.5px;color:var(--muted)}
.areacounts b{color:var(--ink);font-weight:600}
td .loc{opacity:.75}
[hidden]{display:none !important}
</style>
</head>
<body>
<header>
  <div class="title-row">
    <h1>หางาน IT กรุงเทพ</h1>
    <span class="tag">job board · รันในเครื่อง 100%</span>
    <span class="meta">ข้อมูล: <strong id="gen">-</strong> · แสดง <strong id="count">0</strong> / <span id="total">0</span> แถว <span class="tag">(N = หลังกรอง preset · M = ผ่าน include)</span></span>
  </div>
  <div class="controls">
    <label>preset <select id="preset"></select></label>
    <label>ค้น <input id="q" type="search" placeholder="ตำแหน่ง · บริษัท · เขต · สกิล"></label>
    <button id="reset" type="button">ล้างตัวกรอง</button>
    <label><input id="hidegone" type="checkbox"> ซ่อน gone</label>
  </div>
  <div id="warn" class="warnbox" hidden></div>
  <div id="filtersum" class="areacounts"></div>
  <div id="areacounts" class="areacounts"></div>
  <div id="filters" class="filters"></div>
</header>
<main>
  <div id="empty" class="empty" hidden>
    <h2 id="emptyTitle">ยังไม่เคยรัน</h2>
    <p id="emptyText">ยังไม่มีข้อมูลงาน — รัน python src\run_all.py ก่อน</p>
  </div>
  <div id="noresult" hidden>ไม่มีงานตรงตัวกรองที่เลือก — กด "ล้างตัวกรอง" หรือเปลี่ยน preset</div>
  <table id="tbl">
    <thead>
      <tr>
        <th>คะแนน</th><th>ตำแหน่ง</th><th>บริษัท</th><th>เขต / จังหวัด</th>
        <th>เงินเดือน</th><th>โหมด</th><th>แหล่ง</th><th>วันที่โพสต์</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
</main>
<footer><span id="yesterday">เมื่อวานได้: -</span></footer>
<script src="data.js"></script>
<script>
/*LOGIC_START*/
(function (root) {
  'use strict';
  var META = root.META || {};
  var RULES = META.area_rules || { bangkok: [], perimeter: [], other: [] };

  function ageHours(posted) {
    if (!posted) return null;
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(posted));
    if (!m) return null;
    var then = new Date(+m[1], +m[2] - 1, +m[3]);
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var hours = (today - then) / 3600000;
    return hours < 0 ? 0 : hours;
  }

  /* ย่านพื้นที่: province เท่านั้น — null/ว่าง = unknown (ไม่ระบุ) แยกจาก other */
  function areaOf(job) {
    var province = String(job.province || '').trim().toLowerCase();
    if (!province) return 'unknown';
    var list = RULES.bangkok || [];
    var i;
    for (i = 0; i < list.length; i++) {
      var b = String(list[i]).toLowerCase();
      if (b && province.indexOf(b) >= 0) return 'bangkok';
    }
    list = RULES.perimeter || [];
    for (i = 0; i < list.length; i++) {
      var p = String(list[i]).toLowerCase();
      if (p && province.indexOf(p) >= 0) return 'perimeter';
    }
    return 'other';
  }

  function salaryBest(job) {
    if (typeof job.salary_max === 'number') return job.salary_max;
    if (typeof job.salary_min === 'number') return job.salary_min;
    return null;
  }

  function hasSalary(job) {
    return !!job.salary_text || salaryBest(job) !== null;
  }

  function haystack(job) {
    var parts = [job.title, job.company, job.district, job.province, job.location, job.salary_text];
    var skills = job.skills || [];
    for (var i = 0; i < skills.length; i++) parts.push(skills[i]);
    return parts.filter(Boolean).join(' ').toLowerCase();
  }

  function defaults(name) {
    var presets = META.presets || {};
    var p = presets[name] || { areas: [], max_age_hours: 336, salary: 'any', hide_gone: false };
    return {
      preset: name,
      q: '',
      sources: [],
      areas: (p.areas || []).slice(),
      work_modes: [],
      seniorities: [],
      salary: typeof p.salary === 'undefined' ? 'any' : p.salary,
      max_age_hours: typeof p.max_age_hours === 'number' ? p.max_age_hours : 336,
      hide_gone: p.hide_gone !== false
    };
  }

  function matches(job, state, skip) {
    if (state.hide_gone && job.status === 'gone' && skip !== 'hide_gone') return false;
    var query = String(state.q || '').trim().toLowerCase();
    if (query && skip !== 'q') {
      var hay = haystack(job);
      var tokens = query.split(/\s+/);
      for (var i = 0; i < tokens.length; i++) {
        if (tokens[i] && hay.indexOf(tokens[i]) < 0) return false;
      }
    }
    if (skip !== 'sources') {
      var chosen = state.sources || [];
      if (chosen.length) {
        var own = job.sources || [];
        var hit = false;
        for (var j = 0; j < own.length; j++) {
          if (chosen.indexOf(own[j]) >= 0) { hit = true; break; }
        }
        if (!hit) return false;
      }
    }
    if (skip !== 'areas') {
      var pick = state.areas || [];
      if (pick.length && pick.indexOf(areaOf(job)) < 0) return false;
    }
    if (skip !== 'work_modes') {
      var modes = state.work_modes || [];
      if (modes.length && modes.indexOf(job.work_mode || 'unknown') < 0) return false;
    }
    if (skip !== 'seniorities') {
      var levels = state.seniorities || [];
      if (levels.length && levels.indexOf(job.seniority || 'unknown') < 0) return false;
    }
    if (skip !== 'salary') {
      var salary = state.salary || 'any';
      if (salary !== 'any') {
        if (salary === 'unspecified') {
          if (hasSalary(job)) return false;
        } else {
          var best = salaryBest(job);
          if (best === null || best < Number(salary)) return false;
        }
      }
    }
    if (skip !== 'max_age_hours' && state.max_age_hours) {
      var hours = ageHours(job.posted_at);
      if (hours !== null && hours > state.max_age_hours) return false; /* ไม่รู้วัน = ไม่ตัด */
    }
    return true;
  }

  function withPatch(state, patch) {
    var out = {};
    var key;
    for (key in state) {
      if (Object.prototype.hasOwnProperty.call(state, key)) out[key] = state[key];
    }
    for (key in patch) {
      if (Object.prototype.hasOwnProperty.call(patch, key)) out[key] = patch[key];
    }
    return out;
  }

  function countWith(state, patch) {
    var jobs = root.JOBS || [];
    var view = withPatch(state, patch);
    var n = 0;
    for (var i = 0; i < jobs.length; i++) {
      if (matches(jobs[i], view)) n++;
    }
    return n;
  }

  function filterJobs(state) {
    var jobs = root.JOBS || [];
    var out = [];
    for (var i = 0; i < jobs.length; i++) {
      if (matches(jobs[i], state)) out.push(jobs[i]);
    }
    return out;
  }

  function num(job) {
    return typeof job.score === 'number' ? job.score : 0;
  }

  function sortJobs(rows) {
    return rows.slice().sort(function (a, b) {
      if (num(b) !== num(a)) return num(b) - num(a);
      var da = a.posted_at || '';
      var db = b.posted_at || '';
      if (da !== db) return da < db ? 1 : -1;
      return String(a.title || '').localeCompare(String(b.title || ''), 'th');
    });
  }

  root.JOBVIEW = {
    defaults: defaults,
    matches: matches,
    filterJobs: filterJobs,
    sortJobs: sortJobs,
    countWith: countWith,
    areaOf: areaOf,
    ageHours: ageHours,
    hasSalary: hasSalary,
    salaryBest: salaryBest
  };
})(window);
/*LOGIC_END*/
</script>
<script>
(function () {
  'use strict';
  var V = window.JOBVIEW;
  var META = window.META || {};
  var JOBS = window.JOBS || [];
  if (!V) return;
  var KEY = 'jobboard.view.v1';
  var PRESETS = META.presets || {};
  var ORDER = META.source_order || [];
  var LABEL = META.source_label || {};
  var AREA_LABELS = [['bangkok', 'กรุงเทพ'], ['perimeter', 'ปริมณฑล'],
                     ['other', 'พื้นที่อื่น'], ['unknown', 'พื้นที่ไม่ระบุ']];
  function $(id) { return document.getElementById(id); }

  function presetNames() {
    var names = Object.keys(PRESETS);
    names.sort(function (a, b) { return (PRESETS[a].order || 0) - (PRESETS[b].order || 0); });
    return names;
  }

  function fallbackPreset() {
    if (META.active_preset && PRESETS[META.active_preset]) return META.active_preset;
    var names = presetNames();
    return names.indexOf('balanced') >= 0 ? 'balanced' : (names[0] || 'wide');
  }

  function loadState() {
    var base = V.defaults(fallbackPreset());
    try {
      var saved = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (saved && PRESETS[saved.preset]) {
        var fresh = V.defaults(saved.preset);
        Object.keys(fresh).forEach(function (k) {
          if (!Object.prototype.hasOwnProperty.call(saved, k)) return;
          if (Array.isArray(fresh[k])) {
            if (Array.isArray(saved[k])) fresh[k] = saved[k];
            return;
          }
          if (typeof saved[k] === typeof fresh[k]) fresh[k] = saved[k];
        });
        base = fresh;
      }
    } catch (e) { /* localStorage ปิด = ใช้ค่า preset */ }
    return base;
  }

  function saveState() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ไม่เป็นไร */ }
  }

  var state = loadState();

  function fmt(n) { return Number(n).toLocaleString('en-US'); }

  var GROUPS = [
    { key: 'sources', name: 'แหล่ง', multi: true, items: function () {
        return ORDER.map(function (s) { return [s, LABEL[s] || s]; });
      } },
    { key: 'areas', name: 'เขต / จังหวัด', multi: true, items: function () {
        return AREA_LABELS.slice();
      } },
    { key: 'work_modes', name: 'โหมด', multi: true, items: function () {
        return [['remote', 'remote'], ['hybrid', 'hybrid'],
                ['onsite', 'onsite'], ['unknown', 'ไม่ระบุ']];
      } },
    { key: 'seniorities', name: 'ระดับ', multi: true, items: function () {
        return [['intern', 'intern'], ['junior', 'junior'], ['mid', 'mid'],
                ['senior', 'senior'], ['lead', 'lead'], ['manager', 'manager'],
                ['unknown', 'ไม่ระบุ']];
      } },
    { key: 'salary', name: 'เงินเดือน', multi: false, items: function () {
        var out = [['any', 'ทั้งหมด'], ['unspecified', 'ไม่ระบุเงินเดือน']];
        (META.salary_steps || []).forEach(function (step) { out.push([step, '≥ ' + fmt(step)]); });
        return out;
      } },
    { key: 'max_age_hours', name: 'อายุประกาศ', multi: false, items: function () {
        return [[0, 'ทั้งหมด'], [24, '24 ชม.'], [72, '72 ชม.'], [168, '168 ชม.'], [336, '336 ชม.']];
      } }
  ];

  function groupBy(key) {
    for (var i = 0; i < GROUPS.length; i++) if (GROUPS[i].key === key) return GROUPS[i];
    return null;
  }

  function chipValue(group, raw) {
    if (group.key === 'max_age_hours') return Number(raw);
    if (group.key === 'salary' && raw !== 'any' && raw !== 'unspecified') return Number(raw);
    return raw;
  }

  function isOn(group, value) {
    var current = state[group.key];
    if (group.multi) return (current || []).indexOf(value) >= 0;
    return String(current) === String(value);
  }

  function chipCount(group, value) {
    var patch = {};
    patch[group.key] = group.multi ? [value] : value;
    return V.countWith(state, patch);
  }

  function toggleChip(group, value) {
    if (group.multi) {
      var list = (state[group.key] || []).slice();
      var at = list.indexOf(value);
      if (at >= 0) list.splice(at, 1); else list.push(value);
      state[group.key] = list;
    } else {
      state[group.key] = value;
    }
    saveState();
    renderAll();
  }

  function renderFilters() {
    var box = $('filters');
    box.textContent = '';
    GROUPS.forEach(function (group) {
      var row = document.createElement('div');
      row.className = 'grp';
      var name = document.createElement('span');
      name.className = 'gname';
      name.textContent = group.name;
      row.appendChild(name);
      group.items().forEach(function (pair) {
        var raw = pair[0];
        var value = chipValue(group, raw);
        var count = chipCount(group, value);
        var chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip' + (isOn(group, value) ? ' on' : '') + (count ? '' : ' zero');
        chip.dataset.group = group.key;
        chip.dataset.value = String(raw);
        chip.appendChild(document.createTextNode(pair[1] + ' '));
        var badge = document.createElement('b');
        badge.textContent = String(count);
        chip.appendChild(badge);
        row.appendChild(chip);
      });
      box.appendChild(row);
    });
  }

  /* คอลัมน์พื้นที่: province ถ้ามี + location ต้นฉบับต่อท้ายเมื่อต่างกัน (ห้ามแปล) */
  function whereParts(job) {
    var province = String(job.province || '').trim();
    var district = String(job.district || '').trim();
    var location = String(job.location || '').trim();
    var primary = province || district || location;
    var extra = (location && location !== primary) ? location : '';
    return { primary: primary, extra: extra };
  }

  function renderTable() {
    var body = $('rows');
    body.textContent = '';
    var rows = V.sortJobs(V.filterJobs(state));
    rows.forEach(function (job) {
      var tr = document.createElement('tr');
      tr.tabIndex = 0;
      if (job.url) {
        tr.dataset.url = job.url;
        tr.title = 'เปิดประกาศ: ' + (job.title || '');
      }
      var td = document.createElement('td');
      td.className = 'num';
      td.textContent = String(typeof job.score === 'number' ? job.score : 0);
      tr.appendChild(td);

      td = document.createElement('td');
      td.className = 'title';
      td.textContent = job.title || '';
      if (job.status === 'gone') {
        var gone = document.createElement('span');
        gone.className = 'gone';
        gone.textContent = 'gone';
        td.appendChild(gone);
      }
      tr.appendChild(td);

      td = document.createElement('td');
      td.className = 'small';
      td.textContent = job.company || '';
      tr.appendChild(td);

      td = document.createElement('td');
      td.className = 'small';
      var where = whereParts(job);
      td.textContent = where.primary;
      if (where.extra) {
        var loc = document.createElement('span');
        loc.className = 'loc';
        loc.textContent = ' · ' + where.extra;
        td.appendChild(loc);
      }
      tr.appendChild(td);

      td = document.createElement('td');
      td.className = 'small';
      td.textContent = job.salary_text || '';
      tr.appendChild(td);

      td = document.createElement('td');
      td.className = 'small';
      td.textContent = job.work_mode || '';
      tr.appendChild(td);

      td = document.createElement('td');
      (job.sources || []).forEach(function (s) {
        var badge = document.createElement('span');
        badge.className = 'badge ' + s;
        badge.textContent = LABEL[s] || s;
        td.appendChild(badge);
      });
      tr.appendChild(td);

      td = document.createElement('td');
      td.className = 'small';
      td.textContent = job.posted_at || '';
      tr.appendChild(td);

      body.appendChild(tr);
    });
    return rows.length;
  }

  /* ตรวจย้อนได้บนหน้าเว็บ: คลัง → ผ่าน include → ผ่านตัวกรอง · แยกเหตุผลที่ตัด */
  function renderFilterSum() {
    var box = $('filtersum');
    if (!box) return;
    var f = META.filters || {};
    if (typeof f.total !== 'number') { box.textContent = ''; return; }
    var d = f.dropped || {};
    var text = 'คัดจากคลัง ' + f.total + ' แถว → ผ่าน include ' + (f.include_pass || 0) +
      ' → ผ่านตัวกรอง ' + (f.kept || 0) + ' · ตัด: must_not ' + (d.must_not || 0) +
      ' · include ไม่ถึง ' + (d.include_miss || 0) + ' · นอกพื้นที่ ' + (d.area_outside || 0);
    if (d.salary_below_min) text += ' · เงินเดือนต่ำกว่าเกณฑ์ ' + d.salary_below_min;
    box.textContent = text;
  }

  function renderAreaCounts() {
    var box = $('areacounts');
    if (!box) return;
    var counts = META.area_counts || {};
    box.textContent = 'ย่านพื้นที่: ';
    AREA_LABELS.forEach(function (pair, i) {
      if (i) box.appendChild(document.createTextNode(' · '));
      box.appendChild(document.createTextNode(pair[1] + ' '));
      var b = document.createElement('b');
      b.textContent = String(typeof counts[pair[0]] === 'number' ? counts[pair[0]] : 0);
      box.appendChild(b);
    });
  }

  function renderFooter() {
    var y = META.yesterday || {};
    var counts = y.counts || {};
    var parts = ORDER.map(function (s) {
      var n = counts[s];
      return (LABEL[s] || s) + ' ' + (typeof n === 'number' ? n : '-');
    });
    var text = 'เมื่อวานได้: ' + (parts.join(' · ') || '-');
    if (!y.log) text += ' · ไม่มี log ของ ' + (y.date || 'เมื่อวาน');
    $('yesterday').textContent = text;
  }

  function renderAll() {
    $('gen').textContent = META.generated_at || '-';
    $('total').textContent = String(typeof META.include_total === 'number'
      ? META.include_total : JOBS.length);
    $('preset').value = state.preset;
    if ($('q').value !== (state.q || '')) $('q').value = state.q || '';
    $('hidegone').checked = !!state.hide_gone;

    if (!JOBS.length) {
      var f = META.filters || {};
      var hadData = typeof f.total === 'number' && f.total > 0;
      $('empty').hidden = false;
      $('emptyTitle').textContent = hadData ? 'ไม่มีงานที่ผ่านตัวกรอง' : 'ยังไม่เคยรัน';
      $('emptyText').textContent = hadData
        ? (f.total + ' แถวในคลัง · ผ่าน include ' + (f.include_pass || 0) +
           ' · ผ่านตัวกรองทั้งชุด 0 — ตรวจ config\\filters.json')
        : (META.note || 'ยังไม่มีข้อมูลงาน — รัน python src\\run_all.py ก่อน');
      $('filters').hidden = true;
      $('tbl').hidden = true;
      $('noresult').hidden = true;
      $('count').textContent = '0';
      renderFilterSum();
      renderFooter();
      return;
    }

    $('empty').hidden = true;
    $('filters').hidden = false;
    $('tbl').hidden = false;
    if (META.note) {
      $('warn').hidden = false;
      $('warn').textContent = META.note;
    } else {
      $('warn').hidden = true;
    }
    renderFilterSum();
    renderAreaCounts();
    renderFilters();
    var shown = renderTable();
    $('count').textContent = String(shown);
    $('noresult').hidden = shown !== 0;
    renderFooter();
  }

  function openRow(tr) {
    if (!tr || !tr.dataset || !tr.dataset.url) return;
    window.open(tr.dataset.url, '_blank', 'noopener');
  }

  $('filters').addEventListener('click', function (ev) {
    var chip = ev.target.closest ? ev.target.closest('.chip') : null;
    if (!chip) return;
    var group = groupBy(chip.dataset.group);
    if (group) toggleChip(group, chipValue(group, chip.dataset.value));
  });

  $('rows').addEventListener('click', function (ev) {
    openRow(ev.target.closest ? ev.target.closest('tr') : null);
  });

  $('rows').addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var tr = ev.target.closest ? ev.target.closest('tr') : null;
    if (!tr || !tr.dataset.url) return;
    ev.preventDefault();
    openRow(tr);
  });

  $('preset').addEventListener('change', function (ev) {
    state = V.defaults(ev.target.value);
    saveState();
    renderAll();
  });

  $('q').addEventListener('input', function (ev) {
    state.q = ev.target.value;
    saveState();
    renderAll();
  });

  $('reset').addEventListener('click', function () {
    state = V.defaults(state.preset);
    saveState();
    renderAll();
  });

  $('hidegone').addEventListener('change', function (ev) {
    state.hide_gone = ev.target.checked;
    saveState();
    renderAll();
  });

  presetNames().forEach(function (name) {
    var opt = document.createElement('option');
    var spec = PRESETS[name] || {};
    opt.value = name;
    opt.textContent = name + (spec.desc ? ' — ' + spec.desc : '');
    $('preset').appendChild(opt);
  });

  renderAll();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
