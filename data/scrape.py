from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import pandas as pd

chrome_path = r"C:\Users\willv\Downloads\chrome-win64\chrome-win64\chrome.exe"
driver_path = r"C:\Users\willv\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"

options = Options()
options.binary_location = chrome_path  
options.add_argument("--headless=new")

service = Service(driver_path)

try:
    driver = webdriver.Chrome(service=service, options=options)

    driver.get("https://www.baseball-almanac.com/recbooks/100-win-seasons-major-league-baseball.shtml")

    wait = WebDriverWait(driver, 10)
    table = wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    rows = table.find_elements(By.TAG_NAME, "tr")[1:]  

    data = []
    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) == 7:
                record_num = cells[0].text.strip().replace('.', '')
                league = cells[1].text.strip()
                team = cells[2].text.strip()
                wins = cells[3].text.strip()
                losses = cells[4].text.strip()
                win_pct = cells[5].text.strip()
                year = cells[6].text.strip()

                data.append([record_num, league, team, wins, losses, win_pct, year])
        except Exception as row_err:
            print(f"Error parsing row: {row_err}")

finally:
    driver.quit()

try:
    df = pd.DataFrame(data, columns=["Record #", "League", "Team", "Wins", "Losses", "Win %", "Year"])
    df.to_csv("../csv/100_win_seasons.csv", index=False)
    print("✅ Saved 100_win_seasons.csv")
except Exception as file_err:
    print(f"Error writing CSV: {file_err}")
