from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import subprocess
import time

chrome_path = r"C:\Users\willv\Downloads\chrome-win64\chrome-win64\chrome.exe"
driver_path = r"C:\Users\willv\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"

pages = ["roster", "schedule", "hitting", "pitching"]


def close_driver(driver, pid):
    """Close Selenium and clean up its ChromeDriver process tree."""

    if driver is not None:
        try:
            driver.quit()
            print("Selenium session closed.")
        except Exception as e:
            print(f"Graceful shutdown failed: {e}")

    if pid is not None:
        # Windows: terminate only this ChromeDriver process tree.
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    print("Browser cleanup completed.")


for page in pages:
    driver = None
    driver_pid = None

    try:
        options = Options()
        options.binary_location = chrome_path
        options.page_load_strategy = "eager"

        service = Service(executable_path=driver_path)

        print(f"\nStarting fresh Chrome for {page}...", flush=True)

        driver = webdriver.Chrome(
            service=service,
            options=options,
        )

        driver_pid = service.process.pid
        driver.set_page_load_timeout(30)

        url = (
            f"https://www.baseball-almanac.com/teamstats/"
            f"{page}.php?t=NYA&y=1927"
        )

        driver.get(url)

        print("Title:", driver.title)
        print(f"SUCCESS: {page}")

    except Exception as e:
        print(f"FAILED: {page}: {e}")

    finally:
        close_driver(driver, driver_pid)

    # Wait before starting the next browser.
    time.sleep(10)

print("\nAll tests completed.")