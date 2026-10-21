#!/usr/bin/env python3
"""
Cutwater C-28 Boat Listing Monitor
Scrapes BoatTrader, Boats.com, and YachtWorld for Cutwater C-28 listings,
compares against a local JSON database, and emails alerts for new or
price-reduced listings.
"""

import argparse
import json
import logging
import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv, set_key

# ── Paths & constants ─────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
DB_FILE = BASE_DIR / "listings_db.json"
LOG_FILE = BASE_DIR / "monitor.log"
ENV_FILE = BASE_DIR / ".env"

YEAR_MIN, YEAR_MAX = 2012, 2021
MAX_PRICE = 175_000
HOURS_WARN = 600
HOURS_HIGH_RISK = 800

PREFERRED_STATES = {"VA", "MD", "NC", "CT", "NY", "NJ", "FL"}

MODEL_VARIANTS = ["c-28", "c28", "c 28", "c-28 le", "c-28 nw"]

KEYWORD_PATTERNS: dict[str, list[str]] = {
    "generator":        ["generator", "genset"],
    "thruster":         ["thruster", "bow thruster", "stern thruster"],
    "AC":               ["air conditioning", " a/c ", " ac ", "hvac", "air-conditioning"],
    "solar":            ["solar"],
    "Yanmar":           ["yanmar"],
    "Volvo":            ["volvo"],
    "trailer":          ["trailer"],
    "low hours":        ["low hours", "low-hours"],
    "records":          ["service records", "maintenance records", " records"],
    "dealer maintained": ["dealer maintained", "dealer serviced", "dealer-maintained"],
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

logger = logging.getLogger(__name__)

# ── Database ──────────────────────────────────────────────────────────────────

def load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("DB file unreadable; starting fresh.")
    return {}


def save_db(db: dict) -> None:
    DB_FILE.write_text(json.dumps(db, indent=2, default=str), encoding="utf-8")

# ── Scoring ───────────────────────────────────────────────────────────────────

def score_listing(listing: dict, price_drop_pct: float = 0.0) -> int:
    pts = 0
    price = listing.get("price") or 0
    hours = listing.get("engine_hours")
    kw_lower = {k.lower() for k in listing.get("keywords", [])}
    state = (listing.get("state") or "").upper().strip()

    if price and price < 130_000:
        pts += 3
    if hours is not None and hours < 400:
        pts += 2
    if "generator" in kw_lower and "thruster" in kw_lower:
        pts += 2
    if state in PREFERRED_STATES:
        pts += 1
    if price_drop_pct > 5:
        pts += 1
    if "records" in kw_lower or "dealer maintained" in kw_lower:
        pts += 1

    return min(pts, 10)

# ── Shared scraper helpers ────────────────────────────────────────────────────

class BaseScraper:
    SOURCE = "unknown"
    BASE_URL = ""

    def _fetch(self, url: str) -> Optional[requests.Response]:
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
            if resp.status_code == 200:
                return resp
            logger.warning("%s: HTTP %s for %s", self.SOURCE, resp.status_code, url)
        except requests.RequestException as exc:
            logger.warning("%s: request failed for %s — %s", self.SOURCE, url, exc)
        return None

    def scrape(self) -> list[dict]:
        raise NotImplementedError

    # ── text extraction helpers ──

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        if not text:
            return None
        m = re.search(r"\$?\s*([\d,]+)", text)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_year(text: str) -> Optional[int]:
        for m in re.finditer(r"\b(20[012]\d|199\d)\b", text):
            yr = int(m.group(1))
            if YEAR_MIN <= yr <= YEAR_MAX:
                return yr
        return None

    @staticmethod
    def _parse_hours(text: str) -> Optional[int]:
        patterns = [
            r"(\d{1,5})\s*(?:engine\s+)?hours?(?:\s+on\s+engines?)?",
            r"\bhrs?\s*[:\-]?\s*(\d{1,5})\b",
            r"(\d{1,5})\s*hrs?\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if val < 30_000:  # sanity cap
                    return val
        return None

    @staticmethod
    def _parse_keywords(text: str) -> list[str]:
        tl = " " + text.lower() + " "
        found = []
        for label, pats in KEYWORD_PATTERNS.items():
            if any(p in tl for p in pats):
                found.append(label)
        return found

    @staticmethod
    def _parse_location(raw: str) -> tuple[str, str]:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) >= 2:
            state = parts[-1].strip().upper()
            state = re.sub(r"[^A-Z]", "", state)[:2]
            return parts[0], state
        return raw.strip(), ""

    @staticmethod
    def _is_cutwater_28(make: str, model: str, title: str) -> bool:
        combined = f"{make} {model} {title}".lower()
        if "cutwater" not in combined:
            return False
        return any(v in combined for v in MODEL_VARIANTS) or re.search(r"cutwater\s+28\b", combined) is not None

    def _abs_url(self, path: str) -> str:
        if not path:
            return ""
        if path.startswith("http"):
            return path
        return self.BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    def _extract_from_next_data(self, soup: BeautifulSoup) -> list[dict]:
        """Try to pull listings from an embedded Next.js __NEXT_DATA__ blob."""
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag:
            return []
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            return []

        # Drill through common pageProps shapes used by Boats Group sites
        page_props = (data.get("props") or {}).get("pageProps") or {}
        boats: list = []
        for key in ("boats", "listings", "results", "searchResults"):
            candidate = page_props.get(key)
            if isinstance(candidate, list):
                boats = candidate
                break
            if isinstance(candidate, dict):
                for inner in ("boats", "listings", "records", "items"):
                    if isinstance(candidate.get(inner), list):
                        boats = candidate[inner]
                        break
            if boats:
                break

        results = []
        for boat in boats:
            try:
                listing = self._map_boat_dict(boat)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _map_boat_dict(self, boat: dict) -> Optional[dict]:
        """Convert a raw boat dict (from JSON) to a normalised listing dict."""
        raw_price = boat.get("price") or boat.get("normalPrice") or 0
        try:
            price = int(str(raw_price).replace(",", "").replace("$", "")) if raw_price else None
        except (ValueError, TypeError):
            price = None

        if price and price > MAX_PRICE:
            return None

        raw_year = boat.get("year")
        year: Optional[int] = None
        if raw_year:
            try:
                year = int(raw_year)
                if not (YEAR_MIN <= year <= YEAR_MAX):
                    return None
            except (ValueError, TypeError):
                pass

        make  = str(boat.get("make")  or "")
        model = str(boat.get("model") or "")
        title = str(boat.get("headline") or boat.get("title") or boat.get("name") or
                    f"{year or ''} {make} {model}").strip()

        if not self._is_cutwater_28(make, model, title):
            return None

        raw_loc = boat.get("location") or {}
        if isinstance(raw_loc, dict):
            city  = str(raw_loc.get("city")  or "")
            state = str(raw_loc.get("state") or "").upper()[:2]
        else:
            city, state = self._parse_location(str(raw_loc))

        url_path = (boat.get("mappingUrl") or boat.get("seoHref") or
                    boat.get("url")        or boat.get("link") or "")
        full_url = self._abs_url(url_path)

        desc = str(boat.get("description") or boat.get("summary") or "")
        hours = self._parse_hours(desc)
        if hours is None:
            hours = self._parse_hours(title)

        dom = boat.get("daysOnMarket") or boat.get("daysListed")
        try:
            dom = int(dom) if dom is not None else None
        except (ValueError, TypeError):
            dom = None

        return {
            "source": self.SOURCE,
            "url": full_url,
            "title": title,
            "year": year,
            "model": model,
            "price": price,
            "city": city,
            "state": state,
            "engine_hours": hours,
            "days_on_market": dom,
            "keywords": self._parse_keywords(f"{desc} {title}"),
            "description_snippet": desc[:400],
        }

    def _parse_html_cards(self, soup: BeautifulSoup, base: str) -> list[dict]:
        """Fallback: scrape card elements from rendered HTML."""
        selectors = [
            ("article", re.compile(r"listing|boat-card|result", re.I)),
            ("div",     re.compile(r"listing-card|boat-card|search-result", re.I)),
        ]
        cards = []
        for tag, pat in selectors:
            cards = soup.find_all(tag, class_=pat)
            if cards:
                break

        results = []
        for card in cards:
            try:
                listing = self._parse_html_card(card, base)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _parse_html_card(self, card, base_url: str) -> Optional[dict]:
        title_el = card.find(["h2", "h3", "h4", "a"],
                              class_=re.compile(r"title|name|heading", re.I))
        title = title_el.get_text(" ", strip=True) if title_el else ""

        if not title or not self._is_cutwater_28("", "", title):
            return None

        price_el = card.find(class_=re.compile(r"price", re.I))
        price_text = price_el.get_text(" ", strip=True) if price_el else ""
        price = self._parse_price(price_text)
        if price and price > MAX_PRICE:
            return None

        year = self._parse_year(title)

        loc_el = card.find(class_=re.compile(r"location|city|region", re.I))
        city, state = self._parse_location(loc_el.get_text(" ", strip=True) if loc_el else "")

        link = card.find("a", href=True)
        full_url = self._abs_url(link["href"] if link else "")

        text = card.get_text(" ", strip=True)
        return {
            "source": self.SOURCE,
            "url": full_url,
            "title": title,
            "year": year,
            "model": "",
            "price": price,
            "city": city,
            "state": state,
            "engine_hours": self._parse_hours(text),
            "days_on_market": None,
            "keywords": self._parse_keywords(text),
            "description_snippet": text[:400],
        }


# ── Site-specific scrapers ────────────────────────────────────────────────────

class BoatTraderScraper(BaseScraper):
    SOURCE = "BoatTrader"
    BASE_URL = "https://www.boattrader.com"
    SEARCH_PATHS = [
        "/boats/make-cutwater/model-c-28/",
        "/boats/make-cutwater/model-28/",
    ]

    def scrape(self) -> list[dict]:
        listings: list[dict] = []
        seen: set[str] = set()
        for path in self.SEARCH_PATHS:
            url = self.BASE_URL + path
            logger.info("Fetching %s: %s", self.SOURCE, url)
            resp = self._fetch(url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            page_listings = self._extract_from_next_data(soup)
            if not page_listings:
                logger.info("%s: __NEXT_DATA__ empty; falling back to HTML parse", self.SOURCE)
                page_listings = self._parse_html_cards(soup, self.BASE_URL)
            for item in page_listings:
                if item.get("url") and item["url"] not in seen:
                    seen.add(item["url"])
                    listings.append(item)
            time.sleep(1.5)  # polite crawl delay
        logger.info("%s: %d listings collected", self.SOURCE, len(listings))
        return listings


class BoatsDotComScraper(BaseScraper):
    SOURCE = "Boats.com"
    BASE_URL = "https://www.boats.com"
    # Query-param style search; year filter applied post-parse since URL encoding varies
    SEARCH_URLS = [
        "https://www.boats.com/boats-for-sale/?make%5B%5D=Cutwater&model%5B%5D=C-28",
        "https://www.boats.com/boats-for-sale/?make%5B%5D=Cutwater&model%5B%5D=28",
    ]

    def scrape(self) -> list[dict]:
        listings: list[dict] = []
        seen: set[str] = set()
        for url in self.SEARCH_URLS:
            logger.info("Fetching %s: %s", self.SOURCE, url)
            resp = self._fetch(url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            page_listings = self._extract_from_next_data(soup)
            if not page_listings:
                logger.info("%s: __NEXT_DATA__ empty; falling back to HTML parse", self.SOURCE)
                page_listings = self._parse_html_cards(soup, self.BASE_URL)
            for item in page_listings:
                if item.get("url") and item["url"] not in seen:
                    seen.add(item["url"])
                    listings.append(item)
            time.sleep(1.5)
        logger.info("%s: %d listings collected", self.SOURCE, len(listings))
        return listings


class YachtWorldScraper(BaseScraper):
    SOURCE = "YachtWorld"
    BASE_URL = "https://www.yachtworld.com"
    SEARCH_PATHS = [
        "/boats-for-sale/make-cutwater/model-c-28/",
        "/boats-for-sale/make-cutwater/model-28/",
    ]

    def scrape(self) -> list[dict]:
        listings: list[dict] = []
        seen: set[str] = set()
        for path in self.SEARCH_PATHS:
            url = self.BASE_URL + path
            logger.info("Fetching %s: %s", self.SOURCE, url)
            resp = self._fetch(url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            page_listings = self._extract_from_next_data(soup)
            if not page_listings:
                logger.info("%s: __NEXT_DATA__ empty; falling back to HTML parse", self.SOURCE)
                page_listings = self._parse_html_cards(soup, self.BASE_URL)
            for item in page_listings:
                if item.get("url") and item["url"] not in seen:
                    seen.add(item["url"])
                    listings.append(item)
            time.sleep(1.5)
        logger.info("%s: %d listings collected", self.SOURCE, len(listings))
        return listings


# ── Diff / alert logic ────────────────────────────────────────────────────────

AlertTuple = tuple[str, dict]  # (alert_type, listing)


def diff_listings(current: list[dict], db: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (new_listings, price_drops, back_on_market).
    Also updates db in-place: marks unseen URLs inactive, updates last_seen.
    """
    now = datetime.utcnow().isoformat()
    current_by_url: dict[str, dict] = {
        item["url"]: item for item in current if item.get("url")
    }

    new_listings: list[dict] = []
    price_drops:  list[dict] = []
    back_on_market: list[dict] = []

    for url, listing in current_by_url.items():
        if url not in db:
            listing["first_seen"] = now
            listing["last_seen"] = now
            listing["active"] = True
            listing["price_history"] = [{"date": now, "price": listing.get("price")}]
            new_listings.append(listing)
        else:
            stored = db[url]
            new_price = listing.get("price")
            old_price = stored.get("price")

            # Carry over history fields
            listing["first_seen"] = stored.get("first_seen", now)
            listing["last_seen"] = now
            listing["active"] = True
            history = list(stored.get("price_history") or [])

            if not stored.get("active", True):
                history.append({"date": now, "price": new_price})
                listing["price_history"] = history
                back_on_market.append(listing)
            elif old_price and new_price and new_price < old_price:
                drop_pct = (old_price - new_price) / old_price * 100
                listing["price_drop_pct"] = round(drop_pct, 1)
                listing["old_price"] = old_price
                history.append({"date": now, "price": new_price})
                listing["price_history"] = history
                price_drops.append(listing)
            else:
                # Unchanged — just refresh timestamps in DB
                db[url]["last_seen"] = now
                db[url]["active"] = True
                listing["price_history"] = history

    # Mark listings absent from current scrape as inactive
    for url in db:
        if not url.startswith("_") and url not in current_by_url:
            db[url]["active"] = False

    return new_listings, price_drops, back_on_market


def apply_alerts_to_db(db: dict, alerts: list[AlertTuple]) -> None:
    for _, listing in alerts:
        url = listing.get("url")
        if url:
            db[url] = listing


# ── Email formatting ──────────────────────────────────────────────────────────

def _fmt_price(price: Optional[int]) -> str:
    return f"${price:,}" if price else "N/A"


def _hours_html(hours: Optional[int]) -> str:
    if hours is None:
        return "N/A"
    if hours > HOURS_HIGH_RISK:
        return f'<span style="color:#c0392b;font-weight:bold">{hours} ⚠</span>'
    if hours > HOURS_WARN:
        return f'<span style="color:#e67e22">{hours}</span>'
    return str(hours)


_BADGE = {
    "NEW":            '#2980b9',
    "PRICE DROP":     '#27ae60',
    "BACK ON MARKET": '#d35400',
}


def build_html_body(alerts: list[AlertTuple]) -> str:
    rows = []
    for alert_type, lst in alerts:
        price_str = _fmt_price(lst.get("price"))
        if alert_type == "PRICE DROP":
            old = _fmt_price(lst.get("old_price"))
            pct = lst.get("price_drop_pct", 0)
            price_str = (f'{price_str} '
                         f'<span style="color:#27ae60">(↓{pct:.1f}% from {old})</span>')

        score = lst.get("score", 0)
        score_color = "#27ae60" if score >= 7 else ("#e67e22" if score >= 4 else "#7f8c8d")
        badge_color = _BADGE.get(alert_type, "#7f8c8d")
        location = ", ".join(filter(None, [lst.get("city"), lst.get("state")]))
        kw = ", ".join(lst.get("keywords") or []) or "—"
        url = lst.get("url", "#")
        title = lst.get("title", "—")

        rows.append(f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1;white-space:nowrap">
            <span style="background:{badge_color};color:#fff;padding:2px 7px;
                         border-radius:3px;font-size:11px">{alert_type}</span>
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1">
            <a href="{url}" style="color:#2980b9">{title}</a>
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1;white-space:nowrap">
            {price_str}
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1">{location}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1;text-align:center">
            {_hours_html(lst.get("engine_hours"))}
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1;font-size:12px">{kw}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1;text-align:center;
                     font-weight:bold;color:{score_color}">{score}/10</td>
          <td style="padding:8px 10px;border-bottom:1px solid #ecf0f1;font-size:12px">
            {lst.get('source','')}
          </td>
        </tr>""")

    th = ("background:#2c3e50;color:#fff;padding:9px 10px;text-align:left;"
          "font-size:12px;text-transform:uppercase;letter-spacing:.5px")
    headers = "".join(
        f'<th style="{th}">{h}</th>'
        for h in ["Type", "Listing", "Price", "Location", "Hours",
                  "Keywords", "Score", "Source"]
    )

    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#2c3e50">
  <h2 style="border-bottom:2px solid #2980b9;padding-bottom:6px">
    ⚓ Cutwater C-28 Listing Alerts
  </h2>
  <p style="color:#7f8c8d">Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp;
     {len(alerts)} alert(s)</p>
  <table style="border-collapse:collapse;width:100%;max-width:1100px">
    <thead><tr>{headers}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <p style="font-size:11px;color:#95a5a6;margin-top:20px">
    Score rubric: &lt;$130K → +3 &nbsp;|&nbsp; &lt;400 hrs → +2 &nbsp;|&nbsp;
    generator + thruster → +2 &nbsp;|&nbsp; VA/MD/NC/CT/NY/NJ/FL → +1 &nbsp;|&nbsp;
    &gt;5% drop → +1 &nbsp;|&nbsp; records/dealer-maintained → +1
  </p>
</body></html>"""


def build_subject(alerts: list[AlertTuple]) -> str:
    if not alerts:
        return "Cutwater C-28 Monitor: no new alerts"
    best_type, best = max(alerts, key=lambda x: x[1].get("score", 0))
    score = best.get("score", 0)
    title = best.get("title", "Cutwater C-28")
    price = _fmt_price(best.get("price"))
    loc = ", ".join(filter(None, [best.get("city"), best.get("state")]))
    extra = f" (+{len(alerts)-1} more)" if len(alerts) > 1 else ""
    return f"[Score {score}/10] {best_type}: {title} – {price} – {loc}{extra}"


def send_alert_email(alerts: list[AlertTuple]) -> None:
    server  = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    port    = int(os.environ.get("SMTP_PORT", "587"))
    user    = os.environ.get("SMTP_USER", "")
    passwd  = os.environ.get("SMTP_PASSWORD", "")
    to_addr = os.environ.get("ALERT_EMAIL", user)

    if not user or not passwd:
        logger.error("Email credentials missing. Run with --setup or check your .env file.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = build_subject(alerts)
    msg["From"]    = user
    msg["To"]      = to_addr
    msg.attach(MIMEText(build_html_body(alerts), "html", "utf-8"))

    try:
        with smtplib.SMTP(server, port, timeout=30) as conn:
            conn.ehlo()
            conn.starttls()
            conn.login(user, passwd)
            conn.sendmail(user, to_addr, msg.as_string())
        logger.info("Alert email sent → %s | %s", to_addr, msg["Subject"])
    except smtplib.SMTPException as exc:
        logger.error("SMTP error: %s", exc)


# ── First-run credential setup ────────────────────────────────────────────────

def run_setup() -> None:
    print("\n=== Cutwater Monitor — First-Run Setup ===")
    print("For Gmail you need an App Password (not your account password).")
    print("Create one at: https://myaccount.google.com/apppasswords\n")

    smtp_user  = input("Gmail address (sender):      ").strip()
    smtp_pass  = input("App password:                ").strip()
    alert_addr = input(f"Recipient address [{smtp_user}]: ").strip() or smtp_user

    path = str(ENV_FILE)
    set_key(path, "SMTP_SERVER",   "smtp.gmail.com")
    set_key(path, "SMTP_PORT",     "587")
    set_key(path, "SMTP_USER",     smtp_user)
    set_key(path, "SMTP_PASSWORD", smtp_pass)
    set_key(path, "ALERT_EMAIL",   alert_addr)

    print(f"\nCredentials saved to {ENV_FILE}\n")
    logger.info("Credentials saved to .env")


# ── Main run logic ────────────────────────────────────────────────────────────

def run_once() -> None:
    logger.info("=== Cutwater C-28 monitor run started ===")

    all_current: list[dict] = []
    for scraper_cls in (BoatTraderScraper, BoatsDotComScraper, YachtWorldScraper):
        scraper = scraper_cls()
        try:
            results = scraper.scrape()
            all_current.extend(results)
        except Exception as exc:
            logger.error("Scraper %s crashed: %s", scraper.SOURCE, exc)

    logger.info("Total listings scraped across all sources: %d", len(all_current))

    db = load_db()
    is_first_run = "_meta" not in db

    new_l, drops, bom = diff_listings(all_current, db)

    # Score
    for lst in new_l:
        lst["score"] = score_listing(lst)
    for lst in drops:
        lst["score"] = score_listing(lst, lst.get("price_drop_pct", 0))
    for lst in bom:
        lst["score"] = score_listing(lst)

    # Persist
    db["_meta"] = {
        "last_run": datetime.utcnow().isoformat(),
        "total_listings": len(all_current),
    }
    apply_alerts_to_db(db, [("NEW", l) for l in new_l] +
                            [("PRICE DROP", l) for l in drops] +
                            [("BACK ON MARKET", l) for l in bom])
    save_db(db)

    if is_first_run:
        db_entries = sum(1 for k in db if not k.startswith("_"))
        logger.info(
            "First run: database seeded with %d listings. "
            "No alerts sent — run again to detect changes.",
            db_entries,
        )
        print(f"\nFirst run complete. Seeded database with {db_entries} listings.")
        print("Run the script again to detect new listings and price changes.")
        return

    alerts: list[AlertTuple] = (
        [("NEW", l)            for l in new_l] +
        [("PRICE DROP", l)     for l in drops] +
        [("BACK ON MARKET", l) for l in bom]
    )
    alerts.sort(key=lambda x: x[1].get("score", 0), reverse=True)

    logger.info(
        "Alerts — NEW: %d  PRICE DROP: %d  BACK ON MARKET: %d",
        len(new_l), len(drops), len(bom),
    )
    for atype, lst in alerts:
        logger.info(
            "  [%s] Score %d/10 | %s | %s | %s, %s",
            atype, lst.get("score", 0), lst.get("title", ""),
            _fmt_price(lst.get("price")),
            lst.get("city", ""), lst.get("state", ""),
        )

    if alerts:
        send_alert_email(alerts)
    else:
        logger.info("No alerts this run.")

    logger.info("=== Run complete ===\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cutwater C-28 boat listing monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python monitor.py               # single run\n"
            "  python monitor.py --daemon      # loop every 12 hours\n"
            "  python monitor.py --daemon --interval 6\n"
            "  python monitor.py --setup       # reconfigure email credentials\n"
        ),
    )
    parser.add_argument("--daemon",   action="store_true",
                        help="Loop indefinitely on --interval schedule")
    parser.add_argument("--interval", type=int, default=12,
                        help="Hours between daemon runs (default: 12)")
    parser.add_argument("--setup",   action="store_true",
                        help="Re-run credential setup even if .env exists")
    args = parser.parse_args()

    setup_logging()
    load_dotenv(ENV_FILE)

    if args.setup or not ENV_FILE.exists():
        run_setup()
        load_dotenv(ENV_FILE)

    if args.daemon:
        interval_secs = args.interval * 3600
        logger.info("Daemon mode — interval: %dh", args.interval)
        while True:
            run_once()
            logger.info("Sleeping %dh …", args.interval)
            time.sleep(interval_secs)
    else:
        run_once()


if __name__ == "__main__":
    main()
