import base64
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
# CONFIGURATION & CONSTANTS
# -----------------------------------------------------------------------------
BASELINE_CSV_PATH = "baseline_279_invoices.csv"
LOGO_PATH = "logo.png"
BASELINE_DATE = date(2026, 8, 31)
FIVE_BUCKETS = ["Current", "1–30 Days", "31–60 Days", "61–90 Days", "120+ Days"]

def get_logo_html():
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{encoded}" alt="La Salle Logo" style="height: 52px; width: auto; object-fit: contain;" />'
    return """
    <div>
        <div class="brand-title">La Salle</div>
        <div class="brand-sub">Landscaping & Tree Service</div>
    </div>
    """

def clean_numeric(val):
    if pd.isna(val) or val is None:
        return 0.0
    val_str = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0

def parse_date(date_str):
    if pd.isna(date_str) or date_str is None:
        return None
    if isinstance(date_str, (datetime, pd.Timestamp)):
        return date_str.date()
    if isinstance(date_str, date):
        return date_str

    date_str = str(date_str).strip().split(" ")[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def assign_bucket(due_date, as_of_date):
    if not due_date or pd.isna(due_date):
        return "120+ Days"
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

# -----------------------------------------------------------------------------
# FILE PARSER (CSV, EXCEL, PDF)
# -----------------------------------------------------------------------------
def load_comparison_file(uploaded_file):
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv") or filename.endswith(".xlsx") or filename.endswith(".xls"):
        if filename.endswith(".csv"):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)

        inv_col = None
        due_col = None
        bal_col = None

        for c in df.columns:
            clean_c = c.strip().lower()
            if clean_c in ["open balance", "open_balance", "balance due", "balance"]:
                bal_col = c
            elif bal_col is None and clean_c in ["amount", "total", "net"]:
                bal_col = c

            if clean_c in ["num", "invoice number", "invoice #", "inv no", "inv #", "invoice"]:
                inv_col = c

            if clean_c in ["due date", "due_date", "duedate"]:
                due_col = c

        if not inv_col:
            for c in df.columns:
                clean_c = c.strip().lower()
                if ("num" in clean_c or "inv" in clean_c) and "date" not in clean_c:
                    inv_col = c
                    break

        if not bal_col:
            for c in df.columns:
                clean_c = c.strip().lower()
                if "open" in clean_c or "balance" in clean_c:
                    bal_col = c
                    break

        if not due_col:
            for c in df.columns:
                clean_c = c.strip().lower()
                if "due" in clean_c:
                    due_col = c
                    break

        if inv_col and bal_col:
            out_df = pd.DataFrame()
            out_df["Invoice Number"] = df[inv_col].astype(str).str.strip()
            out_df["Balance Due"] = df[bal_col].apply(clean_numeric)
            if due_col:
                out_df["Due Date"] = df[due_col].apply(parse_date)
            else:
                out_df["Due Date"] = None
            return out_df.dropna(subset=["Invoice Number"]).drop_duplicates(subset=["Invoice Number"])

    elif filename.endswith(".pdf"):
        records = []
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
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
                            inv_raw = inv_nums[i].strip() if i < len(inv_nums) else ""
                            due_raw = due_dates[i].strip() if i < len(due_dates) else ""
                            bal_raw = balances[i].strip() if i < len(balances) else ""

                            due_dt = parse_date(due_raw)
                            if inv_raw.isdigit():
                                records.append({
                                    "Invoice Number": str(inv_raw),
                                    "Due Date": due_dt,
                                    "Balance Due": clean_numeric(bal_raw),
                                })

        if records:
            df_pdf = pd.DataFrame(records)
            return df_pdf.drop_duplicates(subset=["Invoice Number"])

    return pd.DataFrame(columns=["Invoice Number", "Due Date", "Balance Due"])

