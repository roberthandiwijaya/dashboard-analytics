import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.data_loader import CANONICAL_COLUMNS, NUMERIC_COLUMNS


DATE_COLUMNS = ["date", "period_start", "period_end"]
TEXT_COLUMNS = [column for column in CANONICAL_COLUMNS if column not in NUMERIC_COLUMNS]
TABLE_COLUMNS = CANONICAL_COLUMNS


def connect(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db(db_path):
    text_defs = ",\n            ".join(
        "{} TEXT".format(column) for column in TEXT_COLUMNS
    )
    numeric_defs = ",\n            ".join(
        "{} REAL NOT NULL DEFAULT 0".format(column) for column in NUMERIC_COLUMNS
    )
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ads_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {text_defs},
                {numeric_defs},
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            )
            """.format(text_defs=text_defs, numeric_defs=numeric_defs)
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                rows_imported INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _clean_text(value):
    if pd.isna(value):
        return ""
    return str(value)


def _clean_number(value):
    if pd.isna(value) or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date_to_text(value):
    if pd.isna(value) or value == "":
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _recalculate(row):
    spend = _clean_number(row.get("spend"))
    revenue = _clean_number(row.get("revenue"))
    clicks = _clean_number(row.get("clicks"))
    impressions = _clean_number(row.get("impressions"))
    conversions = _clean_number(row.get("conversions"))

    row["roas"] = revenue / spend if spend else 0.0
    row["acos"] = spend / revenue if revenue else 0.0
    row["cpa"] = spend / conversions if conversions else 0.0
    row["ctr"] = clicks / impressions if impressions else 0.0
    row["conversion_rate"] = conversions / clicks if clicks else 0.0
    return row


def normalize_for_storage(df):
    normalized = df.copy()
    for column in TABLE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = "" if column in TEXT_COLUMNS else 0.0

    for column in DATE_COLUMNS:
        normalized[column] = normalized[column].apply(_date_to_text)

    for column in TEXT_COLUMNS:
        if column not in DATE_COLUMNS:
            normalized[column] = normalized[column].apply(_clean_text)

    for column in NUMERIC_COLUMNS:
        normalized[column] = normalized[column].apply(_clean_number)

    normalized = normalized.apply(_recalculate, axis=1)
    return normalized[TABLE_COLUMNS]


def _is_blank_row(row):
    important_fields = ["platform", "campaign_name", "ad_name", "spend", "revenue", "clicks"]
    return all(str(row.get(field, "")).strip() in {"", "0", "0.0"} for field in important_fields)


def import_ads(db_path, df, source_file=None):
    normalized = normalize_for_storage(df)
    now = datetime.utcnow().isoformat(timespec="seconds")
    rows = []
    for _, row in normalized.iterrows():
        if _is_blank_row(row):
            continue
        record = row.to_dict()
        if source_file:
            record["source_file"] = source_file
        rows.append(record)

    if not rows:
        return 0

    placeholders = ", ".join(["?"] * (len(TABLE_COLUMNS) + 2))
    column_sql = ", ".join(TABLE_COLUMNS + ["created_at", "updated_at"])
    values = [
        [record.get(column, "" if column in TEXT_COLUMNS else 0.0) for column in TABLE_COLUMNS]
        + [now, now]
        for record in rows
    ]

    with closing(connect(db_path)) as conn:
        conn.executemany(
            "INSERT INTO ads_performance ({}) VALUES ({})".format(column_sql, placeholders),
            values,
        )
        conn.execute(
            "INSERT INTO import_batches (source_file, rows_imported, imported_at) VALUES (?, ?, ?)",
            (source_file or "manual", len(rows), now),
        )
        conn.commit()
    return len(rows)


def get_ads(db_path, include_deleted=False):
    where = "" if include_deleted else "WHERE deleted_at IS NULL"
    with closing(connect(db_path)) as conn:
        df = pd.read_sql_query(
            "SELECT id, {} FROM ads_performance {} ORDER BY id".format(
                ", ".join(TABLE_COLUMNS), where
            ),
            conn,
        )
    if df.empty:
        return pd.DataFrame(columns=["id"] + TABLE_COLUMNS)
    for column in DATE_COLUMNS:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df


def save_editor_rows(db_path, edited_df):
    if edited_df.empty:
        return 0, 0

    edited = edited_df.drop(columns=["delete"], errors="ignore").copy()
    normalized = normalize_for_storage(edited)
    if "id" in edited.columns:
        normalized.insert(0, "id", edited["id"])
    else:
        normalized.insert(0, "id", pd.NA)

    now = datetime.utcnow().isoformat(timespec="seconds")
    updated = 0
    inserted = 0
    set_sql = ", ".join("{} = ?".format(column) for column in TABLE_COLUMNS)
    insert_columns = TABLE_COLUMNS + ["created_at", "updated_at"]
    insert_placeholders = ", ".join(["?"] * len(insert_columns))

    with closing(connect(db_path)) as conn:
        for _, row in normalized.iterrows():
            if _is_blank_row(row):
                continue
            values = [row.get(column, "" if column in TEXT_COLUMNS else 0.0) for column in TABLE_COLUMNS]
            row_id = row.get("id")
            if pd.notna(row_id) and str(row_id).strip() != "":
                conn.execute(
                    "UPDATE ads_performance SET {}, updated_at = ? WHERE id = ?".format(set_sql),
                    values + [now, int(row_id)],
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO ads_performance ({}) VALUES ({})".format(
                        ", ".join(insert_columns), insert_placeholders
                    ),
                    values + [now, now],
                )
                inserted += 1
        conn.commit()
    return updated, inserted


def soft_delete_rows(db_path, row_ids):
    ids = [int(row_id) for row_id in row_ids if pd.notna(row_id)]
    if not ids:
        return 0
    now = datetime.utcnow().isoformat(timespec="seconds")
    placeholders = ", ".join(["?"] * len(ids))
    with closing(connect(db_path)) as conn:
        conn.execute(
            "UPDATE ads_performance SET deleted_at = ?, updated_at = ? WHERE id IN ({})".format(
                placeholders
            ),
            [now, now] + ids,
        )
        conn.commit()
    return len(ids)


def clear_active_rows(db_path):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with closing(connect(db_path)) as conn:
        cursor = conn.execute(
            "UPDATE ads_performance SET deleted_at = ?, updated_at = ? WHERE deleted_at IS NULL",
            (now, now),
        )
        rowcount = cursor.rowcount
        conn.commit()
    return rowcount


def get_import_batches(db_path):
    with closing(connect(db_path)) as conn:
        return pd.read_sql_query(
            "SELECT source_file, rows_imported, imported_at FROM import_batches ORDER BY id DESC",
            conn,
        )
