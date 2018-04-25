import pandas as pd
import sys
f=pd.read_csv(sys.argv[1])
keep_col = ['Date','Open','High','Low','Close','Volume']
new_f = f[keep_col]
new_f.to_csv(sys.argv[1], index=False)
