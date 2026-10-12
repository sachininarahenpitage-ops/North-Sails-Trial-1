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
    st.title("🧵 Tape Inventory")
    st.caption("Current on-hand tape stock, read from the 'Stock (Adcote)' / 'Stock (Morchem)' rows in the Sail List sheet.")
    st.divider()

    data = require_data()
    inv = data.inventory.copy()

    known = inv.dropna(subset=["total_stock"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Tape IDs with stock data", len(known))
    c2.metric("Total stock (Adcote)", f"{inv['stock_adcote'].sum(skipna=True):,.0f}")
    c3.metric("Total stock (Morchem)", f"{inv['stock_morchem'].sum(skipna=True):,.0f}")

    st.divider()

    search = st.text_input("Filter by tape ID", placeholder="e.g. 930515")
    view = inv.copy()
    if search:
        view = view[view["tape_id"].str.contains(search.strip(), case=False, na=False)]

    view = view.sort_values("total_stock", ascending=False, na_position="last")
    display = view.rename(columns={
        "tape_id": "Tape ID", "type": "Type", "stock_adcote": "Stock (Adcote)",
        "stock_morchem": "Stock (Morchem)", "total_stock": "Total Stock",
    })
    st.dataframe(display, hide_index=True, use_container_width=True)

    if inv["total_stock"].isna().all():
        st.caption("No stock rows found — the workbook's Sail List sheet may not have the 'Stock (Adcote)'/'Stock (Morchem)' rows yet.")

    st.divider()
    st.subheader("Order Resin Summary")
    st.caption("Each column is one sail order: Sail ID on the first row, Resin Type on the second.")

    order_search = st.text_input("Filter by Sail ID", placeholder="e.g. SBLK5898-010", key="order_resin_filter")
    oens = None
    if order_search:
        oens = [o for o in data.orders["oen"] if order_search.strip().casefold() in o.casefold()]

    resin_table = data.order_resin_table(oens)
    if resin_table.empty or resin_table.shape[1] == 0:
        st.caption("No matching orders.")
    else:
        st.dataframe(resin_table, use_container_width=True)
