"""fetch_jobspy.py — เรียก python-jobspy (linkedin / indeed / seek=JobsDB / google)

กติกา
  · T0 cookieless ล้วน — ไม่ส่ง cookie/session/proxy ใด ๆ (brief §5)
  · LinkedIn 1 คำ/วัน 100 ผล/คำ · เจอ 429 → log แล้วหยุด ไม่ retry รัว
  · เพดานต่อแหล่งอ่านจาก config\\sources.json (limits) + สวิตช์ boards.* ใน config\\switches.json
  · เก็บผลดิบที่ data\\raw\\<YYYY-MM-DD>\\jobspy.json (แยก envelope ต่อแหล่ง)
  · ไม่ใช้เงิน: ทุกบอร์ดในไฟล์นี้ฟรี → cost_usd = 0.0
  · ไม่มี path absolute: ทุก path มาจาก ROOT = Path(__file__).resolve().parent.parent

ใช้:  python src\\fetch_jobspy.py --keywords developer --sites linkedin,indeed,jobsdb,google
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, time as dtime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"

# ชื่อใน config → ชื่อ site ของ JobSpy
SITE_MAP = {
    "linkedin": "linkedin",
    "indeed": "indeed",
    "jobsdb": "seek",      # SEEK ครอบ JobsDB/JobStreet ไทย (brief §13)
    "google": "google",
}

RATE_LIMIT_MARKERS = ("429", "too many requests", "rate limit", "ratelimit", "blocked")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_sources() -> dict:
    return load_json(CONFIG / "sources.json")


def load_switches() -> dict:
    data = load_json(CONFIG / "switches.json")
    preset = data.get("active")
    switches = dict(data.get("switches") or {})
    if preset and preset in (data.get("presets") or {}):
        switches = dict(data["presets"][preset])
    return switches


# ------------------------------------------------------------------ json safety
def sanitize(value):
    """pandas/NaN/NaT/date → JSON-safe (None แทนค่าที่ไม่รู้)."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return [sanitize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items()}
    try:
        import pandas as pd
        if value is pd.NaT:
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            return sanitize(value.item())
    except ImportError:  # pragma: no cover
        pass
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _is_rate_limit(err: Exception) -> bool:
    msg = f"{type(err).__name__}: {err}".lower()
    return any(marker in msg for marker in RATE_LIMIT_MARKERS)


