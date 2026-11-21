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
  · ข้อมูลงาน/คะแนนคิดสดจาก data\\jobs.json ด้วย src\\filters.py (ไม่ใช้ค่าที่ค้างใน companies.json)
  · ข้อความจากประกาศงาน (title/company) ใส่ด้วย textContent เท่านั้น — ไม่ innerHTML
  · ลิงก์ภายนอกต้องขึ้นต้น http(s):// เท่านั้น (กัน javascript: จากต้นทาง)
  · ไม่มีคีย์ หรือ companies.json ว่าง/ไม่มี → ยังสร้างหน้านี้ แต่เป็นหน้าแบนเนอร์บอกวิธี ไม่เรียก Google เลย
  · คีย์อ่านตอน build แล้วฝังใน dist\\map.html (Maps JS ต้องมีคีย์ฝั่ง client) — ไม่เขียนลง src\\/config\\/data\\
    ⚠ dist\\map.html อยู่บน GitHub Pages แบบสาธารณะ → ต้องจำกัดคีย์ด้วย HTTP referrer
  · ไม่มี path absolute ในไฟล์นี้: ROOT มาจาก __file__

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


def build_payload(entries: list, index: dict, cfg: dict) -> dict:
    on_map, off_map = [], []
    for entry in entries:
        company = str(entry.get("company") or "").strip()
        item = {
            "company": company,
            "lat": round(float(entry["lat"]), 7) if has_coords(entry) else None,
            "lng": round(float(entry["lng"]), 7) if has_coords(entry) else None,
            "formatted_address": str(entry.get("formatted_address") or ""),
            "province": str(entry.get("province") or ""),
            "accuracy": str(entry.get("accuracy") or "unknown"),
            "status": str(entry.get("status") or "unknown"),
            "found_name": str(entry.get("found_name") or ""),
            "jobs": company_jobs(entry, index, cfg),
        }
        if has_coords(entry) and entry.get("in_bangkok") is True:
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
    cfg = load_json(FILTERS_PATH, {}) or {}

    if not key or not entries:
        reason = "ไม่มีคีย์" if not key else "companies.json ว่าง"
        page = render_banner(reason, built_at, key_present=bool(key))
        mode = "banner_no_key" if not key else "banner_no_data"
        payload = None
    else:
        payload = build_payload(entries, job_index(), cfg)
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


