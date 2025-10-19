import sqlalchemy as sa
import sqlite3
import os
import pandas as pd

engine = sa.create_engine('sqlite:///../db/100-win-season.db')
data = pd.read_csv("../csv/cleaned_100_win_seasons.csv", sep=',')
data.to_sql("100_wins", engine, if_exists='append', index=False)
