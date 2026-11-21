"""geocode_companies.py — ค้นพิกัด/ที่อยู่ของบริษัทที่อยู่บนหน้า dashboard ด้วย Google

อ่าน: data\\jobs.json · config\\filters.json · config\\switches.json · config\\secrets.env (เอา GOOGLE_MAPS_API_KEY)
เขียน: data\\companies.json (บริษัทไม่ซ้ำ + พิกัด + ที่อยู่ + ความแม่นของหมุด)

กติกา
  · บริษัทที่เอามาค้น = ชุดเดียวกับที่ขึ้นหน้า dashboard (ผ่าน src\\filters.py drop_reason = None)
    ไม่ใช่ทั้ง 684 แถว — ตัวเลขจึงตรงกับ window.JOBS บนหน้าเว็บ (61 แถว → 47 บริษัท)
  · ห้ามเดาพิกัด: ไม่เจอ/ไม่แน่ใจ → lat/lng = null + accuracy "unknown" (ไม่ใส่จุดกลางกรุงเทพแทน)
  · ไม่ผูกคำค้นกับ "Bangkok": ค้น "<บริษัท> Thailand" แล้วใช้ locationBias กรุงเทพ (เบน ไม่ใช่บังคับ)
    บริษัทที่อยู่นอกกรุงเทพจึงยังรายงานตามจริง ไม่ถูกลากเข้ามากรุงเทพ
  · cache: บริษัทที่ status "ok" และมีพิกัดอยู่แล้ว → ใช้ของเดิม ไม่ยิง API ซ้ำ (โควตา demo key จำกัด)
    --refresh = ยิงใหม่ทั้งชุด (ยกเว้น --limit ตัดก่อน)
  · คีย์ไม่ออก stdout/stderr และไม่ถูกลงไฟล์: ข้อความ error ทุกก้อนผ่าน redact() ก่อนพิมพ์/เก็บ
  · อ่านคีย์จาก config\\secrets.env เป็นหลัก (ถ้ามี env GOOGLE_MAPS_API_KEY ใช้ env ก่อน — สะดวกตอนทดสอบ)
  · ไม่มีคีย์ → พิมพ์ "no GOOGLE_MAPS_API_KEY in config\\secrets.env" แล้ว exit 2 โดยไม่ยิงเน็ต
  · คีย์ผิดรูป (ไม่ใช่ AIza + 35 ตัว = 39) → exit 2 ก่อนยิงเน็ต: Google ตอบ 401 แต่ไม่ได้บอกว่า "ผิดชนิดของ
    credential" คำขอที่เสียไปจึงเปล่าประโยชน์ · ข้อความบอกได้แค่ความยาวกับ 4 ตัวแรก ห้ามพิมพ์คีย์
  · หน่วง >= 0.2 วิ/คำขอ · timeout 15 วิ · error เก็บรายบริษัท ไม่ retry รัว

ใช้
  python src\\geocode_companies.py                # ค้นบริษัทที่ยังไม่มีพิกัด
  python src\\geocode_companies.py --limit 10     # จำกัดจำนวนคำขอรอบนี้
  python src\\geocode_companies.py --refresh      # ยิงใหม่ทุกบริษัท
  python src\\geocode_companies.py --provider geocoding
  python src\\geocode_companies.py --check-key    # ตรวจรูปคีย์เท่านั้น (ไม่ยิงเน็ต) · exit 0 ถูก / 2 ผิด
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import filters as filters_mod  # noqa: E402  (อ่านอย่างเดียว — ใช้คัดแถวให้ตรงกับหน้า dashboard)

DATA = ROOT / "data"
CONFIG = ROOT / "config"
JOBS_PATH = DATA / "jobs.json"
FILTERS_PATH = CONFIG / "filters.json"
SWITCHES_PATH = CONFIG / "switches.json"
SECRETS_PATH = CONFIG / "secrets.env"
OUT_PATH = DATA / "companies.json"

KEY_NAME = "GOOGLE_MAPS_API_KEY"
KEY_SHAPE_RE = re.compile(r"^AIza[0-9A-Za-z_\-]{35}$")   # รูป API key ของ Google Maps = 39 ตัว
KEY_EXPECTED = "AIza+35 chars (39)"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
FIELD_MASK = "places.displayName,places.formattedAddress,places.location,places.addressComponents"
DELAY_SECONDS = 0.25          # >= 0.2 ตามข้อกำหนด (เว้นเผื่อ jitter)
TIMEOUT_SECONDS = 15
BANGKOK_CENTER = (13.7563, 100.5018)
BIAS_RADIUS_M = 50000.0

# ข้อความที่บอกว่าปัญหาอยู่ที่คีย์/การเปิด API ไม่ใช่ที่บริษัทนั้น → หยุดทันที ไม่ยิงต่อให้เปลืองโควตา
AUTH_HINTS = (
    "api key not valid",
    "api_key_invalid",
    "api key expired",
    "request_denied",
    "permission_denied",
    "not authorized",
    "is not enabled",
    "has not been used in project",
    "invalid api key",
)


# ------------------------------------------------------------------------ secrets
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_secrets(path: Path) -> dict:
    """parser เองแบบไม่ใช้แพ็กเกจ: KEY=VALUE · # คอมเมนต์ · ตัด quote ครอบ · export นำหน้าได้."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        values[match.group(1)] = value
    return values


