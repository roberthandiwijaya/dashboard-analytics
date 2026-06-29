import csv
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd


CANONICAL_COLUMNS = [
    "platform",
    "account_name",
    "store_name",
    "campaign_name",
    "ad_group_name",
    "ad_name",
    "ad_id",
    "product_code",
    "status",
    "bidding_mode",
    "placement",
    "date",
    "period_start",
    "period_end",
    "granularity",
    "impressions",
    "clicks",
    "ctr",
    "add_to_cart",
    "add_to_cart_rate",
    "conversions",
    "direct_conversions",
    "conversion_rate",
    "direct_conversion_rate",
    "cpa",
    "direct_cpa",
    "units_sold",
    "direct_units_sold",
    "revenue",
    "direct_revenue",
    "spend",
    "roas",
    "direct_roas",
    "acos",
    "direct_acos",
    "voucher_amount",
    "vouchered_sales",
    "source_file",
]


TEMPLATE_ALIASES = {
    "platform": "platform",
    "account": "account_name",
    "account_name": "account_name",
    "store": "store_name",
    "store_name": "store_name",
    "campaign": "campaign_name",
    "campaign_name": "campaign_name",
    "ad_group": "ad_group_name",
    "ad_group_name": "ad_group_name",
    "ad": "ad_name",
    "ad_name": "ad_name",
    "ad_id": "ad_id",
    "product_code": "product_code",
    "status": "status",
    "bidding_mode": "bidding_mode",
    "placement": "placement",
    "date": "date",
    "period_start": "period_start",
    "period_end": "period_end",
    "granularity": "granularity",
    "impressions": "impressions",
    "clicks": "clicks",
    "ctr": "ctr",
    "add_to_cart": "add_to_cart",
    "add_to_cart_rate": "add_to_cart_rate",
    "conversions": "conversions",
    "direct_conversions": "direct_conversions",
    "conversion_rate": "conversion_rate",
    "direct_conversion_rate": "direct_conversion_rate",
    "cpa": "cpa",
    "direct_cpa": "direct_cpa",
    "units_sold": "units_sold",
    "direct_units_sold": "direct_units_sold",
    "revenue": "revenue",
    "direct_revenue": "direct_revenue",
    "spend": "spend",
    "roas": "roas",
    "direct_roas": "direct_roas",
    "acos": "acos",
    "direct_acos": "direct_acos",
    "voucher_amount": "voucher_amount",
    "vouchered_sales": "vouchered_sales",
}


SHOPEE_MAP = {
    "Nama Iklan": "ad_name",
    "Status": "status",
    "Kode Produk": "product_code",
    "Mode Bidding": "bidding_mode",
    "Penempatan Iklan": "placement",
    "Dilihat": "impressions",
    "Jumlah Klik": "clicks",
    "Persentase Klik": "ctr",
    "Add to Cart": "add_to_cart",
    "Add to Cart Rate": "add_to_cart_rate",
    "Konversi": "conversions",
    "Konversi Langsung": "direct_conversions",
    "Tingkat konversi": "conversion_rate",
    "Tingkat Konversi Langsung": "direct_conversion_rate",
    "Biaya per Konversi": "cpa",
    "Biaya per Konversi Langsung": "direct_cpa",
    "Produk Terjual": "units_sold",
    "Terjual Langsung": "direct_units_sold",
    "Omzet Penjualan": "revenue",
    "Penjualan Langsung (GMV Langsung)": "direct_revenue",
    "Biaya": "spend",
    "Efektifitas Iklan": "roas",
    "Efektivitas Langsung": "direct_roas",
    "Persentase Biaya Iklan terhadap Penjualan dari Iklan (ACOS)": "acos",
    "Persentase Biaya Iklan terhadap Penjualan dari Iklan Langsung (ACOS Langsung)": "direct_acos",
    "Voucher Amount": "voucher_amount",
    "Vouchered Sales": "vouchered_sales",
}


NUMERIC_COLUMNS = [
    "impressions",
    "clicks",
    "ctr",
    "add_to_cart",
    "add_to_cart_rate",
    "conversions",
    "direct_conversions",
    "conversion_rate",
    "direct_conversion_rate",
    "cpa",
    "direct_cpa",
    "units_sold",
    "direct_units_sold",
    "revenue",
    "direct_revenue",
    "spend",
    "roas",
    "direct_roas",
    "acos",
    "direct_acos",
    "voucher_amount",
    "vouchered_sales",
]


