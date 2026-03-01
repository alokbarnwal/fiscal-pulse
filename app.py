"""
Fiscal Pulse — Public Dashboard
Run: streamlit run app.py
"""

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import json
from datetime import datetime

from config import (
    MASTER_CSV, METADATA_JSON, MANUAL_OVERRIDES, INPUTS_DIR,
    INDICATOR_IDS, INDICATOR_NAMES, INDICATOR_GROUP,
    DQ_OK, DQ_MANUAL, DQ_PARSE_ERROR, DQ_PDF_ERROR, STATES,
)

# ─────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fiscal Pulse | India State Finance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────
# CSS — FIXED VERSION
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  /* ── KILL ONLY THE TOP GAP — surgical approach ── */
  header[data-testid="stHeader"]          { display: none !important; }
  #MainMenu                               { display: none !important; }
  footer                                  { display: none !important; }

  .main .block-container {
    padding-top: 0 !important;
    padding-bottom: 1rem !important;
    max-width: 100% !important;
  }
  /* Only target the FIRST child of the outermost app container — not ALL verticalblocks */
  [data-testid="stAppViewContainer"] > section > div > [data-testid="stVerticalBlock"] > div:first-child {
    margin-top: 0 !important;
    padding-top: 0 !important;
  }
  /* Reduce (not eliminate) gap between top-level blocks only */
  [data-testid="stAppViewContainer"] > section > div > [data-testid="stVerticalBlock"] {
    gap: 4px !important;
  }
  /* Tabs should sit right below title */
  .stTabs, [data-testid="stTabs"] { margin-top: 0 !important; }

  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* ── Sidebar — FIX top gap ── */
  section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1F4E79 0%, #2E75B6 100%) !important;
  }
  /* Kill the extra top padding Streamlit puts in sidebar */
  section[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
    margin-top: 0 !important;
  }
  section[data-testid="stSidebar"] > div { padding-top: 0 !important; }
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] span:not([data-baseweb]) { color: white !important; }
  section[data-testid="stSidebar"] [data-baseweb="select"] [class*="singleValue"],
  section[data-testid="stSidebar"] [data-baseweb="select"] input,
  section[data-testid="stSidebar"] [data-baseweb="select"] [class*="placeholder"] {
    color: #111 !important;
  }
  section[data-testid="stSidebar"] [data-baseweb="select"] [class*="control"] {
    background: white !important;
  }
  /* Sidebar widget spacing — comfortable, not cramped */
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.5rem !important;
  }

  /* ── Mobile Responsive ── */
  @media (max-width: 768px) {
    /* Sidebar toggle button always visible */
    [data-testid="collapsedControl"] {
      display: flex !important;
      background: #1F4E79 !important;
      color: white !important;
      border-radius: 0 8px 8px 0 !important;
      top: 10px !important;
    }
    /* Page title smaller on mobile */
    .page-title-text { font-size: 16px !important; }
    .page-title-sub  { font-size: 10px !important; }
    /* Metric cards stack on mobile */
    .metric-card { height: auto !important; margin-bottom: 8px; }
    .metric-value { font-size: 18px !important; }
  }

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab"] {
    font-size: 14px !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
    color: #666 !important;
  }
  .stTabs [aria-selected="true"] {
    color: #1F4E79 !important;
    border-bottom: 3px solid #2E75B6 !important;
  }
  .stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    border-bottom: 2px solid #E2E8F0;
    margin-bottom: 10px;
  }

  /* ── Metric Cards — compact fixed height ── */
  .metric-card {
    background: white;
    border-radius: 10px;
    padding: 12px 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.07);
    border-left: 4px solid #2E75B6;
    height: 90px;              /* compact — was 110px */
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .metric-card.green  { border-left-color: #1E8449; }
  .metric-card.red    { border-left-color: #C0392B; }
  .metric-card.orange { border-left-color: #E67E22; }
  .metric-card.purple { border-left-color: #6C3483; }
  .metric-card.teal   { border-left-color: #148F77; }

  .metric-label {
    font-size: 10px; color: #999; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.6px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .metric-value {
    /* FIX: fluid font — shrinks if number is long */
    font-size: clamp(16px, 2.2vw, 22px);
    font-weight: 800; color: #1F4E79;
    margin: 4px 0 2px; line-height: 1.15;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .metric-value.neg { color: #C0392B; }
  .metric-sub { font-size: 11px; color: #BBB; }

  /* ── Page title bar ── */
  .page-title {
    background: linear-gradient(90deg, #1F4E79 0%, #2E75B6 100%);
    padding: 11px 22px 9px;
    margin-bottom: 0;
  }
  .page-title-text {
    font-size: 20px; font-weight: 800; color: white; display: inline;
  }
  .page-title-sub {
    font-size: 12px; color: #BDD7EE; margin-top: 2px;
  }

  /* ── View banner ── */
  .view-banner {
    background: #EBF3FB; border-left: 4px solid #2E75B6;
    padding: 7px 14px; border-radius: 6px;
    font-size: 13px; margin-bottom: 10px; margin-top: 6px;
    color: #1F4E79;
  }

  /* ── Section header ── */
  .sec-hdr {
    font-size: 11px; font-weight: 700; color: #1F4E79;
    border-bottom: 2px solid #2E75B6; padding-bottom: 3px;
    margin: 10px 0 8px; text-transform: uppercase; letter-spacing: 0.6px;
  }

  /* ── Chart container: card-like wrapper — compact ── */
  .chart-wrap {
    background: white;
    border-radius: 10px;
    padding: 2px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    margin-bottom: 8px;
  }
  /* Tighten column gaps so charts are closer together */
  [data-testid="column"] { padding: 0 4px !important; }

  /* ── Footer ── */
  .brand-footer {
    background: linear-gradient(90deg, #1F4E79, #2E75B6);
    color: white; padding: 10px 22px; border-radius: 8px;
    text-align: center; margin-top: 24px; font-size: 12px;
  }
  .brand-footer a { color: #BDD7EE; text-decoration: none; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data():
    if not Path(MASTER_CSV).exists():
        return pd.DataFrame()
    df = pd.read_csv(MASTER_CSV)
    df["fy_month_order"] = df["fy_month_order"].fillna(0).astype(int)
    return df

@st.cache_data(ttl=3600)
def load_metadata():
    if not Path(METADATA_JSON).exists():
        return {}
    with open(METADATA_JSON) as f:
        return json.load(f)

def load_overrides():
    if not Path(MANUAL_OVERRIDES).exists():
        return pd.DataFrame()
    return pd.read_csv(MANUAL_OVERRIDES)


# ─────────────────────────────────────────────────────────
# FORMATTERS — FIX: consistent decimal handling
# ─────────────────────────────────────────────────────────
def fmt(val):
    """Format ₹ value — always 0 decimals for crores, 2 for lakh crore."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    val = float(val)
    if abs(val) >= 100000:
        return f"₹{val/100000:,.2f}L Cr"
    elif abs(val) >= 1000:
        # FIX: was showing decimals inconsistently — now always 0 decimals
        return f"₹{val:,.0f} Cr"
    else:
        return f"₹{val:,.0f} Cr"  # FIX: was ".1f", unified to ".0f"

def fmt_short(val):
    """Compact format for chart hover tooltips."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    val = float(val)
    if abs(val) >= 100000:
        return f"₹{val/100000:.2f}L Cr"
    elif abs(val) >= 1000:
        return f"₹{val:,.0f} Cr"
    return f"₹{val:.0f} Cr"

def pstr(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:+.1f}%"


# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────
def render_sidebar(df):
    st.sidebar.markdown("""
<div style='padding:10px 0 10px; border-bottom:1px solid rgba(255,255,255,0.2); margin-bottom:10px;'>
  <div style='font-size:18px; font-weight:800; color:white; margin-bottom:2px;'>📊 Fiscal Pulse</div>
  <div style='font-size:11px; color:#BDD7EE;'>India State Finance Dashboard</div>
</div>""", unsafe_allow_html=True)

    active_states = [n for n, _, _, _, av in STATES if av and n in df["state"].unique()]
    sel_state = st.sidebar.selectbox("State / UT", active_states, index=0)

    sdf = df[df["state"] == sel_state]
    avail_fys = sorted(sdf["fy"].unique(), reverse=True)
    sel_fy = st.sidebar.selectbox("Financial Year", avail_fys, index=0)

    fy_df = sdf[sdf["fy"] == sel_fy]
    avail_months = sorted(fy_df["fy_month_order"].unique())
    month_names = [fy_df[fy_df["fy_month_order"] == m]["month_name"].iloc[0] for m in avail_months]
    month_map = dict(zip(month_names, avail_months))
    sel_month_label = st.sidebar.selectbox("Month (up to)", month_names, index=len(month_names)-1)
    sel_month = month_map[sel_month_label]

    view_mode = st.sidebar.radio("View Mode", ["📈 Cumulative", "📅 Monthly"], index=0)

    st.sidebar.markdown("""
<div style='border-top:1px solid rgba(255,255,255,0.2); margin-top:12px; padding-top:10px;
     font-size:11px; color:#BDD7EE; line-height:1.9;'>
  📂 Data: <strong style='color:white'>CAG Monthly Key Indicators</strong><br>
  25 states · Auto-updated monthly<br><br>
  🙋 Built by <strong style='color:white'>Alok Barnwal</strong><br>
  Public Finance Expert<br>
  <a href='https://linkedin.com/in/aloksbarnwal' style='color:#90CAF9;'>LinkedIn ↗</a>
</div>""", unsafe_allow_html=True)

    return sel_state, sel_fy, sel_month, sel_month_label, view_mode


# ─────────────────────────────────────────────────────────
# METRIC CARD
# ─────────────────────────────────────────────────────────
def metric_card(label, value, sub="", color="blue"):
    is_neg = isinstance(value, (int, float)) and not np.isnan(float(value)) and float(value) < 0
    vc = "neg" if is_neg else ""
    vs = fmt(value) if isinstance(value, (int, float)) else str(value)
    st.markdown(f"""
<div class="metric-card {color}">
  <div class="metric-label">{label}</div>
  <div class="metric-value {vc}">{vs}</div>
  <div class="metric-sub">{sub}</div>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# CHART LAYOUT BASE — FIX: proper margins so x-axis shows
# ─────────────────────────────────────────────────────────
C = {
    "blue":   "#2E75B6",
    "green":  "#1E8449",
    "red":    "#C0392B",
    "orange": "#E67E22",
    "purple": "#6C3483",
    "teal":   "#148F77",
    "lgray":  "#F7F9FC",
}

CHART_H = 255  # FIX: reduced from 360 — 2 rows × 255px = 510px, fits with metrics above

# FIX: tighter margins — was b=70 t=52, now b=55 t=40
# b=55 still enough for angled month labels (9 chars max)
BL = dict(
    font=dict(family="Inter, Arial, sans-serif", size=11),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=8, r=36, t=40, b=55),  # tighter all around
    height=CHART_H,
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.28,                # below chart
        xanchor="center",
        x=0.5,
        font=dict(size=10),
        bgcolor="rgba(0,0,0,0)",
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#F0F4F8",
        zeroline=True,
        zerolinecolor="#CCC",
        zerolinewidth=1.2,
        tickfont=dict(size=10),
    ),
    xaxis=dict(
        showgrid=False,
        tickfont=dict(size=10),
        tickangle=-35,
        automargin=True,
    ),
    hoverlabel=dict(
        bgcolor="white",
        bordercolor="#CCC",
        font_size=12,
        font_family="Inter, Arial",
    ),
)


# ─────────────────────────────────────────────────────────
# CHARTS
# ─────────────────────────────────────────────────────────

def _layout(**overrides):
    """Return a copy of BL with optional overrides."""
    import copy
    base = copy.deepcopy(BL)
    base.update(overrides)
    return base


def ch_rev_exp(sdf, fy, vm):
    col = "actuals_cumulative" if "Cumulative" in vm else "actuals_monthly"
    fdf = sdf[sdf["fy"] == fy].sort_values("fy_month_order")
    rev = fdf[fdf["indicator_id"] == "revenue_receipts"][["month_name", col]]
    exp = fdf[fdf["indicator_id"] == "total_expenditure"][["month_name", col]]
    if rev.empty or exp.empty:
        return None

    mode = "Cumulative" if "Cumulative" in vm else "Monthly"
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=rev["month_name"], y=rev[col],
        name="Revenue Receipts",
        marker_color=C["green"], opacity=0.88,
        # FIX: rich hover with ₹ formatting
        hovertemplate="<b>%{x}</b><br>Revenue: %{customdata}<extra></extra>",
        customdata=[fmt_short(v) for v in rev[col]],
    ))
    fig.add_trace(go.Bar(
        x=exp["month_name"], y=exp[col],
        name="Total Expenditure",
        marker_color=C["orange"], opacity=0.88,
        hovertemplate="<b>%{x}</b><br>Expenditure: %{customdata}<extra></extra>",
        customdata=[fmt_short(v) for v in exp[col]],
    ))
    # FIX: shorter title so it doesn't crowd the legend area
    fig.update_layout(
        **_layout(title=dict(text=f"Revenue vs Expenditure ({mode})", font=dict(size=12), x=0)),
        barmode="group",
        yaxis_title="₹ Crore",
    )
    return fig


def ch_fd(sdf, fy, vm):
    col = "actuals_cumulative" if "Cumulative" in vm else "actuals_monthly"
    fdf = sdf[sdf["fy"] == fy].sort_values("fy_month_order")
    fd = fdf[fdf["indicator_id"] == "fiscal_deficit"][["month_name", col, "be"]]
    if fd.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fd["month_name"], y=fd[col],
        mode="lines+markers",
        name="Fiscal Deficit",
        line=dict(color=C["red"], width=2.5),
        marker=dict(size=7, color=C["red"]),
        fill="tozeroy",
        fillcolor="rgba(192,57,43,0.07)",
        hovertemplate="<b>%{x}</b><br>Deficit: %{customdata}<extra></extra>",
        customdata=[fmt_short(v) for v in fd[col]],
    ))

    # FIX: BE annotation — more visible, positioned inside chart not at edge
    if not fd["be"].isna().all() and fd["be"].iloc[0]:
        be_v = fd["be"].iloc[0] / 12 if "Monthly" in vm else fd["be"].iloc[0]
        fig.add_hline(
            y=be_v,
            line_dash="dash",
            line_color=C["orange"],
            line_width=1.8,
            annotation_text=f"  BE: {fmt_short(be_v)}",
            annotation_position="top left",   # FIX: was "right" — moved to avoid clipping
            annotation_font_size=10,
            annotation_font_color=C["orange"],
        )

    fig.update_layout(
        **_layout(title=dict(text="Fiscal Deficit Trajectory", font=dict(size=12), x=0)),
        yaxis_title="₹ Crore",
    )
    return fig


def ch_pct_be(fy_df, month):
    mdf = fy_df[fy_df["fy_month_order"] == month]
    inds = [
        "revenue_receipts", "tax_revenue", "revenue_expenditure",
        "capital_expenditure", "total_expenditure", "fiscal_deficit",
    ]
    rows = []
    for ind in inds:
        r = mdf[mdf["indicator_id"] == ind]
        if r.empty:
            continue
        p = r["pct_be_current"].values[0]
        if p is not None and not (isinstance(p, float) and np.isnan(p)):
            rows.append({"Indicator": INDICATOR_NAMES[ind], "pct": p})
    if not rows:
        return None

    rdf = pd.DataFrame(rows).sort_values("pct")
    clrs = [C["red"] if v > 100 else C["blue"] for v in rdf["pct"]]

    # FIX: horizontal bar — needs different margin (no xaxis tickangle)
    layout = _layout(
        title=dict(text="% of Budget Estimate Achieved", font=dict(size=12), x=0),
        margin=dict(l=8, r=50, t=40, b=12),  # horizontal: small bottom
        height=CHART_H,
    )
    # Remove xaxis tickangle for horizontal bar
    layout["xaxis"] = dict(
        range=[0, max(rdf["pct"].max() * 1.2, 115)],
        showgrid=True,
        gridcolor="#F0F4F8",
        ticksuffix="%",
        tickfont=dict(size=11),
    )
    layout["yaxis"] = dict(showgrid=False, tickfont=dict(size=11))

    fig = go.Figure(go.Bar(
        x=rdf["pct"],
        y=rdf["Indicator"],
        orientation="h",
        marker_color=clrs,
        text=[f"{v:.1f}%" for v in rdf["pct"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.1f}% of BE<extra></extra>",
    ))
    fig.add_vline(x=100, line_dash="dash", line_color="#888", line_width=1.5,
                  annotation_text="100%", annotation_position="top",
                  annotation_font_size=10, annotation_font_color="#888")
    fig.update_layout(**layout)
    return fig


def ch_exp_pie(fy_df, month, vm):
    col = "actuals_cumulative" if "Cumulative" in vm else "actuals_monthly"
    mdf = fy_df[fy_df["fy_month_order"] == month]
    items = {
        "Salaries":  "salaries_wages",
        "Interest":  "interest_payments",
        "Pension":   "pension",
        "Subsidy":   "subsidy",
        "Capital":   "capital_expenditure",
    }
    labs, vals = [], []
    for k, ind in items.items():
        r = mdf[mdf["indicator_id"] == ind][col].values
        if len(r) > 0 and r[0] and not (isinstance(r[0], float) and np.isnan(r[0])) and r[0] > 0:
            labs.append(k)
            vals.append(abs(r[0]))
    if not labs:
        return None

    pie_colors = [C["blue"], C["red"], C["purple"], C["teal"], C["orange"]]
    fig = go.Figure(go.Pie(
        labels=labs, values=vals, hole=0.44,
        marker=dict(colors=pie_colors),
        textinfo="percent+label",
        textfont_size=11,
        hovertemplate="<b>%{label}</b><br>%{percent}<br>%{customdata}<extra></extra>",
        customdata=[fmt_short(v) for v in vals],
    ))
    # FIX: pie chart margin — no bottom space needed for x-axis
    fig.update_layout(
        font=dict(family="Inter, Arial, sans-serif", size=11),
        plot_bgcolor="white", paper_bgcolor="white",
        height=CHART_H,
        margin=dict(l=8, r=8, t=40, b=8),
        title=dict(text="Expenditure Composition", font=dict(size=12), x=0),
        showlegend=True,
        legend=dict(
            orientation="v", x=1.02, y=0.5,
            font=dict(size=11),
        ),
        hoverlabel=dict(bgcolor="white", bordercolor="#CCC", font_size=12),
    )
    return fig


def ch_multistate(df, ind_id, fy, month):
    mdf = df[
        (df["indicator_id"] == ind_id) &
        (df["fy"] == fy) &
        (df["fy_month_order"] == month) &
        (df["data_quality"].isin([DQ_OK, DQ_MANUAL]))
    ].sort_values("actuals_cumulative", ascending=False)

    if mdf.empty:
        return None

    clrs = [C["red"] if v < 0 else C["blue"] for v in mdf["actuals_cumulative"]]
    fig = go.Figure(go.Bar(
        x=mdf["state"],
        y=mdf["actuals_cumulative"],
        marker_color=clrs,
        text=[fmt_short(v) for v in mdf["actuals_cumulative"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>",
        customdata=[fmt_short(v) for v in mdf["actuals_cumulative"]],
    ))
    # FIX: more bottom margin for state names (longer text than month names)
    layout = _layout(
        title=dict(text=f"{INDICATOR_NAMES[ind_id]} — All States | FY {fy}", font=dict(size=12), x=0),
        margin=dict(l=8, r=16, t=40, b=90),  # b=90 for state name labels
        height=400,
    )
    layout["yaxis"]["title"] = "₹ Crore"
    layout["xaxis"]["tickangle"] = -45
    fig.update_layout(**layout)
    return fig


# ─────────────────────────────────────────────────────────
# CHART WRAPPER — renders chart inside a card div
# ─────────────────────────────────────────────────────────
def show_chart(fig, key=None):
    if fig:
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, key=key,
                        config={"displayModeBar": False})  # FIX: hide plotly toolbar for cleaner look
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Insufficient data for this chart.")


# ─────────────────────────────────────────────────────────
# TAB 1: STATE ANALYSIS
# ─────────────────────────────────────────────────────────
def tab_state(df, state, fy, month, month_label, vm):
    sdf  = df[df["state"] == state]
    fy_df = sdf[sdf["fy"] == fy]
    col  = "actuals_cumulative" if "Cumulative" in vm else "actuals_monthly"
    mdf  = fy_df[fy_df["fy_month_order"] == month]
    mode_label = vm.replace("📈 ", "").replace("📅 ", "")

    st.markdown(f"""
<div class="view-banner">
  📅 <strong>{state}</strong> &nbsp;|&nbsp; FY: <strong>{fy}</strong>
  &nbsp;|&nbsp; Month: <strong>{month_label}</strong>
  &nbsp;|&nbsp; Mode: <strong>{mode_label}</strong>
</div>""", unsafe_allow_html=True)

    def get(ind_id):
        r = mdf[mdf["indicator_id"] == ind_id]
        if r.empty:
            return None
        v = r[col].values[0]
        return None if (isinstance(v, float) and np.isnan(v)) else v

    sub = "Cumulative YTD" if "Cumulative" in vm else "This month only"

    # ── METRICS ──
    st.markdown('<div class="sec-hdr">📌 Key Metrics</div>', unsafe_allow_html=True)
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1: metric_card("Revenue Receipts",     get("revenue_receipts"),     sub, "green")
    with m2: metric_card("Total Expenditure",    get("total_expenditure"),    sub, "orange")
    with m3: metric_card("Fiscal Deficit",       get("fiscal_deficit"),       "(–) = deficit", "red")
    with m4: metric_card("Capital Expenditure",  get("capital_expenditure"),  "Infra & devpt", "purple")
    with m5:
        rv = get("revenue_surplus_deficit")
        metric_card("Revenue Surplus/Deficit", rv, "(+) = surplus",
                    "green" if (rv or 0) > 0 else "red")

    # ── CHARTS ──
    st.markdown('<div class="sec-hdr">📈 Charts</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: show_chart(ch_rev_exp(sdf, fy, vm), key="rev_exp")
    with c2: show_chart(ch_fd(sdf, fy, vm),      key="fd")

    c3, c4 = st.columns(2)
    with c3: show_chart(ch_pct_be(fy_df, month),      key="pct_be")
    with c4: show_chart(ch_exp_pie(fy_df, month, vm), key="pie")

    # ── ALL INDICATORS TABLE ──
    st.markdown('<div class="sec-hdr">📋 All Indicators</div>', unsafe_allow_html=True)
    tdf = mdf[["indicator_group", "indicator_name", "be", col,
               "pct_be_current", "pct_be_prev_year", "data_quality"]].copy()
    tdf.columns = ["Group", "Indicator", "BE (₹ Cr)", "Actuals (₹ Cr)",
                   "% BE (Cur)", "% BE (Prev FY)", "Quality"]
    for cc in ["BE (₹ Cr)", "Actuals (₹ Cr)"]:
        tdf[cc] = tdf[cc].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
    for cc in ["% BE (Cur)", "% BE (Prev FY)"]:
        tdf[cc] = tdf[cc].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
    st.dataframe(tdf, use_container_width=True, height=460, hide_index=True)


# ─────────────────────────────────────────────────────────
# TAB 2: STATE COMPARISON
# ─────────────────────────────────────────────────────────
def tab_compare(df, fy, month, vm):
    st.markdown('<div class="sec-hdr">🗺️ Multi-State Comparison</div>', unsafe_allow_html=True)
    sel_ind = st.selectbox(
        "Select Indicator", INDICATOR_IDS,
        format_func=lambda x: INDICATOR_NAMES[x],
        index=INDICATOR_IDS.index("revenue_receipts"),
    )
    show_chart(ch_multistate(df, sel_ind, fy, month), key="multistate")

    st.markdown('<div class="sec-hdr">📊 State Rankings</div>', unsafe_allow_html=True)
    rdf = df[
        (df["indicator_id"] == sel_ind) &
        (df["fy"] == fy) &
        (df["fy_month_order"] == month) &
        (df["data_quality"].isin([DQ_OK, DQ_MANUAL]))
    ][["state", "category", "actuals_cumulative", "pct_be_current"]].copy()
    rdf = rdf.sort_values("actuals_cumulative", ascending=False).reset_index(drop=True)
    rdf.index += 1
    rdf["actuals_cumulative"] = rdf["actuals_cumulative"].apply(fmt)
    rdf["pct_be_current"]     = rdf["pct_be_current"].apply(pstr)
    rdf.columns = ["State", "Category", "Actuals", "% of BE"]
    st.dataframe(rdf, use_container_width=True, hide_index=False)


# ─────────────────────────────────────────────────────────
# TAB 3: DATA QUALITY & OVERRIDE
# ─────────────────────────────────────────────────────────
def tab_dq(df):
    st.markdown('<div class="sec-hdr">🔍 Data Quality Overview</div>', unsafe_allow_html=True)
    rows = []
    for state in sorted(df["state"].unique()):
        sdf   = df[df["state"] == state]
        total = len(sdf)
        ok    = len(sdf[sdf["data_quality"].isin([DQ_OK, DQ_MANUAL])])
        pe    = len(sdf[sdf["data_quality"] == DQ_PARSE_ERROR])
        pdfe  = len(sdf[sdf["data_quality"] == DQ_PDF_ERROR])
        pct   = round(ok / total * 100, 1) if total > 0 else 0
        rows.append({
            "State": state,
            "Completeness %": f"{pct}%",
            "✅ OK": ok,
            "⚠️ Parse Err": pe,
            "❌ PDF Err": pdfe,
            "Total": total,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown('<div class="sec-hdr">⚠️ Records Needing Attention</div>', unsafe_allow_html=True)
    issues = df[~df["data_quality"].isin([DQ_OK, DQ_MANUAL])].copy()
    issues = issues[["state", "fy", "month_name", "indicator_name",
                     "data_quality", "be", "actuals_cumulative", "pdf_url"]]
    issues = issues.sort_values(["state", "fy", "indicator_name"])
    st.dataframe(issues, use_container_width=True, height=280, hide_index=True)

    st.markdown('<div class="sec-hdr">✏️ Add Manual Override</div>', unsafe_allow_html=True)
    st.caption("Fill missing or corrected data below. Saved to `inputs/manual_overrides.csv`.")
    months_map = {
        "April": 1, "May": 2, "June": 3, "July": 4,
        "August": 5, "September": 6, "October": 7, "November": 8,
        "December": 9, "January": 10, "February": 11, "March": 12,
    }
    with st.form("ov_form"):
        co1, co2, co3 = st.columns(3)
        with co1:
            ov_state = st.selectbox("State", sorted(df["state"].unique()))
            ov_fy    = st.selectbox("FY", sorted(df["fy"].unique(), reverse=True))
        with co2:
            ov_mon = st.selectbox("Month", list(months_map.keys()))
            ov_ind = st.selectbox("Indicator", INDICATOR_IDS,
                                  format_func=lambda x: INDICATOR_NAMES[x])
        with co3:
            ov_be  = st.number_input("BE (₹ Cr)", value=0.0, format="%.2f")
            ov_act = st.number_input("Actuals Cumulative (₹ Cr)", value=0.0, format="%.2f")
        co4, co5 = st.columns(2)
        with co4: ov_pc = st.number_input("% BE (Current FY)", value=0.0, format="%.2f")
        with co5: ov_pp = st.number_input("% BE (Prev FY)",    value=0.0, format="%.2f")
        ov_notes = st.text_input("Notes / Source")
        if st.form_submit_button("💾 Save Override", type="primary"):
            nr = {
                "state": ov_state, "fy": ov_fy,
                "calendar_month": months_map[ov_mon], "month_name": ov_mon,
                "indicator_id": ov_ind, "be": ov_be,
                "actuals_cumulative": ov_act,
                "pct_be_current": ov_pc, "pct_be_prev_year": ov_pp,
                "data_quality": "MANUAL", "notes": ov_notes,
            }
            Path(INPUTS_DIR).mkdir(exist_ok=True)
            fp = Path(MANUAL_OVERRIDES)
            ex = pd.read_csv(fp) if fp.exists() else pd.DataFrame()
            up = pd.concat([ex, pd.DataFrame([nr])], ignore_index=True)
            up = up.drop_duplicates(
                subset=["state", "fy", "calendar_month", "indicator_id"], keep="last"
            )
            up.to_csv(fp, index=False)
            st.success(f"✅ Saved: {ov_state} | {ov_fy} | {ov_mon} | {INDICATOR_NAMES[ov_ind]}")
            st.info("Re-run pipeline: `python pipeline.py --mode update`")

    ovdf = load_overrides()
    if not ovdf.empty:
        st.markdown('<div class="sec-hdr">📋 Existing Overrides</div>', unsafe_allow_html=True)
        st.dataframe(ovdf, use_container_width=True, height=200, hide_index=True)


# ─────────────────────────────────────────────────────────
# TAB 4: ABOUT
# ─────────────────────────────────────────────────────────
def tab_about():
    st.markdown("""
## 📊 About Fiscal Pulse
**Fiscal Pulse** tracks monthly fiscal data of Indian states from CAG Monthly Key Indicator reports.

### 🎯 Who is this for?
Policy professionals, UPSC aspirants, journalists covering state budgets, and state finance departments.

### 📋 Data Source
Publicly available PDFs from **CAG** at [cag.gov.in](https://cag.gov.in). 25 states covered.

### 📐 26 Indicators Tracked
Revenue Receipts, Tax Revenue (SGST, Stamps, Land Revenue, Sales Tax, Excise, Union Taxes Share, Other),
Non-Tax Revenue, Grants-in-Aid, Capital Receipts, Recovery of Loans, Borrowings, Total Receipts,
Revenue Expenditure (Interest, Salaries, Pension, Subsidy), Capital Expenditure, Total Expenditure,
Loans Disbursed, Revenue Surplus/Deficit, Fiscal Deficit, Primary Deficit.

### 🔄 Update Frequency
Auto-runs on **25th of every month** via GitHub Actions.

### 🔒 Disclaimer
Independent research tool. Always cross-verify with official sources for policy decisions.
""")
    st.markdown("""
<div class="brand-footer">
  📊 <strong>Fiscal Pulse</strong> &nbsp;|&nbsp;
  Built by <strong>Alok Barnwal</strong>, Public Finance Expert &nbsp;|&nbsp;
  <a href="https://linkedin.com/in/aloksbarnwal">LinkedIn ↗</a> &nbsp;|&nbsp;
  Data: CAG Monthly Key Indicators &nbsp;|&nbsp; <em>India's fiscal data, simplified</em>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def main():
    df   = load_data()
    meta = load_metadata()

    last_upd = meta.get("last_updated", "")
    if last_upd:
        try:
            last_upd = datetime.fromisoformat(last_upd).strftime("%d %b %Y, %H:%M")
        except Exception:
            pass

    st.markdown(f"""
<div class="page-title">
  <span class="page-title-text">📊 Fiscal Pulse</span>
  <div class="page-title-sub">
    India State Finance Dashboard &nbsp;|&nbsp; CAG Monthly Key Indicators
    &nbsp;|&nbsp; Last updated: <strong>{last_upd}</strong>
    &nbsp;|&nbsp; States: <strong>{meta.get('total_states', '—')}</strong>
    &nbsp;|&nbsp; Records: <strong>{len(df):,}</strong>
  </div>
</div>""", unsafe_allow_html=True)

    if df.empty:
        st.warning("⚠️ No data found. Run: `python pipeline.py --mode historical`")
        tab_about()
        return

    state, fy, month, month_label, vm = render_sidebar(df)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📍 State Analysis",
        "🗺️ State Comparison",
        "🔍 Data Quality & Override",
        "ℹ️ About",
    ])
    with tab1: tab_state(df, state, fy, month, month_label, vm)
    with tab2: tab_compare(df, fy, month, vm)
    with tab3: tab_dq(df)
    with tab4: tab_about()

    st.markdown("""
<div class="brand-footer">
  📊 <strong>Fiscal Pulse</strong> &nbsp;|&nbsp;
  Built by <strong>Alok Barnwal</strong>, Public Finance Expert &nbsp;|&nbsp;
  <a href="https://linkedin.com/in/aloksbarnwal">LinkedIn ↗</a> &nbsp;|&nbsp;
  Source: CAG Monthly Key Indicators &nbsp;|&nbsp; <em>India's fiscal data, simplified</em>
</div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()