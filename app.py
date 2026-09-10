import io
import os
import re
from datetime import date, datetime
import pandas as pd
import pdfplumber
import streamlit as st

st.set_page_config(
    page_title="La Salle - A/R Aging & Collection Tracking",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# CSS STYLING (Card Layout Matching Mockup)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .main .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2.5rem;
        max-width: 1200px;
    }

    .dashboard-shell {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 32px 36px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
        border: 1px solid #eef2f6;
        margin-bottom: 25px;
    }

    .brand-header-wrap {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1.5px solid #edf2f7;
        padding-bottom: 22px;
        margin-bottom: 24px;
    }
    .brand-logo-text {
        color: #0b6638;
        font-size: 26px;
        font-weight: 900;
        letter-spacing: -0.5px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .brand-subtitle {
        color: #4a5568;
        font-size: 14px;
        font-style: italic;
        font-weight: 500;
        margin-left: 36px;
        margin-top: -4px;
    }
    .app-title-right {
        text-align: right;
    }
    .app-title-main {
        font-size: 20px;
        font-weight: 900;
        color: #0f172a;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    .app-title-sub {
        font-size: 13px;
        color: #64748b;
        font-weight: 500;
        margin-top: 4px;
    }

    .top-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        border-bottom: 1.5px solid #edf2f7;
        padding-bottom: 26px;
        margin-bottom: 28px;
    }
    .kpi-col {
        text-align: center;
        border-right: 1px solid #f1f5f9;
        padding: 0 10px;
    }
    .kpi-col:last-child {
        border-right: none;
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 800;
        color: #64748b;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .kpi-val {
        font-size: 36px;
        font-weight: 900;
        line-height: 1.1;
    }
    .kpi-val-neutral { color: #0f172a; }
    .kpi-val-green   { color: #0b6638; }
    .kpi-val-amber   { color: #d97706; }

    .graphic-frame {
        border: 1.5px solid #e2e8f0;
        border-radius: 12px;
        padding: 22px 24px;
        margin-bottom: 24px;
        background: #ffffff;
    }
    .graphic-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 18px;
    }
    .graphic-title-green {
        font-size: 13px;
        font-weight: 900;
        color: #0b6638;
        letter-spacing: 0.6px;
        text-transform: uppercase;
    }
    .graphic-title-orange {
        font-size: 13px;
        font-weight: 900;
        color: #d97706;
        letter-spacing: 0.6px;
        text-transform: uppercase;
    }
    .graphic-meta-note {
        font-size: 12px;
        font-weight: 600;
        color: #64748b;
    }

    .buckets-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 12px;
    }
    .bucket-card {
        border-radius: 10px;
        padding: 14px 6px 12px 6px;
        text-align: center;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 105px;
    }
    .b-label {
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.4px;
        text-transform: uppercase;
    }
    .b-count {
        font-size: 32px;
        font-weight: 900;
        margin: 3px 0;
        line-height: 1;
    }
    .b-sub {
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 0.4px;
        text-transform: uppercase;
    }

    .card-current {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
    }
    .card-current .b-label { color: #166534; }
    .card-current .b-count { color: #15803d; }
    .card-current .b-sub   { color: #4ade80; }

    .card-130 {
        background-color: #fefce8;
        border: 1px solid #fef08a;
    }
    .card-130 .b-label { color: #854d0e; }
    .card-130 .b-count { color: #d97706; }
    .card-130 .b-sub   { color: #ca8a04; }

    .card-neutral {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
    }
    .card-neutral .b-label { color: #475569; }
    .card-neutral .b-count { color: #0f172a; }
    .card-neutral .b-sub   { color: #94a3b8; }

    .card-120 {
        background-color: #fff1f2;
        border: 1px solid #fecdd3;
    }
    .card-120 .b-label { color: #9f1239; }
    .card-120 .b-count { color: #e11d48; }
    .card-120 .b-sub   { color: #fb7185; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# CONSTANTS & HELPER FUNCTIONS
# -----------------------------------------------------------------------------
BUCKET_ORDER = ["Current", "1-30", "31-60", "61-90", "91-120", "120+"]
BASELINE_CSV_PATH = "baseline_279_invoices.csv"
BASELINE_DATE = date(2026, 8, 31)

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
    days_past = (as_of_date - due_date).days
    if days_past <= 0:
        return "Current"
    elif 1 <= days_past <= 30:
        return "1-30"
    elif 31 <= days_past <= 60:
        return "31-60"
    elif 61 <= days_past <= 90:
        return "61-90"
    elif 91 <= days_past <= 120:
        return "91-120"
    else:
        return "120+"

def parse_new_pdf(file_bytes):
    """Extract open invoices from the newly uploaded PDF."""
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

def render_bucket_grid(counts_dict):
    grid_html = """<div class="buckets-grid">"""
    configs = [
        ("Current", "card-current", "NOT DUE YET"),
        ("1-30", "card-130", "PAST DUE"),
        ("31-60", "card-neutral", "PAST DUE"),
        ("61-90", "card-neutral", "PAST DUE"),
        ("91-120", "card-neutral", "PAST DUE"),
        ("120+", "card-120", "PAST DUE"),
    ]
    for key, card_class, subtitle in configs:
        count_val = counts_dict.get(key, 0)
        label_text = f"{key} DAYS" if key != "Current" else "CURRENT"
        grid_html += f"""
        <div class="bucket-card {card_class}">
            <div class="b-label">{label_text}</div>
            <div class="b-count">{count_val}</div>
            <div class="b-sub">{subtitle}</div>
        </div>
        """
    grid_html += """</div>"""
    return grid_html

# -----------------------------------------------------------------------------
# LOAD MASTER BASELINE
# -----------------------------------------------------------------------------
if not os.path.exists(BASELINE_CSV_PATH):
    st.error(f"Missing master baseline file: `{BASELINE_CSV_PATH}`. Please upload it to your repository.")
    st.stop()

df_baseline = pd.read_csv(BASELINE_CSV_PATH, dtype={"Invoice Number": str})
df_baseline["Due Date"] = df_baseline["Due Date"].apply(parse_date)
df_baseline["Balance Due"] = df_baseline["Balance Due"].astype(float)
df_baseline["Baseline Bucket"] = df_baseline["Due Date"].apply(lambda d: assign_bucket(d, BASELINE_DATE))

total_baseline_count = len(df_baseline)
total_baseline_balance = df_baseline["Balance Due"].sum()
base_bucket_counts = df_baseline["Baseline Bucket"].value_counts().reindex(BUCKET_ORDER, fill_value=0).to_dict()

# -----------------------------------------------------------------------------
# SIDEBAR RECONCILIATION CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.markdown("### ⚙️ Collection Reconciliation")
new_file = st.sidebar.file_uploader("Upload New Open Invoices PDF", type=["pdf"], key="new_pdf")
current_evaluation_date = st.sidebar.date_input("Comparison / Reconciliation Date", value=date(2026, 9, 4))

# -----------------------------------------------------------------------------
# EVALUATE COLLECTION PROGRESS
# -----------------------------------------------------------------------------
has_comparison = new_file is not None

if has_comparison:
    df_new = parse_new_pdf(new_file.read())
    
    if df_new.empty:
        st.sidebar.warning("PDF uploaded but no valid invoice rows matched format. Displaying baseline only.")
        has_comparison = False
    else:
        baseline_nums = set(df_baseline["Invoice Number"])
        # Only retain invoices that belong to the original 279 baseline
        df_new_matched = df_new[df_new["Invoice Number"].isin(baseline_nums)].copy()

        merged = pd.merge(
            df_baseline,
            df_new_matched[["Invoice Number", "Balance Due"]],
            on="Invoice Number",
            how="left",
            suffixes=("_base", "_new"),
        )

        # Invoices missing from the new statement have been cleared/paid
        merged["Balance Due_new"] = merged["Balance Due_new"].fillna(0.0)
        merged["Cleared Amount"] = (merged["Balance Due_base"] - merged["Balance Due_new"]).clip(lower=0.0)
        merged["Is_Open"] = merged["Balance Due_new"] > 0.01

        open_df = merged[merged["Is_Open"]].copy()
        open_df["Current Bucket"] = open_df["Due Date"].apply(lambda d: assign_bucket(d, current_evaluation_date))
        curr_bucket_counts = open_df["Current Bucket"].value_counts().reindex(BUCKET_ORDER, fill_value=0).to_dict()

        invoices_open = int(merged["Is_Open"].sum())
        invoices_cleared = total_baseline_count - invoices_open
        resolution_pct = (invoices_cleared / total_baseline_count * 100) if total_baseline_count > 0 else 0.0
else:
    invoices_cleared = 0
    invoices_open = total_baseline_count
    resolution_pct = 0.0
    curr_bucket_counts = {k: 0 for k in BUCKET_ORDER}

# -----------------------------------------------------------------------------
# RENDER DASHBOARD
# -----------------------------------------------------------------------------
header_sub_date = current_evaluation_date.strftime("%b %-d, %Y")
base_date_str = BASELINE_DATE.strftime("%m/%d/%Y")
eval_date_str = current_evaluation_date.strftime("%m/%d/%Y")

shell_html = f"""
<div class="dashboard-shell">
    <div class="brand-header-wrap">
        <div>
            <div class="brand-logo-text">
                <span style="font-size:28px;">✳</span> La Salle
            </div>
            <div class="brand-subtitle">Landscaping & Tree Service</div>
        </div>
        <div class="app-title-right">
            <div class="app-title-main">A/R Aging & Collection Tracking</div>
            <div class="app-title-sub">Due Date Basis • Master Baseline Reconciliation (As of {header_sub_date})</div>
        </div>
    </div>

    <div class="top-kpi-grid">
        <div class="kpi-col">
            <div class="kpi-label">Starting Baseline</div>
            <div class="kpi-val kpi-val-neutral">{total_baseline_count}</div>
        </div>
        <div class="kpi-col">
            <div class="kpi-label">Invoices Cleared</div>
            <div class="kpi-val kpi-val-green">{invoices_cleared}</div>
        </div>
        <div class="kpi-col">
            <div class="kpi-label">Remaining Open</div>
            <div class="kpi-val kpi-val-amber">{invoices_open}</div>
        </div>
        <div class="kpi-col">
            <div class="kpi-label">Resolution Progress</div>
            <div class="kpi-val kpi-val-green">{resolution_pct:.1f}%</div>
        </div>
    </div>

    <div class="graphic-frame">
        <div class="graphic-header">
            <div class="graphic-title-green">Graphic 1: Baseline Open Invoices (As of {base_date_str})</div>
            <div class="graphic-meta-note">Total Imported: {total_baseline_count} Invoices (${total_baseline_balance:,.2f})</div>
        </div>
        {render_bucket_grid(base_bucket_counts)}
    </div>

    <div class="graphic-frame">
        <div class="graphic-header">
            <div class="graphic-title-orange">Graphic 2: Baseline Collection Progress (As of {eval_date_str})</div>
            <div class="graphic-meta-note">
                {"Upload comparison PDF in sidebar to track progress" if not has_comparison else f"{invoices_open} Original Invoices Open ({invoices_cleared} Collected / Cleared)"}
            </div>
        </div>
        {render_bucket_grid(curr_bucket_counts)}
    </div>
</div>
"""

st.markdown(shell_html, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# AUDIT & LEDGER DRILLDOWN
# -----------------------------------------------------------------------------
with st.expander("🔍 View Detailed Invoice Ledger & Reconciliation Status", expanded=False):
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
            "Filter rows:", ["All Baseline Invoices", "Only Remaining Open", "Only Cleared / Paid"],
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
