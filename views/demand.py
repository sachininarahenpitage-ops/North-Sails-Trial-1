from __future__ import annotations

import streamlit as st

from core.sailplan import require_data

METRIC_CSS = """
<style>
div[data-testid="stMetricValue"] { font-size: 1.15rem; line-height: 1.3; white-space: normal; overflow-wrap: break-word; }
div[data-testid="stMetricLabel"] { font-size: 0.8rem; }
</style>
"""


def render() -> None:
    st.markdown(METRIC_CSS, unsafe_allow_html=True)
    st.title("📦 Weekly Demand")
    st.caption("Pick a production week to see total tape demand for that week, aggregated across all orders.")
    st.divider()

    data = require_data()

    if not data.weeks:
        st.warning("No week-tagged orders found in the 'Sheet' tab.")
        return

    week = st.selectbox("Week", data.weeks, format_func=lambda w: f"Week {w}")

    block = data.demand_for_week(week)
    orders_this_week = block["oen"].nunique()

    c1, c2, c3 = st.columns(3)
    c1.metric("Orders this week", orders_this_week)
    c2.metric("Tape IDs demanded", block["tape_id"].nunique())
    c3.metric("Total length demanded", f"{block['quantity'].sum():,.0f}")

    st.divider()
    st.subheader(f"Tape demand — Week {week}")

    totals = data.weekly_tape_totals(week)
    search = st.text_input("Filter by tape ID", placeholder="e.g. 930515")
    if search:
        totals = totals[totals["tape_id"].str.contains(search.strip(), case=False, na=False)]

    display = totals.rename(columns={
        "tape_id": "Tape ID", "type": "Type", "total_demand": "Demand (this week)",
        "orders": "Orders", "total_stock": "Stock On Hand",
    })
    cols = [c for c in ["Tape ID", "Type", "Demand (this week)", "Orders", "Stock On Hand"] if c in display.columns]
    st.dataframe(display[cols], hide_index=True, use_container_width=True)

    if totals["type"].eq("Unclassified — confirm type").any():
        st.caption("⚠️ Some tape IDs couldn't be classified with full confidence.")

    with st.expander("Orders included in this week"):
        order_cols = block[["oen", "boat_type", "tyre"]].drop_duplicates().rename(
            columns={"oen": "Order (OEN)", "boat_type": "Boat Type", "tyre": "Tyre"}
        )
        st.dataframe(order_cols, hide_index=True, use_container_width=True)