def find_key() -> tuple[str | None, str | None]:
    """→ (key, แหล่งที่มา) · env มาก่อน แล้วค่อย config\\secrets.env."""
    env_key = (os.environ.get(KEY_NAME) or "").strip()
    if env_key:
        return env_key, "env"
    file_key = (parse_secrets(SECRETS_PATH).get(KEY_NAME) or "").strip()
    if file_key:
        return file_key, "config\\secrets.env"
    return None, None


def key_prefix(key: str | None) -> str:
    """4 ตัวแรกของคีย์ — สั้นกว่านั้นไม่พิมพ์เลย (จะกลายเป็นตัวคีย์เอง)."""
    key = key or ""
    return key[:4] if len(key) > 4 else ""


def key_shape(key: str | None) -> dict:
    """รูปคีย์เท่านั้น — ไม่แตะเน็ต และไม่เก็บค่าคีย์ลงผลลัพธ์."""
    key = key or ""
    return {
        "key_shape": "ok" if KEY_SHAPE_RE.match(key) else "wrong",
        "length": len(key),
        "prefix": key_prefix(key),
        "expected": KEY_EXPECTED,
    }


def shape_error_message(key: str) -> str:
    """คีย์ผิดรูป — บอกความยาว/4 ตัวแรก/รูปที่ต้องการ เท่านั้น (ห้ามพิมพ์คีย์)."""
    prefix = key_prefix(key)
    return (
        f"{KEY_NAME} ผิดรูป: อ่านได้ {len(key)} ตัวอักษร ขึ้นต้นด้วย "
        f"{(chr(34) + prefix + chr(34)) if prefix else '(สั้นกว่า 4 ตัว)'} "
        f"แต่ที่ต้องใช้คือ {KEY_EXPECTED} = \"AIza\" ตามด้วย [0-9A-Za-z_-] อีก 35 ตัว\n"
        "ค่านี้ไม่ใช่ API key ของ Google Maps (token ที่ขึ้นต้น \"AQ.\" เป็น credential ชนิดอื่น) "
        "→ ไม่ยิงเน็ตเลย ไม่เสียคำขอ และไม่ต้องลอง --provider geocoding\n"
        f"วาง API key ตัวจริงใน config\\secrets.env บรรทัด {KEY_NAME}=AIza..."
    )


def redact(text: str, key: str | None) -> str:
    """กันคีย์หลุดผ่านข้อความ error (Geocoding API ใส่คีย์ใน query string)."""
    out = "" if text is None else str(text)
    if key:
        out = out.replace(key, "***")
        quoted = urllib.parse.quote(key, safe="")
        if quoted != key:
            out = out.replace(quoted, "***")
    return out


