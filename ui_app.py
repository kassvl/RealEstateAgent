"""Streamlit UI to visualize price predictions on a map."""
import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="Wroclaw Price Explorer", layout="wide")

st.title("🏠 Wroclaw Real Estate Price Explorer")

uploaded = st.file_uploader("Upload listings CSV", type=["csv"])
if uploaded:
    df = pd.read_csv(uploaded)
    st.write("Loaded", len(df), "rows")

    st.subheader("Map of Listings")
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[longitude, latitude]",
        get_color="[200, 30, 0, 160]",
        get_radius=100,
        pickable=True,
    )
    view_state = pdk.ViewState(latitude=df.latitude.mean(), longitude=df.longitude.mean(), zoom=11)
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))

    if st.button("Predict Prices via API"):
        preds = []
        for _, row in df.iterrows():
            payload = {
                "area_sqm": row.area_sqm,
                "rooms": int(row.rooms or 0),
                "latitude": row.latitude,
                "longitude": row.longitude,
                "year_built": int(row.year_built or 2000),
            }
            r = requests.post("http://api:9000/predict", json=payload, timeout=5)
            preds.append(r.json()["predicted_price"])
        df["predicted_price"] = preds
        st.write(df.head())
