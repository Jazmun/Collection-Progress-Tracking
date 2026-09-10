import io
import re
from datetime import date, datetime
import pandas as pd
import pdfplumber
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="AR Collections Dashboard", layout="wide")

# -----------------------------------------------------------------------------
# PDF PARSING ENGINE
# -----------------------------------------------------------------------------
def clean_numeric(val):
    """Sanitize dollar and credit strings to float."""
    if pd.isna(val) or val is None:
        return 0.0
    val_str = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def parse_ar_pdf(file_bytes):
    """Extract standard invoice table rows from the statement PDF."""
    records = []
    date_regex = re.compile(r"^\d{2}/\d{2}/\d{2}$")

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Clean empty cells
                    cells = [c.strip() if c else "" for c in row]
                    if len(cells) < 8:
                        continue

                    inv_date_raw = cells[0].split("\n")[0].strip()
                    due_date_raw = cells[1].split("\n")[0].strip()
                    inv_num_raw = cells[2].split("\n")[0].strip()
                    customer = cells[3].split("\n")[0].strip()
                    bal_due_raw = cells[7].split("\n")[0].strip()

                    # Validate row by date format and numeric invoice number
                    if date_regex.match(due_date_raw) and inv_num_raw.isdigit():
                        try:
                            due_dt = datetime.strptime(due_date_raw, "%m/%d/%y").date()
                            inv_dt = datetime.strptime(inv_date_raw, "%m/%d/%y").date()
                            balance = clean_numeric(bal_due_raw)
                            records.append({
                                "Invoice Number": inv_num_raw,
                                "Customer": customer,
                                "Invoice Date": inv_dt,
                                "Due Date": due_dt,
                                "Balance Due": balance
                            })
                        except Exception:
                            continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["Invoice Number"])
    return df

# -----------------------------------------------------------------------------
# AGING BUCKET LOGIC
# -----------------------------------------------------------------------------
def assign_bucket(due_date, as_of_date):
    """Assign invoice to aging bucket based on days past due relative to as_of_date."""
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

BUCKET_ORDER = ["Current", "1-30", "31-60", "61-90", "91-120", "120+"]

# -----------------------------------------------------------------------------
# STREAMLIT UI
# -----------------------------------------------------------------------------
st.title("Accounts Receivable Collections & Baseline Tracker")

st.sidebar.header("Data Sources")
baseline_file = st.sidebar.file_uploader(
    "Upload 8/31 Baseline PDF", type=["pdf"], key="baseline_pdf"
)
new_file = st.sidebar.file_uploader(
    "Upload New Statement PDF", type=["pdf"], key="new_pdf"
)

# Comparison Date input
current_evaluation_date = st.sidebar.date_input(
    "Comparison / As-Of Date", value=date(2026, 9, 10)
)
baseline_date = date(2026, 8, 31)

if not baseline_file:
    st.info("Please upload your baseline PDF (8/31/2026) in the sidebar to begin.")
    st.stop()

# Process Baseline
df_baseline = parse_ar_pdf(baseline_file.read())

if df_baseline.empty:
    st.error("Could not parse invoices from the baseline PDF. Please check the document structure.")
    st.stop()

df_baseline["Baseline Bucket"] = df_baseline["Due Date"].apply(
    lambda d: assign_bucket(d, baseline_date)
)

total_baseline_count = len(df_baseline)
total_baseline_balance = df_baseline["Balance Due"].sum()

# If no new PDF is provided yet, show Baseline Summary only
if not new_file:
    st.subheader(f"Baseline Report as of {baseline_date.strftime('%m/%d/%Y')}")
    
    col1, col2 = st.columns(2)
    col1.metric("Total Baseline Invoices", f"{total_baseline_count}")
    col2.metric("Total Outstanding AR", f"${total_baseline_balance:,.2f}")

    bucket_summary = (
        df_baseline.groupby("Baseline Bucket")["Balance Due"]
        .agg(["sum", "count"])
        .reindex(BUCKET_ORDER)
        .fillna(0)
        .reset_index()
    )
    bucket_summary.columns = ["Aging Bucket", "Total Balance", "Invoice Count"]
    bucket_summary["Total Balance Formatted"] = bucket_summary["Total Balance"].map("${:,.2f}".format)

    st.markdown("### Aging Distribution (8/31/2026)")
    c_chart, c_table = st.columns([3, 2])
    with c_chart:
        fig = px.bar(
            bucket_summary,
            x="Aging Bucket",
            y="Total Balance",
            text="Total Balance Formatted",
            title="Baseline Balance by Aging Bucket",
            color="Aging Bucket",
        )
        st.plotly_chart(fig, use_container_width=True)
    with c_table:
        st.dataframe(bucket_summary[["Aging Bucket", "Invoice Count", "Total Balance Formatted"]], hide_index=True)

    st.stop()

# -----------------------------------------------------------------------------
# COMPARISON RUNTIME
# -----------------------------------------------------------------------------
df_new = parse_ar_pdf(new_file.read())

