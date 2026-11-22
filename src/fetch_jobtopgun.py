r"""fetch_jobtopgun.py — เก็บประกาศงานจาก jobtopgun.com (หน้า search ที่ HTML มาฝั่ง server)

ทำไมไฟล์นี้มี
  JobSpy คืน 0 แถวสำหรับคำสาย hypervisor/VMware · jobtopgun.com ตอบ HTML พร้อมการ์ดงาน
  (วัด 22 พ.ย. 2569: keyword=vmware → 200, 30 การ์ด/หน้า) จึงเก็บจากหน้านั้นตรง ๆ
  แบบเดียวกับ src\\fetch_jobthai.py — ฟรี ไม่ใช้ Apify ไม่ต้องมี token

จุดที่วัดจากหน้าจริงก่อนเขียน (และวิธีกันแต่ละข้อ)
  1) การ์ด = <article aria-label="TITLE at COMPANY, LOCATION"> — ใช้ <article> เป็นหน่วยการ์ด
     ไม่ผูกกับ class ที่ถูก hash (เช่น "p-6 border rounded-2xl") ซึ่งเปลี่ยนได้ทุก deploy
  2) งาน 1 ใบมี <a> 2 ตัว (overlay aria-hidden กับ <a> ใน <h2>) → uid ซ้ำต้องยุบ
     (ถ้าไม่ยุบจะได้ 60 แถว/หน้าแทน 30)
  3) ป้าย "Dream Company" เป็น <h3> ไม่ใช่ <h2> → title อ่านจาก <h2> เท่านั้น ป้ายจึงไม่ปนเข้าชื่อตำแหน่ง
  4) เงินเดือนมาเป็น "39,000 - 54,000 บาท/เดือน + ค่าคอมมิชชั่น" → เก็บข้อความตามหน้า
     แต่ salary_min/max มาจากช่วงตัวเลขนำหน้าเท่านั้น · "45,000 บาท" เดี่ยว ๆ = ข้อความ ไม่ใช่ช่วง → min/max None
  5) คำอธิบายย่อเป็น <ul> ที่มีตัวเลขอยู่ข้างใน → การหาข้อความเงินเดือน/วันที่ข้าม subtree ของ <ul>
  6) วันที่บนหน้าเป็นแบบ relative ล้วน ("2 วันที่แล้ว" · "สัปดาห์ที่แล้ว" · "เดือนที่แล้ว")
     ไม่มีวันที่ไทยแบบ absolutes และไม่มี datePosted ใน JSON-LD → posted_at = None
     (ห้ามเดา: ไม่แปลง relative เป็นวันที่เอง)
  7) ลิงก์งานคือ /th/jobs/j<company>-<no> ส่วน /th/jobs/in-<city> คือสถานที่ และ /th/companies/... คือบริษัท
     → จับเฉพาะ path ที่มีรูป j\d+ ไม่งั้นลิงก์สถานที่จะกลายเป็นงาน
  8) pagination จริงคือ ?keyword=<kw>&page=<n> (หน้าแรกไม่มี page) · page=1 = ไม่ใส่ page
     · หน้าเกินหน้าสุด = 200 + 0 การ์ด → note "no_cards" ไม่ใช่ error

กติกา
  · T0 เท่านั้น: ไม่มี cookie / ไม่มี login / ไม่มี proxy / ไม่แตะบัญชีใคร
  · robots.txt: อ่านก่อนยิงทุกครั้ง + ตรวจ can_fetch ต่อ URL (Allow: / แต่ Disallow /api/ /admin/
    /static/ /auth/ /sign-in ...) — อ่าน robots ไม่ได้ = ไม่ยิงเลย ไม่เดา
  · หน่วง 1.5 วิ ระหว่าง request (config\\sources.json → jobtopgun_web.delay_seconds) · timeout 30 วิ
  · error ติดกัน 2 ครั้งในคำเดียว → ข้ามคำนั้น + log
  · ไม่มี path absolute: ทุก path มาจาก ROOT = Path(__file__).resolve().parent.parent

สัญญาที่เทสต์อิง (tests/test_fetch_jobtopgun.py)
  parse_search_html(html, base=...) -> list[dict]
      row keys: source uid title company url location salary_text salary_min
                salary_max posted_at raw_text description
  parse_thai_date มาจาก fetch_jobthai (ตัวเดียวกับที่ jobthai ใช้ — ไม่เขียนซ้ำ)

ใช้:
  python src\\fetch_jobtopgun.py --keywords cloud vmware esxi hyper-v virtualization proxmox nutanix devops --pages 2
  python src\\fetch_jobtopgun.py --keywords vmware --pages 1 --out data\\raw\\2026-11-22\\jobtopgun.json
  python src\\fetch_jobtopgun.py --keywords nutanix --merge      # คำที่ดึงแล้วไม่หาย
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

try:  # ตัวอ่านวันที่ไทยใช้ของ jobthai ตัวเดียว (รันเป็นสคริปต์: src\\ อยู่ใน sys.path แล้ว)
    from fetch_jobthai import parse_thai_date
except ImportError:  # ถูก import จากที่อื่น → เติม src\\ ของโปรเจกต์เอง (ไม่มี path absolute)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fetch_jobthai import parse_thai_date

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"

BASE_URL = "https://www.jobtopgun.com"
SEARCH_PATH = "/th/jobs"
USER_AGENT = "Mozilla/5.0 (compatible; TzJobBoard/1.0; personal job search)"
SOURCE = "jobtopgun"
DEFAULT_PAGES = 2
DEFAULT_DELAY = 1.5
DEFAULT_TIMEOUT = 30
MAX_CONSECUTIVE_ERRORS = 2

# /th/jobs/j15793-68 = งาน · /th/jobs/in-bangkok = สถานที่ · /th/companies/company-c15793 = บริษัท
JOB_PATH_RX = re.compile(r"^/th/jobs/(j\d+(?:-[A-Za-z0-9]+)*)/?$")
COMPANY_RX = re.compile(r"/th/companies/")
LOCATION_RX = re.compile(r"/th/jobs/in-")
# เงินเดือน: ช่วงตัวเลขนำหน้า ("39,000 - 54,000 ...") · เดี่ยว ("45,000 บาท") · ตัวคั่นหน้า/หลังมีได้
SALARY_RANGE_RX = re.compile(r"^(\d[\d,]*)\s*(?:-|–|—|ถึง)\s*(\d[\d,]*)")
SALARY_SINGLE_RX = re.compile(r"^(\d[\d,]*)\s*บาท")
SALARY_TEXT_LIMIT = 100  # ข้อความยาวกว่านี้ = คำอธิบายย่อ ไม่ใช่ช่องเงินเดือน


# ------------------------------------------------------------------------ config
def load_sources() -> dict:
    path = CONFIG / "sources.json"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def web_config(sources: dict | None = None) -> dict:
    """config\\sources.json → jobtopgun_web (คีย์ jobtopgun เดิม = ของ Apify ไม่ถูกแตะ)."""
    cfg = dict((sources if sources is not None else load_sources()).get("jobtopgun_web") or {})
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
        out["keywords"] = ["vmware"]
    return out


# -------------------------------------------------------------------- html parse
def _text(el) -> str | None:
    if el is None:
        return None
    value = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
    return value or None


def job_slug(href: str | None) -> str | None:
    """/th/jobs/j15793-68 → 'j15793-68' · ลิงก์สถานที่/บริษัท/อื่น → None."""
    if not href:
        return None
    path = str(href).split("?")[0].split("#")[0]
    m = JOB_PATH_RX.match(path)
    return m.group(1) if m else None


def _title_anchor(card):
    """<a> ของงานที่มีชื่อตำแหน่งจริง (overlay ของการ์ดไม่มีข้อความ)."""
    for anchor in card.find_all("a", href=True):
        if not job_slug(anchor.get("href")):
            continue
        if _text(anchor):
            return anchor
    return None


def _salary_fields(text: str | None) -> tuple[str | None, int | None, int | None]:
    """"39,000 - 54,000 บาท/เดือน + ค่าคอมมิชชั่น" → (ข้อความเต็ม, 39000, 54000).

    "45,000 บาท" = ข้อความ แต่ไม่ใช่ช่วง → min/max None (ไม่เดาว่า min = max)
    ยอดที่ไม่เป็นบวกหรือกลับด้าน → min/max None
    """
    if not text:
        return None, None, None
    s = re.sub(r"\s+", " ", str(text)).strip()
    if not s:
        return None, None, None
    m = SALARY_RANGE_RX.match(s)
    if not m:
        return s, None, None
    low = int(m.group(1).replace(",", ""))
    high = int(m.group(2).replace(",", ""))
    if low <= 0 or high <= 0 or low > high:
        return s, None, None
    return s, low, high


def _card_salary_text(card) -> str | None:
    """ช่องเงินเดือนในการ์ด — ต้องเป็นข้อความสั้นที่ "เริ่มด้วย" ตัวเลข (ช่วงหรือเดี่ยว).

    ข้าม subtree ของ <ul> (คำอธิบายย่อมีตัวเลขได้) และข้ามยอดที่เป็นแค่ Bath/noise ยาว
    """
    for el in card.find_all(["span", "a", "p"]):
        if el.find_parent("ul") is not None:
            continue
        text = _text(el)
        if not text or len(text) > SALARY_TEXT_LIMIT:
            continue
        if SALARY_RANGE_RX.match(text) or SALARY_SINGLE_RX.match(text):
            return text
    return None


def _card_date_text(card) -> str | None:
    """ข้อความวันที่แบบ absolutes ไทย ("21 พ.ย. 69") ถ้ามี — หน้านี้มีแต่ relative จึงมักได้ None."""
    for el in card.find_all(["span", "p", "div", "time"]):
        if el.find_parent("ul") is not None:
            continue
        text = _text(el)
        if not text or len(text) > 24 or "\n" in text:
            continue
        if parse_thai_date(text):
            return text
    return None


def _card_container(card):
    """การ์ด 1 ใบ: <article> ที่มีลิงก์งาน · ไม่มี <article> เลย → ก้อนรอบลิงก์งาน."""
    if card.name != "article":
        node = card
        for _ in range(6):
            parent = node.parent
            if parent is None or parent.name in ("body", "html", "[document]"):
                break
            node = parent
            if node.find("a", href=COMPANY_RX):
                return node
    return card


def _cards_of(soup):
    """ลิสต์การ์ดในหน้า — <article> ที่มีลิงก์งานเป็นหลัก, มี fallback เมื่อโครงเปลี่ยน."""
    articles = [el for el in soup.find_all("article")
                if any(job_slug(a.get("href")) for a in el.find_all("a", href=True))]
    if articles:
        return articles
    seen: list = []
    for anchor in soup.find_all("a", href=True):
        if not job_slug(anchor.get("href")) or not _text(anchor):
            continue
        card = _card_container(anchor)
        if not any(card is item or card in item.descendants for item in seen):
            seen.append(card)
    return seen


def parse_search_html_with_stats(html: str, base: str = BASE_URL):
    """คืน (rows, stats). stats = {cards, skipped, duplicates} — ใช้รายงานตอนดึงจริง."""
    stats = {"cards": 0, "skipped": 0, "duplicates": 0}
    if not html or BeautifulSoup is None:
        return [], stats
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()

    for card in _cards_of(soup):
        stats["cards"] += 1
        anchor = _title_anchor(card)
        href = (anchor.get("href") if anchor else None) or ""
        slug = job_slug(href)
        title = _text(anchor)
        if not slug or not href:
            stats["skipped"] += 1  # ไม่มี url ของงาน = ใช้ไม่ได้
            continue
        if not title:
            stats["skipped"] += 1  # ไม่มีชื่อตำแหน่ง = ใช้ไม่ได้
            continue
        if slug in seen:
            stats["duplicates"] += 1  # overlay + <a> ใน <h2> ของงานใบเดียวกัน
            continue
        seen.add(slug)

        url = urljoin(str(base).rstrip("/") + "/", href.lstrip("/")) if href else None
        company = _text(card.find("a", href=COMPANY_RX))
        location = _text(card.find("a", href=LOCATION_RX))
        salary_text, salary_min, salary_max = _salary_fields(_card_salary_text(card))
        date_text = _card_date_text(card)

        rows.append({
            "source": SOURCE,
            "uid": slug,
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
    """หน้า search ของ jobtopgun → list ของ raw row (ดูสัญญาที่หัวไฟล์)."""
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
        url += f"&page={int(page)}"  # หน้าแรกของเว็บก็ไม่มี page= (วัดแล้ว: page=1 = ไม่ใส่)
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
    """ยิงหน้า search ของ jobtopgun ทีละคำ/ทีละหน้า → เขียนไฟล์ดิบ + คืนสรุป.

    merge=True: ถ้า out_path มีอยู่ ให้เก็บ envelope/log ของคำที่ไม่ได้ดึงรอบนี้ไว้
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
    out_path = Path(out_path) if out_path else (RAW / day.isoformat() / f"{SOURCE}.json")

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept-Language": "th,en;q=0.8"})

    logs: list[dict] = []
    envelopes: list[dict] = []
    request_count = 0
    started = time.time()

    parser, robots_error = robots_for(base, user_agent, timeout_s, session)
    request_count += 1
    if parser is None:
        log = {"source": SOURCE, "keyword": None, "page": None, "http": None,
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
                log = {"source": SOURCE, "keyword": keyword, "page": page, "http": None,
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
                        # 200 ที่ 0 การ์ด = หน้าสุดท้ายของคำนั้น ไม่ใช่ error
                        note = "no_cards"
            except Exception as exc:
                request_count += 1
                error = f"{type(exc).__name__}: {exc}"

            log = {"source": SOURCE, "keyword": keyword, "page": page, "http": http,
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
                    skip = {"source": SOURCE, "keyword": keyword, "page": None,
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
        "source": SOURCE,
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

    ต้อง resolve ก่อน relative_to: '_x.json'.relative_to(ROOT) โยน ValueError แม้ cwd = ROOT
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
