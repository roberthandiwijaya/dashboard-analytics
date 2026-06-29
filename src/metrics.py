import pandas as pd


def safe_divide(numerator, denominator):
    if denominator in (0, None) or pd.isna(denominator):
        return 0.0
    return float(numerator) / float(denominator)


def build_summary(df):
    spend = float(df["spend"].sum())
    revenue = float(df["revenue"].sum())
    conversions = float(df["conversions"].sum())
    clicks = float(df["clicks"].sum())
    impressions = float(df["impressions"].sum())
    return {
        "spend": spend,
        "revenue": revenue,
        "conversions": conversions,
        "clicks": clicks,
        "impressions": impressions,
        "roas": safe_divide(revenue, spend),
        "acos": safe_divide(spend, revenue),
        "cpa": safe_divide(spend, conversions),
        "cpc": safe_divide(spend, clicks),
        "ctr": safe_divide(clicks, impressions),
        "conversion_rate": safe_divide(conversions, clicks),
    }


def aggregate_by_ad(df):
    group_columns = ["platform", "ad_name", "status"]
    grouped = (
        df.groupby(group_columns, dropna=False, as_index=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            conversions=("conversions", "sum"),
            revenue=("revenue", "sum"),
            spend=("spend", "sum"),
        )
        .fillna({"ad_name": "Unknown ad", "status": "Unknown"})
    )
    grouped["roas"] = grouped["revenue"] / grouped["spend"].replace(0, pd.NA)
    grouped["acos"] = grouped["spend"] / grouped["revenue"].replace(0, pd.NA)
    grouped["cpa"] = grouped["spend"] / grouped["conversions"].replace(0, pd.NA)
    grouped["ctr"] = grouped["clicks"] / grouped["impressions"].replace(0, pd.NA)
    grouped["conversion_rate"] = grouped["conversions"] / grouped["clicks"].replace(0, pd.NA)
    numeric_columns = [
        "impressions",
        "clicks",
        "conversions",
        "revenue",
        "spend",
        "roas",
        "acos",
        "cpa",
        "ctr",
        "conversion_rate",
    ]
    for column in numeric_columns:
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0)
    return grouped