def off_map_rows(payload: dict) -> str:
    """แผงข้าง: บริษัทที่ไม่ขึ้นแผนที่ + เหตุผล (เรนเดอร์ฝั่ง Python — ไม่ต้องพึ่ง JS)."""
    rows = []
    for item in payload["off_map"]:
        rows.append(
            '<li><span class="co">' + html_escape(item["company"]) + '</span>'
            '<span class="why">' + html_escape(item["reason"]) + '</span>'
            '<span class="nj">' + str(len(item["jobs"])) + ' งาน</span></li>'
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
    page = MAP_TEMPLATE
    replacements = {
        "__KEY__": html_escape(urllib.parse.quote(key, safe="")),
        "__MAPDATA__": js_json(payload),
        "__BUILT__": html_escape(built_at),
        "__SOURCE_AT__": source_at,
        "__N_TOTAL__": str(counts["total"]),
        "__N_ONMAP__": str(counts["on_map"]),
        "__N_OFFMAP__": str(counts["off_map"]),
        "__N_EXACT__": str(accuracy.get("exact", 0)),
        "__N_APPROX__": str(accuracy.get("approx", 0)),
        "__N_JOBS__": str(counts["jobs_total"]),
        "__OFFMAP_ROWS__": off_map_rows(payload),
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
 --exact:#1f6feb;--approx:#b45309;--pin:#d1242f;--chip:#eef1f5;--warn:#fff7ed;--warnline:#fed7aa;--warnink:#9a3412}
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
.warn{margin-top:8px;padding:7px 9px;background:var(--warn);border:1px solid var(--warnline);
 color:var(--warnink);font-size:12.5px;border-radius:6px}
.warn code{background:#fff;border:1px solid var(--warnline);border-radius:4px;padding:0 4px}
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
.pin{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;
 color:#fff;font-size:12px;font-weight:600;border:2px solid #fff;cursor:pointer;
 box-shadow:0 1px 3px rgba(0,0,0,.35)}
.pin.exact{background:var(--exact)}
.pin.approx{background:var(--approx)}
.pinwrap{position:relative;display:inline-flex;align-items:center;justify-content:center}
.pinwrap.pinned .pin{background:var(--pin);width:34px;height:34px;font-size:13.5px;border-width:3px;
 box-shadow:0 0 0 3px #fff,0 2px 7px rgba(0,0,0,.45)}
.pinbadge{display:none;position:absolute;top:-9px;right:-12px;background:#fff;border:1px solid var(--pin);
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
    <span>บนแผนที่ <b>__N_ONMAP__</b></span>
    <span>ไม่พบบนแผนที่ <b>__N_OFFMAP__</b></span>
    <span>งานในบริษัทเหล่านี้ <b>__N_JOBS__</b></span>
    <span>งานที่ปักหมุด <b id="pinStat">0</b></span>
  </div>
  <div class="legend">
    <span><span class="dot exact"></span>ตรงชื่อบริษัท + อยู่กรุงเทพ (__N_EXACT__)</span>
    <span><span class="dot approx"></span>ประมาณ — ชื่อไม่ตรงเป๊ะ (__N_APPROX__)</span>
    <span>เฉพาะบริษัทที่อยู่ในกรุงเทพเท่านั้น · ไม่มีวงรัศมีพื้นที่</span>
  </div>
  __WARN_BLOCK__
</header>
<main>
  <div id="map"></div>
  <aside>
    <div class="pinbox">
      <h2>งานที่ปักหมุดไว้ (<span id="pinCount">0</span>) <span>จาก dashboard · ?pins=</span></h2>
      <p class="hint">ปักหมุดจาก dashboard ด้วยปุ่ม 📌 — หมุดของบริษัทที่มีงานถูกปักจะเด่นขึ้น (ไม่เพิ่มหมุดใหม่)</p>
      <ul id="pinlist"></ul>
    </div>
    <div class="offbox">
      <h2>ไม่ปรากฏบนแผนที่ <span>__N_OFFMAP__ บริษัท</span></h2>
      <p class="hint">หมุดขึ้นเฉพาะบริษัทที่ Google ยืนยันว่าอยู่ในกรุงเทพ — ที่เหลือแสดงที่นี่พร้อมเหตุผล</p>
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
  var JOBS = DATA.jobs || {};
  var records = [];

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
      var qs = pins.length ? '?pins=' + pins.map(encodeURIComponent).join(',') : '';
      history.replaceState(null, '', window.location.pathname + qs + (window.location.hash || ''));
    } catch (e) { /* file:// หรือ sandbox ปิดประวัติ — ไม่เป็นไร */ }
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

  function paintCompany(rec) {
    var on = countPinned(rec.company);
    var total = (rec.company.jobs || []).length;
    if (rec.kind === 'adv') {
      rec.wrap.className = 'pinwrap' + (on > 0 ? ' pinned' : '');
      rec.wrap.setAttribute('data-pinned', on > 0 ? 'true' : 'false');
      rec.wrap.setAttribute('data-pinned-count', String(on));
      rec.wrap.setAttribute('data-company', rec.company.company);
      rec.pin.setAttribute('aria-label', rec.company.company
        + (on > 0 ? ' · ปักหมุด ' + on + ' งาน' : ' · ' + total + ' งาน'));
      rec.badge.textContent = on > 0 ? '📌 ' + on : '';
      if (rec.marker) { try { rec.marker.zIndex = on > 0 ? 9000 : 1; } catch (e) { /* ไม่เป็นไร */ } }
      return;
    }
    if (!rec.marker) return;
    try {
      rec.marker.setIcon({
        path: google.maps.SymbolPath.CIRCLE,
        scale: on > 0 ? 12 : 8,
        fillColor: on > 0 ? PIN_COLOR : (rec.exact ? EXACT_COLOR : APPROX_COLOR),
        fillOpacity: 1,
        strokeColor: '#ffffff',
        strokeWeight: on > 0 ? 3 : 2
      });
      rec.marker.setZIndex(on > 0 ? 9000 : 1);
      rec.marker.setTitle(rec.company.company + (on > 0 ? ' · ปักหมุด ' + on + ' งาน' : ''));
    } catch (e) { /* ไม่เป็นไร */ }
  }

  function paintAll() { records.forEach(paintCompany); }

  function removePin(id) {
    var key = String(id === undefined || id === null ? '' : id);
    pins = pins.filter(function (value) { return value !== key; });
    writeStored(pins);
    syncUrl();
    renderPanel();
    paintAll();
  }

  function infoNode(company) {
    var box = el('div', 'iw');
    box.appendChild(el('div', 'iw-name', company.company));
    box.appendChild(el('div', 'iw-addr', company.formatted_address || 'ไม่มีที่อยู่จาก Google'));
    var exact = company.accuracy === 'exact';
    box.appendChild(el('div', 'iw-acc ' + (exact ? 'exact' : 'approx'),
      exact ? 'ที่อยู่จาก Google · ตรงชื่อบริษัท' : 'ประมาณ · ชื่อที่ Google คืนไม่ตรงกับชื่อบริษัท'));
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
    var info = new google.maps.InfoWindow({ maxWidth: 340 });
    var Advanced = google.maps.marker && google.maps.marker.AdvancedMarkerElement
      ? google.maps.marker.AdvancedMarkerElement : null;
    function openInfo(company, anchor) {
      info.setContent(infoNode(company));
      info.open({ map: map, anchor: anchor });
    }
    records = [];
    (DATA.companies || []).forEach(function (company) {
      if (typeof company.lat !== 'number' || typeof company.lng !== 'number') return;
      var position = { lat: company.lat, lng: company.lng };
      var exact = company.accuracy === 'exact';
      var marker, rec;
      if (Advanced) {
        var wrap = el('div', 'pinwrap');
        var pin = el('div', 'pin ' + (exact ? 'exact' : 'approx'), String((company.jobs || []).length));
        pin.setAttribute('role', 'button');
        pin.setAttribute('aria-label', company.company);
        var badge = el('span', 'pinbadge', '');
        wrap.appendChild(pin);
        wrap.appendChild(badge);
        marker = new Advanced({ map: map, position: position, title: company.company, content: wrap });
        rec = { kind: 'adv', wrap: wrap, pin: pin, badge: badge, marker: marker, company: company, exact: exact };
      } else {
        marker = new google.maps.Marker({
          map: map,
          position: position,
          title: company.company,
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: exact ? EXACT_COLOR : APPROX_COLOR,
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 2
          }
        });
        rec = { kind: 'legacy', marker: marker, company: company, exact: exact };
      }
      marker.addListener('click', function () { openInfo(company, marker); });
      records.push(rec);
      paintCompany(rec);
    });
    READY = true;
  };

  var pinList = document.getElementById('pinlist');
  if (pinList) {
    pinList.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('button.pj-remove') : null;
      if (!btn) return;
      removePin(btn.dataset.jobId);
    });
  }
  renderPanel();

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
  src="https://maps.googleapis.com/maps/api/js?key=__KEY__&amp;language=th&amp;region=TH&amp;libraries=marker&amp;loading=async&amp;callback=initMap&amp;v=weekly"></script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