# Filter new file: Ignore invoice numbers that were not on the baseline
baseline_numbers = set(df_baseline["Invoice Number"])
df_new_matched = df_new[df_new["Invoice Number"].isin(baseline_numbers)].copy()

# Determine status for each baseline invoice
# Merged by invoice number to capture partial balance changes or cleared status
merged = pd.merge(
    df_baseline,
    df_new_matched[["Invoice Number", "Balance Due"]],
    on="Invoice Number",
    how="left",
    suffixes=("_base", "_new"),
)

# If not present in new PDF, balance is 0 (fully cleared/paid)
merged["Balance Due_new"] = merged["Balance Due_new"].fillna(0.0)
merged["Collected Amount"] = merged["Balance Due_base"] - merged["Balance Due_new"]

# Cap collections at baseline balance to guard against rounding/overpayments
merged["Collected Amount"] = merged["Collected Amount"].clip(lower=0.0)

# Determine Current Aging Bucket for open invoices as of the selected date
merged["Current Bucket"] = merged.apply(
    lambda row: "Resolved / Paid" if row["Balance Due_new"] <= 0.01 else assign_bucket(row["Due Date"], current_evaluation_date),
    axis=1,
)

# -----------------------------------------------------------------------------
# KPI METRICS
# -----------------------------------------------------------------------------
total_remaining_balance = merged["Balance Due_new"].sum()
total_collected = merged["Collected Amount"].sum()
resolution_percentage = (total_collected / total_baseline_balance * 100) if total_baseline_balance > 0 else 0.0

resolved_count = (merged["Balance Due_new"] <= 0.01).sum()
remaining_count = total_baseline_count - resolved_count

st.markdown(f"## Comparison: Baseline (08/31/2026) vs. {current_evaluation_date.strftime('%m/%d/%Y')}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Baseline Total", f"${total_baseline_balance:,.2f}", f"{total_baseline_count} Invoices")
m2.metric("Remaining Open Balance", f"${total_remaining_balance:,.2f}", f"{remaining_count} Open", delta_color="inverse")
m3.metric("Cleared / Collected", f"${total_collected:,.2f}", f"{resolved_count} Paid")
m4.metric("Resolution Rate", f"{resolution_percentage:.1f}%")

st.progress(min(resolution_percentage / 100.0, 1.0))

# -----------------------------------------------------------------------------
# AGING BUCKET COMPARISON
# -----------------------------------------------------------------------------
st.markdown("### Aging Bucket Progression")

# Aggregate baseline vs remaining open in the same buckets
base_grouped = df_baseline.groupby("Baseline Bucket")["Balance Due"].sum().reindex(BUCKET_ORDER).fillna(0)
curr_open_only = merged[merged["Balance Due_new"] > 0.01]
curr_grouped = curr_open_only.groupby("Current Bucket")["Balance Due_new"].sum().reindex(BUCKET_ORDER).fillna(0)

comp_df = pd.DataFrame({
    "Aging Bucket": BUCKET_ORDER,
    "Baseline (08/31)": base_grouped.values,
    f"Active Open ({current_evaluation_date.strftime('%m/%d')})": curr_grouped.values,
})

fig_comp = px.bar(
    comp_df,
    x="Aging Bucket",
    y=["Baseline (08/31)", f"Active Open ({current_evaluation_date.strftime('%m/%d')})"],
    barmode="group",
    title="Aging Breakdown: Baseline vs. Current Outstanding",
    labels={"value": "Balance ($)", "variable": "Report"}
)
st.plotly_chart(fig_comp, use_container_width=True)

# -----------------------------------------------------------------------------
# DETAILED AUDIT TABLE
# -----------------------------------------------------------------------------
st.markdown("### Invoice Audit Ledger")

display_df = merged[[
    "Invoice Number",
    "Customer",
    "Due Date",
    "Baseline Bucket",
    "Balance Due_base",
    "Balance Due_new",
    "Collected Amount",
    "Current Bucket",
]].copy()

display_df.columns = [
    "Invoice #",
    "Customer",
    "Due Date",
    "Orig Bucket (8/31)",
    "Baseline Balance",
    "Open Balance",
    "Cleared / Collected",
    "Status / Current Bucket",
]

# Formatting
display_df["Baseline Balance"] = display_df["Baseline Balance"].map("${:,.2f}".format)
display_df["Open Balance"] = display_df["Open Balance"].map("${:,.2f}".format)
display_df["Cleared / Collected"] = display_df["Cleared / Collected"].map("${:,.2f}".format)

# Filter option
status_filter = st.selectbox("Filter ledger by status:", ["All", "Only Paid / Cleared", "Only Open"])
if status_filter == "Only Paid / Cleared":
    display_df = display_df[display_df["Status / Current Bucket"] == "Resolved / Paid"]
elif status_filter == "Only Open":
    display_df = display_df[display_df["Status / Current Bucket"] != "Resolved / Paid"]

st.dataframe(display_df, use_container_width=True, hide_index=True)
