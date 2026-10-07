"""Loading and shaping the North Sails workbook for the Demand and Inventory tabs.

Two different sheets feed two different tabs:

  'Sheet'      -> Demand tab. Laid out as repeating blocks, each starting with
                  a marker row ("week 27", "week 28", ...) in the OE column,
                  followed by order rows for that week (mixed in with
                  category-header rows like "OCEAN & ENDURANCE" and some
                  pre-existing manual calculation rows - "requirement CS",
                  "stock", "pregger1..5", "left" - which we deliberately
                  leave untouched and don't try to reinterpret). Only rows
                  whose OE value matches an order-number pattern are treated
                  as real demand.

  'Sail List'  -> Inventory tab. Same tape-ID columns, but two special rows
                  at the bottom (OE = "Stock (Adcote)" / "Stock (Morchem)")
                  hold current on-hand stock per tape ID, split by resin.

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

DEMAND_SHEET = "Sheet"
STOCK_SHEET = "Sail List"

WEEK_PATTERN = re.compile(r"^week\s*(\d+)", re.IGNORECASE)
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
    orders: pd.DataFrame     # oen, internal, external, resin_type — one row per order

    @property
    def weeks(self) -> list[int]:
        return sorted(self.demand["week"].dropna().unique().tolist())

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
        table = pd.DataFrame(
            [view["oen"].tolist(), view["resin_type"].tolist()],
            index=["Sail ID", "Resin Type"],
            columns=[f"Order {i+1}" for i in range(len(view))],
        )
        return table


@st.cache_data(show_spinner=False)
def load_sail_data(payload: bytes) -> SailData:
    # ---------------- Demand (from 'Sheet') ----------------------------
    raw = pd.read_excel(io.BytesIO(payload), sheet_name=DEMAND_SHEET, header=0)
    oe_col = raw["OE"].astype(str)

    week_marker_idx = raw.index[oe_col.str.match(WEEK_PATTERN, na=False)].tolist()
    week_numbers = [int(WEEK_PATTERN.match(oe_col[i]).group(1)) for i in week_marker_idx]

    tape_cols = list(raw.columns[7:])  # Boat Type..OE occupy positions 0-6

    frames = []
    for pos, start in enumerate(week_marker_idx):
        end = week_marker_idx[pos + 1] if pos + 1 < len(week_marker_idx) else len(raw)
        block = raw.iloc[start + 1:end].copy()
        block = block[block["OE"].astype(str).str.match(OEN_PATTERN, na=False)]
        if block.empty:
            continue
        block["week"] = week_numbers[pos]
        keep = ["week", "Boat Type", "Tyre", "OE"] + tape_cols
        frames.append(block[keep])

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=["week", "Boat Type", "Tyre", "OE"] + tape_cols)

    combined = combined.rename(columns={"Boat Type": "boat_type", "Tyre": "tyre", "OE": "oen"})
    long = combined.melt(
        id_vars=["week", "boat_type", "tyre", "oen"],
        value_vars=[str(c) for c in tape_cols] if False else tape_cols,
        var_name="tape_id", value_name="quantity",
    )
    long["tape_id"] = long["tape_id"].astype(str)
    long["quantity"] = pd.to_numeric(long["quantity"], errors="coerce")
    long = long.dropna(subset=["quantity"])
    long = long[long["quantity"] > 0].reset_index(drop=True)
    long["type"] = long["tape_id"].map(classify_tape)

    # ---------------- Inventory (from 'Sail List' stock rows) -----------
    sail_list = pd.read_excel(io.BytesIO(payload), sheet_name=STOCK_SHEET, header=0)
    stock_tape_cols = list(sail_list.columns[9:])
    stock_rows = sail_list[sail_list["OE"].astype(str).str.contains("Stock", case=False, na=False)]

    adcote = pd.Series(dtype=float)
    morchem = pd.Series(dtype=float)
    hit = stock_rows[stock_rows["OE"].astype(str).str.contains("Adcote", case=False, na=False)]
    if not hit.empty:
        adcote = pd.to_numeric(hit.iloc[0][stock_tape_cols], errors="coerce")
    hit = stock_rows[stock_rows["OE"].astype(str).str.contains("Morchem", case=False, na=False)]
    if not hit.empty:
        morchem = pd.to_numeric(hit.iloc[0][stock_tape_cols], errors="coerce")

    all_tape_ids = sorted({str(c) for c in stock_tape_cols} | set(long["tape_id"].unique()))
    inventory = pd.DataFrame({"tape_id": all_tape_ids})
    inventory["stock_adcote"] = inventory["tape_id"].map(lambda t: adcote.get(t) if not adcote.empty else None)
    inventory["stock_morchem"] = inventory["tape_id"].map(lambda t: morchem.get(t) if not morchem.empty else None)
    # min_count=1 keeps NaN when BOTH resin columns are missing, instead of
    # collapsing "no data" into a misleading 0.
    inventory["total_stock"] = inventory[["stock_adcote", "stock_morchem"]].sum(axis=1, min_count=1)
    inventory["type"] = inventory["tape_id"].map(classify_tape)

    # ---------------- Orders (oen -> resin type, from 'Sail List') ------
    order_rows = sail_list[sail_list["OE"].astype(str).str.match(OEN_PATTERN, na=False)].copy()
    orders = order_rows[["OE", "Internal", "External"]].rename(
        columns={"OE": "oen", "Internal": "internal", "External": "external"}
    )
    orders["oen"] = orders["oen"].astype(str).str.strip()
    orders = orders.drop_duplicates(subset="oen").reset_index(drop=True)

    def _resin_label(row: pd.Series) -> str:
        internal, external = row["internal"], row["external"]
        if pd.isna(internal) and pd.isna(external):
            return "—"
        if pd.notna(internal) and pd.notna(external) and str(internal).strip().casefold() == str(external).strip().casefold():
            return str(internal).strip()
        parts = [str(v).strip() for v in (internal, external) if pd.notna(v)]
        return " / ".join(parts) if parts else "—"

    orders["resin_type"] = orders.apply(_resin_label, axis=1)

    return SailData(demand=long, inventory=inventory, orders=orders)


def current_data() -> SailData | None:
    return st.session_state.get("sail_data")


def require_data() -> SailData:
    data = current_data()
    if data is None:
        st.info("Upload the Sail Plan workbook in the sidebar to get started.")
        st.stop()
    return data
