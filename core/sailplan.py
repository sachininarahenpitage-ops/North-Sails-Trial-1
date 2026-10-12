"""Loading and shaping the North Sails workbook for the Demand and Inventory tabs.

Everything now comes from the 'Sail List' sheet:

  * Order rows  -> one row per sail order. The 'week' column (added by the
                   supervisor) says which production week the order belongs to.
                   These feed the Demand tab.
  * Stock rows  -> two special rows at the bottom whose OE value is
                   "Stock (Adcote)" / "Stock (Morchem)". They hold current
                   on-hand stock per tape ID, split by resin. These feed the
                   Inventory tab.

Columns are located by header name, not by position, so inserting or moving
columns (like the new 'week' column) doesn't break the loader. Every column
to the right of 'OE' is treated as a tape-ID column.

The old 'Sheet' tab (with its "week 27 ... week 37" marker rows) is no longer
read: those week numbers were found to be incorrect.

Tape ID classification (4th character of the 6-character base code):
  '1' -> Internal Raw      'M' -> Internal Myler
  '6' -> External Raw      '0' -> External Cloth
Anything else is left "Unclassified" rather than guessed - the non-woven vs
taffeta split inside External Cloth isn't confirmed for every code yet.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd
import streamlit as st

SHEET_NAME = "Sail List"
REQUIRED_COLUMNS = ["OE", "week", "Boat Type", "Tyre", "Internal", "External"]

OEN_PATTERN = re.compile(r"^[A-Za-z0-9]+[-_]\d{3}$")

RESIN_CURING_DAYS = {"adcote": 8, "morchem": 12}


def curing_days_for(resin: str | None) -> int | None:
    if not resin:
        return None
    lowered = str(resin).strip().casefold()
    for name, days in RESIN_CURING_DAYS.items():
        if name in lowered:
            return days
    return None


def classify_tape(tape_id: str) -> str:
    code = str(tape_id).strip()[:6]
    if len(code) < 4:
        return "Unclassified — confirm type"
    marker = code[3].upper()
    if marker == "1":
        return "Internal Raw"
    if marker == "M":
        return "Internal Myler"
    if marker == "6":
        return "External Raw"
    if marker == "0":
        return "External Cloth"
    return "Unclassified — confirm type"


@dataclass
class SailData:
    demand: pd.DataFrame     # week, oen, boat_type, tyre, tape_id, type, quantity
    inventory: pd.DataFrame  # tape_id, type, stock_adcote, stock_morchem, total_stock
    orders: pd.DataFrame     # oen, week, internal, external, resin_type — one row per order
    unassigned_orders: int = 0  # orders with no week filled in (excluded from demand)

    @property
    def weeks(self) -> list[int]:
        return sorted(int(w) for w in self.demand["week"].dropna().unique())

    def demand_for_week(self, week: int) -> pd.DataFrame:
        return self.demand[self.demand["week"] == week]

    def weekly_tape_totals(self, week: int) -> pd.DataFrame:
        block = self.demand_for_week(week)
        totals = (
            block.groupby(["tape_id", "type"], as_index=False)
            .agg(total_demand=("quantity", "sum"), orders=("oen", "nunique"))
            .sort_values("total_demand", ascending=False)
        )
        return totals.merge(self.inventory[["tape_id", "total_stock"]], on="tape_id", how="left")

    def order_resin_table(self, oens: list[str] | None = None) -> pd.DataFrame:
        """Transposed view: one column per order, first row Sail ID, second row Resin Type."""
        view = self.orders if not oens else self.orders[self.orders["oen"].isin(oens)]
        return pd.DataFrame(
            [view["oen"].tolist(), view["resin_type"].tolist()],
            index=["Sail ID", "Resin Type"],
            columns=[f"Order {i + 1}" for i in range(len(view))],
        )


def _resin_label(internal, external) -> str:
    if pd.isna(internal) and pd.isna(external):
        return "—"
    if pd.notna(internal) and pd.notna(external) and str(internal).strip().casefold() == str(external).strip().casefold():
        return str(internal).strip()
    parts = [str(v).strip() for v in (internal, external) if pd.notna(v)]
    return " / ".join(parts) if parts else "—"


@st.cache_data(show_spinner=False)
def load_sail_data(payload: bytes) -> SailData:
    raw = pd.read_excel(io.BytesIO(payload), sheet_name=SHEET_NAME, header=0)
    raw.columns = [str(c).strip() for c in raw.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"The '{SHEET_NAME}' sheet is missing column(s): {', '.join(missing)}")

    # Every column to the right of 'OE' is a tape ID.
    oe_pos = list(raw.columns).index("OE")
    tape_cols = list(raw.columns[oe_pos + 1:])

    oe = raw["OE"].astype(str).str.strip()
    is_order = oe.str.match(OEN_PATTERN, na=False)

    # ---------------- Orders ------------------------------------------
    order_rows = raw[is_order].copy()
    order_rows["OE"] = order_rows["OE"].astype(str).str.strip()
    order_rows["week"] = pd.to_numeric(order_rows["week"], errors="coerce")
    order_rows = order_rows.drop_duplicates(subset="OE")

    orders = order_rows[["OE", "week", "Internal", "External"]].rename(
        columns={"OE": "oen", "Internal": "internal", "External": "external"}
    ).reset_index(drop=True)
    orders["resin_type"] = [_resin_label(i, e) for i, e in zip(orders["internal"], orders["external"])]
    unassigned = int(orders["week"].isna().sum())

    # ---------------- Demand (orders with a week, melted by tape) -----
    with_week = order_rows.dropna(subset=["week"])
    long = with_week.melt(
        id_vars=["week", "Boat Type", "Tyre", "OE"],
        value_vars=tape_cols,
        var_name="tape_id",
        value_name="quantity",
    ).rename(columns={"Boat Type": "boat_type", "Tyre": "tyre", "OE": "oen"})
    long["week"] = long["week"].astype(int)
    long["tape_id"] = long["tape_id"].astype(str)
    long["quantity"] = pd.to_numeric(long["quantity"], errors="coerce")
    long = long.dropna(subset=["quantity"])
    long = long[long["quantity"] > 0].reset_index(drop=True)
    long["type"] = long["tape_id"].map(classify_tape)

    # ---------------- Inventory (stock rows) --------------------------
    stock_rows = raw[oe.str.contains("Stock", case=False, na=False)]

    def _stock_series(resin: str) -> pd.Series:
        hit = stock_rows[stock_rows["OE"].astype(str).str.contains(resin, case=False, na=False)]
        if hit.empty:
            return pd.Series(dtype=float)
        series = pd.to_numeric(hit.iloc[0][tape_cols], errors="coerce")
        series.index = series.index.astype(str)
        return series

    adcote, morchem = _stock_series("Adcote"), _stock_series("Morchem")

    all_tape_ids = sorted({str(c) for c in tape_cols} | set(long["tape_id"].unique()))
    inventory = pd.DataFrame({"tape_id": all_tape_ids})
    inventory["stock_adcote"] = inventory["tape_id"].map(adcote) if not adcote.empty else float("nan")
    inventory["stock_morchem"] = inventory["tape_id"].map(morchem) if not morchem.empty else float("nan")
    # min_count=1 keeps NaN when BOTH resin columns are missing, instead of
    # collapsing "no data" into a misleading 0.
    inventory["total_stock"] = inventory[["stock_adcote", "stock_morchem"]].sum(axis=1, min_count=1)
    inventory["type"] = inventory["tape_id"].map(classify_tape)

    return SailData(demand=long, inventory=inventory, orders=orders, unassigned_orders=unassigned)


def current_data() -> SailData | None:
    return st.session_state.get("sail_data")


def require_data() -> SailData:
    data = current_data()
    if data is None:
        st.info("Upload the Sail Plan workbook in the sidebar to get started.")
        st.stop()
    return data