# ----------------------------------------------------------------------- fetch
class _LogCollector(logging.Handler):
    """ดักข้อความ WARNING/ERROR ที่ไลบรารี jobspy เขียนลง log ระหว่างยิง 1 ครั้ง
    (เช่น 'location not found', 'no job data returned') เพื่อเอาไปเขียน runs log จริง."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):  # pragma: no cover - ขึ้นกับพฤติกรรมไลบรารี
        try:
            self.messages.append(f"{record.levelname}:{record.getMessage()}")
        except Exception:
            pass


def fetch_site(site_key: str, keyword: str, location: str, results_wanted: int,
               hours_old: int, country_indeed: str, fetch_description: bool,
               verbose: int = 1,
               google_search_term: str | None = None) -> tuple[list[dict], dict]:
    """ยิง JobSpy 1 ครั้ง (1 แหล่ง 1 คำ) — คืน (rows, log). ไม่ retry."""
    started = time.time()
    log = {
        "source": site_key,
        "site_name": SITE_MAP.get(site_key, site_key),
        "keyword": keyword,
        "ok": False,
        "results": 0,
        "error": None,
        "rate_limited": False,
        "elapsed_s": 0.0,
        "cost_usd": 0.0,
        "warnings": [],
    }
    try:
        from jobspy import scrape_jobs
    except Exception as exc:  # import ไม่ได้ = หยุดทั้งไฟล์
        log["error"] = f"import_error: {type(exc).__name__}: {exc}"
        log["elapsed_s"] = round(time.time() - started, 1)
        raise

    collector = _LogCollector()
    lib_logger = logging.getLogger("jobspy")
    lib_logger.addHandler(collector)
    try:
        df = scrape_jobs(
            site_name=[SITE_MAP.get(site_key, site_key)],
            search_term=keyword,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country_indeed,
            linkedin_fetch_description=fetch_description,
            google_search_term=google_search_term or None,
            description_format="markdown",
            verbose=verbose,
        )
        records = [] if df is None else [sanitize(r) for r in df.to_dict(orient="records")]
        for row in records:
            row["_site"] = site_key
        log["ok"] = True
        log["results"] = len(records)
        log["warnings"] = collector.messages[-5:]
        if not records:
            # ไม่มี exception แต่ไลบรารีคืน 0 แถว — บันทึกตามจริง ไม่เดาว่าสำเร็จ
            log["error"] = "no_rows_returned" + (
                f" ({log['warnings'][-1]})" if log["warnings"] else "")
        return records, log
    except Exception as exc:
        log["error"] = f"{type(exc).__name__}: {exc}"
        log["rate_limited"] = _is_rate_limit(exc)
        log["warnings"] = collector.messages[-5:]
        return [], log
    finally:
        lib_logger.removeHandler(collector)
        log["elapsed_s"] = round(time.time() - started, 1)


def desired_sites(switches: dict) -> list[str]:
    out = []
    for key in SITE_MAP:
        if switches.get(f"boards.{key}", True):
            out.append(key)
    return out


def run(keywords=None, sites=None, location=None, results_wanted=None,
        hours_old=None, day=None, verbose: int = 1) -> dict:
    sources = load_sources()
    switches = load_switches()
    jcfg = sources.get("jobspy") or {}
    limits = (sources.get("limits") or {})

    keywords = list(keywords or jcfg.get("keywords") or ["developer"])
    sites = [s for s in (sites or desired_sites(switches)) if s in SITE_MAP]
    base_location = location or jcfg.get("location") or "Bangkok, Thailand"
    per_site_location = {k: v for k, v in (jcfg.get("locations") or {}).items()
                         if not k.startswith("_")}
    google_term = jcfg.get("google_search_term")
    country_indeed = jcfg.get("country_indeed") or "thailand"
    day = day or date.today()

    per_board = int(switches.get("limit.per_board") or results_wanted or 100)
    if results_wanted:
        per_board = min(per_board, int(results_wanted))
    hours_old = int(hours_old or switches.get("time.window_hours") or jcfg.get("hours_old") or 72)
    fetch_desc = bool(switches.get("details.fetch_description", False))

    logs: list[dict] = []
    envelopes: list[dict] = []

    for site_key in sites:
        cap = limits.get(site_key, {}).get("results") or limits.get(site_key, {}).get("results_per_keyword")
        want = min(per_board, int(cap)) if cap else per_board
        rows_for_site: list[dict] = []
        site_stopped = False
        site_location = per_site_location.get(site_key, base_location)
        for keyword in keywords:
            if site_stopped:
                break
            rows, log = fetch_site(site_key, keyword, site_location, want, hours_old,
                                   country_indeed, fetch_desc, verbose,
                                   google_search_term=google_term)
            logs.append(log)
            rows_for_site.extend(rows)
            print(json.dumps(log, ensure_ascii=False))
            if log["rate_limited"] or log["error"] and log["error"].startswith("import_error"):
                site_stopped = True  # 429/import พัง = หยุดแหล่งนี้ทันที ไม่ retry
        envelopes.append({"source": site_key, "location": site_location,
                          "keyword": ",".join(keywords), "jobs": rows_for_site})

    out_dir = RAW / day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "jobspy.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "jobspy",
        "params": {
            "keywords": keywords,
            "sites": sites,
            "location": base_location,
            "locations": per_site_location,
            "country_indeed": country_indeed,
            "results_wanted_per_site": per_board,
            "hours_old": hours_old,
            "linkedin_fetch_description": fetch_desc,
            "session": "T0 (cookieless)",
        },
        "logs": logs,
        "raw": envelopes,
    }
    payload = merge_payload(out_path, payload, set(sites))
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    total = sum(e["results"] for e in logs)
    return {
        "path": str(out_path),
        "params": payload["params"],
        "total_rows": total,
        "per_source": {log["source"]: log["results"] for log in logs},
        "errors": [f"{log['source']}:{log['keyword']}: {log['error']}"
                   for log in logs if log["error"]],
        "cost_usd": 0.0,
        "logs": logs,
    }


def _job_key(job: dict) -> str:
    return (job.get("job_url") or job.get("url") or "") + "|" + (job.get("title") or "")


def merge_payload(out_path: Path, payload: dict, fetched_sites: set[str]) -> dict:
    """รวมกับ jobspy.json เดิมของวันเดียวกัน: แทน envelope ของแหล่งที่ยิงรอบนี้,
    เก็บแหล่งที่ไม่ได้ยิง, union แถวด้วย (job_url, title), ต่อ log ไว้เป็นประวัติ."""
    if not out_path.is_file():
        return payload
    try:
        with out_path.open("r", encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return payload

    old_env = {e.get("source"): e for e in old.get("raw") or [] if isinstance(e, dict)}
    merged_env = []
    for env in payload["raw"]:
        src = env.get("source")
        prev = old_env.get(src)
        if prev:
            seen = {_job_key(j) for j in env["jobs"]}
            env = dict(env)
            env["jobs"] = list(env["jobs"]) + [j for j in prev.get("jobs") or []
                                               if _job_key(j) not in seen]
        merged_env.append(env)
    for src, prev in old_env.items():
        if src not in fetched_sites:
            merged_env.append(prev)

    order = list(SITE_MAP)
    merged_env.sort(key=lambda e: order.index(e["source"]) if e.get("source") in order else 99)
    payload["raw"] = merged_env
    payload["logs"] = list(old.get("logs") or []) + list(payload["logs"])

    # params ของรันแรกของวันคงไว้ (ใช้รายงาน) + รวมรายชื่อแหล่งที่ยิงทั้งวัน
    if old.get("params"):
        merged_params = dict(old["params"])
        merged_params["sites"] = sorted(
            set(old["params"].get("sites") or []) | set(payload["params"].get("sites") or []))
        merged_params["runs"] = list(old["params"].get("runs") or []) + [
            {"at": payload["generated_at"],
             "sites": payload["params"].get("sites"),
             "keywords": payload["params"].get("keywords")}]
        payload["params"] = merged_params
    else:
        payload["params"]["runs"] = [{"at": payload["generated_at"],
                                      "sites": payload["params"].get("sites"),
                                      "keywords": payload["params"].get("keywords")}]
    return payload


def parse_args(argv: list[str]) -> dict:
    opts = {"keywords": [], "sites": [], "location": None,
            "results_wanted": None, "hours_old": None, "verbose": 1}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--keywords" and i + 1 < len(argv):
            opts["keywords"].append(argv[i + 1]); i += 2
        elif arg.startswith("--keywords="):
            opts["keywords"].append(arg.split("=", 1)[1]); i += 1
        elif arg == "--sites" and i + 1 < len(argv):
            opts["sites"] = [s.strip() for s in argv[i + 1].split(",") if s.strip()]; i += 2
        elif arg.startswith("--sites="):
            opts["sites"] = [s.strip() for s in arg.split("=", 1)[1].split(",") if s.strip()]; i += 1
        elif arg == "--location" and i + 1 < len(argv):
            opts["location"] = argv[i + 1]; i += 2
        elif arg.startswith("--location="):
            opts["location"] = arg.split("=", 1)[1]; i += 1
        elif arg == "--results-wanted" and i + 1 < len(argv):
            opts["results_wanted"] = int(argv[i + 1]); i += 2
        elif arg.startswith("--results-wanted="):
            opts["results_wanted"] = int(arg.split("=", 1)[1]); i += 1
        elif arg == "--hours-old" and i + 1 < len(argv):
            opts["hours_old"] = int(argv[i + 1]); i += 2
        elif arg.startswith("--hours-old="):
            opts["hours_old"] = int(arg.split("=", 1)[1]); i += 1
        elif arg == "--quiet":
            opts["verbose"] = 0; i += 1
        else:
            i += 1
    return opts


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = parse_args(argv)
    try:
        summary = run(**opts)
    except Exception as exc:  # import พัง = รายงาน ไม่แพตช์ไลบรารี
        print(json.dumps({"fatal": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps({k: v for k, v in summary.items() if k != "logs"}, ensure_ascii=False))
    failures = [log for log in summary["logs"] if not log["ok"]]
    return 0 if len(failures) < len(summary["logs"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
