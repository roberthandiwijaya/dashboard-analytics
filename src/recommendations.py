from src.metrics import aggregate_by_ad


def _priority_sort(action):
    order = {
        "Pause / investigate": 1,
        "Review": 2,
        "Scale carefully": 3,
        "Monitor": 4,
        "Already paused": 5,
    }
    return order.get(action, 9)


def build_recommendations(df):
    ads = aggregate_by_ad(df)
    rows = []

    total_spend = float(ads["spend"].sum())
    median_roas = float(ads.loc[ads["spend"] > 0, "roas"].median() or 0)
    min_meaningful_spend = max(total_spend * 0.005, 50000)

    for _, row in ads.iterrows():
        status = str(row["status"])
        spend = float(row["spend"])
        revenue = float(row["revenue"])
        conversions = float(row["conversions"])
        roas = float(row["roas"])
        acos = float(row["acos"])

        if "Dijeda" in status or status.lower() in {"paused", "pause", "inactive"}:
            action = "Already paused"
            reason = "This ad is already paused, so no new action is needed."
        elif spend >= min_meaningful_spend and conversions == 0:
            action = "Pause / investigate"
            reason = "It has meaningful spend but zero conversions."
        elif spend >= min_meaningful_spend and roas > 0 and median_roas > 0 and roas < median_roas * 0.65:
            action = "Review"
            reason = "ROAS is materially below the current account median."
        elif spend >= min_meaningful_spend and acos >= 0.30:
            action = "Review"
            reason = "ACOS is high, meaning ad cost is taking too much of attributed sales."
        elif spend >= min_meaningful_spend and roas >= max(median_roas * 1.35, 6):
            action = "Scale carefully"
            reason = "ROAS is strong compared with the current account benchmark."
        else:
            action = "Monitor"
            reason = "Performance is not triggering a pause or scale rule."

        rows.append(
            {
                "priority": _priority_sort(action),
                "action": action,
                "platform": row["platform"],
                "ad_name": row["ad_name"],
                "status": status,
                "spend": round(spend, 0),
                "revenue": round(revenue, 0),
                "conversions": round(conversions, 0),
                "roas": round(roas, 2),
                "acos": round(acos, 4),
                "reason": reason,
            }
        )

    recommendations = ads.iloc[0:0].copy()
    if rows:
        import pandas as pd

        recommendations = pd.DataFrame(rows)
        recommendations = recommendations.sort_values(
            ["priority", "spend"], ascending=[True, False]
        ).reset_index(drop=True)
    return recommendations
