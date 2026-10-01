from __future__ import annotations

import streamlit as st

from core.sailplan import load_sail_plan
from views import sail_lookup

st.set_page_config(
    page_title="North Sails — Sail Plan Inventory",
    page_icon="⛵",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = {
    "🔍 Order & Tape Lookup": sail_lookup.render,
}

with st.sidebar:
    st.markdown("### ⛵ North Sails")
    st.caption("Sail Plan Inventory")
    st.divider()

    st.markdown("**Data source**")
    upload = st.file_uploader("Upload the Sail Plan workbook", type=["xlsx", "xls"], label_visibility="collapsed")
    if upload is not None:
        payload = upload.getvalue()
        if st.session_state.get("_upload_name") != upload.name or st.session_state.get("_upload_size") != len(payload):
            try:
                st.session_state["sail_plan"] = load_sail_plan(payload)
                st.session_state["_upload_name"] = upload.name
                st.session_state["_upload_size"] = len(payload)
            except Exception as exc:
                st.error(f"Couldn't read that file: {exc}")

    plan = st.session_state.get("sail_plan")
    if plan is not None:
        st.success(f"Loaded — {len(plan.orders)} orders, {len(plan.tape_ids)} tape IDs")

    st.divider()
    st.markdown("**Navigation**")
    page_name = st.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")

    st.divider()
    st.caption("More pages (reorder alerts, order planner) are on hold pending confirmation of remaining lead-time stages and tape stock data.")

PAGES[page_name]()
