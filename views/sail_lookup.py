from __future__ import annotations

import pandas as pd
import streamlit as st

from core.sailplan import require_plan

TAPE_ID_COLUMNS = {
    "tape_id": "Tape ID",
    "color": "Color",
    "quantity": "Quantity",
    "oen": "Order (OEN)",
    "boat_type": "Boat Type",
    "cloth_type": "Cloth Type",
    "mold_status": "Mold Status",
}


def render() -> None:
    st.title("🔍 Order & Tape Lookup")
    st.caption("Search by order number (OEN) to see its material breakdown, or by tape ID to see every order that uses it.")
    st.divider()

    plan = require_plan()

    mode = st.radio("Search by", ["Order number (OEN)", "Tape ID"], horizontal=True)

    if mode == "Order number (OEN)":
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Enter order number", placeholder="e.g. OIT108790-001")
        with col2:
            st.write("")
            st.write("")
            options = plan.order_numbers
            picked = st.selectbox("or pick one", options, index=None, placeholder="browse orders", label_visibility="collapsed")
        oen = (query or picked or "").strip()

        if not oen:
            st.info(f"{len(plan.orders)} orders loaded. Type an order number or pick one to browse.")
            return

        match = plan.order_lookup(oen)
        if match.empty:
            st.warning(f"No order found matching '{oen}'.")
            return

        row = match.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Boat Type", row["boat_type"] or "—")
        c2.metric("Cloth Type", row["cloth_type"] or "—")
        c3.metric("Mold Status", row["mold_status"] or "—")
        c4.metric("Total Length", f"{row['total_length']:,.0f}" if pd.notna(row["total_length"]) else "—")

        st.markdown("##### Material (tape) breakdown")
        materials = plan.consumption[plan.consumption["oen"] == row["oen"]].copy()
        if plan.tape_colors is not None and not plan.tape_colors.empty:
            materials = materials.merge(plan.tape_colors, on="tape_id", how="left")
        materials = materials.sort_values("quantity", ascending=False)

        if materials.empty:
            st.caption("No tape consumption recorded for this order.")
        else:
            display = materials.rename(columns={"tape_id": "Tape ID", "quantity": "Quantity", "color": "Color"})
            cols = [c for c in ["Tape ID", "Color", "Quantity"] if c in display.columns]
            st.dataframe(display[cols], hide_index=True, use_container_width=True)
            st.caption(f"Summary from sheet: {row['tape_summary'] or '—'}")

    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Enter tape ID", placeholder="e.g. 930515")
        with col2:
            st.write("")
            st.write("")
            options = plan.tape_ids
            picked = st.selectbox("or pick one", options, index=None, placeholder="browse tape IDs", label_visibility="collapsed")
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

        c1, c2, c3 = st.columns(3)
        c1.metric("Orders using this tape", len(matches))
        c2.metric("Total quantity demanded", f"{matches['quantity'].sum():,.0f}")
        c3.metric("Color", color or "—")

        st.markdown("##### Orders")
        display = matches.rename(columns={
            "oen": "Order (OEN)", "boat_type": "Boat Type", "cloth_type": "Cloth Type",
            "mold_status": "Mold Status", "quantity": "Quantity",
        })
        cols = [c for c in ["Order (OEN)", "Boat Type", "Cloth Type", "Mold Status", "Quantity"] if c in display.columns]
        st.dataframe(display[cols].sort_values("Quantity", ascending=False), hide_index=True, use_container_width=True)