def render_bucket_row_html(counts_dict):
    c_cur = counts_dict.get("Current", 0)
    c_130 = counts_dict.get("1–30 Days", 0)
    c_3160 = counts_dict.get("31–60 Days", 0)
    c_6190 = counts_dict.get("61–90 Days", 0)
    c_120 = counts_dict.get("120+ Days", 0)

    return (
        '<div class="bucket-row">'
        '<div class="bucket b-current">'
        '<div class="bucket-header">CURRENT<br><span class="b-es">AL CORRIENTE</span></div>'
        f'<div class="bucket-qty">{c_cur}</div>'
        '<div class="bucket-footer">NOT DUE YET<br><span class="f-es">POR VENCER</span></div>'
        '</div>'
        '<div class="bucket b-amber">'
        '<div class="bucket-header">1–30 DAYS<br><span class="b-es">1–30 DÍAS</span></div>'
        f'<div class="bucket-qty">{c_130}</div>'
        '<div class="bucket-footer">PAST DUE<br><span class="f-es">VENCIDAS</span></div>'
        '</div>'
        '<div class="bucket">'
        '<div class="bucket-header">31–60 DAYS<br><span class="b-es">31–60 DÍAS</span></div>'
        f'<div class="bucket-qty">{c_3160}</div>'
        '<div class="bucket-footer">PAST DUE<br><span class="f-es">VENCIDAS</span></div>'
        '</div>'
        '<div class="bucket">'
        '<div class="bucket-header">61–90 DAYS<br><span class="b-es">61–90 DÍAS</span></div>'
        f'<div class="bucket-qty">{c_6190}</div>'
        '<div class="bucket-footer">PAST DUE<br><span class="f-es">VENCIDAS</span></div>'
        '</div>'
        '<div class="bucket b-red">'
        '<div class="bucket-header">120+ DAYS<br><span class="b-es">120+ DÍAS</span></div>'
        f'<div class="bucket-qty">{c_120}</div>'
        '<div class="bucket-footer">PAST DUE<br><span class="f-es">VENCIDAS</span></div>'
        '</div>'
        '</div>'
    )

# -----------------------------------------------------------------------------
# BASELINE LOAD
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

base_bucket_counts = {b: 0 for b in FIVE_BUCKETS}
for k, v in df_baseline["Baseline Bucket"].value_counts().items():
    if k in base_bucket_counts:
        base_bucket_counts[k] = int(v)

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.markdown("### ⚙️ Collection Progress / Progreso de Cobranza")
new_file = st.sidebar.file_uploader(
    "Upload Open Invoices / Subir Facturas Abiertas (CSV, XLSX, PDF)",
    type=["csv", "xlsx", "xls", "pdf"],
    key="comparison_file",
)
comparison_date = st.sidebar.date_input("As-Of Date / Fecha de Corte", value=date(2026, 9, 4))

# -----------------------------------------------------------------------------
# RECONCILIATION LOGIC
# -----------------------------------------------------------------------------
curr_bucket_counts = {b: 0 for b in FIVE_BUCKETS}
has_comparison = False
invoices_cleared = 0
invoices_open = total_baseline_count
resolution_pct = 0.0

if new_file is not None:
    df_new = load_comparison_file(new_file)
    if df_new.empty:
        st.sidebar.warning("Could not identify invoice data. Showing baseline report.")
    else:
        has_comparison = True
        baseline_nums = set(df_baseline["Invoice Number"].astype(str))
        df_new_matched = df_new[df_new["Invoice Number"].astype(str).isin(baseline_nums)].copy()

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

        for k, v in open_df["Current Bucket"].value_counts().items():
            if k in curr_bucket_counts:
                curr_bucket_counts[k] = int(v)

        invoices_open = int(merged["Is_Open"].sum())
        invoices_cleared = total_baseline_count - invoices_open
        resolution_pct = (invoices_cleared / total_baseline_count * 100) if total_baseline_count > 0 else 0.0

# -----------------------------------------------------------------------------
# HTML RENDERING (BILINGUAL DASHBOARD)
# -----------------------------------------------------------------------------
header_date_str = comparison_date.strftime("%b %-d, %Y")
base_date_str = BASELINE_DATE.strftime("%m/%d/%Y")
comp_date_str = comparison_date.strftime("%m/%d/%Y")

g1_html = render_bucket_row_html(base_bucket_counts)
g2_html = render_bucket_row_html(curr_bucket_counts)
logo_markup = get_logo_html()

