from typing import List, Dict
from models import Bucket, Giant
from math import isclose

def normalize_percents(buckets: List[Bucket]) -> List[float]:
    total = sum(b.percent for b in buckets)
    if total <= 0:
        return [0.0 for _ in buckets]
    if not isclose(total, 100.0, abs_tol=0.01):
        norm = 100.0 / total
    else:
        norm = 1.0
    return [round(b.percent * norm, 2) for b in buckets]

def compute_bucket_splits(buckets: List[Bucket], total_income: float) -> List[Dict]:
    percents = normalize_percents(buckets)
    out = []
    for b, p in zip(buckets, percents):
        value = round(total_income * (p / 100.0), 2)
        out.append({
            "bucket_id": b.id,
            "name": b.name,
            "percent_effective": p,
            "value": value
        })
    return out

def payoff_efficiency(giant: Giant, monthly_input: float) -> Dict:
    if monthly_input <= 0:
        return {"r_per_1k": 0.0, "months_to_victory": None}
    eff = round(1000.0 / monthly_input, 2)
    months = int((giant.total_to_pay + (monthly_input - 1)) // monthly_input)
    return {"r_per_1k": eff, "months_to_victory": months}
    