# --------------------------------------------------------------------------- jobs
def load_json(path: Path, default=None):
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def load_jobs() -> list:
    raw = load_json(JOBS_PATH)
    rows = raw.get("jobs") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def page_rows(rows: list, cfg: dict, sw_map: dict) -> list:
    """แถวที่ขึ้นหน้า dashboard จริง (ตรรกะเดียวกับ src\\build_page.py: drop_reason = None)."""
    kept = []
    for row in rows:
        try:
            reason = filters_mod.drop_reason(row, cfg, sw_map)
        except Exception:  # แถวพังไม่ทำให้ทั้งชุดหาย — นับเป็นถูกตัด
            reason = "error"
        if reason is None:
            kept.append(row)
    return kept


def collect_companies(rows: list) -> list:
    """→ [{company, jobs, job_ids}] เรียงตามชื่อ · บริษัทว่างไม่นับ (ไม่มีอะไรให้ค้น)."""
    groups: dict[str, dict] = {}
    for row in rows:
        name = str(row.get("company") or "").strip()
        if not name:
            continue
        entry = groups.setdefault(name, {"company": name, "job_ids": []})
        job_id = str(row.get("id") or "").strip()
        if job_id:
            entry["job_ids"].append(job_id)
    out = list(groups.values())
    for entry in out:
        entry["jobs"] = len(entry["job_ids"])
    out.sort(key=lambda item: item["company"].casefold())
    return out


# ------------------------------------------------------------------ name matching
PAREN_RE = re.compile(r"[\(\[].*?[\)\]]")
NON_WORD_RE = re.compile(r"[^\w\u0e00-\u0e7f]+")
LEGAL_SUFFIXES = (
    "company limited",
    "co ltd",
    "co limited",
    "public company limited",
    "pte ltd",
    "pte",
    "ltd",
    "limited",
    "incorporated",
    "inc",
    "corporation",
    "corp",
    "plc",
    "pcl",
    "llc",
    "gmbh",
    "jsc",
    "co",
)


def norm_name(value) -> str:
    """ชื่อบริษัทเทียบกันได้: ตัดวงเล็บ/เครื่องหมาย/คำต่อท้ายนิติบุคคล แล้วยุบช่องว่าง."""
    text = str(value or "").casefold()
    text = PAREN_RE.sub(" ", text)
    text = text.replace("&", " and ")
    text = NON_WORD_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    changed = True
    while changed and text:
        changed = False
        for suffix in sorted(LEGAL_SUFFIXES, key=len, reverse=True):
            if text == suffix:
                return ""
            if text.endswith(" " + suffix):
                text = text[: -len(suffix) - 1].strip()
                changed = True
                break
    return text


def name_matches(company: str, found: str) -> bool:
    """ชื่อตรงแบบไม่โกง: เท่ากัน หรือคำสั้นเป็นคำนำหน้าของอีกฝั่งที่ขอบคำ (คำสั้น >= 4 ตัวอักษร)."""
    left = norm_name(company)
    right = norm_name(found)
    if not left or not right:
        return False
    if left == right:
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    if len(short) < 4 or not long.startswith(short):
        return False
    return long[len(short)] == " "


# -------------------------------------------------------------------- area (BKK)
def province_tokens(cfg: dict) -> dict:
    groups = filters_mod.province_tokens(cfg or {})
    return {key: [str(t) for t in (groups.get(key) or [])] for key in ("bangkok", "perimeter", "other")}


def area_of_name(name: str, groups: dict) -> str | None:
    """province ที่ Google คืน → bangkok / perimeter / other / None (ไม่รู้จัก = ไม่เดา)."""
    text = str(name or "").strip().casefold()
    if not text:
        return None
    for group in ("bangkok", "perimeter", "other"):
        for token in groups.get(group) or []:
            if token and token.casefold() in text:
                return group
    return None


def in_bangkok(formatted_address: str, province: str, groups: dict) -> bool:
    kind = area_of_name(province, groups)
    if kind is not None:
        return kind == "bangkok"
    # ไม่มี administrative_area_level_1 → สแกนที่อยู่เต็ม (ยังไม่เดาพิกัด เป็นแค่การอ่านข้อความที่ Google คืน)
    return area_of_name(formatted_address, groups) == "bangkok"