g2_subtitle = (
    "Upload comparison file in sidebar / Suba archivo en el panel izquierdo"
    if not has_comparison
    else f"{invoices_open} Open Invoices / Abiertas ({invoices_cleared} Cleared / Saldadas)"
)

full_dashboard_html = f"""
<style>
  .dashboard-wrapper {{
    background: #0f172a;
    padding: 20px 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .dashboard {{
    width: 960px;
    background: #ffffff;
    border-radius: 16px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
    overflow: hidden;
    margin: 0 auto;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 36px;
    background: #ffffff;
    border-bottom: 2px solid #e2e8f0;
  }}
  .brand-group {{
    display: flex;
    align-items: center;
    gap: 16px;
  }}
  .header-meta {{
    text-align: right;
  }}
  .header-meta h2 {{
    font-size: 16px;
    font-weight: 800;
    color: #1e293b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0;
  }}
  .header-meta .sub-es {{
    font-size: 13px;
    color: #00874e;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-top: 1px;
  }}
  .header-meta p {{
    font-size: 11.5px;
    color: #64748b;
    margin-top: 3px;
    font-weight: 500;
    margin-bottom: 0;
  }}
  .summary-strip {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    padding: 14px 24px;
  }}
  .summary-item {{
    text-align: center;
    border-right: 1px solid #e2e8f0;
    padding: 0 8px;
  }}
  .summary-item:last-child {{ border-right: none; }}
  .summary-item .label {{
    font-size: 10.5px;
    text-transform: uppercase;
    font-weight: 800;
    color: #334155;
    letter-spacing: 0.4px;
    line-height: 1.25;
  }}
  .summary-item .label-es {{
    display: block;
    font-size: 9.5px;
    font-weight: 600;
    color: #64748b;
  }}
  .summary-item .value {{
    font-size: 24px;
    font-weight: 900;
    color: #0f172a;
    margin-top: 3px;
  }}
  .summary-item .value.green {{ color: #00874e; }}
  .summary-item .value.amber {{ color: #d97706; }}
  .content {{
    padding: 26px 36px;
    display: flex;
    flex-direction: column;
    gap: 22px;
  }}
  .graphic-card {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  }}
  .card-top {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #f1f5f9;
  }}
  .card-top h3 {{
    font-size: 14px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin: 0;
  }}
  .card-top h3 .title-es {{
    font-size: 12px;
    font-weight: 600;
    color: #64748b;
    margin-left: 4px;
  }}
  .card-top h3.green {{ color: #00874e; }}
  .card-top h3.amber {{ color: #b45309; }}
  .card-top span {{
    font-size: 11.5px;
    color: #64748b;
    font-weight: 600;
  }}
  .bucket-row {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
  }}
  .bucket {{
    border-radius: 10px;
    padding: 14px 6px;
    text-align: center;
    border: 1px solid #e2e8f0;
    background: #f8fafc;
  }}
  .bucket-header {{
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    color: #334155;
    line-height: 1.2;
    margin-bottom: 6px;
  }}
  .bucket-header .b-es {{
    font-size: 9px;
    font-weight: 600;
    color: #64748b;
  }}
  .bucket-qty {{
    font-size: 32px;
    font-weight: 900;
    line-height: 1;
    color: #0f172a;
    margin: 4px 0;
  }}
  .bucket-footer {{
    font-size: 9.5px;
    color: #475569;
    text-transform: uppercase;
    font-weight: 700;
    line-height: 1.2;
  }}
  .bucket-footer .f-es {{
    font-size: 8.5px;
    font-weight: 600;
    color: #94a3b8;
  }}
  .bucket.b-current {{
    background: #f0fdf4;
    border-color: #bbf7d0;
  }}
  .bucket.b-current .bucket-qty {{ color: #16a34a; }}
  .bucket.b-current .bucket-header {{ color: #166534; }}
  .bucket.b-amber {{
    background: #fffbeb;
    border-color: #fde68a;
  }}
  .bucket.b-amber .bucket-qty {{ color: #d97706; }}
  .bucket.b-amber .bucket-header {{ color: #854d0e; }}
  .bucket.b-red {{
    background: #fef2f2;
    border-color: #fecaca;
  }}
  .bucket.b-red .bucket-qty {{ color: #dc2626; }}
  .bucket.b-red .bucket-header {{ color: #991b1b; }}
</style>

<div class="dashboard-wrapper">
  <div class="dashboard">
    <div class="header">
      <div class="brand-group">
        {logo_markup}
      </div>
      <div class="header-meta">
        <h2>A/R Aging & Collections Tracker</h2>
        <div class="sub-es">Antigüedad de Saldos y Cobranza</div>
        <p>Master {total_baseline_count} Baseline &bull; As of / Al {header_date_str}</p>
      </div>
    </div>

    <div class="summary-strip">
      <div class="summary-item">
        <div class="label">STARTING BASELINE <span class="label-es">BASE INICIAL</span></div>
        <div class="value">{total_baseline_count}</div>
      </div>
      <div class="summary-item">
        <div class="label">INVOICES CLEARED <span class="label-es">FACTURAS SALDADAS</span></div>
        <div class="value green">{invoices_cleared}</div>
      </div>
      <div class="summary-item">
        <div class="label">REMAINING OPEN <span class="label-es">PENDIENTES DE PAGO</span></div>
        <div class="value amber">{invoices_open}</div>
      </div>
      <div class="summary-item">
        <div class="label">RESOLUTION RATE <span class="label-es">% DE RESOLUCIÓN</span></div>
        <div class="value green">{resolution_pct:.1f}%</div>
      </div>
    </div>

    <div class="content">
      <div class="graphic-card">
        <div class="card-top">
          <h3 class="green">Graphic 1: Baseline Open Invoices <span class="title-es">(Facturas Abiertas al {base_date_str})</span></h3>
          <span>Original Master List: {total_baseline_count} Invoices (${total_baseline_balance:,.2f})</span>
        </div>
        {g1_html}
      </div>

      <div class="graphic-card">
        <div class="card-top">
          <h3 class="amber">Graphic 2: Baseline Collection Progress <span class="title-es">(Progreso de Cobranza al {comp_date_str})</span></h3>
          <span>{g2_subtitle}</span>
        </div>
        {g2_html}
      </div>
    </div>
  </div>
</div>
"""

