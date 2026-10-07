from __future__ import annotations

import streamlit as st

from core.sailplan import load_sail_data
from views import demand, inventory

st.set_page_config(
    page_title="North Sails — Inventory & Demand",
    page_icon="⛵",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = {
    "🧵 Inventory": inventory.render,
    "📦 Demand": demand.render,
}

with st.sidebar:
    st.markdown("### ⛵ North Sails")
    st.caption("Inventory & Weekly Demand")
    st.divider()

    st.markdown("**Data source**")
    upload = st.file_uploader("Upload the Sail Plan workbook", type=["xlsx", "xls"], label_visibility="collapsed")
    if upload is not None:
        payload = upload.getvalue()
        if st.session_state.get("_upload_name") != upload.name or st.session_state.get("_upload_size") != len(payload):
            try:
                st.session_state["sail_data"] = load_sail_data(payload)
                st.session_state["_upload_name"] = upload.name
                st.session_state["_upload_size"] = len(payload)
            except Exception as exc:
                st.error(f"Couldn't read that file: {exc}")

    data = st.session_state.get("sail_data")
    if data is not None:
        st.success(f"Loaded — {len(data.weeks)} weeks, {len(data.inventory)} tape IDs")

    st.divider()
    st.markdown("**Navigation**")
    page_name = st.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")

PAGES[page_name]()
