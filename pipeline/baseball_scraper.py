"""Page-aware Baseball Almanac team-season scraper.

Install: python -m pip install -U selenium pandas psutil beautifulsoup4
Run: python baseball_scraper_fresh_sessions.py
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import shutil
import psutil
import logging
import sys
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.robotparser import RobotFileParser

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "https://www.baseball-almanac.com"
OUTPUT_DIR = Path(__file__).resolve().parent / "baseball_data"
TEAMS = [
    {"name": "New York Yankees", "code": "NYA", "year": 1927},
    {"name": "New York Mets", "code": "NYN", "year": 1986},
    {"name": "New York Giants", "code": "NY1", "year": 1905},
]
CATEGORIES = ("roster", "schedule", "hitting", "pitching")
DELAY_RANGE = (8, 15)
MAX_REQUESTS = 12
USER_AGENT = "MLBHistoricalResearchBot"
CHROME_PATH = Path(r"C:\Users\willv\Downloads\chrome-win64\chrome-win64\chrome.exe")
CHROMEDRIVER_PATH = Path(r"C:\Users\willv\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe")
# Snapshot supplied by the user; this is NOT a live verification of site rules.
ROBOTS_SNAPSHOT = """User-agent: *
Disallow: /4723erika156/
Disallow: /banners/
Disallow: /maildir/
Disallow: /pass/
Disallow: /php.common/
Disallow: /temp/
Disallow: /test.php/
Sitemap: https://a79215.sitemaphosting.com/3943883/sitemap.xml

User-agent: AmazonAdBot
"""
POSITION_NAMES = {
    "pitchers": "Pitcher", "catchers": "Catcher",
    "infielders": "Infielder", "outfielders": "Outfielder",
    "designated hitters": "Designated Hitter",
    "utility players": "Utility Player",
}


def configure_logging():
    """Write timestamped status messages to both terminal and a log file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("baseball_scraper")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logfile = logging.FileHandler(OUTPUT_DIR / "scraper_status.log", encoding="utf-8")
    logfile.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(logfile)
    return logger


LOG = configure_logging()


def clean(value):
    return " ".join(value.split()).strip()


def slug(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")


def url_for(team, category):
    return f"{BASE_URL}/teamstats/{category}.php?" + urlencode({"t": team["code"], "y": team["year"]})


def identify_page(driver, team, category):
    """Validate the heading using one browser-side read."""
    expected_base = f"{team['year']} {team['name']}"
    expected = {
        "roster": f"Roster for the {expected_base}",
        "schedule": f"{expected_base} Schedule",
        "hitting": f"{expected_base} Hitting Stats",
        "pitching": f"{expected_base} Pitching Stats",
    }[category]
    heading = WebDriverWait(driver, 30).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "div.intro h1"))
    )
    title = clean(heading.text)
    if title.casefold() != expected.casefold():
        raise ValueError(f"Unexpected heading: {title!r}; expected {expected!r}")
    return {"title": title, "team": team["name"], "year": team["year"], "category": category}


def wait_for_table(driver, category):
    selectors = {
        "roster": "div.ba-table table.boxed tbody tr",
        "schedule": "div.ba-table table.boxed tbody tr",
        "hitting": "table#hitting-stats tbody tr[role='row']",
        "pitching": "table#pitching-stats tbody tr[role='row']",
    }
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selectors[category]))
    )


def cell_text(cell):
    return clean(cell.get_text(" ", strip=True))


def is_banner(cells):
    return bool(cells) and all("banner" in cell.get("class", []) for cell in cells)


