from pathlib import Path

import xlsxwriter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "templates" / "ads_import_template.xlsx"


COLUMNS = [
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
]


EXAMPLE_ROWS = [
    [
        "Shopee Ads",
        "idolahometextile",
        "Idola Style Official Store",
        "Shop GMV Max",
        "",
        "Shop GMV Max",
        "",
        "",
        "Berjalan",
        "GMV Max Auto Bidding (Shop)",
        "Semua Penempatan",
        "2026-06-01",
        "2026-06-01",
        "2026-06-01",
        "daily",
        5824,
        268,
        0.046,
        0,
        0,
        8,
        4,
        0.0299,
        0.0149,
        16539,
        31132,
        9,
        4,
        1095440,
        613201,
        127747,
        8.58,
        4.80,
        0.1166,
        0.2083,
        103352,
        517308,
    ],
    [
        "Meta Ads",
        "Main account",
        "",
        "June Prospecting",
        "Broad Audience",
        "UGC Variant A",
        "23800000001",
        "",
        "Active",
        "Lowest cost",
        "Feed/Reels",
        "2026-06-01",
        "2026-06-01",
        "2026-06-01",
        "daily",
        12000,
        240,
        0.02,
        18,
        0.075,
        6,
        0,
        0.025,
        0,
        50000,
        0,
        6,
        0,
        900000,
        0,
        300000,
        3,
        0,
        0.3333,
        0,
        0,
        0,
    ],
]


DEFINITIONS = [
    ("platform", "Ad platform name, for example Shopee Ads, Meta Ads, Google Ads."),
    ("date", "Use for daily rows. Leave blank for monthly summary rows if needed."),
    ("period_start / period_end", "Reporting period covered by the row."),
    ("granularity", "daily, weekly, monthly, or period."),
    ("spend", "Ad cost in account currency. Use numbers only."),
    ("revenue", "Attributed sales or conversion value. Use numbers only."),
    ("roas", "Revenue divided by spend. Optional; app can calculate it."),
    ("acos", "Spend divided by revenue. Optional; app can calculate it."),
    ("ctr / conversion_rate", "Use decimal format, for example 4.5% should be 0.045."),
]


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(OUTPUT))

    header_format = workbook.add_format(
        {"bold": True, "bg_color": "#1F4E78", "font_color": "white", "border": 1}
    )
    text_format = workbook.add_format({"border": 1})
    number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
    percent_format = workbook.add_format({"border": 1, "num_format": "0.00%"})
    date_format = workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd"})
    note_format = workbook.add_format({"text_wrap": True, "valign": "top"})

    ads_sheet = workbook.add_worksheet("ads_data")
    for col, name in enumerate(COLUMNS):
        ads_sheet.write(0, col, name, header_format)
        width = max(14, min(len(name) + 4, 28))
        ads_sheet.set_column(col, col, width)

    percent_columns = {"ctr", "add_to_cart_rate", "conversion_rate", "direct_conversion_rate", "acos", "direct_acos"}
    date_columns = {"date", "period_start", "period_end"}

    for row_index, row in enumerate(EXAMPLE_ROWS, start=1):
        for col_index, value in enumerate(row):
            column_name = COLUMNS[col_index]
            if column_name in date_columns:
                ads_sheet.write(row_index, col_index, value, date_format)
            elif column_name in percent_columns:
                ads_sheet.write(row_index, col_index, value, percent_format)
            elif isinstance(value, (int, float)):
                ads_sheet.write(row_index, col_index, value, number_format)
            else:
                ads_sheet.write(row_index, col_index, value, text_format)

    ads_sheet.freeze_panes(1, 0)
    ads_sheet.autofilter(0, 0, len(EXAMPLE_ROWS), len(COLUMNS) - 1)

    definitions_sheet = workbook.add_worksheet("definitions")
    definitions_sheet.write(0, 0, "Field", header_format)
    definitions_sheet.write(0, 1, "Definition", header_format)
    definitions_sheet.set_column(0, 0, 24)
    definitions_sheet.set_column(1, 1, 90)
    for row_index, (field, definition) in enumerate(DEFINITIONS, start=1):
        definitions_sheet.write(row_index, 0, field, text_format)
        definitions_sheet.write(row_index, 1, definition, note_format)

    workbook.close()
    print("Generated {}".format(OUTPUT))


if __name__ == "__main__":
    main()
