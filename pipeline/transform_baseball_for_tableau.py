"""Transform Baseball Almanac scraper CSVs into Tableau-ready datasets.

Run from the pipeline folder: python transform_baseball_for_tableau.py
Optional: python transform_baseball_for_tableau.py --input path/to/baseball_data --output path/to/tableau_data
No network calls; original scraper CSVs are not modified.
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
import pandas as pd

LOG = logging.getLogger('baseball_transform')
TEAMS = [
    ('NYA_1927', 'New York Yankees', 'NYA', 1927),
    ('NYN_1986', 'New York Mets', 'NYN', 1986),
    ('NY1_1905', 'New York Giants', 'NY1', 1905),
]
NUMERIC_HITTING = ['G', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'BB', 'IBB', 'SO', 'AVG', 'OBP', 'SLG']
NUMERIC_PITCHING = ['G', 'GS', 'W', 'L', 'PCT', 'ERA', 'SV', 'H', 'ER', 'R', 'HR', 'BB', 'SO']
SCORE_PATTERN = re.compile(r'^\s*(\d+)\s*[-–:]\s*(\d+)\s*$')


def ratio(n, d):
    """Return nullable ratio; zero denominator -> NA."""
    return n.div(d.where(d.ne(0)))


def as_number(df, cols):
    for c in cols:
        if c not in df.columns:
            raise ValueError(f'Missing expected column {c!r}; found {list(df.columns)}')
        df[c] = pd.to_numeric(df[c].replace({'': pd.NA, '-': pd.NA, '—': pd.NA}), errors='coerce')
    return df


def load_csv(folder, filename, required):
    path = folder / filename
    if not path.exists():
        raise FileNotFoundError(f'Missing input file: {path}')
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f'{path}: missing columns {sorted(missing)}')
    return df


def parse_game_score(score, result):
    """Return (team_runs, opponent_runs) for a normal completed W/L/T game.

    Uses outcome to assign higher/lower score; works whether score is winner-first
    or team-first. Does NOT establish scores for forfeits or malformed outcomes.
    """
    m = SCORE_PATTERN.fullmatch(str(score))
    if not m or result not in {'W', 'L', 'T'}:
        return (pd.NA, pd.NA)
    a, b = int(m.group(1)), int(m.group(2))
    if (result == 'T' and a != b) or (result != 'T' and a == b):
        return (pd.NA, pd.NA)
    if result == 'W':
        return max(a, b), min(a, b)
    if result == 'L':
        return min(a, b), max(a, b)
    return a, b


def parse_innings(value):
    """Convert baseball IP notation (7.2 = 7 innings, 2 outs) to true innings."""
    s = str(value).strip()
    if not s or s in {'-', '—', 'nan'}:
        return float('nan')
    m = re.fullmatch(r'(\d+)(?:\.(\d))?', s)
    if not m:
        return float('nan')
    whole = int(m.group(1))
    outs = int(m.group(2) or 0)
    if outs > 2:
        return float('nan')
    return (whole * 3 + outs) / 3


def transform_schedule(df, team_id):
    out = df.rename(columns={'Game': 'game_label', 'Date': 'game_date',
                             'Opponent': 'opponent', 'Score': 'score_raw',
                             'Decision': 'decision_raw', 'Record': 'record_raw'}).copy()
    out.insert(0, 'team_season_id', team_id)
    out['game_date'] = pd.to_datetime(out['game_date'], format='%m-%d-%Y', errors='coerce')
    if out['game_date'].isna().any():
        LOG.warning('%s: %s unparseable dates', team_id, out['game_date'].isna().sum())
    out['result'] = out['decision_raw'].astype(str).str.strip().str.upper().str.extract(r'^([WLT])\b', expand=False)
    unknown = out['result'].isna().sum()
    if unknown:
        LOG.warning('%s: %s unrecognized results; not counted as W/L/T', team_id, unknown)
    runs = [parse_game_score(score, result) for score, result in zip(out['score_raw'], out['result'])]
    out['team_runs'] = pd.array([x[0] for x in runs], dtype='Int64')
    out['opponent_runs'] = pd.array([x[1] for x in runs], dtype='Int64')
    missing_runs = out['team_runs'].isna().sum()
    if missing_runs:
        LOG.warning('%s: %s game scores could not be interpreted; run metrics exclude these', team_id, missing_runs)
    out['run_differential'] = out['team_runs'] - out['opponent_runs']
    out['is_win'] = (out['result'] == 'W').astype('Int64')
    out['is_loss'] = (out['result'] == 'L').astype('Int64')
    out['is_tie'] = (out['result'] == 'T').astype('Int64')
    out['month'] = out['game_date'].dt.to_period('M').astype('string')
    # Preserve original schedule order for same-day doubleheaders.
    out['source_row'] = range(1, len(out) + 1)
    out = out.sort_values(['game_date', 'source_row'], kind='stable').reset_index(drop=True)
    out['game_number'] = range(1, len(out) + 1)
    out['cumulative_wins'] = out['is_win'].cumsum()
    out['cumulative_losses'] = out['is_loss'].cumsum()
    out['cumulative_ties'] = out['is_tie'].cumsum()
    out['cumulative_win_pct'] = ratio(out['cumulative_wins'], out['cumulative_wins'] + out['cumulative_losses'])
    return out


def transform_hitting(df, team_id):
    out = as_number(df.copy(), NUMERIC_HITTING).rename(columns={'Name': 'player'})
    out.insert(0, 'team_season_id', team_id)
    out = out.rename(columns={c: 'bat_' + c.lower() for c in NUMERIC_HITTING})
    out['bat_singles'] = out['bat_h'] - out['bat_2b'] - out['bat_3b'] - out['bat_hr']
    out['bat_total_bases'] = out['bat_singles'] + 2*out['bat_2b'] + 3*out['bat_3b'] + 4*out['bat_hr']
    out['bat_ops'] = out['bat_obp'] + out['bat_slg']
    out['bat_iso'] = out['bat_slg'] - out['bat_avg']
    out['bat_avg_percent'] = out['bat_avg'] * 100
    out['bat_hr_per_game'] = ratio(out['bat_hr'], out['bat_g'])
    out['bat_walk_to_strikeout'] = ratio(out['bat_bb'], out['bat_so'])
    out['bat_qualified_100_ab'] = out['bat_ab'] >= 100  # optional dashboard filter, not official qualification
    return out


def transform_pitching(df, team_id):
    out = as_number(df.copy(), NUMERIC_PITCHING).rename(columns={'Name': 'player'})
    out.insert(0, 'team_season_id', team_id)
    out['pitch_ip_raw'] = out['IP'].astype(str)
    out['pitch_innings'] = out['IP'].map(parse_innings)
    if out['pitch_innings'].isna().any():
        LOG.warning('%s: %s invalid innings-pitched values', team_id, out['pitch_innings'].isna().sum())
    out = out.drop(columns=['IP']).rename(columns={c: 'pitch_' + c.lower() for c in NUMERIC_PITCHING})
    out['pitch_whip'] = ratio(out['pitch_bb'] + out['pitch_h'], out['pitch_innings'])
    out['pitch_k_per_9'] = ratio(out['pitch_so'] * 9, out['pitch_innings'])
    out['pitch_bb_per_9'] = ratio(out['pitch_bb'] * 9, out['pitch_innings'])
    out['pitch_hr_per_9'] = ratio(out['pitch_hr'] * 9, out['pitch_innings'])
    out['pitch_k_bb_ratio'] = ratio(out['pitch_so'], out['pitch_bb'])
    out['pitch_qualified_30_ip'] = out['pitch_innings'] >= 30  # optional filter, not official qualification
    return out


def summary(team_id, team_name, team_code, season, games, hitters, pitchers, roster):
    w = int(games['is_win'].sum())
    l = int(games['is_loss'].sum())
    t = int(games['is_tie'].sum())
    n = len(games)
    known_scores = int(games['team_runs'].notna().sum())
    team_hits = hitters['bat_h'].sum(min_count=1)
    team_abs = hitters['bat_ab'].sum(min_count=1)
    total_runs = games['team_runs'].sum(min_count=1)
    allowed = games['opponent_runs'].sum(min_count=1)
    # Sum ER and IP instead of averaging player ERA; roster may omit relief splits.
    total_ip = pitchers['pitch_innings'].sum(min_count=1)
    total_er = pitchers['pitch_er'].sum(min_count=1)
    return dict(team_season_id=team_id, team_name=team_name, team_code=team_code,
                season=season, games_recorded=n, wins=w, losses=l, ties=t,
                win_pct=w/(w+l) if w+l else None,
                game_win_share=w/n if n else None,
                games_with_parsed_scores=known_scores,
                highest_game_runs=games['team_runs'].max(),
                total_runs_scored=total_runs, total_runs_allowed=allowed,
                runs_per_game=total_runs/known_scores if known_scores else None,
                runs_allowed_per_game=allowed/known_scores if known_scores else None,
                run_differential=total_runs-allowed if known_scores else None,
                team_hits=team_hits, team_at_bats=team_abs,
                team_batting_avg=team_hits/team_abs if pd.notna(team_abs) and team_abs else None,
                team_home_runs=hitters['bat_hr'].sum(min_count=1),
                team_earned_runs_allowed=total_er, team_pitching_innings=total_ip,
                team_era_from_pitcher_totals=(total_er*9/total_ip if pd.notna(total_ip) and total_ip else None),
                roster_players=len(roster), hitters=len(hitters), pitchers=len(pitchers))


def run(input_dir, output_dir):
    if not input_dir.is_dir():
        raise FileNotFoundError(f'Input directory not found: {input_dir}')
    output_dir.mkdir(parents=True, exist_ok=True)
    collected = {name: [] for name in ['teams', 'games', 'hitters', 'pitchers', 'roster']}
    for team_id, name, code, season in TEAMS:
        folder = input_dir / f'{name.replace(" ", "_")}_{season}'
        games = transform_schedule(load_csv(folder, 'schedule.csv', ['Game', 'Date', 'Opponent', 'Score', 'Decision', 'Record']), team_id)
        hitters = transform_hitting(load_csv(folder, 'hitting.csv', ['Name'] + NUMERIC_HITTING), team_id)
        pitchers = transform_pitching(load_csv(folder, 'pitching.csv', ['Name', 'IP'] + NUMERIC_PITCHING), team_id)
        roster = load_csv(folder, 'roster.csv', ['Player', 'Position']).rename(columns={'Player': 'player', 'Position': 'position'})
        roster.insert(0, 'team_season_id', team_id)
        collected['teams'].append(summary(team_id, name, code, season, games, hitters, pitchers, roster))
        for label, frame in [('games', games), ('hitters', hitters), ('pitchers', pitchers), ('roster', roster)]:
            collected[label].append(frame)
        LOG.info('%s: %d games, %d hitters, %d pitchers, %d roster players', team_id, len(games), len(hitters), len(pitchers), len(roster))
    for label, frames in collected.items():
        result = pd.DataFrame(frames) if label == 'teams' else pd.concat(frames, ignore_index=True)
        target = output_dir / f'{label}.csv'
        result.to_csv(target, index=False)
        LOG.info('Wrote %s (%d rows)', target, len(result))
    monthly = (pd.concat(collected['games'], ignore_index=True)
               .groupby(['team_season_id', 'month'], dropna=False)
               .agg(games=('game_number', 'size'), wins=('is_win', 'sum'),
                    losses=('is_loss', 'sum'), ties=('is_tie', 'sum'),
                    runs_scored=('team_runs', 'sum'), runs_allowed=('opponent_runs', 'sum'))
               .reset_index())
    monthly['win_pct'] = ratio(monthly['wins'], monthly['wins'] + monthly['losses'])
    monthly['run_differential'] = monthly['runs_scored'] - monthly['runs_allowed']
    monthly.to_csv(output_dir / 'monthly_summary.csv', index=False)
    LOG.info('Wrote %s (%d rows)', output_dir / 'monthly_summary.csv', len(monthly))
    LOG.info('Finished transformation; source CSVs untouched')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path(__file__).resolve().parent
    parser.add_argument('--input', type=Path, default=base / 'baseball_data')
    parser.add_argument('--output', type=Path, default=base / 'tableau_data')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    run(args.input, args.output)
