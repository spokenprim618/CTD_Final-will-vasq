# Historical MLB Team Performance Dashboard

A Python and Tableau project analyzing historical Major League Baseball team performance. Data was collected from [Baseball Almanac](https://www.baseball-almanac.com/), cleaned and transformed into CSV files, and visualized in an interactive dashboard.

**[View the Tableau Dashboard](https://public.tableau.com/app/profile/william.william1387/viz/Book2twb_17918572924710/Dashboard1?publish=yes)**

## Teams Analyzed

- **1905 New York Giants**
- **1927 New York Yankees**
- **1986 New York Mets**

## Dashboard Features

A team selector filters the dashboard's performance metrics and charts.

**Key metrics:** Total wins, highest single-game runs, team batting average, runs per game, and run differential.

**Visualizations:** Game outcomes, top five hitters by batting average, monthly runs scored versus runs allowed, and pitching effectiveness.

## Tools

- **Python:** Selenium, Beautiful Soup, and pandas for data collection and preparation
- **Tableau Public:** Interactive dashboard and visualizations
- **CSV:** Data exchange between Python and Tableau

## Data Pipeline

1. Scrape roster, schedule, hitting, and pitching data from Baseball Almanac.
2. Clean and combine records across the three team seasons.
3. Export Tableau-ready datasets: `teams.csv`, `games.csv`, `hitters.csv`, `pitchers.csv`, `roster.csv`, and `monthly_summary.csv`.
4. Relate the datasets in Tableau using `team_season_id` and build the dashboard.

## Setup

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the scraping and transformation scripts in the `pipeline` directory, then connect the resulting CSV files to Tableau.

## Data Source

[Baseball Almanac](https://www.baseball-almanac.com/) — historical MLB team rosters, schedules, batting statistics, and pitching statistics.
