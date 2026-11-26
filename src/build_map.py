"""build_map.py — สร้าง dist\\map.html (หน้าแผนที่บริษัท · แยกหน้าจาก dashboard แต่ repo เดียวกัน)

อ่าน: data\\companies.json (พิกัดจาก src\\geocode_companies.py) · data\\jobs.json · config\\filters.json
      + คีย์ GOOGLE_MAPS_API_KEY (env ก่อน แล้วค่อย config\\secrets.env)
เขียน: dist\\map.html (หน้าเดียวจบ · inline CSS/JS · โหลดจากภายนอกเฉพาะ Google Maps JavaScript API)

กติกา
  · แสดงเฉพาะหมุดที่ in_bangkok = true · ที่เหลืออยู่ในแผงข้าง "ไม่ปรากฏบนแผนที่" พร้อมเหตุผล
  · ไม่วาดวงกลม/รัศมีใด ๆ (Tz สั่ง: แสดงเฉพาะกรุงเทพ) · center กรุงเทพ zoom 11
  · หมุด = AdvancedMarkerElement + mapId "DEMO_MAP_ID" (ข้อกำหนดของ Maps Demo Key)
    ถ้าไลบรารี marker ไม่มา → ถอยไปใช้ google.maps.Marker ธรรมดา (สีเดียวกัน) ไม่ปล่อยหน้าเปล่า
  · คลิกหมุด → info window: ชื่อ · ที่อยู่จาก Google · ป้ายความแม่น · รายชื่องาน (ชื่อ + คะแนน) ลิงก์แท็บใหม่
  · มุมมอง 3 โหมด (all = ทั้งหมด · pinned = เฉพาะบริษัทที่ปัก · mix = ทั้งหมด + ไฮไลต์ที่ปัก = ค่าเริ่มต้น)
    เก็บใน localStorage['jobboard.mapview'] · ?view=all|pinned|mix ทับ · ค่าไม่ถูกต้อง → mix
  · ข้อมูลงาน/คะแนนคิดสดจาก data\\jobs.json ด้วย src\\filters.py (ไม่ใช้ค่าที่ค้างใน companies.json)
  · ข้อความจากประกาศงาน (title/company) ใส่ด้วย textContent เท่านั้น — ไม่ innerHTML
  · ลิงก์ภายนอกต้องขึ้นต้น http(s):// เท่านั้น (กัน javascript: จากต้นทาง)
  · ไม่มีคีย์ หรือ companies.json ว่าง/ไม่มี → ยังสร้างหน้านี้ แต่เป็นหน้าแบนเนอร์บอกวิธี ไม่เรียก Google เลย
  · คีย์อ่านตอน build แล้วฝังใน dist\\map.html (Maps JS ต้องมีคีย์ฝั่ง client) — ไม่เขียนลง src\\/config\\/data\\
    ⚠ dist\\map.html อยู่บน GitHub Pages แบบสาธารณะ → ต้องจำกัดคีย์ด้วย HTTP referrer
  · ไม่มี path absolute ในไฟล์นี้: ROOT มาจาก __file__
  · พิกัดที่แก้เอง: อ่าน data\\company_overrides.json ถ้ามี ({"<ชื่อบริษัท>":{"lat":..,"lng":..}}) แล้วใช้แทนพิกัดจาก geocode
    ไฟล์นี้สร้างจากปุ่ม "ส่งออกพิกัดที่แก้ (N)" บนหน้า map — ไม่มีไฟล์/อ่านไม่ได้ = ใช้พิกัด geocode ตามเดิม ไม่พัง
  · หมุดเล็กลง 12px (เดิม 28px) แต่พื้นที่กด 28px (.pinwrap padding) · ลากหมุดแก้พิกัดได้
    (AdvancedMarkerElement gmpDraggable + event gmp-dragend → localStorage['jobboard.pinpos'])
  · ปุ่ม "ค้นหาใน Google" แยกจากปุ่มอื่น — Places API (New) REST places:searchText ฝั่งเบราว์เซอร์
    (PlacesService แบบ legacy ใช้กับคีย์ชุดนี้ไม่ได้: LegacyApiNotActivatedMapError)
    fetch ล้มเหลว/ถูกบล็อก → ถอยไป google.maps.importLibrary("places") + Place.searchByText
    สำหรับบริษัทที่ไม่มีพิกัดและบริษัทที่พิกัดหยาบ — ผลลัพธ์ติดป้าย "Google · ค้นหาใหม่"
    + จังหวัด (ในไทย) หรือชื่อประเทศ (นอกไทย) ไม่ปนกับพิกัดที่ geocode ตอน build
    ไม่พบผลลัพธ์จริง → "Google ไม่พบผลลัพธ์" และไม่เดาพิกัด

ใช้: python src\\build_map.py            (ไม่ต้องมีคีย์ก็ได้ — ได้หน้าแบนเนอร์)
     python src\\build_map.py --out dist\\_maptest.html   (เขียนที่อื่นเพื่อทดสอบ ไม่ทับของจริง)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import filters as filters_mod  # noqa: E402  (อ่านอย่างเดียว — ให้คะแนนงานตรงกับ dashboard)
import geocode_companies as geo  # noqa: E402  (ใช้ find_key/parse_secrets ตัวเดียวกับตอน geocode)

DATA = ROOT / "data"
CONFIG = ROOT / "config"
DIST = ROOT / "dist"
COMPANIES_PATH = DATA / "companies.json"
JOBS_PATH = DATA / "jobs.json"
FILTERS_PATH = CONFIG / "filters.json"
OUT_PATH = DIST / "map.html"
OVERRIDES_PATH = DATA / "company_overrides.json"

CENTER = (13.7563, 100.5018)
ZOOM = 11
MAP_ID = "DEMO_MAP_ID"
KEY_NAME = geo.KEY_NAME
BANNER_COMMAND = "python src\\geocode_companies.py && python src\\build_map.py"


def load_json(path: Path, default=None):
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def load_company_entries() -> tuple[dict, list]:
    raw = load_json(COMPANIES_PATH, {}) or {}
    rows = raw.get("companies") if isinstance(raw, dict) else raw
    entries = []
    for row in rows or []:
        if isinstance(row, dict) and str(row.get("company") or "").strip():
            entries.append(row)
    return (raw if isinstance(raw, dict) else {}), entries


def normalize_positions(raw) -> dict:
    """ไฟล์พิกัดที่แก้เอง → dict ชื่อบริษัท → {lat,lng} (ทนรูปแบบห่อ companies/overrides/positions/pins)"""
    rows = raw
    if isinstance(raw, dict):
        for key in ("companies", "overrides", "positions", "pins"):
            if isinstance(raw.get(key), dict):
                rows = raw[key]
                break
    if not isinstance(rows, dict):
        return {}
    out = {}
    for name, pos in rows.items():
        company = str(name or "").strip()
        if not company or not isinstance(pos, dict):
            continue
        try:
            lat = float(pos.get("lat"))
            lng = float(pos.get("lng"))
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            continue
        out[company] = {"lat": lat, "lng": lng}
    return out


def load_overrides() -> tuple[dict, bool]:
    """พิกัดที่แก้เองจาก data\\company_overrides.json — ไม่มีไฟล์/อ่านไม่ได้ = {} (ไม่พัง)"""
    if not OVERRIDES_PATH.is_file():
        return {}, False
    raw = load_json(OVERRIDES_PATH, None)
    if raw is None:
        return {}, True
    return normalize_positions(raw), True


def job_index() -> dict:
    raw = load_json(JOBS_PATH, {}) or {}
    rows = raw.get("jobs") if isinstance(raw, dict) else raw
    index = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get("id"):
            index[str(row["id"])] = row
    return index


def company_jobs(entry: dict, index: dict, cfg: dict) -> list:
    """งานของบริษัทนั้น: ชื่อ + คะแนน (คิดสดด้วย src\\filters.py) + url."""
    out = []
    for job_id in entry.get("job_ids") or []:
        job = index.get(str(job_id))
        if not job:
            continue
        try:
            score = int(filters_mod.score(job, cfg))
        except Exception:
            score = 0
        out.append({
            "id": str(job.get("id") or ""),
            "title": str(job.get("title") or ""),
            "score": score,
            "url": str(job.get("url") or ""),
            "posted_at": str(job.get("posted_at") or ""),
        })
    out.sort(key=lambda item: (-item["score"], item["title"]))
    return out


def job_lookup(entries: list, index: dict, cfg: dict) -> dict:
    """ดัชนีงานทั้งชุด (id → ชื่อ/บริษัท/คะแนน/url) สำหรับแผง "งานที่ปักหมุดไว้".

    ครอบทั้งบริษัทที่ขึ้นแผนที่และไม่ขึ้น — งานที่ปักอาจอยู่บริษัทนอกกรุงเทพ
    ฝังใน payload ตอน build เพื่อให้หน้าเว็บทำงานแบบไฟล์เดียวจบ (ไม่ fetch)
    """
    out = {}
    for entry in entries:
        company = str(entry.get("company") or "").strip()
        for job_id in entry.get("job_ids") or []:
            key = str(job_id)
            if key in out:
                continue
            job = index.get(key)
            if not job:
                continue
            try:
                score = int(filters_mod.score(job, cfg))
            except Exception:
                score = 0
            out[key] = {
                "title": str(job.get("title") or ""),
                "company": company,
                "score": score,
                "url": str(job.get("url") or ""),
            }
    return out


def has_coords(entry: dict) -> bool:
    return (isinstance(entry.get("lat"), (int, float))
            and isinstance(entry.get("lng"), (int, float)))


def off_reason(entry: dict) -> str:
    """เหตุผลที่หมุดไม่ขึ้นแผนที่ — บอกตามจริง ไม่เดา."""
    status = str(entry.get("status") or "")
    if status == "pending":
        return "ยังไม่ได้ค้นที่อยู่ (รัน geocode ด้วย --limit ไว้)"
    if status == "not_found":
        return "ไม่พบที่อยู่จาก Google"
    if status == "error":
        return "ค้นหาไม่สำเร็จ (Google error)"
    if not has_coords(entry):
        return "ไม่พบที่อยู่"
    province = str(entry.get("province") or "").strip()
    return "อยู่นอกกรุงเทพ" + (f" · {province}" if province else "")


def build_payload(entries: list, index: dict, cfg: dict, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    on_map, off_map = [], []
    applied = 0
    for entry in entries:
        company = str(entry.get("company") or "").strip()
        lat = round(float(entry["lat"]), 7) if has_coords(entry) else None
        lng = round(float(entry["lng"]), 7) if has_coords(entry) else None
        pos_source = "geocode"
        override = overrides.get(company)
        if override:
            lat = round(override["lat"], 7)
            lng = round(override["lng"], 7)
            pos_source = "override"
            applied += 1
        item = {
            "company": company,
            "lat": lat,
            "lng": lng,
            "formatted_address": str(entry.get("formatted_address") or ""),
            "province": str(entry.get("province") or ""),
            "accuracy": str(entry.get("accuracy") or "unknown"),
            "status": str(entry.get("status") or "unknown"),
            "found_name": str(entry.get("found_name") or ""),
            "pos_source": pos_source,
            "jobs": company_jobs(entry, index, cfg),
        }
        pinned_by_user = pos_source == "override" and lat is not None and lng is not None
        if pinned_by_user or (has_coords(entry) and entry.get("in_bangkok") is True):
            on_map.append(item)
        else:
            item["reason"] = off_reason(entry)
            off_map.append(item)
    on_map.sort(key=lambda item: item["company"].casefold())
    off_map.sort(key=lambda item: item["company"].casefold())
    accuracy = {"exact": 0, "approx": 0, "unknown": 0}
    for item in on_map + off_map:
        accuracy[item["accuracy"]] = accuracy.get(item["accuracy"], 0) + 1
    return {
        "center": {"lat": CENTER[0], "lng": CENTER[1]},
        "zoom": ZOOM,
        "map_id": MAP_ID,
        "companies": on_map,
        "off_map": off_map,
        "jobs": job_lookup(entries, index, cfg),
        "overrides": {
            "read": len(overrides),
            "applied": applied,
            "unmatched": sum(1 for name in overrides
                             if name not in {str(e.get("company") or "").strip() for e in entries}),
        },
        "counts": {
            "total": len(entries),
            "on_map": len(on_map),
            "off_map": len(off_map),
            "jobs_total": sum(len(item["jobs"]) for item in on_map + off_map),
            "accuracy": accuracy,
        },
    }


def js_json(value) -> str:
    """JSON ที่ฝังใน <script> ได้ปลอดภัย: ปิดช่อง </script> และ <!--."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("</", "<\\/").replace("<!--", "<\\!--")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def html_escape(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_banner(reason: str, built_at: str, key_present: bool) -> str:
    """หน้าแบนเนอร์: ยังไม่มีคีย์/ยังไม่มีข้อมูล — ไม่เรียก Google เลย หน้าเว็บไม่พัง."""
    if key_present:
        head = "ยังไม่มีข้อมูลบริษัท (data\\companies.json ว่างหรือไม่มีไฟล์)"
        detail = f"ยังไม่มีพิกัดบริษัทให้ปักหมุด — รัน <code>{BANNER_COMMAND}</code> เพื่อสร้างข้อมูล"
    else:
        head = f"ยังไม่มี {KEY_NAME} ใน config\\secrets.env"
        detail = (f"วางคีย์แล้วรัน <code>{BANNER_COMMAND}</code>"
                  f" — ไฟล์ config\\secrets.env อยู่ใน .gitignore ไม่ขึ้น repo")
    return BANNER_TEMPLATE.replace("__TITLE__", html_escape(head)) \
                         .replace("__DETAIL__", detail) \
                         .replace("__REASON__", html_escape(reason)) \
                         .replace("__BUILT__", html_escape(built_at))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="สร้าง dist\\map.html จาก data\\companies.json")
    parser.add_argument("--out", default=None, help="เขียนไฟล์อื่นเพื่อทดสอบ (ค่าเริ่มต้น dist\\map.html)")
    args = parser.parse_args(argv)

    out_path = Path(args.out) if args.out else OUT_PATH
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    built_at = datetime.now().isoformat(timespec="seconds")
    key, key_source = geo.find_key()
    raw, entries = load_company_entries()
    overrides, overrides_file = load_overrides()
    cfg = load_json(FILTERS_PATH, {}) or {}

    if not key or not entries:
        reason = "ไม่มีคีย์" if not key else "companies.json ว่าง"
        page = render_banner(reason, built_at, key_present=bool(key))
        mode = "banner_no_key" if not key else "banner_no_data"
        payload = None
    else:
        payload = build_payload(entries, job_index(), cfg, overrides)
        page = render_map(payload, key, built_at, raw)
        mode = "map"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    try:
        shown = out_path.relative_to(ROOT).as_posix()
    except ValueError:
        shown = out_path.name

    report = {
        "mode": mode,
        "out": shown,
        "bytes": out_path.stat().st_size,
        "key_present": bool(key),
        "key_source": key_source,
        "companies_json": "data\\companies.json" if COMPANIES_PATH.exists() else None,
        "companies_read": len(entries),
        "companies_json_generated_at": (raw or {}).get("generated_at"),
        "built_at": built_at,
    }
    report["overrides"] = {
        "file": (OVERRIDES_PATH.relative_to(ROOT).as_posix() if overrides_file else None),
        "read": len(overrides),
        "applied": (payload or {}).get("overrides", {}).get("applied", 0),
        "unmatched": (payload or {}).get("overrides", {}).get("unmatched", 0),
    }
    if payload is not None:
        report["counts"] = payload["counts"]
    print(json.dumps(report, ensure_ascii=False))
    return 0


