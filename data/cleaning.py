import pandas as pd

df = pd.read_csv("../csv/100_win_seasons.csv")
def replace_record(df):
    count = 0
    for i in range(len(df)):
        if not pd.isna(df.loc[i, 'Record #']):
            count = df.loc[i, 'Record #']
        else:
            count += 1                     
            df.loc[i, 'Record #'] = count  
    df["Record #"] = df['Record #'].astype(int)
    return df

df['Team'] = df['Team'].apply(lambda s: s[5:])

cleaned_df = replace_record(df)
print(cleaned_df.info())

cleaned_df.to_csv("../csv/cleaned_100_win_seasons.csv")