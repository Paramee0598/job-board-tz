"""fetch_jobthai.py — เก็บประกาศงานจาก jobthai.com (หน้า search ที่ HTML มาฝั่ง server)

ทำไมไฟล์นี้มี
  JobSpy คืน 0 แถวสำหรับคำสาย cloud/hypervisor (วัด 22 พ.ย.) แต่ jobthai.com ตอบ HTML
  พร้อมการ์ดงาน จึงเก็บจากหน้านั้นตรง ๆ แบบไม่เสียเงิน ไม่ใช้ Apify ไม่ต้องมี token

กติกา
  · T0 เท่านั้น: ไม่มี cookie / ไม่มี login / ไม่มี proxy / ไม่แตะบัญชีใคร
  · Catalan robots: อ่าน robots.txt ของโดเมนก่อนยิงทุกครั้ง และตรวจ can_fetch ต่อ URL
    (path ที่ถูก Disallow = ข้าม + log; อ่าน robots ไม่ได้ = ไม่ยิงเลย ไม่เดา)
  · หน่วง 1.5 วิ ระหว่าง request (ค่าจาก config\\sources.json → jobthai_web.delay_seconds)
  · error ติดกัน 2 ครั้งในคำเดียว → ข้ามคำนั้น + log (ไม่ retry รัว)
  · ห้ามเดาค่าที่ไม่มีในหน้า: เงินเดือนที่ไม่ใช่ช่วงตัวเลขชัดเจน → salary_min/max = None
    วันที่ที่อ่านไม่ออก → posted_at = None (ไม่ใส่วันนี้แทน)
  · ไม่มี path absolute: ทุก path มาจาก ROOT = Path(__file__).resolve().parent.parent

สัญญาที่เทสต์อิง (tests/test_fetch_jobthai.py)
  parse_thai_date(text) -> str | None            "21 พ.ย. 69" → "2026-11-21"
  parse_search_html(html, base=...) -> list[dict]
      row keys: source uid title company url location salary_text salary_min
                salary_max posted_at raw_text description

ใช้:
  python src\\fetch_jobthai.py --keywords cloud hypervisor --pages 2
  python src\\fetch_jobthai.py --keywords cloud --pages 1 --out data\\raw\\2026-11-22\\jobthai.json
  python src\\fetch_jobthai.py --keywords esxi virtualisation --merge   # คำที่ดึงแล้วไม่หาย
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from urllib.robotparser import RobotFileParser

try:  # parse ใช้ bs4, ยิงเน็ตใช้ requests — import ไม่ได้ก็ยังให้เทสต์ parse ทำงาน
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"

BASE_URL = "https://www.jobthai.com"
SEARCH_PATH = "/th/jobs"
USER_AGENT = "Mozilla/5.0 (compatible; TzJobBoard/1.0; personal job search)"
DEFAULT_PAGES = 2
DEFAULT_DELAY = 1.5
DEFAULT_TIMEOUT = 30
MAX_CONSECUTIVE_ERRORS = 2

# เดือนไทย: ย่อ (มีจุด/ไม่มีจุด) + เต็ม — key ถูก normalize ด้วย _month_key()
THAI_MONTHS = {
    "ม.ค.": 1, "มกราคม": 1,
    "ก.พ.": 2, "กุมภาพันธ์": 2,
    "มี.ค.": 3, "มีนาคม": 3,
    "เม.ย.": 4, "เมษายน": 4,
    "พ.ค.": 5, "พฤษภาคม": 5,
    "มิ.ย.": 6, "มิถุนายน": 6,
    "ก.ค.": 7, "กรกฎาคม": 7,
    "ส.ค.": 8, "สิงหาคม": 8,
    "ก.ย.": 9, "กันยายน": 9,
    "ต.ค.": 10, "ตุลาคม": 10,
    "พ.ย.": 11, "พฤศจิกายน": 11,
    "ธ.ค.": 12, "ธันวาคม": 12,
}
_MONTH_KEYS = {re.sub(r"[.\s]", "", k): v for k, v in THAI_MONTHS.items()}

THAI_DATE_RX = re.compile(r"^(\d{1,2})\s+(\S+)\s+(\d{2,4})$")
JOB_HREF_RX = re.compile(r"/company/job/(\d+)")
SALARY_RANGE_RX = re.compile(
    r"^([\d,]+)\s*([Kk])?\s*(?:-|–|—|ถึง)\s*([\d,]+)\s*([Kk])?$")
# ข้อความที่หน้าใช้แทน "ไม่มีเงินเดือน" — ไม่ใช่ตัวเลข = salary_text None (ไม่เดา 0)
SALARY_EMPTY_MARKERS = {"", "-", "ไม่ระบุ", "ไม่ระบุเงินเดือน", "ไม่มีข้อมูล"}


# ------------------------------------------------------------------------ config
def load_sources() -> dict:
    path = CONFIG / "sources.json"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def web_config(sources: dict | None = None) -> dict:
    """config\\sources.json → jobthai_web (ของเดิม jobthai = Apify ไม่ถูกแตะ)."""
    cfg = dict((sources if sources is not None else load_sources()).get("jobthai_web") or {})
    out = {
        "base_url": cfg.get("base_url") or BASE_URL,
        "search_path": cfg.get("search_path") or SEARCH_PATH,
        "keywords": [k for k in (cfg.get("keywords") or []) if k],
        "pages": cfg.get("pages") or DEFAULT_PAGES,
        "delay_seconds": cfg.get("delay_seconds", DEFAULT_DELAY),
        "timeout_seconds": cfg.get("timeout_seconds") or DEFAULT_TIMEOUT,
        "user_agent": cfg.get("user_agent") or USER_AGENT,
    }
    if not out["keywords"]:
        out["keywords"] = ["cloud"]
    return out


# ------------------------------------------------------------- Thai date parsing
def _month_key(token: str) -> str:
    return re.sub(r"[.\s]", "", token or "")


def _buddhist_year(token: str) -> int | None:
    """ปี พ.ศ. จากสตริง: 2 หลัก → 25xx (00-99); 4 หลักต้องอยู่ใน 2400-2699.

    จุดที่ต่างจากใบงานโดยตั้งใจ: ใบงานเขียน "70-99 → 2400+yy" แต่กติกานั้นทำให้
    "70" = พ.ศ. 2470 = ค.ศ. 1927 ซึ่งเป็นวันประกาศงานไม่ได้ และเทสต์ที่บังคับใช้
    (tests/test_fetch_jobthai.py: test_15_s_k_70_year70_is_2570) ปักไว้ที่ 2570 →
    2027-08-15. งานบนบอร์ดอยู่ในช่วง 256x-257x เท่านั้น จึงอ่าน 2 หลักเป็น 25xx ทั้งช่วง
    """
    if not token.isdigit():
        return None
    if len(token) == 2:
        return 2500 + int(token)
    if len(token) == 4:
        year = int(token)
        return year if 2400 <= year <= 2699 else None
    return None


def parse_thai_date(text) -> str | None:
    """'21 พ.ย. 69' / '21 พ.ย. 2569' / '21 พฤศจิกายน 2569' → '2026-11-21'.

    อ่านไม่ออก ไม่ใช่วันที่ หรือวันที่ไม่มีจริง (32 ม.ค.) → None. ห้ามเดา.
    """
    if not isinstance(text, str):
        return None
    raw = text.strip().replace(",", "")
    if not raw:
        return None
    m = THAI_DATE_RX.match(raw)
    if not m:
        return None
    day_text, month_text, year_text = m.group(1), m.group(2), m.group(3)
    month = _MONTH_KEYS.get(_month_key(month_text))
    if month is None:
        return None
    be_year = _buddhist_year(year_text)
    if be_year is None:
        return None
    try:
        ce = datetime(be_year - 543, month, int(day_text))
    except ValueError:
        return None
    return ce.date().isoformat()


# -------------------------------------------------------------------- html parse
def _text(el) -> str | None:
    if el is None:
        return None
    value = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
    return value or None


def _salary_fields(text: str | None) -> tuple[str | None, int | None, int | None]:
    """ข้อความเงินเดือนตามหน้า → (salary_text, min, max).

    ช่วงตัวเลขชัดเจนเท่านั้นที่ได้ min/max ("35,000 - 40,000", "22K - 28K");
    "ตามตกลง"/"ตามประสบการณ์" = เก็บเป็นข้อความ แต่ min/max None (ไม่เดาเป็น 0)
    """
    if text is None:
        return None, None, None
    s = re.sub(r"\s+", " ", str(text)).strip()
    if re.sub(r"\s*บาท\s*$", "", s).strip() in SALARY_EMPTY_MARKERS:
        return None, None, None
    s = re.sub(r"\s*บาท\s*$", "", s).strip()
    if not s:
        return None, None, None
    m = SALARY_RANGE_RX.match(s)
    if not m:
        return s, None, None
    low = int(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
    high = int(m.group(3).replace(",", "")) * (1000 if m.group(4) else 1)
    if low <= 0 or high <= 0 or low > high:
        return s, None, None
    return s, low, high


def _card_date_text(card) -> str | None:
    """หาข้อความวันที่สีเทาในการ์ด — สแกนข้อความ ไม่ผูกกับ class hash ของ styled-components."""
    for chunk in card.stripped_strings:
        value = chunk.strip()
        if len(value) <= 24 and parse_thai_date(value):
            return value
    return None


def _uid_of(card, href: str) -> str | None:
    uid = (card.get("ga-job-id") or "").strip()
    if uid:
        return uid
    m = JOB_HREF_RX.search(href or "")
    return m.group(1) if m else None


def parse_search_html_with_stats(html: str, base: str = BASE_URL):
    """คืน (rows, stats). stats = {cards, skipped, duplicates} — ใช้รายงานตอนดึงจริง."""
    stats = {"cards": 0, "skipped": 0, "duplicates": 0}
    if not html or BeautifulSoup is None:
        return [], stats
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()

    for card in soup.find_all("a", href=True):
        href = card.get("href") or ""
        if not JOB_HREF_RX.search(href):
            continue
        stats["cards"] += 1

        uid = _uid_of(card, href)
        url = urljoin(base.rstrip("/") + "/", href) if href else None
        title_el = card.select_one("h2[id^='job-card-item']") or card.find("h2")
        title = _text(title_el)
        if not title or not url or not uid:
            stats["skipped"] += 1  # การ์ดที่ไม่มี title/url/uid = ใช้ไม่ได้
            continue
        if uid in seen:
            stats["duplicates"] += 1
            continue
        seen.add(uid)

        company = _text(card.select_one("[id^='job-list-company-name-']"))
        if company is None:
            for el in card.find_all("h2"):
                if el is title_el:
                    continue
                company = _text(el)
                if company:
                    break

        location = _text(card.select_one("#location-text"))
        salary_text, salary_min, salary_max = _salary_fields(
            _text(card.select_one("#salary-text")))
        date_text = _card_date_text(card)

        rows.append({
            "source": "jobthai",
            "uid": uid,
            "title": title,
            "company": company,
            "url": url,
            "location": location,
            "salary_text": salary_text,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "posted_at": parse_thai_date(date_text) if date_text else None,
            "raw_text": None,
            "description": None,
        })
    return rows, stats


def parse_search_html(html: str, base: str = BASE_URL) -> list[dict]:
    """หน้า search ของ jobthai → list ของ raw row (ดูสัญญาที่หัวไฟล์)."""
    rows, _ = parse_search_html_with_stats(html, base)
    return rows


# ----------------------------------------------------------------------- fetching
def build_search_url(base: str, keyword: str, page: int = 1, search_path: str = SEARCH_PATH) -> str:
    if not re.match(r"^https?://[A-Za-z0-9.\-]+(:[0-9]+)?$", str(base).rstrip("/")):
        raise ValueError(f"base ต้องเป็น origin ของ http(s) เท่านั้น: {base!r}")
    keyword = re.sub(r"[\x00-\x1f\x7f]", " ", str(keyword)).strip()
    if not keyword:
        raise ValueError("keyword ว่าง")
    url = f"{base.rstrip('/')}{search_path}?keyword={quote_plus(keyword)}"
    if page and int(page) > 1:
        url += f"&page={int(page)}"
    return url


def robots_for(base: str, user_agent: str, timeout: int, session):
    """อ่าน robots.txt ของโดเมน → (parser | None, error | None)."""
    if requests is None:  # pragma: no cover
        return None, "requests_missing"
    parser = RobotFileParser()
    url = base.rstrip("/") + "/robots.txt"
    parser.set_url(url)
    try:
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    except Exception as exc:
        return None, f"robots_fetch_failed: {type(exc).__name__}: {exc}"
    if resp.status_code != 200:
        return None, f"robots_http_{resp.status_code}"
    parser.parse((resp.text or "").splitlines())
    return parser, None


def run(keywords=None, pages=None, out_path=None, day: date | None = None,
        delay: float | None = None, timeout: int | None = None,
        base: str | None = None, search_path: str | None = None,
        merge: bool = False, verbose: bool = True) -> dict:
    """ยิงหน้า search ของ jobthai ทีละคำ/ทีละหน้า → เขียนไฟล์ดิบ + คืนสรุป.

    merge=True: ถ้า out_path มีอยู่ ให้เก็บ envelope/log ของคำที่ไม่ได้ดึงรอบนี้ไว้
    (ดึงซ้ำเฉพาะคำใหม่ได้โดยผลของคำเดิมไม่หาย — ไฟล์เดียวเขียนทับทั้งก้อนโดยปริยาย)
    """
    if requests is None:
        raise RuntimeError("ต้องมีไลบรารี requests เพื่อยิงเว็บ")

    cfg = web_config()
    keywords = [k for k in (keywords or cfg["keywords"]) if k]
    pages = int(pages or cfg["pages"])
    delay_s = float(cfg["delay_seconds"] if delay is None else delay)
    timeout_s = int(timeout or cfg["timeout_seconds"])
    base = (base or cfg["base_url"]).rstrip("/")
    search_path = search_path or cfg["search_path"]
    user_agent = cfg["user_agent"]
    day = day or date.today()
    out_path = Path(out_path) if out_path else (RAW / day.isoformat() / "jobthai.json")

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept-Language": "th,en;q=0.8"})

    logs: list[dict] = []
    envelopes: list[dict] = []
    request_count = 0
    started = time.time()

    parser, robots_error = robots_for(base, user_agent, timeout_s, session)
    request_count += 1
    if parser is None:
        log = {"source": "jobthai", "keyword": None, "page": None, "http": None,
               "ok": False, "results": 0, "error": robots_error, "cost_usd": 0.0}
        logs.append(log)
        if verbose:
            print(json.dumps(log, ensure_ascii=False))
        payload = _payload(keywords, pages, delay_s, timeout_s, base, search_path,
                           out_path, logs, envelopes)
        return {"path": str(out_path), "params": payload["params"], "total_rows": 0,
                "per_keyword": {}, "requests": request_count, "errors": [robots_error],
                "cost_usd": 0.0, "logs": logs,
                "elapsed_s": round(time.time() - started, 1)}

    for keyword in keywords:
        consecutive_errors = 0
        for page in range(1, pages + 1):
            url = build_search_url(base, keyword, page, search_path)
            if not parser.can_fetch(user_agent, url):
                log = {"source": "jobthai", "keyword": keyword, "page": page, "http": None,
                       "ok": False, "results": 0, "error": "robots_disallow",
                       "url": url, "cost_usd": 0.0}
                logs.append(log)
                if verbose:
                    print(json.dumps(log, ensure_ascii=False))
                consecutive_errors = MAX_CONSECUTIVE_ERRORS
                break

            if request_count:
                time.sleep(delay_s)  # หน่วงระหว่าง request (ไม่หน่วงก่อนตัวแรกของรอบ)
            t0 = time.time()
            http = None
            error = None
            note = None
            rows: list[dict] = []
            stats = {"cards": 0, "skipped": 0, "duplicates": 0}
            try:
                resp = session.get(url, timeout=timeout_s)
                request_count += 1
                http = resp.status_code
                if http != 200:
                    error = f"http_{http}"
                else:
                    rows, stats = parse_search_html_with_stats(resp.text, base)
                    if not rows:
                        # 200 ที่ไม่มีการ์ด = หน้าสุดท้ายของคำนั้น (ผลไม่ถึงหน้านี้) —
                        # ไม่ใช่ error จึงไม่นับเข้าถฎ "error 2 ครั้งติด → ข้ามคำ"
                        note = "no_cards"
            except Exception as exc:
                request_count += 1
                error = f"{type(exc).__name__}: {exc}"

            log = {"source": "jobthai", "keyword": keyword, "page": page, "http": http,
                   "ok": error is None, "results": len(rows),
                   "cards": stats["cards"], "skipped": stats["skipped"],
                   "duplicates": stats["duplicates"], "url": url, "error": error,
                   "note": note, "elapsed_s": round(time.time() - t0, 1), "cost_usd": 0.0}
            logs.append(log)
            envelopes.append({"keyword": keyword, "page": page, "jobs": rows})
            if verbose:
                print(json.dumps(log, ensure_ascii=False))

            if error:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    skip = {"source": "jobthai", "keyword": keyword, "page": None,
                            "http": None, "ok": False, "results": 0,
                            "error": f"skip_keyword: error {consecutive_errors} ครั้งติดกัน",
                            "cost_usd": 0.0}
                    logs.append(skip)
                    if verbose:
                        print(json.dumps(skip, ensure_ascii=False))
                    break
            else:
                consecutive_errors = 0

    payload = _payload(keywords, pages, delay_s, timeout_s, base, search_path,
                       out_path, logs, envelopes)
    if merge:
        payload = _merge_payload(out_path, payload, keywords)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    per_keyword: dict[str, int] = {}
    for env in envelopes:
        per_keyword[env["keyword"]] = per_keyword.get(env["keyword"], 0) + len(env["jobs"])
    errors = [f"{e.get('keyword')}:{e.get('page')}: {e['error']}"
              for e in logs if e.get("error")]
    return {
        "path": str(out_path),
        "params": payload["params"],
        "total_rows": sum(len(env["jobs"]) for env in envelopes),
        "rows_in_file": sum(len(env.get("jobs") or []) for env in payload["raw"]),
        "keywords_in_file": payload["params"]["keywords"],
        "merged": bool(merge),
        "per_keyword": per_keyword,
        "requests": request_count,
        "errors": errors,
        "cost_usd": 0.0,
        "logs": logs,
        "elapsed_s": round(time.time() - started, 1),
    }


def _payload(keywords, pages, delay_s, timeout_s, base, search_path, out_path,
             logs, envelopes) -> dict:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "jobthai",
        "params": {
            "keywords": keywords,
            "pages": pages,
            "base_url": base,
            "search_path": search_path,
            "delay_seconds": delay_s,
            "timeout_seconds": timeout_s,
            "user_agent": USER_AGENT,
            "session": "T0 (cookieless)",
            "out": _rel(out_path),
        },
        "logs": logs,
        "raw": envelopes,
    }


def _merge_payload(path: Path, new: dict, keywords) -> dict:
    """รวม payload ใหม่เข้ากับไฟล์เดิม: คำที่ดึงรอบนี้แทนที่ของเดิม คำอื่นคงไว้ครบ.

    ไฟล์เดิมเสียหาย/ไม่มี = ใช้ payload ใหม่ (ไม่ทำให้รอบนี้ล้ม)
    """
    if not Path(path).is_file():
        return new
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return new
    if not isinstance(old, dict):
        return new
    done = {str(k) for k in keywords}
    old_raw = old.get("raw")
    old_logs = old.get("logs")
    raw = [env for env in (old_raw if isinstance(old_raw, list) else [])
           if isinstance(env, dict) and str(env.get("keyword")) not in done]
    logs = [log for log in (old_logs if isinstance(old_logs, list) else [])
            if not isinstance(log, dict) or str(log.get("keyword")) not in done]
    merged_keywords = list(((old.get("params") or {}).get("keywords")) or [])
    for k in keywords:
        if k not in merged_keywords:
            merged_keywords.append(k)
    merged = dict(new)
    merged["raw"] = raw + list(new.get("raw") or [])
    merged["logs"] = logs + list(new.get("logs") or [])
    merged["params"] = dict(new["params"], keywords=merged_keywords,
                            merged_at=datetime.now().isoformat(timespec="seconds"),
                            merged_kept_rows=sum(len(e.get("jobs") or []) for e in raw))
    return merged


def _rel(path) -> str:
    """path → ข้อความที่อ้างจาก ROOT ถ้าอยู่ใต้ ROOT (path สัมพัทธ์ก็ได้) · นอก ROOT = คงข้อความเดิม.

    ต้อง resolve ก่อน relative_to: 'data\\raw\\x.json'.relative_to(ROOT) โยน ValueError แม้ cwd = ROOT
    (เขียน --out เป็น path สัมพัทธ์ตาม CLI แล้วพัง — เจอตอนรันจริง)
    """
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path(ROOT).resolve()))
    except (ValueError, OSError):
        return str(p)


# ---------------------------------------------------------------------------- cli
def parse_args(argv: list[str]) -> dict:
    opts = {"keywords": [], "pages": None, "out": None, "delay": None,
            "timeout": None, "merge": False, "verbose": True}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--keywords":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                opts["keywords"].extend(k.strip() for k in argv[i].split(",") if k.strip())
                i += 1
        elif arg.startswith("--keywords="):
            opts["keywords"].extend(k.strip() for k in arg.split("=", 1)[1].split(",") if k.strip())
            i += 1
        elif arg == "--pages" and i + 1 < len(argv):
            opts["pages"] = int(argv[i + 1]); i += 2
        elif arg.startswith("--pages="):
            opts["pages"] = int(arg.split("=", 1)[1]); i += 1
        elif arg == "--out" and i + 1 < len(argv):
            opts["out"] = argv[i + 1]; i += 2
        elif arg.startswith("--out="):
            opts["out"] = arg.split("=", 1)[1]; i += 1
        elif arg == "--delay" and i + 1 < len(argv):
            opts["delay"] = float(argv[i + 1]); i += 2
        elif arg.startswith("--delay="):
            opts["delay"] = float(arg.split("=", 1)[1]); i += 1
        elif arg == "--timeout" and i + 1 < len(argv):
            opts["timeout"] = int(argv[i + 1]); i += 2
        elif arg.startswith("--timeout="):
            opts["timeout"] = int(arg.split("=", 1)[1]); i += 1
        elif arg == "--merge":
            opts["merge"] = True; i += 1
        elif arg == "--quiet":
            opts["verbose"] = False; i += 1
        else:
            i += 1
    return opts


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = parse_args(argv)
    out = opts.pop("out")
    try:
        summary = run(out_path=Path(out) if out else None, **opts)
    except Exception as exc:
        print(json.dumps({"fatal": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps({k: v for k, v in summary.items() if k != "logs"}, ensure_ascii=False))
    return 0 if summary["total_rows"] or not summary["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
