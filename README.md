# North Sails — Sail Plan Inventory

## Run locally
    pip install -r requirements.txt
    streamlit run app.py

## Deploy to Streamlit Community Cloud
1. Push this folder to a GitHub repo.
2. On share.streamlit.io, point a new app at app.py.
3. No secrets needed — the workbook is uploaded by the user each session.

## Current status
- **Order & Tape Lookup** (working): search by order number (OEN) to see its
  boat type, mold status, and full tape/material breakdown; or search by tape
  ID to see every order using it and the total quantity demanded.
- **Demand forecasting / dates**: on hold. The "Sail Plan (2)" sheet has no
  date field — Mold Status is text (e.g. "Unscheduled", "3Di Review"), not a
  date. The Master sheet has a `Production Order Number` (joinable to OEN)
  and a `Ship Date`, so forecasting can be added once you confirm which date
  field to project against.
- Other nav pages from the original app (Stock Movement, Reorder Alerts,
  Order Evaluator, Order Date Planner, Reorder Optimizer) are not built yet —
  say which ones you need and against which sheet.

## Structure
    app.py               sidebar shell: file upload + page nav
    core/sailplan.py      parses the "Sail Plan (2)" sheet into orders + a
                           long-form order-to-tape consumption table
    views/sail_lookup.py  the Order & Tape Lookup page
