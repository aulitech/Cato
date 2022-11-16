import pandas as pd

df = pd.read_csv("raw_full_scale_data.csv", names = ["time", "gx", "gy", "gz"], header = None )
print(df)
update_times = []
for row in range(len(df) - 1):
    if df.loc[row]["gx"] != df.loc[row+1]["gx"]:
        update_times.append(df.loc[row + 1]["time"] - df.loc[row]["time"])

for t in update_times:
    print(f"{t:.4f}")

mean = sum(update_times) / len(update_times)
print(f"Mean: {mean}")
print(f"To freq: {1.0/mean} HZ")