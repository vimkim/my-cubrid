import csv
import json

input_file = "combined.jsonl"
output_file = "output.csv"

# Read each line, parse JSON into Python dict
with open(input_file, "r") as f:
    data = [json.loads(line) for line in f if line.strip()]

# Write to CSV
with open(output_file, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

print(f"CSV file created: {output_file}")
