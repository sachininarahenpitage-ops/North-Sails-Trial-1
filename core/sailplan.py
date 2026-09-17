"""Loading and shaping the 'Sail Plan (2)' sheet.

Layout in the source file (fixed positions, verified against the workbook):
  - Header row is row 1 (pandas header=0).
  - Real order rows start further down; junk header/label rows above them are
    dropped because they have no OEN.
  - Column A / position 0  : OEN            (order number, e.g. SBLK5908-001)
  - Column AJ / position 35: OE             (duplicate of OEN - used to align
                                              the tape-matrix block)
  - Columns AK..DH / positions 36..111      : one column per Tape ID, value =
                                              quantity of that tape consumed
                                              by the order in that row.
  - Column I(second) / position 8 ("Tyre.1"): cloth/material type, e.g.
                                              "3Di RAW 360"
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
import streamlit as st

SHEET_NAME = "Sail Plan (2)"
TAPE_COL_START, TAPE_COL_END = 36, 111  # inclusive, 0-indexed positions

ORDER_COLUMNS = {
    0: "oen",
    6: "boat_type",
    7: "market_segment",
    8: "cloth_type",
    9: "dpi",
    10: "luff",
    11: "mold_status",
    13: "tape_summary",
    14: "total_length",
}


@dataclass
class SailPlan:
    orders: pd.DataFrame       # one row per order, order-level fields only
    consumption: pd.DataFrame  # long form: oen, tape_id, quantity (>0 only)
    tape_colors: pd.DataFrame  # tape_id -> color, from the COLOR sheet

    @property
    def order_numbers(self) -> list[str]:
        return sorted(self.orders["oen"].dropna().unique().tolist())

    @property
    def tape_ids(self) -> list[str]:
        return sorted(self.consumption["tape_id"].dropna().unique().tolist())

    def order_lookup(self, oen: str) -> pd.DataFrame:
        return self.orders[self.orders["oen"].str.casefold() == oen.strip().casefold()]

    def tape_lookup(self, tape_id: str) -> pd.DataFrame:
        matches = self.consumption[self.consumption["tape_id"].astype(str).str.casefold() == str(tape_id).strip().casefold()]
        return matches.merge(self.orders, on="oen", how="left")


@st.cache_data(show_spinner=False)
def load_sail_plan(payload: bytes) -> SailPlan:
    raw = pd.read_excel(io.BytesIO(payload), sheet_name=SHEET_NAME, header=0)

    # --- order-level fields ---------------------------------------------
    positions = list(ORDER_COLUMNS.keys())
    orders = raw.iloc[:, positions].copy()
    orders.columns = list(ORDER_COLUMNS.values())
    orders["oen"] = orders["oen"].astype(str).str.strip()
    orders = orders[orders["oen"].str.match(r"^[A-Za-z0-9]+-\d{3}$", na=False)]
    orders["dpi"] = pd.to_numeric(orders["dpi"], errors="coerce")
    orders["luff"] = pd.to_numeric(orders["luff"], errors="coerce")
    orders["total_length"] = pd.to_numeric(orders["total_length"], errors="coerce")
    orders = orders.drop_duplicates(subset="oen").reset_index(drop=True)

    # --- tape consumption matrix, melted to long form ---------------------
    tape_block = raw.iloc[:, TAPE_COL_START:TAPE_COL_END + 1].copy()
    tape_block.columns = [str(c) for c in tape_block.columns]
    tape_block.insert(0, "oen", raw.iloc[:, 0].astype(str).str.strip())
    tape_block = tape_block[tape_block["oen"].isin(orders["oen"])]

    long = tape_block.melt(id_vars="oen", var_name="tape_id", value_name="quantity")
    long["quantity"] = pd.to_numeric(long["quantity"], errors="coerce")
    long = long.dropna(subset=["quantity"])
    long = long[long["quantity"] > 0].reset_index(drop=True)

    # --- tape -> color reference, if the sheet is present ------------------
    try:
        colors = pd.read_excel(io.BytesIO(payload), sheet_name="COLOR", header=0)
        colors.columns = ["tape_id", "color"]
        colors["tape_id"] = colors["tape_id"].astype(str).str.strip()
    except Exception:
        colors = pd.DataFrame(columns=["tape_id", "color"])

    return SailPlan(orders=orders, consumption=long, tape_colors=colors)


def current_plan() -> SailPlan | None:
    return st.session_state.get("sail_plan")


def require_plan() -> SailPlan:
    plan = current_plan()
    if plan is None:
        st.info("Upload the Sail Plan workbook in the sidebar to get started.")
        st.stop()
    return plan