def _clean_number(value):
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in {"", "-"}:
        return 0.0
    is_percent = text.endswith("%")
    text = text.replace("%", "").replace(",", "").replace("IDR", "").strip()
    try:
        number = float(text)
    except ValueError:
        return 0.0
    if is_percent:
        return number / 100
    return number


def _normalize_dates(df):
    for column in ["date", "period_start", "period_end"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce", dayfirst=True)
    return df


def _finalize(df, source_file):
    for column in CANONICAL_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    for column in NUMERIC_COLUMNS:
        df[column] = df[column].apply(_clean_number)

    df = _normalize_dates(df)
    df["source_file"] = source_file
    df["platform"] = df["platform"].fillna("Unknown")
    df["status"] = df["status"].fillna("Unknown")
    df["granularity"] = df["granularity"].fillna("period")

    if df["roas"].eq(0).all():
        df["roas"] = df["revenue"] / df["spend"].replace(0, pd.NA)
        df["roas"] = df["roas"].fillna(0)
    if df["acos"].eq(0).all():
        df["acos"] = df["spend"] / df["revenue"].replace(0, pd.NA)
        df["acos"] = df["acos"].fillna(0)

    return df[CANONICAL_COLUMNS]


def _read_text(file_obj):
    if isinstance(file_obj, (str, Path)):
        return Path(file_obj).read_text(encoding="utf-8-sig")
    raw = file_obj.getvalue()
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8-sig")


def _metadata_value(lines, label):
    for line in lines:
        cells = next(csv.reader([line]))
        if cells and cells[0] == label and len(cells) > 1:
            return cells[1]
    return None


def _parse_period(text):
    if not text or " - " not in text:
        return pd.NaT, pd.NaT
    start, end = text.split(" - ", 1)
    return pd.to_datetime(start, dayfirst=True, errors="coerce"), pd.to_datetime(
        end, dayfirst=True, errors="coerce"
    )


def _is_shopee_export(text):
    return "Laporan Iklan Produk - Shopee Indonesia" in text and "Nama Iklan" in text


def _load_shopee_csv(file_obj, source_file):
    text = _read_text(file_obj)
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        if line.startswith("Urutan,Nama Iklan,Status"):
            header_index = index
            break
    if header_index is None:
        raise ValueError("Could not find Shopee Ads table header.")

    table_text = "\n".join(lines[header_index:])
    df = pd.read_csv(StringIO(table_text))
    df = df.rename(columns=SHOPEE_MAP)

    period_start, period_end = _parse_period(_metadata_value(lines, "Periode"))
    df["platform"] = "Shopee Ads"
    df["account_name"] = _metadata_value(lines, "Username")
    df["store_name"] = _metadata_value(lines, "Nama Toko")
    df["campaign_name"] = df["ad_name"]
    df["period_start"] = period_start
    df["period_end"] = period_end
    df["granularity"] = "period"
    return _finalize(df, source_file)


def _load_template_dataframe(df, source_file):
    renamed = {}
    for column in df.columns:
        key = str(column).strip().lower().replace(" ", "_")
        if key in TEMPLATE_ALIASES:
            renamed[column] = TEMPLATE_ALIASES[key]
    normalized = df.rename(columns=renamed)
    return _finalize(normalized, source_file)


def load_one_file(file_obj, source_file):
    suffix = Path(source_file).suffix.lower()
    if suffix == ".csv":
        text = _read_text(file_obj)
        if _is_shopee_export(text):
            return _load_shopee_csv(BytesIO(text.encode("utf-8")), source_file)
        df = pd.read_csv(StringIO(text))
        return _load_template_dataframe(df, source_file)

    if suffix == ".xlsx":
        df = pd.read_excel(file_obj, sheet_name="ads_data")
        return _load_template_dataframe(df, source_file)

    raise ValueError("Unsupported file type: {}".format(source_file))


def load_ads_files(uploaded_files):
    frames = []
    errors = []
    for uploaded_file in uploaded_files:
        try:
            frames.append(load_one_file(uploaded_file, uploaded_file.name))
        except Exception as exc:
            errors.append("Could not import {}: {}".format(uploaded_file.name, exc))
    if not frames:
        return None, errors
    return pd.concat(frames, ignore_index=True), errors


def load_sample_file(path):
    try:
        return load_one_file(path, str(path.name)), []
    except Exception as exc:
        return None, ["Could not import sample file: {}".format(exc)]
