import pandas as pd

df = pd.read_csv('data/master.csv')
cg_df = df[df['state'] == 'Chhattisgarh']

print("\n--- Recent data check ---")
for fy in ['2023-24', '2024-25', '2025-26']:
    subset = cg_df[cg_df['fy'] == fy]
    months = subset['month_name'].unique()
    print(f"FY {fy}: {len(subset)} rows across {len(months)} months: {months}")
    if len(subset) > 0:
        bad_rows = subset[subset['be'].isna() | subset['actuals_cumulative'].isna()]
        print(f"   Missing BE/Actuals: {len(bad_rows)} rows")

# Let's inspect data_quality
print("\n--- Data Quality Breakdown ---")
print(cg_df['data_quality'].value_counts())

# Check recent months data explicitly
recent = cg_df[cg_df['fy'].isin(['2024-25', '2025-26'])]
if not recent.empty:
    print("\nSample recent data:")
    print(recent.head()[['fy', 'month_name', 'indicator_id', 'be', 'actuals_cumulative', 'data_quality']])
