# 📊 Fiscal Pulse
**India State Finance Dashboard | Powered by CAG Monthly Key Indicators**

> Tracking monthly fiscal data of 25 Indian states — Revenue, Expenditure, Fiscal Deficit, Capital Expenditure and more.

---

## 🗂️ Project Structure

```
fiscal_pulse/
├── app.py                    ← Streamlit dashboard (public website)
├── pipeline.py               ← Main data pipeline
├── parser.py                 ← PDF text extraction & indicator parsing
├── excel_exporter.py         ← Formatted Office Excel generator
├── config.py                 ← All states, indicators, constants
├── requirements.txt
│
├── inputs/
│   ├── gsdp_input.xlsx       ← Fill GSDP data here (you do this manually)
│   └── manual_overrides.csv  ← Add missing/corrected data here
│
├── data/
│   ├── master.csv            ← Long-format master dataset (auto-generated)
│   ├── metadata.json         ← Pipeline run info
│   ├── pipeline.log          ← Detailed logs
│   └── states/               ← Per-state CSVs
│       ├── chhattisgarh.csv
│       ├── andhra_pradesh.csv
│       └── ...
│
├── outputs/
│   └── CAG_Monthly_Key_Indicators_Office.xlsx  ← EY office file
│
└── .github/
    └── workflows/
        └── monthly_update.yml  ← Auto-runs on 25th each month
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. First-time historical data pull
```bash
python pipeline.py --mode historical
```
This will collect ~2 years of data for all 25 states. Takes ~30-45 minutes.

### 3. Run the dashboard
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`

### 4. Monthly update (run on 25th)
```bash
python pipeline.py --mode update
```

### 5. Single state run
```bash
python pipeline.py --mode state --state "Chhattisgarh"
```

---

## 📋 States Covered

| Status | States |
|--------|--------|
| ✅ Monthly MKI data | Andhra Pradesh, Arunachal Pradesh, Assam, Bihar, Chhattisgarh, Gujarat, Haryana, Himachal Pradesh, Jharkhand, Karnataka, Kerala, Maharashtra, Manipur, Meghalaya, Mizoram, Nagaland, Odisha, Rajasthan, Sikkim, Tamil Nadu, Telangana, Tripura, **Uttar Pradesh**, Uttarakhand, West Bengal |
| ⚠️ Annual data only | Madhya Pradesh, Punjab |
| ❌ No CAG monthly data | Delhi, Goa |

---

## 📊 Indicators Tracked (26)

**Receipts:** Revenue Receipts, Tax Revenue (SGST, Stamps & Registration, Land Revenue, Sales Tax, State Excise, Union Taxes Share, Other Taxes), Non-Tax Revenue, Grants-in-Aid, Capital Receipts, Recovery of Loans, Borrowings, Total Receipts

**Expenditure:** Revenue Expenditure (Interest Payments, Salaries & Wages, Pension, Subsidy), Capital Expenditure, Total Expenditure, Loans Disbursed

**Fiscal Position:** Revenue Surplus/Deficit, Fiscal Deficit, Primary Deficit

---

## 📝 Manual Override System

When CAG data is missing or has parsing errors, add data manually:

### Option 1: Dashboard form (easiest)
1. Go to **Data Quality & Override** tab in the dashboard
2. Fill the form with state, month, indicator and values
3. Click **Save Override**
4. Re-run pipeline: `python pipeline.py --mode update`

### Option 2: Edit CSV directly
Edit `inputs/manual_overrides.csv`:

```csv
state,fy,calendar_month,month_name,indicator_id,be,actuals_cumulative,...
Chhattisgarh,2024-25,4,April,revenue_receipts,250000,12500,5.0,4.8,MANUAL,CG Budget 2024-25
```

**Indicator IDs reference:**
| Indicator | ID |
|-----------|-----|
| Revenue Receipts | `revenue_receipts` |
| Tax Revenue | `tax_revenue` |
| SGST / GST | `sgst` |
| Stamps & Registration | `stamps_registration` |
| Non-Tax Revenue | `non_tax_revenue` |
| Grants-in-Aid | `grants_in_aid` |
| Capital Receipts | `capital_receipts` |
| Borrowings | `borrowings` |
| Total Receipts | `total_receipts` |
| Revenue Expenditure | `revenue_expenditure` |
| Interest Payments | `interest_payments` |
| Salaries & Wages | `salaries_wages` |
| Pension | `pension` |
| Subsidy | `subsidy` |
| Capital Expenditure | `capital_expenditure` |
| Total Expenditure | `total_expenditure` |
| Fiscal Deficit | `fiscal_deficit` |
| Revenue Surplus/Deficit | `revenue_surplus_deficit` |
| Primary Deficit | `primary_deficit` |

---

## 🌐 GSDP Data Entry

Fill `inputs/gsdp_input.xlsx` → **📊 GSDP_Data** sheet:
- Yellow cells = input values in ₹ Crore
- One row per state, one column per financial year
- Source: MoSPI, RBI State Finances Report, State Budget documents

---

## 🌐 Deploy to Streamlit Cloud (Free Public URL)

1. Push project to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set **Main file:** `app.py`
5. Click **Deploy**

Your public URL: `https://your-app-name.streamlit.app`

---

## 🔄 GitHub Actions Auto-Update

The pipeline auto-runs on **25th of every month** at 11:30 AM IST.

To set up:
1. Push repo to GitHub
2. Actions will run automatically
3. Updated CSVs are committed back to repo
4. Streamlit Cloud picks up changes automatically

Manual trigger: GitHub → Actions → "Fiscal Pulse Monthly Update" → Run workflow

---

## 🔍 Data Quality Flags

| Flag | Meaning |
|------|---------|
| `OK` | Successfully parsed from CAG PDF |
| `MANUAL` | Manually entered via override |
| `PARSE_ERROR` | PDF downloaded but indicator not found |
| `PDF_ERROR` | PDF download failed |
| `MISSING` | Month not yet uploaded on CAG website |

---

## 📬 Contact

**Alok Barnwal** | Public Finance Expert | EY  
[LinkedIn](https://linkedin.com/in/alokbarnwal)

---

*Fiscal Pulse v1.0 | Data: CAG Monthly Key Indicators | India's fiscal data, simplified*