def scrape_roster(soup):
    records, warnings = [], []
    position = None
    found_banners = set()
    for table in soup.select("div.ba-table table.boxed"):
        for row in table.select("tbody > tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) != 7:
                continue
            if is_banner(cells):
                label = cell_text(cells[1]).casefold()
                position = POSITION_NAMES.get(label)
                if position:
                    found_banners.add(position)
                else:
                    warnings.append(f"Unknown roster banner: {label}")
                continue
            if position is None or "datacolBlue" not in cells[1].get("class", []):
                continue
            link = cells[1].select_one("a[href*='/players/player.php']")
            if link:
                name = cell_text(link)
                if name:
                    records.append({"Player": name, "Position": position})
    LOG.info("Roster position groups found: %s", ", ".join(sorted(found_banners)) or "none")
    if not found_banners:
        warnings.append("No position banners found")
    df = pd.DataFrame(records, columns=["Player", "Position"]).drop_duplicates()
    LOG.info("Roster: %d player records extracted", len(df))
    if df.empty:
        warnings.append("No roster player records found")
    return df, warnings


def row_values(row):
    """Read direct table cells locally, never through Selenium."""
    return [cell_text(c) for c in row.find_all(["th", "td"], recursive=False)]


def scrape_schedule(soup):
    """Schedule: tbody row 3 is the header; final two rows are footers."""
    columns = ["Game", "Date", "Opponent", "Score", "Decision", "Record"]
    for table in soup.select("div.ba-table table.boxed"):
        body = table.find("tbody", recursive=False)
        if body is None:
            continue
        rows = body.find_all("tr", recursive=False)
        if len(rows) < 6:
            continue
        header = row_values(rows[2])
        if len(header) != 6 or header[0].casefold() != "game" or header[2].casefold() != "opponent":
            continue
        records = []
        skipped = 0
        for row in rows[3:-2]:
            values = row_values(row)
            if len(values) != 6 or not values[0]:
                skipped += 1
                continue
            records.append(values)
        df = pd.DataFrame(records, columns=columns)
        LOG.info("Schedule: %d tbody rows, %d data rows, %d skipped", len(rows), len(df), skipped)
        warnings = [] if not df.empty else ["Schedule table found but no game rows extracted"]
        if skipped:
            warnings.append(f"Skipped {skipped} schedule rows without six cells")
        return df, warnings
    LOG.warning("Schedule: no table with expected third-row header found")
    return pd.DataFrame(columns=columns), ["Schedule third-row header did not match expected structure"]


def scrape_stats(soup, category):
    """Stats: final thead row defines columns, tbody contains data, tfoot is excluded."""
    table = soup.select_one(f"table#{category}-stats")
    if table is None:
        raise ValueError(f"Missing {category}-stats table in captured HTML")
    thead = table.find("thead", recursive=False)
    tbody = table.find("tbody", recursive=False)
    if thead is None or tbody is None:
        raise ValueError(f"Missing thead or tbody for {category}")
    header_rows = thead.find_all("tr", recursive=False)
    if not header_rows:
        raise ValueError(f"No {category} thead rows found")
    columns = row_values(header_rows[-1])
    if not columns or columns[0].casefold() != "name":
        raise ValueError(f"Unexpected {category} final thead row: {columns}")
    records = []
    counts = {}
    for row in tbody.find_all("tr", recursive=False):
        values = row_values(row)
        counts[len(values)] = counts.get(len(values), 0) + 1
        if len(values) != len(columns) or not values[0]:
            continue
        records.append(values)
    df = pd.DataFrame(records, columns=columns)
    LOG.info("%s: %d headers, body cell counts %s; %d rows extracted", category.title(), len(columns), counts, len(df))
    warnings = [] if not df.empty else [f"No {category} rows matched the header width"]
    return df, warnings


def scrape_category(html, category):
    """All extraction happens locally: no Selenium commands per cell."""
    soup = BeautifulSoup(html, "html.parser")
    if category == "roster":
        return scrape_roster(soup)
    if category == "schedule":
        return scrape_schedule(soup)
    return scrape_stats(soup, category)


def process_family(service):
    """Snapshot the exact driver and Chrome processes belonging to this session."""
    process = getattr(service, "process", None)
    if process is None:
        return []
    try:
        parent = psutil.Process(process.pid)
        return [parent, *parent.children(recursive=True)]
    except psutil.Error:
        return []


def live_processes(processes):
    """Exclude dead/reused PIDs using psutil's process identity tracking."""
    alive = []
    for proc in processes:
        try:
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                alive.append(proc)
        except psutil.Error:
            pass
    return alive


def stop_processes(processes):
    """Terminate session-owned descendants first, then the driver; escalate only if needed."""
    alive = live_processes(processes)
    if not alive:
        return True
    # Snapshot lists driver first, then descendants. Stop descendants first.
    for proc in reversed(alive):
        try:
            proc.terminate()
        except psutil.Error:
            pass
    _, remaining = psutil.wait_procs(alive, timeout=5)
    for proc in remaining:
        try:
            proc.kill()
        except psutil.Error:
            pass
    _, remaining = psutil.wait_procs(remaining, timeout=5)
    if remaining:
        LOG.error("Processes still alive after forced cleanup: %s", [p.pid for p in remaining])
    return not remaining


def launch_browser():
    """Create a session with a private profile and return resources even on failure."""
    profile = Path(tempfile.mkdtemp(prefix="baseball_chrome_"))
    options = Options()
    options.binary_location = str(CHROME_PATH)
    options.add_argument("--window-size=1600,1000")
    options.add_argument(f"--user-data-dir={profile}")
    options.page_load_strategy = "eager"
    service = Service(executable_path=str(CHROMEDRIVER_PATH))
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        return driver, service, profile
    except BaseException:
        LOG.exception("Browser startup failed; cleaning up partial session")
        stop_processes(process_family(service))
        shutil.rmtree(profile, ignore_errors=True)
        raise


def close_browser(driver, service, profile):
    """Bound quit, then independently verify and clean up the owned process family."""
    import threading

    # Record descendants BEFORE quit: ChromeDriver may disappear while Chrome survives.
    owned = process_family(service)
    quit_done = threading.Event()
    errors = []

    def graceful_quit():
        try:
            driver.quit()
        except Exception as exc:
            errors.append(str(exc))
        finally:
            quit_done.set()

    if driver is not None:
        worker = threading.Thread(target=graceful_quit, daemon=True)
        worker.start()
        if not quit_done.wait(timeout=12):
            LOG.warning("Selenium quit blocked >12s; terminating owned process family to unblock it")
            stop_processes(owned)
            worker.join(timeout=3)
            if worker.is_alive():
                LOG.error("Selenium quit thread remains blocked after process termination")
        elif errors:
            LOG.warning("Selenium quit returned error: %s", errors[0])
        else:
            LOG.info("Selenium quit finished")

    # A successful quit call does not prove Chrome's child processes have exited.
    remaining = live_processes(owned)
    if remaining:
        _, remaining = psutil.wait_procs(remaining, timeout=5)
    if remaining:
        LOG.warning("%d owned browser/driver processes remain; cleaning up", len(remaining))
        stop_processes(remaining)
    remaining = live_processes(owned)
    if remaining:
        LOG.error("Cleanup incomplete; live PIDs: %s", [p.pid for p in remaining])
        raise RuntimeError("Browser cleanup incomplete; refusing to launch another instance")

    if profile is not None:
        try:
            shutil.rmtree(profile)
        except OSError as exc:
            LOG.warning("Temporary profile removal failed: %s", exc)
    LOG.info("Verified browser and ChromeDriver processes exited")


def main():
    started = time.monotonic()
    successful = empty = failed = count = 0
    LOG.info("Starting scraper: %d teams, %d categories, request limit %d", len(TEAMS), len(CATEGORIES), MAX_REQUESTS)
    LOG.info("Output folder: %s", OUTPUT_DIR)
    LOG.info("Checking hardcoded robots.txt snapshot (user-provided; not live-verified)")
    robots = RobotFileParser()
    robots.parse(ROBOTS_SNAPSHOT.splitlines())
    test_url = url_for(TEAMS[0], "roster")
    if not robots.can_fetch(USER_AGENT, test_url):
        LOG.warning("Hardcoded robots rules prohibit this path. Stopping.")
        return
    for label, path in (("Chrome", CHROME_PATH), ("ChromeDriver", CHROMEDRIVER_PATH)):
        if not path.is_file():
            LOG.error("%s executable not found: %s", label, path)
            return

    for team in TEAMS:
        folder = OUTPUT_DIR / slug(f"{team['name']}_{team['year']}")
        folder.mkdir(parents=True, exist_ok=True)
        LOG.info("=== Team: %s (%s) ===", team["name"], team["year"])
        metadata = {"team": team["name"], "team_code": team["code"],
                    "year": team["year"], "pages": {}}
        for category in CATEGORIES:
            if count >= MAX_REQUESTS:
                break
            url = url_for(team, category)
            if not robots.can_fetch(USER_AGENT, url):
                LOG.warning("DISALLOWED: %s", url)
                metadata["pages"][category] = {"url": url, "status": "disallowed"}
                continue
            if count:
                delay = random.uniform(*DELAY_RANGE)
                LOG.info("Waiting %.1f seconds before next request", delay)
                time.sleep(delay)
            count += 1
            LOG.info("[%d/%d] Loading %s", count, MAX_REQUESTS, url)
            driver = service = profile = None
            page_started = time.monotonic()
            try:
                driver, service, profile = launch_browser()
                driver.get(url)
                page = identify_page(driver, team, category)
                LOG.info("Page verified: %s", page["title"])
                wait_for_table(driver, category)
                LOG.info("Expected %s table rows detected", category)
                LOG.info("Capturing page HTML in one Selenium command")
                html = driver.page_source
                LOG.info("Captured %d HTML characters; parsing locally", len(html))
                df, warnings = scrape_category(html, category)
                status = "empty" if df.empty else "saved"
                if not df.empty:
                    destination = folder / f"{category}.csv"
                    df.to_csv(destination, index=False, encoding="utf-8-sig")
                    successful += 1
                    LOG.info("SAVED %d rows -> %s", len(df), destination)
                else:
                    empty += 1
                    LOG.warning("EMPTY: %s; no CSV written", category)
                for warning in warnings:
                    LOG.warning("%s: %s", category, warning)
                metadata["pages"][category] = {
                    "url": url, "title": page["title"], "status": status,
                    "rows": len(df), "columns": list(df.columns),
                    "warnings": warnings, "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
                }
                LOG.info("Completed %s in %.1f seconds", category, time.monotonic() - page_started)
            except Exception as exc:
                failed += 1
                LOG.exception("FAILED %s for %s %s", category, team["name"], team["year"])
                metadata["pages"][category] = {"url": url, "status": "error", "error": str(exc)}
            finally:
                if service is not None:
                    close_browser(driver, service, profile)
                (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if count >= MAX_REQUESTS:
            break
    LOG.info("Finished: %d saved, %d empty, %d failed, %d page requests; elapsed %.1f seconds",
             successful, empty, failed, count, time.monotonic() - started)
    LOG.info("Full status log: %s", OUTPUT_DIR / "scraper_status.log")


if __name__ == "__main__":
    main()
