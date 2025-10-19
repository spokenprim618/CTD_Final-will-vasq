import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

df = pd.read_csv("../csv/cleaned_100_win_seasons.csv")
np.random.seed(10)

st.title("MLB Wins Dashboard")

st.header("Dist of Win Percentage")
fig_dist = px.histogram(df, x="Win %", nbins=10, title="Win % Distribution")
st.plotly_chart(fig_dist)

top_something_slider = st.slider("Top",0,20)
st.header(f"Top {top_something_slider} Wins")
top_df = df.sort_values(by="Wins", ascending=False).head(top_something_slider)
fig_top = px.bar(top_df, x="Team", y="Wins", text="Wins", color="Wins", title=f"Top {top_something_slider} Teams by Wins")
st.plotly_chart(fig_top)

bottom_something_slider = st.slider("Bottom",0,20)
st.header(f"Bottom {bottom_something_slider} Wins")
bottom_df = df.sort_values(by="Wins", ascending=True).head(bottom_something_slider)

fig_bottom = px.bar(bottom_df, x="Team", y="Wins", text="Wins", color="Wins", title=f"Bottom {bottom_something_slider} Teams by Wins")
st.plotly_chart(fig_bottom)

st.header("Grouped Wins by League")

option = st.selectbox("Choose an option", ["All","AL", "NL"])

if option != "All":
    grouped_df = df[df["League"] == option]
else:
    grouped_df=df


fig_grouped = px.scatter(grouped_df, x="Team", y="Wins", color="League",
                        size="Win %", hover_data=["Losses", "Year"],
                        title=f"Wins by Team ({option})")
st.plotly_chart(fig_grouped)