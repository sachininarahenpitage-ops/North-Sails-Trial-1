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
    st.caption("Inventory & Weekly Demand · v3 (weeks from Sail List)")
    st.divider()

    st.markdown("**Data source**")
    upload = st.file_uploader("Upload the Sail Plan workbook", type=["xlsx", "xls"], label_visibility="collapsed")

    # Re-run the (cached) loader on every run instead of trusting data saved in
    # the session, so a code update can never leave stale results on screen.
    if upload is not None:
        try:
            st.session_state["sail_data"] = load_sail_data(upload.getvalue())
        except Exception as exc:
            st.session_state.pop("sail_data", None)
            st.error(f"Couldn't read that file: {exc}")
    else:
        st.session_state.pop("sail_data", None)

    data = st.session_state.get("sail_data")
    if data is not None:
        st.success(f"Loaded — {len(data.weeks)} week(s), {len(data.inventory)} tape IDs")

    st.divider()
    st.markdown("**Navigation**")
    page_name = st.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")

PAGES[page_name]()
