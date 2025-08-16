```python
# ===========================
# AUTO SWITCH CAMPAIGN 
# ===========================

print("Campaign Switch 3.0 report started")

# --- path hygiene (optional) ---
import sys, shutil, os
try:
    shutil.rmtree(r'X:\Python\lib\__pycache__')
except:
    pass
finally:
    sys.path.append(r'X:\Python\lib')

user = os.getlogin()
try:
    shutil.rmtree(f'C:\\Users\\{user}\\lib\\__pycache__')
except:
    pass
finally:
    sys.path.append(f'C:\\Users\\{user}\\lib')

# --- DB connector ---
import db_conn  # was `connection`; expected to expose connect_to_warehouse() with .execute(), .cursor(), .commit()

# ===========================
# RESULTS table
# ===========================
con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table CAMPAIGN_RESULTS purge")
except:
    pass

con.execute("""
    create table CAMPAIGN_RESULTS(
        METRIC  varchar2(80),
        FIGURES number
    )
""")
con.close()

# ===========================
# Load input file -> stage table
# ===========================
import pandas as pd

# replace with your local sample file
input_df = pd.read_csv(r'.\data\campaign_input.csv')  # single column expected: EXT_REF (formerly CDU_NUMBER)
input_df.columns = ["EXT_REF"]

con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table CAMPAIGN_INPUT purge")
except:
    pass

con.execute("""
    create table CAMPAIGN_INPUT(
        EXT_REF varchar2(20)
    )
""")
cur = con.cursor()
cur.executemany("insert into CAMPAIGN_INPUT(EXT_REF) values (:1)", input_df.values.tolist())
con.commit()
cur.close()
con.close()

# ===========================
# Map external refs to customer ids
# ===========================
con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table INPUT_MATCHED purge")
except:
    pass

con.execute("""
    create table INPUT_MATCHED as
    select distinct m.CUSTOMER_ID
    from CAMPAIGN_INPUT i
    join WAREHOUSE.DM_ID_LOOKUP m          -- was MINERVADMMART.DM_CDU_NUMBER_LOOKUP
      on cast(i.EXT_REF as varchar2(20)) = cast(m.ID_EXTERNAL as varchar2(20))
""")
con.close()

# ===========================
# Customer account status snapshot
# ===========================
con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table ACCOUNT_STATUS_SNAPSHOT purge")
except:
    pass

con.execute("""
    create table ACCOUNT_STATUS_SNAPSHOT as
    select distinct
           x.CUSTOMER_ID,
           c.CARD_STATUS,               -- was CC_STATUS
           c.E_STATEMENT_FLAG,          -- was CC_STMT_FLAG
           c.CARD_CLOSE_DATE,           -- was CC_DATE_CLOSED
           c.CARD_BLOCK_CODE,           -- was CC_BLOCK_CODE
           k.DECEASED_FLAG,             -- was DEAD
           c.CURRENT_BALANCE            -- was CC_CURR_BALANCE
    from INPUT_MATCHED x
    join WAREHOUSE.DM_CARD c
      on x.CUSTOMER_ID = c.CUSTOMER_ID
    join WAREHOUSE.DM_CUSTOMER k
      on x.CUSTOMER_ID = k.CUSTOMER_ID
    where c.CARD_CLOSE_DATE is null
       or c.CARD_CLOSE_DATE >= date '2023-11-23'
""")
con.close()

# ===========================
# Simple metrics
# ===========================
con = db_conn.connect_to_warehouse()

# Reverted to paper
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Reverted to paper statements', count(distinct CUSTOMER_ID)
    from ACCOUNT_STATUS_SNAPSHOT
    where E_STATEMENT_FLAG is null
""")
con.commit()

# Closed account
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Closed their account', count(distinct CUSTOMER_ID)
    from ACCOUNT_STATUS_SNAPSHOT
    where CARD_STATUS = '8'
""")
con.commit()

# Deceased
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Deceased', count(distinct CUSTOMER_ID)
    from ACCOUNT_STATUS_SNAPSHOT
    where DECEASED_FLAG is not null
""")
con.commit()

# Positive balance
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Has a positive balance', count(distinct CUSTOMER_ID)
    from ACCOUNT_STATUS_SNAPSHOT
    where CURRENT_BALANCE > 0
""")
con.commit()
con.close()

# ===========================
# Fee / refund events since a given date
# ===========================
con = db_conn.connect_to_warehouse()

# Late payment fee applied (7701)
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Late payment fee applied (since 23-Nov-2023)', count(distinct x.CUSTOMER_ID)
    from INPUT_MATCHED x
    join WAREHOUSE.DM_CARD c
      on x.CUSTOMER_ID = c.CUSTOMER_ID
    join WAREHOUSE.DM_CARD_TXN t
      on c.CARD_ACCT_ID = t.CARD_ACCT_ID
    where t.TXN_LOAD_DATE >= date '2023-11-23'
      and t.TXN_MONETARY_CODE = '7701'
""")
con.commit()

# Late payment fee refunded (0410)
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Late payment fee refunded (since 23-Nov-2023)', count(distinct x.CUSTOMER_ID)
    from INPUT_MATCHED x
    join WAREHOUSE.DM_CARD c
      on x.CUSTOMER_ID = c.CUSTOMER_ID
    join WAREHOUSE.DM_CARD_TXN t
      on c.CARD_ACCT_ID = t.CARD_ACCT_ID
    where t.TXN_LOAD_DATE >= date '2023-11-23'
      and t.TXN_MONETARY_CODE = '410'
""")
con.commit()
con.close()

# ===========================
# Channel activity (last 12 months)
# ===========================
con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table WEB_ACTIVE purge")
except:
    pass
con.execute("""
    create table WEB_ACTIVE as
    select x.CUSTOMER_ID,
           max(e.WEB_ACTION_DATE) as LAST_ACTION
    from INPUT_MATCHED x
    join WAREHOUSE.DM_WEB_EVENTS e
      on x.CUSTOMER_ID = e.CUSTOMER_ID
    group by x.CUSTOMER_ID
    having max(e.WEB_ACTION_DATE) >= add_months(sysdate, -12)
""")
con.close()

con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table APP_ACTIVE purge")
except:
    pass
con.execute("""
    create table APP_ACTIVE as
    select x.CUSTOMER_ID,
           max(m.APP_EVENT_DATE) as LAST_ACTION
    from INPUT_MATCHED x
    join WAREHOUSE.DM_MOBILE_EVENTS m
      on x.CUSTOMER_ID = m.CUSTOMER_ID
    group by x.CUSTOMER_ID
    having max(m.APP_EVENT_DATE) >= add_months(sysdate, -12)
""")
con.close()

con = db_conn.connect_to_warehouse()
try:
    con.execute("drop table DIGITAL_ACTIVE purge")
except:
    pass
con.execute("""
    create table DIGITAL_ACTIVE as
    select u.CUSTOMER_ID, max(u.LAST_ACTION) as LAST_ACTION
    from (
        select CUSTOMER_ID, LAST_ACTION from WEB_ACTIVE
        union
        select CUSTOMER_ID, LAST_ACTION from APP_ACTIVE
    ) u
    group by u.CUSTOMER_ID
""")
con.close()

# 90-day digitally active
con = db_conn.connect_to_warehouse()
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Digitally active (last 90 days)', count(distinct x.CUSTOMER_ID)
    from INPUT_MATCHED x
    join DIGITAL_ACTIVE d
      on x.CUSTOMER_ID = d.CUSTOMER_ID
    where d.LAST_ACTION >= (sysdate - 90)
""")
con.commit()

# 12-month digitally active
con.execute("""
    insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
    select 'Digitally active (last 12 months)', count(distinct x.CUSTOMER_ID)
    from INPUT_MATCHED x
    join DIGITAL_ACTIVE d
      on x.CUSTOMER_ID = d.CUSTOMER_ID
""")
con.commit()
con.close()

# ===========================
# Digital ladder distribution
# ===========================
ladder_df = pd.read_csv(r'.\data\digital_ladder.csv')      # columns: CUSTOMER_ID, LADDER_SEGMENT (was CATEGORY)
ladder_df["CUSTOMER_ID"] = ladder_df["CUSTOMER_ID"].astype(str)

con = db_conn.connect_to_warehouse()
input_ids = pd.read_sql("select CUSTOMER_ID from INPUT_MATCHED", con)
con.close()

input_ids["CUSTOMER_ID"] = input_ids["CUSTOMER_ID"].astype(str)
combined = pd.merge(input_ids, ladder_df, on="CUSTOMER_ID", how="inner")

seg_counts = combined["LADDER_SEGMENT"].value_counts()

con = db_conn.connect_to_warehouse()
for seg, cnt in seg_counts.items():
    con.execute(f"""
        insert into CAMPAIGN_RESULTS(METRIC, FIGURES)
        select '{str(seg).strip()}', {int(cnt)} from dual
    """)
    con.commit()
con.close()

# ===========================
# Export results
# ===========================
con = db_conn.connect_to_warehouse()
results = pd.read_sql("select * from CAMPAIGN_RESULTS", con)
con.close()

os.makedirs(r'.\output', exist_ok=True)
results.to_csv(r'.\output\campaign_switch_results.csv', index=False)

# ===========================
# Cleanup
# ===========================
con = db_conn.connect_to_warehouse()
for stmt in [
    "drop table CAMPAIGN_INPUT purge",
    "drop table INPUT_MATCHED purge",
    "drop table ACCOUNT_STATUS_SNAPSHOT purge",
    "drop table WEB_ACTIVE purge",
    "drop table APP_ACTIVE purge",
    "drop table DIGITAL_ACTIVE purge"
]:
    try:
        con.execute(stmt)
    except:
        pass
con.close()

print("Campaign Switch 3.0 report completed")