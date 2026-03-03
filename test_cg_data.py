import pandas as pd
df = pd.read_csv('data/master.csv')
cg_df = df[df['state'] == 'Chhattisgarh']
cols = cg_df.columns.tolist()
print("Columns:", cols)
cols_to_print = ['fy', 'month_name', 'indicator_id'] + [c for c in cols if 'be' in c or 'actual' in c]
if len(cg_df) > 0:
    print(f"Total rows: {len(cg_df)}")
    print(cg_df.head(10)[cols_to_print])
    print(cg_df[cols_to_print].isna().sum())
else:
    print("No data for Chhattisgarh.")
