"""Loading and shaping the 'Sail List' sheet (trimmed automation workbook).

Fixed column layout, verified against the workbook:
  - Header row is row 1 (pandas header=0).
  - Positions 0..8   : order-level fields (Boat Type, Market Segment, Tyre,
                        DPI, Luff, Internal, External, Lead time, OE)
  - Positions 9..84  : one column per Tape ID, value = quantity (length) of
                        that tape consumed by the order in that row.

An optional 'Tape stock' sheet, if populated, supplies on-hand quantity per
tape ID. It ships empty in this workbook; the loader tolerates that and the
app simply omits stock figures until it's filled in.

Tape ID classification (per the supervisor's rule, 4th character of the
6-character base code):
  '1' -> Internal Raw      'M' -> Internal Myler
  '6' -> External Raw      '0' -> External Cloth
Anything else is left "Unclassified" rather than guessed, since the
non-woven/taffeta split inside External Cloth isn't fully confirmed yet for
every code (e.g. the 930505/930515/930535 family).

Curing days are resin-dependent: Adcote = 8 days, Morchem = 12 days, read
from the sheet's Internal / External columns.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd
import streamlit as st

SHEET_NAME = "Sail List"
STOCK_SHEET_NAME = "Tape stock"
TAPE_COL_START, TAPE_COL_END = 9, 84  # inclusive, 0-indexed positions

ORDER_COLUMNS = {
    8: "oen",
    0: "boat_type",
    1: "market_segment",
    2: "cloth_type",
    3: "dpi",
    4: "luff",
    5: "internal",
    6: "external",
    7: "lead_time_days",
}

OEN_PATTERN = re.compile(r"^[A-Za-z0-9]+-\d{3}$")

# Curing days by resin, as given by the supervisor.
RESIN_CURING_DAYS = {"adcote": 8, "morchem": 12}


def curing_days_for(resin: str | None) -> int | None:
    """Look up curing days for a resin name (case-insensitive substring match)."""
    if not resin:
        return None
    lowered = str(resin).strip().casefold()
    for name, days in RESIN_CURING_DAYS.items():
        if name in lowered:
            return days
    return None


def classify_tape(tape_id: str) -> str:
    """Classify a tape ID using the 4th-character rule.

    1 -> Internal Raw, M -> Internal Myler, 6 -> External Raw,
    0 -> External Cloth (non-woven/taffeta split not yet confirmed for all codes).
    Anything else is flagged for manual confirmation rather than guessed.
    """
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
class SailPlan:
    orders: pd.DataFrame        # one row per order, order-level fields only
    consumption: pd.DataFrame   # long form: oen, tape_id, quantity (>0 only), type
    tape_colors: pd.DataFrame   # tape_id -> color, from the COLOR sheet (if present)
    tape_stock: pd.DataFrame    # tape_id -> on_hand, from 'Tape stock' (if populated)

    @property
    def order_numbers(self) -> list[str]:
        return sorted(self.orders["oen"].dropna().unique().tolist())

    @property
    def tape_ids(self) -> list[str]:
        return sorted(self.consumption["tape_id"].dropna().unique().tolist())

    @property
    def has_stock_data(self) -> bool:
        return self.tape_stock is not None and not self.tape_stock.empty

    def order_lookup(self, oen: str) -> pd.DataFrame:
        return self.orders[self.orders["oen"].str.casefold() == oen.strip().casefold()]

    def tape_lookup(self, tape_id: str) -> pd.DataFrame:
        matches = self.consumption[self.consumption["tape_id"].astype(str).str.casefold() == str(tape_id).strip().casefold()]
        return matches.merge(self.orders, on="oen", how="left")

    def stock_for(self, tape_id: str) -> float | None:
        if not self.has_stock_data:
            return None
        hit = self.tape_stock[self.tape_stock["tape_id"].astype(str).str.casefold() == str(tape_id).strip().casefold()]
        return float(hit.iloc[0]["on_hand"]) if not hit.empty else None


@st.cache_data(show_spinner=False)
def load_sail_plan(payload: bytes) -> SailPlan:
    raw = pd.read_excel(io.BytesIO(payload), sheet_name=SHEET_NAME, header=0)

    # --- order-level fields ---------------------------------------------
    positions = list(ORDER_COLUMNS.keys())
    orders = raw.iloc[:, positions].copy()
    orders.columns = list(ORDER_COLUMNS.values())
    orders["oen"] = orders["oen"].astype(str).str.strip()
    orders = orders[orders["oen"].str.match(OEN_PATTERN, na=False)]
    for numeric in ("dpi", "luff", "lead_time_days"):
        orders[numeric] = pd.to_numeric(orders[numeric], errors="coerce")
    orders = orders.drop_duplicates(subset="oen").reset_index(drop=True)

    # --- tape consumption matrix, melted to long form ---------------------
    tape_block = raw.iloc[:, TAPE_COL_START:TAPE_COL_END + 1].copy()
    tape_block.columns = [str(c) for c in tape_block.columns]
    tape_block.insert(0, "oen", raw.iloc[:, 8].astype(str).str.strip())
    tape_block = tape_block[tape_block["oen"].isin(orders["oen"])]

    long = tape_block.melt(id_vars="oen", var_name="tape_id", value_name="quantity")
    long["quantity"] = pd.to_numeric(long["quantity"], errors="coerce")
    long = long.dropna(subset=["quantity"])
    long = long[long["quantity"] > 0].reset_index(drop=True)
    long["type"] = long["tape_id"].map(classify_tape)

    # --- tape -> color reference, if the sheet is present ------------------
    try:
        colors = pd.read_excel(io.BytesIO(payload), sheet_name="COLOR", header=0)
        colors.columns = ["tape_id", "color"]
        colors["tape_id"] = colors["tape_id"].astype(str).str.strip()
    except Exception:
        colors = pd.DataFrame(columns=["tape_id", "color"])

    # --- tape stock, if the sheet has been populated ------------------------
    stock = pd.DataFrame(columns=["tape_id", "on_hand"])
    try:
        raw_stock = pd.read_excel(io.BytesIO(payload), sheet_name=STOCK_SHEET_NAME, header=0)
        raw_stock = raw_stock.dropna(how="all")
        if not raw_stock.empty and raw_stock.shape[1] >= 2:
            cols_lower = [str(c).strip().casefold() for c in raw_stock.columns]
            id_col = next((c for c, low in zip(raw_stock.columns, cols_lower) if "tape" in low or "id" in low), raw_stock.columns[0])
            qty_col = next((c for c, low in zip(raw_stock.columns, cols_lower) if "stock" in low or "qty" in low or "quantity" in low or "on hand" in low), raw_stock.columns[1])
            stock = raw_stock[[id_col, qty_col]].copy()
            stock.columns = ["tape_id", "on_hand"]
            stock["tape_id"] = stock["tape_id"].astype(str).str.strip()
            stock["on_hand"] = pd.to_numeric(stock["on_hand"], errors="coerce")
            stock = stock.dropna(subset=["tape_id", "on_hand"])
    except Exception:
        pass

    return SailPlan(orders=orders, consumption=long, tape_colors=colors, tape_stock=stock)


def current_plan() -> SailPlan | None:
    return st.session_state.get("sail_plan")


def require_plan() -> SailPlan:
    plan = current_plan()
    if plan is None:
        st.info("Upload the Sail Plan workbook in the sidebar to get started.")
        st.stop()
    return plan