st.html(full_dashboard_html)

# -----------------------------------------------------------------------------
# DETAILED AUDIT TABLE (BILINGUAL LABELS)
# -----------------------------------------------------------------------------
with st.expander("🔍 View Master Ledger / Ver Detalle de Facturas", expanded=False):
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
            lambda x: "Active / Pendiente" if x else "Resolved / Pagada"
        )
        audit_table["Balance Due_base"] = audit_table["Balance Due_base"].map("${:,.2f}".format)
        audit_table["Balance Due_new"] = audit_table["Balance Due_new"].map("${:,.2f}".format)
        audit_table["Cleared Amount"] = audit_table["Cleared Amount"].map("${:,.2f}".format)
        audit_table = audit_table.drop(columns=["Is_Open"])
        audit_table.columns = [
            "Invoice # / Factura",
            "Customer / Cliente",
            "Due Date / Vencimiento",
            "8/31 Aging / Antigüedad",
            "Baseline Balance / Saldo Base",
            "Open Balance / Saldo Actual",
            "Cleared / Monto Pagado",
            "Status / Estado",
        ]

        filter_sel = st.radio(
            "Filter ledger / Filtrar reporte:",
            ["All Baseline Invoices / Todas", "Only Remaining Open / Solo Pendientes", "Only Cleared / Solo Pagadas"],
            horizontal=True,
        )
        if "Solo Pendientes" in filter_sel:
            audit_table = audit_table[audit_table["Status / Estado"] == "Active / Pendiente"]
        elif "Solo Pagadas" in filter_sel:
            audit_table = audit_table[audit_table["Status / Estado"] == "Resolved / Pagada"]

        st.dataframe(audit_table, use_container_width=True, hide_index=True)
    else:
        st.dataframe(
            df_baseline[["Invoice Number", "Customer", "Due Date", "Balance Due", "Baseline Bucket"]],
            use_container_width=True,
            hide_index=True,
        )
