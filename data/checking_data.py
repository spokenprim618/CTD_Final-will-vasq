import pandas as pd

df = pd.read_csv('../csv/cleaned_100_win_seasons.csv')

def counted(df, column_name):
    
    unique_values = df[column_name].drop_duplicates().to_list()

    count_dict = {}

    for val in unique_values:
        
        filtered = df[df[column_name] == val]
        count_dict[val] = filtered.shape[0]

    count_df = pd.DataFrame(list(count_dict.items()), columns=[column_name, 'Count']).copy()
    count_df = count_df.sort_values(by='Count', ascending=False).reset_index(drop=True)
    
    return count_df

Category_count_df = counted(df, 'League')
Country_count_df = counted(df, 'Team')
Customer_name_count_df = counted(df, 'Wins')
Market_count_df = counted(df, 'Losses')
Market_nt_df = counted(df, 'Win %')
Year = counted(df, 'Year')

print(Category_count_df)
print(Country_count_df)
print(Market_count_df)
print(Customer_name_count_df)
print(Market_nt_df)
print(Year)
