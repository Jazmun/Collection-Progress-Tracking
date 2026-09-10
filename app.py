import io
import os
from datetime import date, datetime
import pandas as pd
import pdfplumber
import streamlit as st

st.set_page_config(
    page_title="La Salle Landscaping - AR Collections Progress",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# CSS THEME & SHELL STYLING
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      
      .stApp {
        background: #0f172a;
      }
      .main .block-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1040px;
      }
      .dashboard {
        width: 960px;
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
        overflow: hidden;
        margin: 0 auto;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 24px 36px;
        background: #ffffff;
        border-bottom: 2px solid #e2e8f0;
      }
      .brand-group {
        display: flex;
        align-items: center;
        gap: 14px;
      }
      .brand-title {
        font-size: 26px;
        font-weight: 900;
        color: #00874e;
        line-height: 1;
      }
      .brand-sub {
        font-size: 14px;
        font-weight: 700;
        color: #78350f;
        font-style: italic;
        margin-top: 4px;
      }
      .header-meta {
        text-align: right;
      }
      .header-meta h2 {
        font-size: 17px;
        font-weight: 800;
        color: #1e293b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .header-meta p {
        font-size: 12px;
        color: #64748b;
        margin-top: 4px;
        font-weight: 500;
      }
      .summary-strip {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        background: #f8fafc;
        border-bottom: 1px solid #e2e8f0;
        padding: 16px 36px;
      }
      .summary-item {
        text-align: center;
        border-right: 1px solid #e2e8f0;
      }
      .summary-item:last-child { border-right: none; }
      .summary-item .label {
        font-size: 11px;
        text-transform: uppercase;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.5px;
      }
      .summary-item .value {
        font-size: 24px;
        font-weight: 900;
        color: #0f172a;
        margin-top: 2px;
      }
      .summary-item .value.green { color: #00874e; }
      .summary-item .value.amber { color: #d97706; }

      .content {
        padding: 30px 36px;
        display: flex;
        flex-direction: column;
        gap: 26px;
      }
      .graphic-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      }
      .card-top {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 16px;
        padding-bottom: 10px;
        border-bottom: 1px solid #f1f5f9;
      }
      .card-top h3 {
        font-size: 15px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .card-top h3.green { color: #00874e; }
      .card-top h3.amber { color: #b45309; }
      .card-top span {
        font-size: 12px;
        color: #64748b;
        font-weight: 600;
      }
      .bucket-row {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 12px;
      }
      .bucket {
        border-radius: 10px;
        padding: 18px 10px;
        text-align: center;
        border: 1px solid #e2e8f0;
        background: #f8fafc;
      }
      .bucket-header {
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        color: #475569;
        margin-bottom: 8px;
      }
      .bucket-qty {
        font-size: 34px;
        font-weight: 900;
        line-height: 1;
        color: #0f172a;
      }
      .bucket-footer {
        font-size: 10px;
        color: #94a3b8;
        text-transform: uppercase;
        margin-top: 8px;
        font-weight: 600;
      }
      .bucket.b-current {
        background: #f0fdf4;
        border-color: #bbf7d0;
      }
      .bucket.b-current .bucket-qty { color: #16a34a; }

      .bucket.b-amber {
        background: #fffbeb;
        border-color: #fde68a;
      }
      .bucket.b-amber .bucket-qty { color: #d97706; }

      .bucket.b-red {
        background: #fef2f2;
        border-color: #fecaca;
      }
      .bucket.b-red .bucket-qty { color: #dc2626; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# CONFIGURATION & 5-BUCKET AGING ENGINE
# -----------------------------------------------------------------------------
BASELINE_CSV_PATH = "baseline_279_invoices.csv"
BASELINE_DATE = date(2026, 8, 31)
FIVE_BUCKETS = ["Current", "1–30 Days", "31–60 Days", "61–90 Days", "120+ Days"]

def clean_numeric(val):
    if pd.isna(val) or val is None:
        return 0.0
    val_str = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def parse_date(date_str):
    date_str = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def assign_bucket(due_date, as_of_date):
    """5-Bucket rule: combines 91+ into 120+ Days to match template design."""
    days_past = (as_of_date - due_date).days
    if days_past <= 0:
        return "Current"
    elif 1 <= days_past <= 30:
        return "1–30 Days"
    elif 31 <= days_past <= 60:
        return "31–60 Days"
    elif 61 <= days_past <= 90:
        return "61–90 Days"
    else:
        return "120+ Days"

def parse_new_pdf(file_bytes):
    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    cells = [c.strip() if c else "" for c in row]
                    if len(cells) < 8:
                        continue

                    due_dates = cells[1].split("\n")
                    inv_nums = cells[2].split("\n")
                    balances = cells[7].split("\n")

                    num_entries = max(len(inv_nums), len(due_dates), len(balances))
                    for i in range(num_entries):
                        inv_num_raw = inv_nums[i].strip() if i < len(inv_nums) else ""
                        due_date_raw = due_dates[i].strip() if i < len(due_dates) else ""
                        bal_raw = balances[i].strip() if i < len(balances) else ""

                        due_dt = parse_date(due_date_raw)
                        if inv_num_raw.isdigit() and due_dt is not None:
                            records.append({
                                "Invoice Number": str(inv_num_raw),
                                "Due Date": due_dt,
                                "Balance Due": clean_numeric(bal_raw),
                            })

    if not records:
        return pd.DataFrame(columns=["Invoice Number", "Due Date", "Balance Due"])

    df = pd.DataFrame(records)
    return df.drop_duplicates(subset=["Invoice Number"])

def render_bucket_row_html(counts_dict):
    """Render the 5-bucket flex card deck."""
    return f"""
    <div class="bucket-row">
      <div class="bucket b-current">
        <div class="bucket-header">Current</div>
        <div class="bucket-qty">{counts_dict.get('Current', 0)}</div>
        <div class="bucket-footer">Not Due Yet</div>
      </div>
      <div class="bucket b-amber">
        <div class="bucket-header">1–30 Days</div>
        <div class="bucket-qty">{counts_dict.get('1–30 Days', 0)}</div>
        <div class="bucket-footer">Past Due</div>
      </div>
      <div class="bucket">
        <div class="bucket-header">31–60 Days</div>
        <div class="bucket-qty">{counts_dict.get('31–60 Days', 0)}</div>
        <div class="bucket-footer">Past Due</div>
      </div>
      <div class="bucket">
        <div class="bucket-header">61–90 Days</div>
        <div class="bucket-qty">{counts_dict.get('61–90 Days', 0)}</div>
        <div class="bucket-footer">Past Due</div>
      </div>
      <div class="bucket b-red">
        <div class="bucket-header">120+ Days</div>
        <div class="bucket-qty">{counts_dict.get('120+ Days', 0)}</div>
        <div class="bucket-footer">Past Due</div>
      </div>
    </div>
    """

# -----------------------------------------------------------------------------
# DATA ENGINE: LOAD REPOSITORY BASELINE
# -----------------------------------------------------------------------------
if not os.path.exists(BASELINE_CSV_PATH):
    st.error(f"Missing master baseline file: `{BASELINE_CSV_PATH}` in your GitHub repository.")
    st.stop()

df_baseline = pd.read_csv(BASELINE_CSV_PATH, dtype={"Invoice Number": str})
df_baseline["Due Date"] = df_baseline["Due Date"].apply(parse_date)
df_baseline["Balance Due"] = df_baseline["Balance Due"].astype(float)
df_baseline["Baseline Bucket"] = df_baseline["Due Date"].apply(lambda d: assign_bucket(d, BASELINE_DATE))

total_baseline_count = len(df_baseline)
total_baseline_balance = df_baseline["Balance Due"].sum()
base_bucket_counts = df_baseline["Baseline Bucket"].value_counts().reindex(FIVE_BUCKETS, fill_value=0).to_dict()

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.markdown("### ⚙️ Collection Progress")
new_file = st.sidebar.file_uploader("Upload Comparison Report (PDF)", type=["pdf"], key="new_pdf")
comparison_date = st.sidebar.date_input("As-Of Evaluation Date", value=date(2026, 9, 4))

# -----------------------------------------------------------------------------
# RECONCILIATION LOGIC
# -----------------------------------------------------------------------------
has_comparison = new_file is not None

if has_comparison:
    df_new = parse_new_pdf(new_file.read())
    if df_new.empty:
        st.sidebar.warning("Uploaded PDF parsed 0 rows. Showing baseline status only.")
        has_comparison = False
    else:
        baseline_nums = set(df_baseline["Invoice Number"])
        # Match only the baseline's 279 invoices, ignore new or non-baseline invoices
        df_new_matched = df_new[df_new["Invoice Number"].isin(baseline_nums)].copy()

        merged = pd.merge(
            df_baseline,
            df_new_matched[["Invoice Number", "Balance Due"]],
            on="Invoice Number",
            how="left",
            suffixes=("_base", "_new"),
        )

        merged["Balance Due_new"] = merged["Balance Due_new"].fillna(0.0)
        merged["Cleared Amount"] = (merged["Balance Due_base"] - merged["Balance Due_new"]).clip(lower=0.0)
        merged["Is_Open"] = merged["Balance Due_new"] > 0.01

        open_df = merged[merged["Is_Open"]].copy()
        open_df["Current Bucket"] = open_df["Due Date"].apply(lambda d: assign_bucket(d, comparison_date))
        curr_bucket_counts = open_df["Current Bucket"].value_counts().reindex(FIVE_BUCKETS, fill_value=0).to_dict()

        invoices_open = int(merged["Is_Open"].sum())
        invoices_cleared = total_baseline_count - invoices_open
        resolution_pct = (invoices_cleared / total_baseline_count * 100) if total_baseline_count > 0 else 0.0
else:
    invoices_cleared = 0
    invoices_open = total_baseline_count
    resolution_pct = 0.0
    curr_bucket_counts = {k: 0 for k in FIVE_BUCKETS}

# -----------------------------------------------------------------------------
# RENDER CUSTOM HTML DASHBOARD
# -----------------------------------------------------------------------------
header_date_str = comparison_date.strftime("%b %-d, %Y")
base_date_str = BASELINE_DATE.strftime("%m/%d/%Y")
comp_date_str = comparison_date.strftime("%m/%d/%Y")

dashboard_html = f"""
<div class="dashboard">
  <!-- Header with Brand Identification -->
  <div class="header">
    <div class="brand-group">
      <svg width="46" height="46" viewBox="0 0 100 100" fill="none">
        <path d="M50 5 L58 32 L78 22 L72 45 L95 50 L75 62 L85 85 L60 75 L50 95 L40 75 L15 85 L25 62 L5 50 L28 45 L22 22 L42 32 Z" fill="#00874e"/>
        <path d="M50 5 L50 95" stroke="#ffffff" stroke-width="2"/>
      </svg>
      <div>
        <div class="brand-title">La Salle</div>
        <div class="brand-sub">Landscaping & Tree Service</div>
      </div>
    </div>
    <div class="header-meta">
      <h2>A/R Aging & Collections Tracker</h2>
      <p>Due Date Basis &bull; Master {total_baseline_count} Baseline Progress (As of {header_date_str})</p>
    </div>
  </div>

  <!-- Executive Summary -->
  <div class="summary-strip">
    <div class="summary-item">
      <div class="label">Starting Baseline</div>
      <div class="value">{total_baseline_count}</div>
    </div>
    <div class="summary-item">
      <div class="label">Invoices Cleared</div>
      <div class="value green">{invoices_cleared}</div>
    </div>
    <div class="summary-item">
      <div class="label">Remaining Open</div>
      <div class="value amber">{invoices_open}</div>
    </div>
    <div class="summary-item">
      <div class="label">Resolution Rate</div>
      <div class="value green">{resolution_pct:.1f}%</div>
    </div>
  </div>

  <div class="content">
    <!-- Graphic 1: Baseline Imported as of 8/31/2026 -->
    <div class="graphic-card">
      <div class="card-top">
        <h3 class="green">Graphic 1: Baseline Open Invoices (As of {base_date_str})</h3>
        <span>Original Master List: {total_baseline_count} Invoices (${total_baseline_balance:,.2f})</span>
      </div>
      {render_bucket_row_html(base_bucket_counts)}
    </div>

    <!-- Graphic 2: Current Progress -->
    <div class="graphic-card">
      <div class="card-top">
        <h3 class="amber">Graphic 2: Baseline Collection Progress (As of {comp_date_str})</h3>
        <span>{"Upload comparison PDF in sidebar to track progress" if not has_comparison else f"{invoices_open} Original Baseline Invoices Open ({invoices_cleared} Invoices Cleared)"}</span>
      </div>
      {render_bucket_row_html(curr_bucket_counts)}
    </div>
  </div>
</div>
"""

st.markdown(dashboard_html, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# AUDIT DRILLDOWN TABLE
# -----------------------------------------------------------------------------
with st.expander("🔍 View Master Ledger & Resolution Match Details", expanded=False):
    if has_comparison:
        audit_table = merged[[
            "Invoice Number",
            "Customer",
            "Due Date",
            "Baseline Bucket",
            "Balance Due_base",
            "Balance Due_new",
            "Cleared Amount",
            "Is_Open",
        ]].copy()

        audit_table["Status"] = audit_table["Is_Open"].apply(
            lambda x: "Active / Open" if x else "Resolved / Paid"
        )
        audit_table["Balance Due_base"] = audit_table["Balance Due_base"].map("${:,.2f}".format)
        audit_table["Balance Due_new"] = audit_table["Balance Due_new"].map("${:,.2f}".format)
        audit_table["Cleared Amount"] = audit_table["Cleared Amount"].map("${:,.2f}".format)
        audit_table = audit_table.drop(columns=["Is_Open"])
        audit_table.columns = [
            "Invoice #",
            "Customer",
            "Due Date",
            "8/31 Bucket",
            "Baseline Balance",
            "Current Balance",
            "Amount Cleared",
            "Status",
        ]

        filter_sel = st.radio(
            "Filter ledger:", ["All Baseline Invoices", "Only Remaining Open", "Only Cleared / Paid"],
            horizontal=True,
        )
        if filter_sel == "Only Remaining Open":
            audit_table = audit_table[audit_table["Status"] == "Active / Open"]
        elif filter_sel == "Only Cleared / Paid":
            audit_table = audit_table[audit_table["Status"] == "Resolved / Paid"]

        st.dataframe(audit_table, use_container_width=True, hide_index=True)
    else:
        st.dataframe(
            df_baseline[["Invoice Number", "Customer", "Due Date", "Balance Due", "Baseline Bucket"]],
            use_container_width=True,
            hide_index=True,
        )
