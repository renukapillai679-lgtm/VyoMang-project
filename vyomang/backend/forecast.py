"""Demand forecast (trend + festival uplift, with a 4-week backtest) and reorder recommendations."""
import math
from datetime import date, timedelta

FESTIVALS = [("Diwali", "2026-11-08", 0.60), ("Christmas", "2026-12-25", 0.25),
             ("New Year", "2027-01-01", 0.15), ("Holi", "2027-03-04", 0.30)]


def fit(history):
    """Straight-line trend through the last 12 weeks. Returns intercept, slope, n, noise."""
    y = history[-12:]
    n = len(y)
    sx, sy = sum(range(n)), sum(y)
    sxy = sum(i * v for i, v in enumerate(y))
    sxx = sum(i * i for i in range(n))
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    a = (sy - b * sx) / n
    sd = math.sqrt(sum((v - a - b * i) ** 2 for i, v in enumerate(y)) / (n - 2))
    return a, b, n, sd


def bump(days_to_festival):
    """Demand ramps up over the 14 days before a festival and fades 4 days after."""
    x = days_to_festival
    if x > 14 or x < -4:
        return 0
    return 1 - x / 14 * 0.6 if x >= 0 else 0.4 * (1 + x / 4)


def forecast(history, festival_sens, weeks, today):
    a, b, n, sd = fit(history)
    out = []
    for j in range(weeks):
        mid = today + timedelta(days=j * 7 + 3)
        uplift, name = 0.0, None
        for fname, fdate, u in FESTIVALS:
            v = festival_sens * u * bump((date.fromisoformat(fdate) - mid).days)
            if v > uplift:
                uplift, name = v, fname
        v = (a + b * (n + j)) * (1 + uplift)
        width = 1.28 * sd * math.sqrt(1 + j / 3)
        out.append({"v": v, "up": uplift, "fn": name, "lo": max(0.0, v - width), "hi": v + width})
    return out


def accuracy(history):
    a, b, n, _ = fit(history[:-4])
    err = 0.0
    for j in range(4):
        actual = history[len(history) - 4 + j]
        err += abs(a + b * (n + j) - actual) / actual
    return math.floor((1 - err / 4) * 1000 + 0.5) / 10


def recommend(sku, history, today):
    """sku is a dict with id, festival_sens, lead_time, on_hand."""
    F = forecast(history, sku["festival_sens"], 12, today)
    daily = lambda k: F[min(11, k // 7)]["v"] / 7
    need = lambda days: sum(daily(k) for k in range(days))
    cum, cover = 0.0, None
    for k in range(84):
        d = daily(k)
        if cum + d >= sku["on_hand"]:
            cover = k + (sku["on_hand"] - cum) / d
            break
        cum += d
    if cover is None:
        cover = 84 + (sku["on_hand"] - cum) / daily(83)
    lead = sku["lead_time"]
    sd = fit(history)[3]
    safety = math.ceil(1.65 * sd / math.sqrt(7) * math.sqrt(lead))
    qty = max(0, math.ceil((need(lead + 14) + safety - sku["on_hand"]) / 10) * 10)
    if cover < lead:
        status = "CRITICAL"
    elif cover < lead + 7:
        status = "LOW"
    elif cover > 45:
        status = "OVER"
    else:
        status = "HEALTHY"
    return {"id": sku["id"], "cover": cover, "safety_stock": safety,
            "reorder_point": math.ceil(need(lead) + safety), "order_qty": qty,
            "status": status, "accuracy": accuracy(history),
            "order_by_days": None if qty == 0 else max(0, math.floor(cover - lead))}
