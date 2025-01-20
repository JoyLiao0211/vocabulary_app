import pandas as pd
from math import floor
df=pd.read_csv("contents0.csv")
n=len(df)

output=[0]*10

for i in range(n):
  a = int(floor(10*df.loc[i]["score"]))
  output[a]+=1

for i in range(10):
  output[i]/=n
  output[i]=round(output[i]*100)

# print(output)

for i in range(9,-1,-1):
  print(f"{i*10}: {output[i]} %")