# ------------------------------------------------------------------------- HTTP
def _loads(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _snippet(raw: str, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    return text[:limit]


def http_json(url: str, payload, headers: dict, key: str):
    """→ (http_status|None, obj|None, error_text|None) · ไม่ retry · error ถูก redact แล้ว."""
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=dict(headers),
                                     method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, _loads(raw), None
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        return exc.code, _loads(raw), redact(_snippet(raw) or f"HTTP {exc.code}", key)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return None, None, redact(_snippet(reason) or exc.__class__.__name__, key)


def looks_like_auth_error(status, error_text: str | None, obj) -> bool:
    if status in (401, 403):
        return True
    if status is not None and status >= 500:
        return False
    blob = " ".join(str(x) for x in (error_text or "", json.dumps(obj, ensure_ascii=False)
                                     if isinstance(obj, (dict, list)) else "")).casefold()
    return any(hint in blob for hint in AUTH_HINTS)


# --------------------------------------------------------------------- providers
def _component_name(components, kind: str):
    for comp in components or []:
        types = comp.get("types") or []
        if kind in types:
            return comp.get("longText") or comp.get("long_name") or ""
    return ""


def search_places(company: str, key: str):
    """Places API (Text Search, New) — ค้นชื่อบริษัทในประเทศไทย."""
    payload = {
        "textQuery": f"{company} Thailand",
        "languageCode": "th",
        "regionCode": "TH",
        "pageSize": 1,
        "locationBias": {"circle": {
            "center": {"latitude": BANGKOK_CENTER[0], "longitude": BANGKOK_CENTER[1]},
            "radius": BIAS_RADIUS_M,
        }},
    }
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    status, obj, error = http_json(PLACES_URL, payload, headers, key)
    if status is None:
        return {"status": "error", "http": None, "error": error, "raw": None}
    if status != 200:
        return {"status": "error", "http": status, "error": error, "raw": obj}
    places = (obj or {}).get("places") or []
    if not places:
        return {"status": "not_found", "http": status, "error": None, "raw": None}
    place = places[0]
    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return {"status": "not_found", "http": status, "error": "ผลค้นหาไม่มีพิกัด", "raw": None}
    components = place.get("addressComponents") or []
    return {
        "status": "ok",
        "http": status,
        "error": None,
        "lat": float(lat),
        "lng": float(lng),
        "found_name": str((place.get("displayName") or {}).get("text") or ""),
        "formatted_address": str(place.get("formattedAddress") or ""),
        "province": _component_name(components, "administrative_area_level_1"),
        "source": "places_text_search",
    }


def search_geocoding(company: str, key: str):
    """Geocoding API — ทางสำรอง (บาง demo key เปิด Places ไม่ได้)."""
    params = {
        "address": f"{company} Thailand",
        "components": "country:TH",
        "language": "th",
        "region": "th",
        "key": key,
    }
    url = GEOCODE_URL + "?" + urllib.parse.urlencode(params)
    status, obj, error = http_json(url, None, {}, key)
    if status is None:
        return {"status": "error", "http": None, "error": error, "raw": None}
    api_status = str((obj or {}).get("status") or "")
    results = (obj or {}).get("results") or []
    if status != 200 or api_status in ("REQUEST_DENIED", "INVALID_REQUEST", "OVER_QUERY_LIMIT",
                                       "UNKNOWN_ERROR"):
        return {"status": "error", "http": status,
                "error": redact(error or f"{api_status} {_snippet((obj or {}).get('error_message') or '')}",
                                key),
                "raw": obj}
    if api_status == "ZERO_RESULTS" or not results:
        return {"status": "not_found", "http": status, "error": None, "raw": None}
    result = results[0]
    location = (result.get("geometry") or {}).get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return {"status": "not_found", "http": status, "error": "ผลค้นหาไม่มีพิกัด", "raw": None}
    components = result.get("address_components") or []
    return {
        "status": "ok",
        "http": status,
        "error": None,
        "lat": float(lat),
        "lng": float(lng),
        "found_name": str(_component_name(components, "establishment")
                          or _component_name(components, "point_of_interest") or ""),
        "formatted_address": str(result.get("formatted_address") or ""),
        "province": _component_name(components, "administrative_area_level_1"),
        "source": "geocoding",
    }


PROVIDERS = {"places": search_places, "geocoding": search_geocoding}


def build_entry(base: dict, result: dict, groups: dict, provider: str) -> dict:
    """ผลดิบจาก provider → รายการบริษัทตามสคีมาของ data\\companies.json."""
    ok = result.get("status") == "ok"
    province = str(result.get("province") or "") if ok else ""
    address = str(result.get("formatted_address") or "") if ok else ""
    bangkok = bool(ok and in_bangkok(address, province, groups))
    matched = bool(ok and result.get("found_name") and name_matches(base["company"], result["found_name"]))
    if not ok:
        accuracy = "unknown"
    elif matched and bangkok:
        accuracy = "exact"
    else:
        accuracy = "approx"
    return {
        "company": base["company"],
        "query": base.get("query") or f"{base['company']} Thailand",
        "status": result.get("status") or "error",
        "lat": round(result["lat"], 7) if ok else None,
        "lng": round(result["lng"], 7) if ok else None,
        "formatted_address": address,
        "province": province,
        "in_bangkok": bangkok,
        "accuracy": accuracy,
        "found_name": str(result.get("found_name") or ""),
        "matched_name": matched,
        "source": provider if ok else (result.get("source") or provider),
        "http": result.get("http"),
        "error": result.get("error"),
        "jobs": base["jobs"],
        "job_ids": base["job_ids"],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def pending_entry(base: dict) -> dict:
    """บริษัทที่ยังไม่ได้ค้นในรอบนี้ (--limit) — เก็บไว้ให้เห็นจำนวนครบ ไม่เดาพิกัด."""
    return {
        "company": base["company"],
        "query": base.get("query") or f"{base['company']} Thailand",
        "status": "pending",
        "lat": None,
        "lng": None,
        "formatted_address": "",
        "province": "",
        "in_bangkok": False,
        "accuracy": "unknown",
        "found_name": "",
        "matched_name": False,
        "source": None,
        "http": None,
        "error": None,
        "jobs": base["jobs"],
        "job_ids": base["job_ids"],
        "fetched_at": None,
    }


def cached_ok(entry) -> bool:
    return (isinstance(entry, dict) and entry.get("status") == "ok"
            and isinstance(entry.get("lat"), (int, float))
            and isinstance(entry.get("lng"), (int, float)))


# ------------------------------------------------------------------------- main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ค้นพิกัดบริษัทด้วย Google (Places / Geocoding)")
    parser.add_argument("--refresh", action="store_true", help="ยิง API ใหม่ทุกบริษัท (ไม่ใช้ cache)")
    parser.add_argument("--limit", type=int, default=None, help="จำนวนคำขอสูงสุดในรอบนี้ (ประหยัดโควตา)")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="places",
                        help="places (ค่าเริ่มต้น ตามที่ Tz สั่ง) หรือ geocoding (ทางสำรอง)")
    parser.add_argument("--check-key", action="store_true",
                        help="ตรวจรูปคีย์แล้วจบ ไม่ยิงเน็ต (exit 0 ถูก / 2 ผิดหรือไม่มีคีย์)")
    args = parser.parse_args(argv)

    key, key_source = find_key()
    if args.check_key:
        shape = key_shape(key)
        print(json.dumps(shape, ensure_ascii=False))
        return 0 if shape["key_shape"] == "ok" else 2
    if not key:
        print(f"no {KEY_NAME} in config\\secrets.env", file=sys.stderr)
        print(f"วางบรรทัด {KEY_NAME}=... ใน config\\secrets.env (ไฟล์นี้อยู่ใน .gitignore) แล้วรันใหม่",
              file=sys.stderr)
        return 2
    if not KEY_SHAPE_RE.match(key):
        print(shape_error_message(key), file=sys.stderr)
        return 2

    cfg = load_json(FILTERS_PATH, {}) or {}
    switches = load_json(SWITCHES_PATH, {}) or {}
    sw_map = switches.get("switches") or {}
    groups = province_tokens(cfg)

    rows = load_jobs()
    kept = page_rows(rows, cfg, sw_map)
    companies = collect_companies(kept)
    skipped_rows = len(kept) - sum(entry["jobs"] for entry in companies)
    if not companies:
        print(json.dumps({"error": "ไม่มีบริษัทให้ค้น", "kept_rows": len(kept)}, ensure_ascii=False))
        return 0

    previous = {}
    old = load_json(OUT_PATH, {}) or {}
    for entry in (old.get("companies") or []) if isinstance(old, dict) else []:
        if isinstance(entry, dict) and entry.get("company"):
            previous[str(entry["company"])] = entry

    search = PROVIDERS[args.provider]
    started = time.time()
    requests_made = 0
    reused = 0
    results: list[dict] = []
    last_call = 0.0
    aborted = None

    for base in companies:
        name = base["company"]
        old_entry = previous.get(name)
        if not args.refresh and cached_ok(old_entry):
            entry = dict(old_entry)
            entry["jobs"] = base["jobs"]
            entry["job_ids"] = base["job_ids"]
            reused += 1
            results.append(entry)
            continue
        if args.limit is not None and requests_made >= args.limit:
            results.append(pending_entry(base))
            continue

        # หน่วงระหว่างคำขอ (นับจากคำขอล่าสุด กันการยิงรัวเมื่อมี error เร็ว ๆ)
        wait = DELAY_SECONDS - (time.time() - last_call)
        if last_call and wait > 0:
            time.sleep(wait)
        last_call = time.time()
        requests_made += 1
        raw = search(name, key)

        if raw.get("status") == "error" and looks_like_auth_error(raw.get("http"), raw.get("error"),
                                                                  raw.get("raw")):
            aborted = {"company": name, "http": raw.get("http"), "error": raw.get("error"),
                       "provider": args.provider}
            # บริษัทที่เหลือยังไม่ถูกค้น — เก็บสถานะ pending ไว้ ไม่เดาพิกัด
            for rest in companies[len(results):]:
                results.append(pending_entry(rest))
            break
        results.append(build_entry(base, raw, groups, args.provider))

    known = {entry["company"] for entry in results}
    for base in companies:  # กันหลุด: บริษัทไหนไม่มีผลเลยให้เป็น pending
        if base["company"] not in known:
            results.append(pending_entry(base))
    results.sort(key=lambda item: item["company"].casefold())

    counts = {"ok": 0, "not_found": 0, "error": 0, "pending": 0}
    accuracy = {"exact": 0, "approx": 0, "unknown": 0}
    on_map = 0
    for entry in results:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        accuracy[entry["accuracy"]] = accuracy.get(entry["accuracy"], 0) + 1
        if entry.get("in_bangkok"):
            on_map += 1

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": args.provider,
        "key_source": key_source,
        "source_file": "data\\jobs.json",
        "jobs_total": len(rows),
        "jobs_on_page": len(kept),
        "rows_without_company": skipped_rows,
        "total_companies": len(results),
        "status": counts,
        "accuracy": accuracy,
        "in_bangkok": on_map,
        "requests": requests_made,
        "cache_reused": reused,
        "limit": args.limit,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    if results:
        report["last_error"] = next(({"company": e["company"], "error": e["error"]}
                                     for e in results if e["status"] == "error"), None)
    if aborted:
        report["aborted"] = aborted

    # เขียนทุกครั้ง: ไฟล์ต้องสะท้อนบริษัททั้งชุด (pending = ยังไม่ได้ค้น → ไม่เดาพิกัด)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": report["generated_at"],
        "provider": args.provider,
        "source_file": report["source_file"],
        "jobs_on_page": report["jobs_on_page"],
        "total_companies": len(results),
        "in_bangkok": on_map,
        "accuracy_counts": accuracy,
        "status_counts": counts,
        "requests": requests_made,
        "companies": results,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report["companies_json"] = "data\\companies.json"
    report["companies_json_bytes"] = OUT_PATH.stat().st_size

    print(json.dumps(report, ensure_ascii=False))
    if aborted:
        print(f"หยุดกลางทาง: คีย์/การเปิด API มีปัญหา ({args.provider}) → {aborted['error']}\n"
              f"ลอง --provider geocoding ถ้า demo key เปิด Places ไม่ได้", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
