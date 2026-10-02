from __future__ import annotations

import pandas as pd
import streamlit as st

from core.sailplan import curing_days_for, require_plan

METRIC_CSS = """
<style>
div[data-testid="stMetricValue"] {
    font-size: 1.15rem;
    line-height: 1.3;
    white-space: normal;
    overflow-wrap: break-word;
}
div[data-testid="stMetricLabel"] {
    font-size: 0.8rem;
}
</style>
"""


def render() -> None:
    st.markdown(METRIC_CSS, unsafe_allow_html=True)

    st.title("🔍 Order & Tape Lookup")
    st.caption("Search by order number (OEN) to see its full breakdown, or by tape ID to see every order that uses it.")
    st.divider()

    plan = require_plan()

    mode = st.radio("Search by", ["Order number (OEN)", "Tape ID"], horizontal=True)

    if mode == "Order number (OEN)":
        _order_mode(plan)
    else:
        _tape_mode(plan)


def _order_mode(plan) -> None:
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Enter order number", placeholder="e.g. SBLK5898-010")
    with col2:
        st.write("")
        st.write("")
        picked = st.selectbox("or pick one", plan.order_numbers, index=None, placeholder="browse orders", label_visibility="collapsed")
    oen = (query or picked or "").strip()

    if not oen:
        st.info(f"{len(plan.orders)} orders loaded. Type an order number or pick one to browse.")
        return

    match = plan.order_lookup(oen)
    if match.empty:
        st.warning(f"No order found matching '{oen}'.")
        return

    row = match.iloc[0]

    # --- General Information -----------------------------------------------
    st.subheader("General Information")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Boat Type", row["boat_type"] or "—")
    c2.metric("Market Segment", row["market_segment"] or "—")
    c3.metric("Tyre", row["cloth_type"] or "—")
    c4.metric("DPI", f"{row['dpi']:,.0f}" if pd.notna(row["dpi"]) else "—")
    c5.metric("Luff", f"{row['luff']:,.2f}" if pd.notna(row["luff"]) else "—")

    st.divider()

    # --- Sail Structure -------------------------------------------------
    st.subheader("Sail Structure")
    materials = plan.consumption[plan.consumption["oen"] == row["oen"]].copy()
    if plan.tape_colors is not None and not plan.tape_colors.empty:
        materials = materials.merge(plan.tape_colors, on="tape_id", how="left")
    if plan.has_stock_data:
        materials = materials.merge(plan.tape_stock, on="tape_id", how="left")
    materials = materials.sort_values(["type", "quantity"], ascending=[True, False])

    if materials.empty:
        st.caption("No tape consumption recorded for this order.")
    else:
        type_counts = materials["type"].value_counts()
        badge_cols = st.columns(len(type_counts))
        for col, (t, n) in zip(badge_cols, type_counts.items()):
            col.caption(f"**{t}**: {n} tape(s)")

        rename = {"tape_id": "Tape ID", "type": "Type", "quantity": "Tape Length", "color": "Color", "on_hand": "Stock On Hand"}
        display = materials.rename(columns=rename)
        cols = [c for c in ["Tape ID", "Type", "Color", "Tape Length", "Stock On Hand"] if c in display.columns]
        st.dataframe(display[cols], hide_index=True, use_container_width=True)
        if not plan.has_stock_data:
            st.caption("Stock levels aren't loaded yet — 'Tape stock' sheet is currently empty.")
        if (materials["type"] == "Unclassified — confirm type").any():
            st.caption("⚠️ Some tape IDs couldn't be classified with full confidence — flagged above for confirmation.")

    st.divider()

    # --- Lead Time -----------------------------------------------------
    st.subheader("Lead Time")
    internal_days = curing_days_for(row["internal"])
    external_days = curing_days_for(row["external"])

    lc1, lc2, lc3 = st.columns(3)
    lc1.metric("Internal Resin", row["internal"] or "—", f"{internal_days} curing days" if internal_days else "unmapped resin")
    lc2.metric("External Resin", row["external"] or "—", f"{external_days} curing days" if external_days else "unmapped resin")
    curing_total = max([d for d in (internal_days, external_days) if d is not None], default=None)
    lc3.metric("Curing Days (mold)", curing_total if curing_total is not None else "—")

    st.caption("Process: Mold → Curing → Transfer → Finishing → Shipping. Only curing days are mapped so far (Adcote = 8, Morchem = 12); Transfer, Finishing, and Shipping day-counts are pending from your supervisor.")

    if curing_total is not None:
        mold_date = st.date_input("Mold start date (optional, to estimate when curing finishes)", value=None)
        if mold_date:
            finish = mold_date + pd.Timedelta(days=curing_total)
            st.success(f"Estimated curing complete: **{finish.strftime('%d %b %Y')}** ({curing_total} days from mold start). Transfer/finishing/shipping time still needs adding once those day-counts are confirmed.")


def _tape_mode(plan) -> None:
    from core.sailplan import classify_tape

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Enter tape ID", placeholder="e.g. 930515")
    with col2:
        st.write("")
        st.write("")
        picked = st.selectbox("or pick one", plan.tape_ids, index=None, placeholder="browse tape IDs", label_visibility="collapsed")
    tape_id = (query or picked or "").strip()

    if not tape_id:
        st.info(f"{len(plan.tape_ids)} tape IDs in use across {len(plan.consumption)} order-material records.")
        return

    matches = plan.tape_lookup(tape_id)
    if matches.empty:
        st.warning(f"No orders found using tape ID '{tape_id}'.")
        return

    color = None
    if plan.tape_colors is not None and not plan.tape_colors.empty:
        hit = plan.tape_colors[plan.tape_colors["tape_id"] == tape_id]
        color = hit.iloc[0]["color"] if not hit.empty else None

    tape_type = classify_tape(tape_id)
    total_demand = matches["quantity"].sum()
    stock = plan.stock_for(tape_id)

    st.caption(f"Type: **{tape_type}**")
    if stock is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Orders using this tape", len(matches))
        c2.metric("Total length demanded", f"{total_demand:,.0f}")
        c3.metric("Stock On Hand", f"{stock:,.0f}")
        balance = stock - total_demand
        c4.metric("Balance", f"{balance:,.0f}")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Orders using this tape", len(matches))
        c2.metric("Total length demanded", f"{total_demand:,.0f}")
        c3.metric("Color", color or "—")

    st.markdown("##### Orders")
    display = matches.rename(columns={
        "oen": "Order (OEN)", "boat_type": "Boat Type", "cloth_type": "Tyre",
        "lead_time_days": "Lead Time (days)", "quantity": "Tape Length",
    })
    cols = [c for c in ["Order (OEN)", "Boat Type", "Tyre", "Lead Time (days)", "Tape Length"] if c in display.columns]
    st.dataframe(display[cols].sort_values("Tape Length", ascending=False), hide_index=True, use_container_width=True)

    if stock is None:
        st.caption("Stock levels aren't loaded yet — 'Tape stock' sheet is currently empty.")
