# Campaign Switch — Analytics (Python + SQL)

This project assembles a **single results table** of post-campaign outcomes for a cardholder cohort. Starting from an external reference list, the script maps to internal customer IDs, snapshots account status, checks fee/refund events since a reference date, measures recent digital activity across web/app, and summarizes digital-ladder segments. Outputs are written both to a database table and to a CSV for easy reporting.

---

## What it does

- **Maps cohort**: `data/campaign_input.csv` (external references) → `WAREHOUSE.DM_ID_LOOKUP` → internal `CUSTOMER_ID`.
- **Builds status view**: pulls card status, statement delivery flag, close date, block code, deceased flag, and current balance.
- **Counts key events** since `2023-11-23`: late-payment fee applied/refunded.
- **Measures digital activity**: last 90-day and last 12-month activity across **WEB** (site) and **APP** (mobile), using the max of either stream.
- **Profiles customers** on a **digital ladder** using `data/digital_ladder.csv`.
- **Writes results** into:
  - Table: `CAMPAIGN_RESULTS (METRIC, FIGURES)`
  - File: `output/campaign_switch_results.csv`

---

## Data flow at a glance

1. **Input staging**
   - Create `CAMPAIGN_INPUT` and insert external refs (`EXT_REF`) from CSV.
   - `INPUT_MATCHED`: resolve to `CUSTOMER_ID` via `WAREHOUSE.DM_ID_LOOKUP`.

2. **Account snapshot**
   - `ACCOUNT_STATUS_SNAPSHOT` from `WAREHOUSE.DM_CARD` + `WAREHOUSE.DM_CUSTOMER`
   - Filter: open or recently closed (≥ `2023-11-23`).

3. **Event metrics**
   - Fee applied/refunded joins via `WAREHOUSE.DM_CARD_TXN` by `CARD_ACCT_ID`.

4. **Digital activity (channels)**
   - `WEB_ACTIVE`: max `WEB_ACTION_DATE` (site).
   - `APP_ACTIVE`: max `APP_EVENT_DATE` (mobile).
   - `DIGITAL_ACTIVE`: union-max of both.

5. **Digital ladder**
   - Join `INPUT_MATCHED` with `data/digital_ladder.csv` (`CUSTOMER_ID`, `LADDER_SEGMENT`).

6. **Results sink**
   - Insert all tallies into `CAMPAIGN_RESULTS`.
   - Export to `output/campaign_switch_results.csv`.

---

## Warehouse objects referenced (logical)

- `WAREHOUSE.DM_ID_LOOKUP` — external → internal ID mapping  
- `WAREHOUSE.DM_CARD` — card account status & balances  
- `WAREHOUSE.DM_CUSTOMER` — customer attributes (e.g., deceased flag)  
- `WAREHOUSE.DM_CARD_TXN` — monetary events (codes)  
- `WAREHOUSE.DM_WEB_EVENTS` — web session/action dates  
- `WAREHOUSE.DM_MOBILE_EVENTS` — app session/action dates

> The script uses a lightweight connector `db_conn.connect_to_warehouse()` expected to expose `.execute()`, `.cursor()`, `.commit()`.

---

## Inputs & outputs

**Inputs (files)**
- `data/campaign_input.csv` — column: `EXT_REF`
- `data/digital_ladder.csv` — columns: `CUSTOMER_ID`, `LADDER_SEGMENT`

**Outputs**
- **DB table**: `CAMPAIGN_RESULTS (METRIC, FIGURES)`
- **CSV**: `output/campaign_switch_results.csv`

**Intermediate tables (dropped at end)**
- `CAMPAIGN_INPUT`, `INPUT_MATCHED`, `ACCOUNT_STATUS_SNAPSHOT`,  
  `WEB_ACTIVE`, `APP_ACTIVE`, `DIGITAL_ACTIVE`

---

## Metrics produced (definitions)

- **Reverted to paper statements** — count where `E_STATEMENT_FLAG IS NULL`.
- **Closed their account** — count where `CARD_STATUS = '8'`.
- **Deceased** — count where `DECEASED_FLAG IS NOT NULL`.
- **Has a positive balance** — count where `CURRENT_BALANCE > 0`.
- **Late payment fee applied (since 23-Nov-2023)** — `TXN_MONETARY_CODE = '7701'`.
- **Late payment fee refunded (since 23-Nov-2023)** — `TXN_MONETARY_CODE = '410'`.
- **Digitally active (last 90 days)** — `DIGITAL_ACTIVE.LAST_ACTION >= SYSDATE-90`.
- **Digitally active (last 12 months)** — present in `DIGITAL_ACTIVE`.
- **Digital ladder distribution** — counts per `LADDER_SEGMENT`.

---