BANNER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1c2128;--muted:#6b7280;--line:#e3e6ea;--warn:#b45309;--accent:#1f6feb}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.5;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Leelawadee UI","Noto Sans Thai",Tahoma,Arial,sans-serif}
.card{max-width:760px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 22px}
h1{font-size:18px;margin:0 0 10px}
p{margin:6px 0;color:var(--muted)}
code{background:#f1f3f7;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12.5px;color:var(--ink)}
.note{margin-top:14px;padding:10px 12px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:8px;font-size:13px}
.foot{margin-top:16px;font-size:12.5px;color:var(--muted)}
a{color:var(--accent);display:inline-block;padding:4px 2px;line-height:16px}
</style>
</head>
<body>
<div class="card">
  <h1>__TITLE__</h1>
  <p>__DETAIL__</p>
  <div class="note">สาเหตุที่หน้านี้ยังไม่แสดงแผนที่: __REASON__ · หน้านี้ไม่เรียก Google เลย</div>
  <p class="foot">สร้างเมื่อ __BUILT__ · <a href="index.html">← กลับหน้า dashboard</a></p>
</div>
</body>
</html>
"""


def find_button(company: str) -> str:
    """ปุ่ม "ค้นหาใน Google" (แยกจากปุ่มอื่น) — เรียก Places API (New) ฝั่งเบราว์เซอร์"""
    co = html_escape(company)
    return ('<button type="button" class="findbtn" data-company="' + co
            + '" data-query="' + co + '">ค้นหาใน Google</button>')


def off_map_rows(payload: dict) -> str:
    """แผงข้าง: บริษัทที่ไม่ขึ้นแผนที่ + เหตุผล + ปุ่มค้นหา Google (เรนเดอร์ฝั่ง Python)."""
    rows = []
    for item in payload["off_map"]:
        co = html_escape(item["company"])
        rows.append(
            '<li data-company="' + co + '">'
            '<span class="co">' + co + '</span>'
            '<span class="why">' + html_escape(item["reason"]) + '</span>'
            '<span class="nj">' + str(len(item["jobs"])) + ' งาน · ความแม่น '
            + html_escape(item.get("accuracy") or "unknown") + '</span>'
            '<div class="rowbtns">' + find_button(item["company"])
            + '<span class="findres" hidden></span></div></li>'
        )
    return "".join(rows)


def approx_rows(payload: dict) -> str:
    """แถวบริษัทที่พิกัดหยาบ (accuracy=approx) บนแผนที่ — แต่ละแถวมีปุ่มค้นหา Google ของตัวเอง"""
    rows = []
    for item in payload["companies"]:
        if str(item.get("accuracy") or "") != "approx":
            continue
        if item.get("pos_source") == "override":
            continue
        co = html_escape(item["company"])
        rows.append(
            '<li data-company="' + co + '">'
            '<span class="co">' + co + '</span>'
            '<span class="why">' + html_escape(item.get("formatted_address") or "") + '</span>'
            '<div class="rowbtns">' + find_button(item["company"])
            + '<span class="findres" hidden></span></div></li>'
        )
    return "".join(rows)


def render_map(payload: dict, key: str, built_at: str, raw: dict) -> str:
    """หน้าที่มีคีย์: แผนที่ + หมุดกรุงเทพ + แผงบริษัทที่ไม่ขึ้นแผนที่."""
    import urllib.parse

    counts = payload["counts"]
    accuracy = counts["accuracy"]
    warn = ""
    if counts["on_map"] == 0:
        warn = ('<div class="warn" id="warnbox">ยังไม่มีบริษัทที่มีพิกัดในกรุงเทพให้ปักหมุด — '
                'บริษัทที่ยังไม่มีพิกัดรออยู่ในแผงด้านขวา (ลองรัน <code>'
                + html_escape(BANNER_COMMAND) + '</code>)</div>')
    source_at = html_escape(str((raw or {}).get("generated_at") or "-"))
    approx_html = approx_rows(payload)
    approx_n = approx_html.count('class="findbtn"')
    applied = int(payload.get("overrides", {}).get("applied", 0) or 0)
    override_note = ('' if not applied else
                     '<div class="warn" id="ovbox">ใช้พิกัดที่แก้เองจาก data\\company_overrides.json '
                     + str(applied) + ' บริษัท (ทับพิกัดจาก geocode)</div>')
    page = MAP_TEMPLATE
    replacements = {
        "__KEY__": html_escape(urllib.parse.quote(key, safe="")),
        "__MAPDATA__": js_json(payload),
        "__PLACES_KEY__": js_json(key),
        "__BUILT__": html_escape(built_at),
        "__SOURCE_AT__": source_at,
        "__N_TOTAL__": str(counts["total"]),
        "__N_ONMAP__": str(counts["on_map"]),
        "__N_OFFMAP__": str(counts["off_map"]),
        "__N_EXACT__": str(accuracy.get("exact", 0)),
        "__N_APPROX__": str(accuracy.get("approx", 0)),
        "__N_JOBS__": str(counts["jobs_total"]),
        "__OFFMAP_ROWS__": off_map_rows(payload),
        "__APPROX_ROWS__": approx_html,
        "__N_APPROX_SEARCH__": str(approx_n),
        "__OVERRIDE_NOTE__": override_note,
        "__WARN_BLOCK__": warn,
    }
    for token, value in replacements.items():
        page = page.replace(token, value)
    return page


MAP_TEMPLATE = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>บริษัทในประกาศงาน — แผนที่กรุงเทพ</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1c2128;--muted:#6b7280;--line:#e3e6ea;--accent:#1f6feb;
 --exact:#1f6feb;--approx:#b45309;--pin:#d1242f;--chip:#eef1f5;--warn:#fff7ed;--warnline:#fed7aa;--warnink:#9a3412;
 --found:#1a7f37;--fixed:#8250df}
*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%}
body{background:var(--bg);color:var(--ink);font-size:14px;line-height:1.45;display:flex;flex-direction:column;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Leelawadee UI","Noto Sans Thai",Tahoma,Arial,sans-serif}
header{background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px 8px;flex:0 0 auto}
.title-row{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h1{font-size:18px;margin:0}
.tag{font-size:12px;color:var(--muted)}
.meta{margin-left:auto;font-size:12px;color:var(--muted)}
a{color:var(--accent)}
.navlink{font-size:13px;text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:3px 8px;background:#fff}
.navlink:hover{background:#f2f7ff}
.stats{margin-top:6px;font-size:13px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap}
.stats b{color:var(--ink);font-weight:600}
.legend{margin-top:4px;font-size:12px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid #fff;
 box-shadow:0 0 0 1px var(--line);margin-right:5px;vertical-align:-1px}
.dot.exact{background:var(--exact)}
.dot.approx{background:var(--approx)}
.dot.found{background:var(--found)}
.dot.fixed{background:var(--fixed)}
.warn{margin-top:8px;padding:7px 9px;background:var(--warn);border:1px solid var(--warnline);
 color:var(--warnink);font-size:12.5px;border-radius:6px}
.warn code{background:#fff;border:1px solid var(--warnline);border-radius:4px;padding:0 4px}
.viewbar{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;align-items:center}
.viewbtn{font:inherit;font-size:12.5px;padding:3px 10px;border:1px solid var(--line);background:#fff;color:var(--ink);
 border-radius:999px;cursor:pointer;line-height:18px}
.viewbtn:hover{border-color:var(--accent);color:var(--accent)}
.viewbtn[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.viewbtn[aria-pressed="true"]:hover{color:#fff}
.viewbtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{flex:1 1 auto;display:flex;min-height:0}
#map{flex:1 1 auto;min-height:320px;background:#e9edf2}
aside{flex:0 0 320px;border-left:1px solid var(--line);background:var(--card);display:flex;flex-direction:column;min-height:0}
aside h2{font-size:13px;margin:0;padding:10px 12px;border-bottom:1px solid var(--line);color:var(--ink);
 display:flex;justify-content:space-between;align-items:baseline;gap:8px}
aside h2 span{font-size:12px;color:var(--muted);font-weight:400}
aside .hint{margin:0;padding:8px 12px;font-size:12px;color:var(--muted);border-bottom:1px solid var(--line)}
#offlist{list-style:none;margin:0;padding:0;overflow:auto;flex:1 1 auto}
#offlist li{display:flex;flex-direction:column;gap:2px;padding:8px 12px;border-bottom:1px solid var(--line)}
#offlist .co{font-weight:600}
#offlist .why{font-size:12px;color:var(--warnink)}
#offlist .nj{font-size:11.5px;color:var(--muted)}
#offlist .empty{padding:14px 12px;color:var(--muted);font-size:12.5px}
#maperr{margin:8px 12px;padding:8px 10px;background:var(--warn);border:1px solid var(--warnline);
 color:var(--warnink);font-size:12.5px;border-radius:6px}
/* จุดหมุด 12px (เดิม 28px) — พื้นที่กด 28px มาจาก padding ของ .pinwrap โดยไม่ทำให้จุดดูใหญ่ */
.pin{position:relative;width:12px;height:12px;border-radius:50%;display:block;
 color:#fff;font-size:0;font-weight:600;border:2px solid #fff;cursor:pointer;
 box-shadow:0 1px 3px rgba(0,0,0,.35)}
.pin.exact{background:var(--exact)}
.pin.approx{background:var(--approx)}
.pin.search{background:var(--found)}
.pin.override{background:var(--fixed)}
/* AdvancedMarkerElement ยึดจุดที่กลางขอบล่างของ content — เลื่อน content ลงครึ่งกล่อง (14px)
   ให้ "จุด" อยู่ที่พิกัดจริง ไม่ใช่มุมล่าง (ไม่มี anchorPoint ใน API รุ่นนี้) */
.pinwrap{position:relative;display:inline-flex;align-items:center;justify-content:center;padding:8px;cursor:pointer;
 transform:translateY(14px)}
.pinwrap.pinned .pin{box-shadow:0 0 0 2px #fff,0 0 0 4px var(--pin),0 2px 7px rgba(0,0,0,.45)}
.pinbadge{display:none;position:absolute;top:-2px;right:-6px;background:#fff;border:1px solid var(--pin);
 color:var(--pin);font-size:10.5px;font-weight:700;border-radius:999px;padding:0 4px;line-height:15px;white-space:nowrap}
.pinwrap.pinned .pinbadge{display:block}
.iw-jobs li.iw-pinned{background:#fff5f5;font-weight:600}
.iw-pinmark{color:var(--pin);font-size:11px;font-weight:700;flex:0 0 auto}
.pinbox{flex:0 0 auto;display:flex;flex-direction:column;min-height:0;max-height:48%;border-bottom:1px solid var(--line)}
#pinlist{list-style:none;margin:0;padding:0;overflow:auto;flex:1 1 auto}
#pinlist li{display:flex;flex-direction:column;gap:2px;padding:8px 12px;border-bottom:1px solid var(--line)}
#pinlist .pj-title{font-weight:600}
#pinlist .pj-title a{color:var(--accent);text-decoration:none}
#pinlist .pj-title a:hover{text-decoration:underline}
#pinlist .pj-meta{font-size:11.5px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap}
#pinlist .pj-remove{align-self:flex-start;margin-top:3px;font:inherit;font-size:11.5px;border:1px solid var(--line);
 background:#fff;color:var(--muted);border-radius:6px;padding:1px 6px;cursor:pointer}
#pinlist .pj-remove:hover{border-color:var(--pin);color:var(--pin)}
#pinlist .empty,#pinlist li.empty{padding:10px 12px;color:var(--muted);font-size:12.5px}
.offbox{flex:1 1 auto;display:flex;flex-direction:column;min-height:0}
.iw{max-width:320px;font-size:13px;color:var(--ink);font-family:inherit}
.iw-name{font-weight:700;font-size:14px;margin-bottom:2px}
.iw-addr{color:var(--muted);font-size:12.5px;margin-bottom:4px}
.iw-acc{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:999px;margin-bottom:6px}
.iw-acc.exact{background:#dbeafe;color:#1e40af}
.iw-acc.approx{background:#fef3c7;color:#92400e}
.iw-jobs{list-style:none;margin:0;padding:0}
.iw-jobs li{display:flex;gap:8px;justify-content:space-between;align-items:baseline;
 padding:3px 0;border-top:1px solid #eef1f5}
.iw-jobs a{color:var(--accent);text-decoration:none}
.iw-jobs a:hover{text-decoration:underline}
.iw-score{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;flex:0 0 auto}
.iw-empty{color:var(--muted);font-size:12px}
/* ปุ่ม "ค้นหาใน Google" — แยกจากปุ่มอื่น เห็นชัดทุกแถว (hit area >= 24px) */
.findbtn{font:inherit;font-size:11.5px;padding:2px 8px;min-height:24px;border:1px solid var(--line);background:#fff;
 color:var(--accent);border-radius:6px;cursor:pointer;line-height:16px}
.findbtn:hover{border-color:var(--accent);background:#f2f7ff}
.findbtn:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
#offlist .rowbtns,#approxlist .rowbtns{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:3px}
.findres{font-size:11.5px;color:var(--found)}
.findres[hidden]{display:none}
.approxbox{flex:0 1 auto;max-height:30%;min-height:0;display:flex;flex-direction:column;
 border-bottom:1px solid var(--line);overflow:hidden}
.approxbox[open]{max-height:42%}
.approxbox summary{cursor:pointer;font-size:13px;font-weight:600;padding:9px 12px;list-style:none}
.approxbox summary::-webkit-details-marker{display:none}
.approxbox summary::marker{content:''}
.approxbox summary:hover{color:var(--accent)}
#approxlist{list-style:none;margin:0;padding:0;overflow:auto;flex:1 1 auto}
#approxlist li{display:flex;flex-direction:column;gap:2px;padding:6px 12px;border-bottom:1px solid var(--line)}
#approxlist .co{font-weight:600;font-size:12.5px}
#approxlist .why{font-size:11.5px;color:var(--muted)}
.posbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:6px}
.posbtn:disabled{opacity:.55;cursor:not-allowed}
.posnote{font-size:11.5px;color:var(--muted)}
.exportbox{margin-top:6px;border:1px solid var(--line);border-radius:8px;padding:8px;background:#fbfcfd}
#exporttext{width:100%;height:104px;font-family:ui-monospace,Consolas,monospace;font-size:11.5px;
 border:1px solid var(--line);border-radius:6px;padding:6px;resize:vertical;background:#fff;color:var(--ink)}
.exportact{display:flex;gap:8px;margin-top:6px;flex-wrap:wrap}
.iw-acc.found{background:#dcfce7;color:#166534}
.iw-acc.fixed{background:#ede9fe;color:#5b21b6}
.iw-coords{font-size:11.5px;color:var(--muted);margin:0 0 6px;font-variant-numeric:tabular-nums}
.iw-find{margin:0 0 6px}
.chk{display:inline-flex;align-items:center;gap:4px;margin-left:6px;font-size:12px;color:var(--ink);cursor:pointer}
footer{flex:0 0 auto;border-top:1px solid var(--line);background:var(--card);padding:6px 16px;
 font-size:12px;color:var(--muted);display:flex;gap:12px;flex-wrap:wrap;align-items:center}
footer a{display:inline-block;padding:4px 2px;line-height:16px}
@media (max-width: 760px){
  main{flex-direction:column}
  #map{min-height:52vh}
  aside{flex:1 1 auto;border-left:0;border-top:1px solid var(--line);max-height:40vh}
}
</style>
</head>
<body>
<header>
  <div class="title-row">
    <h1>บริษัทในประกาศงาน — แผนที่กรุงเทพ</h1>
    <span class="tag">Google Maps · หมุดจาก Google Places</span>
    <span class="meta"><a class="navlink" href="index.html">← กลับหน้า dashboard</a></span>
  </div>
  <div class="stats">
    <span>บริษัททั้งหมด <b>__N_TOTAL__</b></span>
    <span>บนแผนที่ <b id="statOnmap">__N_ONMAP__</b></span>
    <span>ไม่พบบนแผนที่ <b id="statOffmap">__N_OFFMAP__</b></span>
    <span>งานในบริษัทเหล่านี้ <b>__N_JOBS__</b></span>
    <span>งานที่ปักหมุด <b id="pinStat">0</b></span>
  </div>
  <div class="viewbar" id="viewbar" role="group" aria-label="มุมมองหมุดบนแผนที่">
    <button type="button" class="viewbtn" data-view="all" aria-pressed="false">ทั้งหมด (__N_ONMAP__)</button>
    <button type="button" class="viewbtn" data-view="pinned" aria-pressed="false">ปักหมุด (<span id="viewPinCount">0</span>)</button>
    <button type="button" class="viewbtn" data-view="mix" aria-pressed="true">ผสม (ไฮไลต์ที่ปัก)</button>
  </div>
  <div class="posbar">
    <button type="button" class="viewbtn posbtn" id="exportbtn" disabled>ส่งออกพิกัดที่แก้ (0)</button>
    <span class="posnote" id="exportnote">ยังไม่มีพิกัดที่แก้ — ลากหมุดหรือกด "ค้นหาใน Google" ก่อน</span>
  </div>
  <div class="exportbox" id="exportbox" hidden>
    <textarea id="exporttext" readonly spellcheck="false" aria-label="JSON พิกัดที่แก้ (company_overrides.json)"></textarea>
    <div class="exportact">
      <button type="button" class="viewbtn" id="exportcopy">คัดลอก</button>
      <button type="button" class="viewbtn" id="exportdl">ดาวน์โหลด company_overrides.json</button>
    </div>
  </div>
  <div class="warn" id="viewempty" hidden>ยังไม่มีงานที่ปักหมุด — ปักจากหน้า dashboard</div>
  <div class="legend">
    <span><span class="dot exact"></span>ตรงชื่อบริษัท + อยู่กรุงเทพ (__N_EXACT__)</span>
    <span><span class="dot approx"></span>ประมาณ — ชื่อไม่ตรงเป๊ะ (__N_APPROX__)</span>
    <span><span class="dot fixed"></span>ตำแหน่งที่แก้เอง (ลากหมุด/company_overrides.json)</span>
    <span><span class="dot found"></span>Google · ค้นหาใหม่</span>
    <span>เฉพาะบริษัทที่อยู่ในกรุงเทพเท่านั้น · ไม่มีวงรัศมีพื้นที่ · ลากหมุดเพื่อแก้พิกัดได้</span>
  </div>
  __WARN_BLOCK__
  __OVERRIDE_NOTE__
</header>
<main>
  <div id="map"></div>
  <aside>
    <div class="pinbox">
      <h2>งานที่ปักหมุดไว้ (<span id="pinCount">0</span>) <span>จาก dashboard · ?pins=</span></h2>
      <p class="hint">ปักหมุดจาก dashboard ด้วยปุ่ม 📌 — หมุดของบริษัทที่มีงานถูกปักจะเด่นขึ้น (ไม่เพิ่มหมุดใหม่)</p>
      <ul id="pinlist"></ul>
    </div>
    <details class="approxbox" id="approxbox">
      <summary>พิกัดหยาบ — ค้นหาใหม่ (<span id="approxCount">__N_APPROX_SEARCH__</span>)</summary>
      <p class="hint">Google จับคู่ชื่อบริษัทไม่ตรงเป๊ะ · กด "ค้นหาใน Google" เพื่อปักพิกัดใหม่ (ติดป้าย Google · ค้นหาใหม่ + จังหวัด/ประเทศ)</p>
      <ul id="approxlist">__APPROX_ROWS__</ul>
    </details>
    <div class="offbox">
      <h2>ไม่ปรากฏบนแผนที่ <span>__N_OFFMAP__ บริษัท</span></h2>
      <p class="hint">หมุดขึ้นเฉพาะบริษัทที่ Google ยืนยันว่าอยู่ในกรุงเทพ — ที่เหลือแสดงที่นี่พร้อมเหตุผล · กด "ค้นหาใน Google" เพื่อหาพิกัดเอง
        <label class="chk"><input type="checkbox" id="searchbkk"> เติม «กรุงเทพ» ในคำค้น</label></p>
      <div id="maperr" hidden></div>
      <ul id="offlist">__OFFMAP_ROWS__</ul>
    </div>
  </aside>
</main>
<footer>
  <span>พิกัดจาก data\companies.json (สร้าง __SOURCE_AT__)</span>
  <span>หน้าเว็บสร้าง __BUILT__</span>
  <span><a href="index.html">dashboard</a></span>
</footer>
<script>
window.MAPDATA = __MAPDATA__;
(function () {
  'use strict';
  var DATA = window.MAPDATA || { companies: [], counts: {} };
  var EXACT_COLOR = '#1f6feb';
  var APPROX_COLOR = '#b45309';
  var PIN_COLOR = '#d1242f';
  var READY = false;

  function notice(message) {
    var box = document.getElementById('maperr');
    if (!box) return;
    box.textContent = message;
    box.hidden = false;
  }

  /* Google เรียกตัวนี้เมื่อคีย์ถูกปฏิเสธ — หน้าเว็บยังอ่านแผงรายชื่อได้ */
  window.gm_authFailure = function () {
    notice('Google ปฏิเสธคีย์ (auth failure) — ตรวจ GOOGLE_MAPS_API_KEY และการเปิด Maps JavaScript API');
  };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function safeUrl(value) {
    return /^https?:\/\//i.test(String(value || '')) ? String(value) : '';
  }

  /* ---------- ปักหมุด: ไฮไลต์บริษัทเดิมเท่านั้น ไม่เพิ่มหมุดใหม่ ----------
     อ่าน: localStorage['jobboard.pins'] (ค่าเริ่มต้น) · ?pins=id1,id2 (ถ้ามี = ทับ)
     ลบในแผง = ออกจาก localStorage + URL · localStorage ใช้ไม่ได้ = อยู่ในหน่วยความจำ */
  var PINS_KEY = 'jobboard.pins';
  var POS_KEY = 'jobboard.pinpos';
  var JOBS = DATA.jobs || {};
  var records = [];
  var recsByCompany = {};
  var AdvancedMarker = null;
  var openRec = null;

  /* ---------- พิกัดที่แก้เอง: localStorage['jobboard.pinpos'] ----------
     รูปแบบ {"<ชื่อบริษัท>":{"lat":..,"lng":..}} — รูปแบบเดียวกับ data\company_overrides.json
     เก็บจาก (ก) ลากหมุด (by="drag") และ (ข) ผลค้นหา Google (by="search", label = จังหวัด/ประเทศ)
     ปุ่ม "ส่งออกพิกัดที่แก้" พิมพ์เฉพาะ lat/lng ให้เอาไปวางเป็น data\company_overrides.json ได้ตรง ๆ */
  function readPositions() {
    var out = {};
    try {
      var raw = localStorage.getItem(POS_KEY);
      var obj = raw ? JSON.parse(raw) : {};
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return out;
      Object.keys(obj).forEach(function (name) {
        var pos = obj[name];
        if (!pos || typeof pos !== 'object') return;
        var lat = Number(pos.lat), lng = Number(pos.lng);
        if (!isFinite(lat) || !isFinite(lng)) return;
        if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
        out[name] = {
          lat: lat,
          lng: lng,
          label: String(pos.label || ''),
          by: String(pos.by || 'drag')
        };
      });
    } catch (e) { return {}; }
    return out;
  }

  function writePositions() {
    try { localStorage.setItem(POS_KEY, JSON.stringify(posStore)); } catch (e) { /* localStorage ปิด (file:// ที่บล็อก) */ }
  }

  var posStore = readPositions();

  function savePosition(company, lat, lng, label, by) {
    var key = String(company === undefined || company === null ? '' : company).trim();
    var latN = Number(lat), lngN = Number(lng);
    if (!key || !isFinite(latN) || !isFinite(lngN)) return;
    if (latN < -90 || latN > 90 || lngN < -180 || lngN > 180) return;
    posStore[key] = {
      lat: Math.round(latN * 1e7) / 1e7,
      lng: Math.round(lngN * 1e7) / 1e7,
      label: String(label || ''),
      by: String(by || 'drag')
    };
    writePositions();
    updateExportUI();
  }

  function positionCount() { return Object.keys(posStore).length; }

  function exportObject() {
    var out = {};
    Object.keys(posStore).sort().forEach(function (name) {
      out[name] = { lat: posStore[name].lat, lng: posStore[name].lng };
    });
    return out;
  }

  function updateExportUI() {
    var n = positionCount();
    var btn = document.getElementById('exportbtn');
    var box = document.getElementById('exportbox');
    var text = document.getElementById('exporttext');
    var note = document.getElementById('exportnote');
    if (btn) {
      btn.textContent = 'ส่งออกพิกัดที่แก้ (' + n + ')';
      btn.disabled = n === 0;
      btn.setAttribute('aria-disabled', n === 0 ? 'true' : 'false');
    }
    if (note) {
      note.textContent = n === 0
        ? 'ยังไม่มีพิกัดที่แก้ — ลากหมุดหรือกด "ค้นหาใน Google" ก่อน'
        : 'มี ' + n + ' พิกัดที่แก้ — คัดลอก/ดาวน์โหลด JSON แล้ววางเป็น data\\company_overrides.json (build_map.py อ่านตอน build)';
    }
    if (text) text.value = n === 0 ? '' : JSON.stringify(exportObject(), null, 2);
    if (box && n === 0) box.hidden = true;
  }

  function copyExport() {
    var text = JSON.stringify(exportObject(), null, 2);
    var box = document.getElementById('exporttext');
    var note = document.getElementById('exportnote');
    if (box) box.value = text;
    var ok = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch (e) { ok = false; }
    if (!ok && box) {
      try { box.select(); ok = document.execCommand('copy'); } catch (e) { ok = false; }
    }
    if (note) {
      note.textContent = ok
        ? 'คัดลอกแล้ว — วางเป็น data\\company_overrides.json'
        : 'คัดลอกอัตโนมัติไม่ได้ — เลือกข้อความในช่องแล้วคัดลอกเอง';
    }
  }

  function downloadExport() {
    var text = JSON.stringify(exportObject(), null, 2);
    var note = document.getElementById('exportnote');
    try {
      var blob = new Blob([text], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'company_overrides.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      if (note) note.textContent = 'ดาวน์โหลด company_overrides.json แล้ว — วางไว้ที่ data\\company_overrides.json';
    } catch (e) {
      if (note) note.textContent = 'ดาวน์โหลดไม่ได้ในเบราว์เซอร์นี้ — คัดลอกจากช่องข้อความแทน';
    }
  }

  function dedupe(list) {
    var out = [];
    (list || []).forEach(function (value) {
      var s = String(value === undefined || value === null ? '' : value).trim();
      if (s && out.indexOf(s) < 0) out.push(s);
    });
    return out;
  }

  function readStored() {
    try {
      var raw = localStorage.getItem(PINS_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? dedupe(arr) : [];
    } catch (e) { return []; }
  }

  function writeStored(list) {
    try { localStorage.setItem(PINS_KEY, JSON.stringify(list)); } catch (e) { /* localStorage ปิด (file:// ที่บล็อก) */ }
  }

  function queryPins() {
    var search = '';
    try { search = String(window.location.search || ''); } catch (e) { return null; }
    if (!search || search === '?') return null;
    try {
      var params = new URLSearchParams(search);
      if (!params.has('pins')) return null;
      return dedupe(String(params.get('pins') || '').split(','));
    } catch (e) { return null; }
  }

  var fromQuery = queryPins();
  var pins = fromQuery === null ? readStored() : fromQuery;
  if (fromQuery !== null) writeStored(pins);  /* ให้ dashboard เห็นชุดเดียวกัน */

  /* ---------- มุมมอง 3 โหมด: all (ทั้งหมด) · pinned (เฉพาะที่ปัก) · mix (ทั้งหมด + ไฮไลต์ที่ปัก) ----------
     อ่าน: ?view=all|pinned|mix (ทับ) · ไม่งั้น localStorage['jobboard.mapview'] · ไม่มี/ไม่ถูกต้อง → mix */
  var VIEW_KEY = 'jobboard.mapview';
  var VIEWS = ['all', 'pinned', 'mix'];
  var DEFAULT_VIEW = 'mix';
  var state = { map: null, info: null };

  function readView() {
    try {
      var raw = String(localStorage.getItem(VIEW_KEY) || '');
      return VIEWS.indexOf(raw) >= 0 ? raw : null;
    } catch (e) { return null; }
  }

  function writeView(value) {
    try { localStorage.setItem(VIEW_KEY, value); } catch (e) { /* localStorage ปิด (file:// ที่บล็อก) */ }
  }

  function queryView() {
    try {
      var params = new URLSearchParams(String(window.location.search || ''));
      if (!params.has('view')) return null;
      var value = String(params.get('view') || '').trim().toLowerCase();
      return VIEWS.indexOf(value) >= 0 ? value : DEFAULT_VIEW;
    } catch (e) { return null; }
  }

  var fromQueryView = queryView();
  var view = fromQueryView || readView() || DEFAULT_VIEW;
  writeView(view);

  function isPinned(id) {
    return pins.indexOf(String(id === undefined || id === null ? '' : id)) >= 0;
  }

  function countPinned(company) {
    var n = 0;
    (company.jobs || []).forEach(function (job) { if (isPinned(job.id)) n++; });
    return n;
  }

  function syncUrl() {
    try {
      if (!window.history || typeof history.replaceState !== 'function') return;
      var parts = [];
      if (pins.length) parts.push('pins=' + pins.map(encodeURIComponent).join(','));
      if (view !== DEFAULT_VIEW) parts.push('view=' + encodeURIComponent(view));
      var qs = parts.length ? '?' + parts.join('&') : '';
      history.replaceState(null, '', window.location.pathname + qs + (window.location.hash || ''));
    } catch (e) { /* file:// หรือ sandbox ปิดประวัติ — ไม่เป็นไร */ }
  }

  /* จำนวนบริษัทบนแผนที่ที่มีงานถูกปัก (= หมุดที่เห็นในโหมด pinned) */
  function pinnedCompanyCount() {
    var n = 0;
    (DATA.companies || []).forEach(function (company) { if (countPinned(company) > 0) n++; });
    return n;
  }

  function updateViewUI() {
    var buttons = document.querySelectorAll('#viewbar button.viewbtn');
    var n = pinnedCompanyCount();
    var badge = document.getElementById('viewPinCount');
    if (badge) badge.textContent = String(n);
    for (var i = 0; i < buttons.length; i++) {
      var on = buttons[i].getAttribute('data-view') === view;
      buttons[i].setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    var empty = document.getElementById('viewempty');
    if (empty) empty.hidden = !(view === 'pinned' && n === 0);
  }

  /* ตัวเลขสรุปหัวเว็บจาก state จริง: หมุดที่มีพิกัด = บนแผนที่ · ที่เหลือจาก counts.total = ไม่พบ
     (คำนวณจาก records/posStore ที่โหลดมา ไม่rebuild หน้า) */
  function updateCountsUI() {
    var on = records.length;
    var off = Math.max(0, Number((DATA.counts || {}).total || 0) - on);
    var onEl = document.getElementById('statOnmap');
    var offEl = document.getElementById('statOffmap');
    if (onEl) onEl.textContent = String(on);
    if (offEl) offEl.textContent = String(off);
  }

  function pinItem(id) {
    var job = JOBS[id];
    var li = el('li');
    if (!job) {
      li.className = 'missing';
      li.appendChild(el('span', 'pj-title', id));
      li.appendChild(el('span', 'pj-meta', 'ไม่พบงานนี้ใน data\\companies.json (อาจถูกตัดออกหรือเปลี่ยน id)'));
    } else {
      var title = el('span', 'pj-title');
      var url = safeUrl(job.url);
      if (url) {
        var link = el('a', null, job.title || '(ไม่มีชื่อตำแหน่ง)');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        title.appendChild(link);
      } else {
        title.textContent = job.title || '(ไม่มีชื่อตำแหน่ง)';
      }
      li.appendChild(title);
      var meta = el('span', 'pj-meta');
      meta.appendChild(el('span', null, job.company || '(ไม่ทราบบริษัท)'));
      meta.appendChild(el('span', null, 'คะแนน ' + (typeof job.score === 'number' ? job.score : 0)));
      li.appendChild(meta);
    }
    var remove = el('button', 'pj-remove', 'เอาเครื่องหมายออก');
    remove.type = 'button';
    remove.dataset.jobId = id;
    remove.setAttribute('aria-label', 'เอาเครื่องหมายออก: ' + (job && job.title ? job.title : id));
    li.appendChild(remove);
    return li;
  }

  function renderPanel() {
    var list = document.getElementById('pinlist');
    var stat = document.getElementById('pinStat');
    var head = document.getElementById('pinCount');
    if (stat) stat.textContent = String(pins.length);
    if (head) head.textContent = String(pins.length);
    if (!list) return;
    list.textContent = '';
    if (!pins.length) {
      list.appendChild(el('li', 'empty', 'ยังไม่มีงานที่ปักหมุด — กด 📌 ที่ dashboard แล้วเปิดหน้านี้ หรือส่ง ?pins=id1,id2 มา'));
      return;
    }
    pins.forEach(function (id) { list.appendChild(pinItem(id)); });
  }

  var FOUND_COLOR = '#1a7f37';
  var FIXED_COLOR = '#8250df';

  function defaultLabel(company) {
    if (company.pos_source === 'override') return 'ตำแหน่งที่แก้เอง (company_overrides.json)';
    if (company.accuracy === 'exact') return 'ที่อยู่จาก Google · ตรงชื่อบริษัท';
    if (company.accuracy === 'approx') return 'ประมาณ · ชื่อที่ Google คืนไม่ตรงกับชื่อบริษัท';
    return 'ไม่ทราบความแม่นของพิกัด';
  }

  /* ชนิดของตำแหน่ง: '' = จาก geocode ตอน build · 'override' = แก้เอง · 'search' = ผลค้นหา Google */
  function posKindOf(rec) {
    return rec.posKind || (rec.company.pos_source === 'override' ? 'override' : '');
  }

  function pinClass(rec) {
    var kind = posKindOf(rec);
    if (kind === 'search') return 'search';
    if (kind === 'override') return 'override';
    return rec.exact ? 'exact' : 'approx';
  }

  function pinColor(rec) {
    var kind = posKindOf(rec);
    if (kind === 'search') return FOUND_COLOR;
    if (kind === 'override') return FIXED_COLOR;
    return rec.exact ? EXACT_COLOR : APPROX_COLOR;
  }

  function currentLabel(rec) {
    return rec.posLabel || defaultLabel(rec.company);
  }

  function paintCompany(rec) {
    var on = countPinned(rec.company);
    var hl = on > 0 && view !== 'all';   /* โหมด "ทั้งหมด" ไม่ไฮไลต์ (กติกา Tz) */
    var total = (rec.company.jobs || []).length;
    var label = currentLabel(rec);
    if (rec.kind === 'adv') {
      rec.wrap.className = 'pinwrap' + (hl ? ' pinned' : '');
      rec.wrap.setAttribute('data-pinned', hl ? 'true' : 'false');
      rec.wrap.setAttribute('data-pinned-count', String(on));
      rec.wrap.setAttribute('data-company', rec.company.company);
      rec.wrap.setAttribute('data-pos', pinClass(rec));
      rec.pin.className = 'pin ' + pinClass(rec);
      rec.pin.title = label;
      rec.pin.setAttribute('aria-label', rec.company.company + ' · ' + label
        + (on > 0 ? ' · ปักหมุด ' + on + ' งาน' : ' · ' + total + ' งาน'));
      rec.badge.textContent = hl ? '📌 ' + on : '';
      if (rec.marker) { try { rec.marker.zIndex = hl ? 9000 : 1; } catch (e) { /* ไม่เป็นไร */ } }
      return;
    }
    if (!rec.marker) return;
    try {
      rec.marker.setIcon({
        path: google.maps.SymbolPath.CIRCLE,
        scale: hl ? 11 : 7,
        fillColor: hl ? PIN_COLOR : pinColor(rec),
        fillOpacity: 1,
        strokeColor: '#ffffff',
        strokeWeight: hl ? 3 : 2
      });
      rec.marker.setZIndex(hl ? 9000 : 1);
      rec.marker.setTitle(rec.company.company + ' · ' + label);
    } catch (e) { /* ไม่เป็นไร */ }
  }

  /* ซ่อน/แสดงหมุดตามโหมด · fit bounds ตามหมุดที่มองเห็น (ไม่มีเลย → กลับไป center กรุงเทพ) */
  function applyView(refit) {
    var onlyPinned = view === 'pinned';
    records.forEach(function (rec) {
      var show = !onlyPinned || countPinned(rec.company) > 0;
      rec.visible = show;
      if (state.map) {
        try {
          if (rec.kind === 'adv') rec.marker.map = show ? state.map : null;
          else rec.marker.setMap(show ? state.map : null);
        } catch (e) { /* ไม่เป็นไร */ }
      }
      paintCompany(rec);
    });
    updateCountsUI();
    if (refit) fitVisible();
  }

  function fitVisible() {
    if (!state.map || !window.google || !google.maps) return;
    var shown = records.filter(function (rec) { return rec.visible; });
    if (!shown.length) {
      state.map.setCenter(DATA.center || { lat: 13.7563, lng: 100.5018 });
      state.map.setZoom(DATA.zoom || 11);
      return;
    }
    if (shown.length === 1) {
      var only = shown[0].position ? shown[0].position() : null;
      if (only) {
        state.map.setCenter(only);
        state.map.setZoom(14);
      }
      return;
    }
    var bounds = new google.maps.LatLngBounds();
    shown.forEach(function (rec) {
      var pos = rec.position ? rec.position() : null;
      if (pos) bounds.extend(pos);
    });
    state.map.fitBounds(bounds, 40);
  }

  function removePin(id) {
    var key = String(id === undefined || id === null ? '' : id);
    pins = pins.filter(function (value) { return value !== key; });
    writeStored(pins);
    syncUrl();
    renderPanel();
    updateViewUI();
    applyView(true);
  }

  function toLatLng(value) {
    if (!value) return null;
    var lat = typeof value.lat === 'function' ? value.lat() : Number(value.lat);
    var lng = typeof value.lng === 'function' ? value.lng() : Number(value.lng);
    if (!isFinite(lat) || !isFinite(lng)) return null;
    return { lat: lat, lng: lng };
  }

  function findCompany(name) {
    var all = (DATA.companies || []).concat(DATA.off_map || []);
    for (var i = 0; i < all.length; i++) {
      if (String(all[i].company) === String(name)) return all[i];
    }
    return { company: String(name), lat: null, lng: null, formatted_address: '', province: '',
             accuracy: 'unknown', status: 'unknown', jobs: [] };
  }

  function openInfo(rec) {
    if (!state.map || !state.info) return;
    state.info.setContent(infoNode(rec));
    state.info.open({ map: state.map, anchor: rec.marker });
    openRec = rec;
  }

  function infoNode(rec) {
    var company = rec.company;
    var kind = posKindOf(rec);
    var box = el('div', 'iw');
    box.appendChild(el('div', 'iw-name', company.company));
    box.appendChild(el('div', 'iw-addr', company.formatted_address || 'ไม่มีที่อยู่จาก Google'));
    var accClass = kind === 'search' ? 'found'
      : (kind === 'override' ? 'fixed' : (company.accuracy === 'exact' ? 'exact' : 'approx'));
    box.appendChild(el('div', 'iw-acc ' + accClass, currentLabel(rec)));
    var pos = rec.position ? rec.position() : null;
    if (pos) {
      box.appendChild(el('div', 'iw-coords', 'พิกัด ' + pos.lat.toFixed(5) + ', ' + pos.lng.toFixed(5)
        + ' · ลากหมุดเพื่อแก้ตำแหน่งได้'));
    }
    if (company.accuracy !== 'exact' || kind) {
      var find = el('button', 'findbtn iw-find', 'ค้นหาใน Google');
      find.type = 'button';
      find.dataset.company = company.company;
      box.appendChild(find);
    }
    var jobs = company.jobs || [];
    var list = el('ul', 'iw-jobs');
    jobs.forEach(function (job) {
      var pinned = isPinned(job.id);
      var row = el('li', pinned ? 'iw-pinned' : null);
      var url = safeUrl(job.url);
      var link = url ? el('a', null, job.title || '(ไม่มีชื่อตำแหน่ง)') : el('span', null, job.title || '(ไม่มีชื่อตำแหน่ง)');
      if (url) {
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
      row.appendChild(link);
      if (pinned) row.appendChild(el('span', 'iw-pinmark', '📌 ปักหมุด'));
      row.appendChild(el('span', 'iw-score', 'คะแนน ' + (typeof job.score === 'number' ? job.score : 0)));
      list.appendChild(row);
    });
    if (!jobs.length) list.appendChild(el('li', 'iw-empty', 'ไม่มีงานของบริษัทนี้ในชุดที่แสดง'));
    box.appendChild(list);
    return box;
  }

  /* เขียนผลค้นหา/ผลลากลงแถวในแผง (off-map หรือพิกัดหยาบ) — ไม่มีแถวก็ไม่เป็นไร */
  function updateRow(company, text) {
    var rows = document.querySelectorAll('#offlist li, #approxlist li');
    for (var i = 0; i < rows.length; i++) {
      var res = rows[i].querySelector('.findres');
      if (!res) continue;
      var btn = rows[i].querySelector('button.findbtn');
      if (!btn || btn.dataset.company !== company) continue;
      res.textContent = text;
      res.hidden = false;
    }
  }

  /* ---------- ค้นหาใน Google = Places API (New) REST places:searchText ----------
     ตัวเก่าแบบ legacy (google.maps.places.* คลาสเก่า) ใช้กับคีย์ชุดนี้ไม่ได้
     → LegacyApiNotActivatedMapError · คีย์ที่ใช้ = คีย์เดียวกับที่ฝังในหน้านี้ ไม่ hardcode ใหม่
     fetch ถูกบล็อก/ล้มเหลว → ถอยไป importLibrary("places") + Place.searchByText */
  var PLACES_URL = 'https://places.googleapis.com/v1/places:searchText';
  var PLACES_FIELDS = 'places.displayName,places.formattedAddress,places.location,places.addressComponents';
  var PLACES_KEY = __PLACES_KEY__;

  /* ผลลัพธ์ Places (New) → {lat,lng,formattedAddress,components} · ไม่มีพิกัด = null (ไม่เดาพิกัด) */
  function normalizePlace(place) {
    if (!place) return null;
    var loc = place.location || {};
    var lat = typeof loc.lat === 'function' ? loc.lat()
      : (loc.latitude !== undefined ? Number(loc.latitude) : Number(loc.lat));
    var lng = typeof loc.lng === 'function' ? loc.lng()
      : (loc.longitude !== undefined ? Number(loc.longitude) : Number(loc.lng));
    if (!isFinite(lat) || !isFinite(lng)) return null;
    return {
      lat: lat,
      lng: lng,
      formattedAddress: String(place.formattedAddress || place.formatted_address || ''),
      components: place.addressComponents || place.address_components || []
    };
  }

  function searchByFetch(query) {
    return fetch(PLACES_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': PLACES_KEY,
        'X-Goog-FieldMask': PLACES_FIELDS
      },
      body: JSON.stringify({ textQuery: query, languageCode: 'th', regionCode: 'TH', pageSize: 1 })
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function (data) {
      return normalizePlace(((data && data.places) || [])[0]);
    });
  }

  function searchBySdk(query) {
    return google.maps.importLibrary('places').then(function (lib) {
      if (!lib || !lib.Place || typeof lib.Place.searchByText !== 'function') {
        throw new Error('ไลบรารี places ไม่มี Place.searchByText');
      }
      return lib.Place.searchByText({
        textQuery: query,
        fields: ['displayName', 'formattedAddress', 'location', 'addressComponents'],
        language: 'th',
        region: 'TH',
        maxResultCount: 1
      });
    }).then(function (res) {
      return normalizePlace(((res && res.places) || [])[0]);
    });
  }

  /* → Promise<place|null> · null = ไม่พบผลลัพธ์จริง (ไม่เดาพิกัด) · reject = ยิงไม่สำเร็จ */
  function searchPlaces(query) {
    if (!window.google || !google.maps || typeof fetch !== 'function') return searchBySdk(query);
    return searchByFetch(query).catch(function () { return searchBySdk(query); });
  }

  /* จังหวัด (ในไทย) หรือชื่อประเทศ (นอกไทย) จาก addressComponents — อยู่นอกกรุงเทพเท่านั้น */
  function placeWhere(place) {
    var comps = (place && place.components) || [];
    var country = null, admin = null;
    comps.forEach(function (comp) {
      var types = comp.types || [];
      if (types.indexOf('country') >= 0) country = comp;
      if (types.indexOf('administrative_area_level_1') >= 0) admin = comp;
    });
    function longText(comp) {
      if (!comp) return '';
      return String(comp.longText || comp.long_name || comp.shortText || comp.short_name || '');
    }
    function shortText(comp) {
      if (!comp) return '';
      return String(comp.shortText || comp.short_name || comp.longText || comp.long_name || '');
    }
    var addr = String((place && place.formattedAddress) || '');
    var bangkok = /กรุงเทพ|Bangkok/i.test(addr)
      || /Bangkok|กรุงเทพ/i.test(longText(admin) + ' ' + shortText(admin));
    if (bangkok) return '';
    if (country && shortText(country).toUpperCase() !== 'TH') return longText(country);
    if (admin) return longText(admin);
    if (country) return longText(country);
    /* ไม่มี components → parse จาก formattedAddress: ท่อนที่มีรหัสไปรษณีย์ = จังหวัด · ไม่มี → ท่อนสุดท้าย (ประเทศ) */
    var parts = addr.split(',');
    for (var i = parts.length - 1; i >= 0; i--) {
      if (/\d{5}/.test(parts[i])) return parts[i].replace(/\d{5}/, '').replace(/\s+/g, ' ').trim();
    }
    return parts.length > 1 ? String(parts[parts.length - 1]).trim() : '';
  }

  /* ปุ่ม "ค้นหาใน Google" (แยก): ผลแรกที่มีพิกัด → ปักหมุด + บันทึกใน jobboard.pinpos */
  function searchCompany(company) {
    if (!state.map) { notice('ยังโหลดแผนที่ไม่เสร็จ — รอสักครู่แล้วกดใหม่'); return; }
    var chk = document.getElementById('searchbkk');
    var query = String(company) + (chk && chk.checked ? ' กรุงเทพ' : '');
    updateRow(company, 'กำลังค้นหา: ' + query);
    searchPlaces(query).then(function (place) {
      if (!place) { updateRow(company, 'Google ไม่พบผลลัพธ์'); return; }
      var where = placeWhere(place);
      var label = 'Google · ค้นหาใหม่' + (where ? ' · ' + where : '');
      var rec = applyCompanyPosition(company, place.lat, place.lng, label, 'search');
      savePosition(company, place.lat, place.lng, label, 'search');
      if (rec) {
        if (place.formattedAddress) rec.company.formatted_address = place.formattedAddress;
        paintCompany(rec);
      }
      updateRow(company, label + ' → ปักหมุดแล้ว');
      applyView(false);
      if (rec) openInfo(rec);
    }).catch(function (err) {
      updateRow(company, 'ค้นหาไม่สำเร็จ (' + String((err && err.message) || err) + ')');
    });
  }

  function onDragEnd(rec) {
    var pos = rec.position ? rec.position() : null;
    if (!pos) return;
    rec.posLabel = 'ตำแหน่งที่แก้เอง';
    rec.posKind = 'override';
    paintCompany(rec);
    savePosition(rec.company.company, pos.lat, pos.lng, rec.posLabel, 'drag');
    updateRow(rec.company.company, 'ตำแหน่งที่แก้เอง → ' + pos.lat.toFixed(5) + ', ' + pos.lng.toFixed(5));
    if (openRec === rec) openInfo(rec);
  }

  /* หมุดหนึ่งอัน: มาจาก build หรือจากผลค้นหา/พิกัดที่แก้เอง · ลากได้ทั้งคู่ */
  function makeRecord(company, position, posLabel, posKind) {
    var exact = company.accuracy === 'exact';
    var rec, marker;
    if (AdvancedMarker) {
      var wrap = el('div', 'pinwrap');
      var pin = el('div', 'pin ' + (exact ? 'exact' : 'approx'));
      pin.setAttribute('role', 'button');
      var badge = el('span', 'pinbadge', '');
      wrap.appendChild(pin);
      wrap.appendChild(badge);
      marker = new AdvancedMarker({ map: state.map, position: position, title: company.company, content: wrap });
      marker.gmpDraggable = true;   /* แอตทริบิวต์ gmp-draggable: ลากหมุดเพื่อแก้พิกัดได้ */
      rec = { kind: 'adv', wrap: wrap, pin: pin, badge: badge, marker: marker, company: company,
              exact: exact, posLabel: posLabel || '', posKind: posKind || '', visible: true };
      marker.addListener('gmp-dragend', function () { onDragEnd(rec); });
    } else {
      marker = new google.maps.Marker({
        map: state.map,
        position: position,
        title: company.company,
        draggable: true,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 7,
          fillColor: exact ? EXACT_COLOR : APPROX_COLOR,
          fillOpacity: 1,
          strokeColor: '#ffffff',
          strokeWeight: 2
        }
      });
      marker.addListener('dragend', function () { onDragEnd(rec); });
      rec = { kind: 'legacy', marker: marker, company: company, exact: exact,
              posLabel: posLabel || '', posKind: posKind || '', visible: true };
    }
    rec.position = function () {
      return rec.kind === 'adv' ? toLatLng(rec.marker.position) : toLatLng(rec.marker.getPosition());
    };
    marker.addListener('click', function () { openInfo(rec); });
    company.lat = position.lat;
    company.lng = position.lng;
    records.push(rec);
    recsByCompany[company.company] = rec;
    return rec;
  }

  /* ย้าย/สร้างหมุดของบริษัทหนึ่งตามพิกัดที่กำหนด แล้วติดป้ายตามชนิด (search/override) */
  function applyCompanyPosition(name, lat, lng, label, kind) {
    if (!state.map) return null;
    var rec = recsByCompany[name];
    var company;
    if (rec) {
      try {
        if (rec.kind === 'adv') rec.marker.position = { lat: lat, lng: lng };
        else rec.marker.setPosition({ lat: lat, lng: lng });
      } catch (e) { /* ไม่เป็นไร */ }
      company = rec.company;
    } else {
      company = findCompany(name);
      rec = makeRecord(company, { lat: lat, lng: lng }, label, kind);
    }
    company.lat = lat;
    company.lng = lng;
    rec.posLabel = label || '';
    rec.posKind = kind || '';
    paintCompany(rec);
    return rec;
  }

  window.initMap = function () {
    var host = document.getElementById('map');
    if (!host) return;
    if (!window.google || !google.maps) {
      notice('โหลด Google Maps ไม่ได้ — ยังใช้แผงรายชื่อด้านขวาได้');
      return;
    }
    var map;
    try {
      map = new google.maps.Map(host, {
        center: DATA.center || { lat: 13.7563, lng: 100.5018 },
        zoom: DATA.zoom || 11,
        mapId: DATA.map_id || 'DEMO_MAP_ID',
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: true
      });
    } catch (err) {
      notice('สร้างแผนที่ไม่ได้: ' + (err && err.message ? err.message : String(err)));
      return;
    }
    state.map = map;
    state.info = new google.maps.InfoWindow({ maxWidth: 340 });
    AdvancedMarker = google.maps.marker && google.maps.marker.AdvancedMarkerElement
      ? google.maps.marker.AdvancedMarkerElement : null;
    records = [];
    recsByCompany = {};
    var failed = 0;
    (DATA.companies || []).forEach(function (company) {
      if (typeof company.lat !== 'number' || typeof company.lng !== 'number') return;
      try {
        var rec = makeRecord(company, { lat: company.lat, lng: company.lng }, '', '');
        paintCompany(rec);
      } catch (e) { failed++; }
    });
    if (failed) notice('สร้างหมุดไม่ได้ ' + failed + ' รายการ — แผงรายชื่อด้านขวายังใช้ได้');
    /* พิกัดที่แก้เองจาก localStorage['jobboard.pinpos'] ทับพิกัดที่ build มา + สร้างหมุดให้บริษัทที่ยังไม่มีหมุด */
    Object.keys(posStore).forEach(function (name) {
      var pos = posStore[name];
      var label = pos.label || 'ตำแหน่งที่แก้เอง';
      var kind = (pos.by === 'search' || label.indexOf('Google · ค้นหาใหม่') === 0) ? 'search' : 'override';
      try { applyCompanyPosition(name, pos.lat, pos.lng, label, kind); } catch (e) { /* หมุดเดียวเสียไม่ทำให้ทั้งหน้าพัง */ }
    });
    READY = true;
    updateExportUI();
    applyView(fromQueryView !== null);   /* โหมดเริ่มต้นคงเดิม (center กรุงเทพ) เว้นแต่ URL ระบุมา */
  };

  var pinList = document.getElementById('pinlist');
  if (pinList) {
    pinList.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('button.pj-remove') : null;
      if (!btn) return;
      removePin(btn.dataset.jobId);
    });
  }

  var viewbar = document.getElementById('viewbar');
  if (viewbar) {
    viewbar.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('button.viewbtn') : null;
      if (!btn) return;
      var next = btn.getAttribute('data-view');
      if (VIEWS.indexOf(next) < 0) return;
      view = next;
      writeView(view);
      syncUrl();
      updateViewUI();
      applyView(true);
    });
  }
  /* ปุ่ม "ค้นหาใน Google" — ใช้ร่วมกันทั้งแผง off-map, แผงพิกัดหยาบ และ info window */
  document.addEventListener('click', function (ev) {
    var target = ev.target;
    var btn = target && target.closest ? target.closest('button.findbtn') : null;
    if (!btn) return;
    ev.preventDefault();
    var company = String(btn.dataset.company || '').trim();
    if (company) searchCompany(company);
  });

  var exportBtn = document.getElementById('exportbtn');
  if (exportBtn) {
    exportBtn.addEventListener('click', function () {
      updateExportUI();
      var box = document.getElementById('exportbox');
      if (box) box.hidden = false;
      var text = document.getElementById('exporttext');
      if (text) { text.focus(); try { text.select(); } catch (e) { /* ไม่เป็นไร */ } }
    });
  }
  var copyBtn = document.getElementById('exportcopy');
  if (copyBtn) copyBtn.addEventListener('click', copyExport);
  var dlBtn = document.getElementById('exportdl');
  if (dlBtn) dlBtn.addEventListener('click', downloadExport);

  renderPanel();
  updateViewUI();
  updateExportUI();

  window.addEventListener('load', function () {
    setTimeout(function () {
      if (READY) return;
      notice('โหลด Google Maps ไม่ได้ภายใน 10 วินาที — ตรวจคีย์/การเปิด Maps JavaScript API '
        + '(แผนที่ว่าง แต่รายชื่อบริษัทด้านขวายังครบ)');
    }, 10000);
  });
})();
</script>
<script async
  src="https://maps.googleapis.com/maps/api/js?key=__KEY__&amp;language=th&amp;region=TH&amp;libraries=marker,places&amp;loading=async&amp;callback=initMap&amp;v=weekly"></script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
