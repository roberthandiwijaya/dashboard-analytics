import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from src.chat import answer_question, is_in_scope
from src.data_loader import load_ads_files, load_sample_file
from src.database import (
    TABLE_COLUMNS,
    clear_active_rows,
    get_ads,
    get_import_batches,
    import_ads,
    init_db,
    save_editor_rows,
    soft_delete_rows,
)
from src.metrics import aggregate_by_ad, build_summary
from src.recommendations import build_recommendations


ROOT = Path(__file__).resolve().parent
SAMPLE_FILE = ROOT / "Data-+Semua-Iklan-Produk-01_06_2026-29_06_2026.csv"
TEMPLATE_FILE = ROOT / "data" / "templates" / "ads_import_template.xlsx"
DB_FILE = ROOT / "data" / "ads_dashboard.sqlite"

load_dotenv(ROOT / ".env")


st.set_page_config(
    page_title="Ads Performance Dashboard",
    layout="wide",
)


def format_idr(value):
    try:
        return "IDR {:,.0f}".format(float(value))
    except (TypeError, ValueError):
        return "IDR 0"


def format_ratio(value, suffix="x"):
    try:
        return "{:,.2f}{}".format(float(value), suffix)
    except (TypeError, ValueError):
        return "0.00{}".format(suffix)


def empty_state():
    st.info("No saved ads data yet. Open Data Manager to import a CSV/XLSX file or load the bundled Shopee sample.")
    if TEMPLATE_FILE.exists():
        with open(TEMPLATE_FILE, "rb") as file:
            st.download_button(
                "Download import template",
                data=file,
                file_name="ads_import_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def render_sidebar():
    st.sidebar.header("Data")
    st.sidebar.caption("Manage saved rows from the Data Manager tab.")

    if TEMPLATE_FILE.exists():
        with open(TEMPLATE_FILE, "rb") as file:
            st.sidebar.download_button(
                "Download XLSX template",
                data=file,
                file_name="ads_import_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def render_ai_settings():
    st.sidebar.header("AI Settings")

    provider_options = {
        "Rule-based only": "",
        "Ollama": "ollama",
        "DeepSeek": "deepseek",
        "OpenAI-compatible": "openai-compatible",
        "OpenRouter": "openrouter",
        "LiteLLM": "litellm",
    }
    env_provider = os.environ.get("AI_PROVIDER", "")
    default_label = next(
        (label for label, value in provider_options.items() if value == env_provider),
        "Rule-based only",
    )
    provider_label = st.sidebar.selectbox(
        "Provider",
        list(provider_options.keys()),
        index=list(provider_options.keys()).index(default_label),
        help="Frontend settings override .env for this browser session.",
    )
    provider = provider_options[provider_label]

    settings = {"provider": provider}
    if not provider:
        st.sidebar.caption("Uses built-in analytics rules. No external AI endpoint is called.")
        return settings

    if provider == "ollama":
        settings["model"] = st.sidebar.text_input(
            "Model",
            value=os.environ.get("AI_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3.1"),
        )
        settings["ollama_base_url"] = st.sidebar.text_input(
            "Ollama base URL",
            value=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        st.sidebar.caption("In Docker Desktop, use http://host.docker.internal:11434 for host Ollama.")
        return settings

    default_base_urls = {
        "deepseek": "https://api.deepseek.com",
        "openrouter": "https://openrouter.ai/api/v1",
        "litellm": "http://localhost:4000/v1",
        "openai-compatible": os.environ.get("AI_BASE_URL", ""),
    }
    default_models = {
        "deepseek": "deepseek-v4-flash",
        "openrouter": "deepseek/deepseek-chat",
        "litellm": os.environ.get("AI_MODEL", ""),
        "openai-compatible": os.environ.get("AI_MODEL", ""),
    }

    settings["base_url"] = st.sidebar.text_input(
        "Base URL",
        value=os.environ.get("AI_BASE_URL", default_base_urls.get(provider, "")),
    )
    settings["api_key"] = st.sidebar.text_input(
        "API key",
        value=os.environ.get("AI_API_KEY", ""),
        type="password",
    )
    settings["model"] = st.sidebar.text_input(
        "Model",
        value=os.environ.get("AI_MODEL", default_models.get(provider, "")),
    )
    settings["temperature"] = st.sidebar.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=float(os.environ.get("AI_TEMPERATURE", "0.2")),
        step=0.1,
    )
    st.sidebar.caption("API keys entered here stay in this Streamlit session and are not written to disk.")
    return settings


def render_filters(df):
    st.sidebar.header("Filters")
    platforms = sorted(df["platform"].dropna().unique().tolist())
    statuses = sorted(df["status"].dropna().unique().tolist())
    selected_platforms = st.sidebar.multiselect("Platform", platforms, default=platforms)
    selected_statuses = st.sidebar.multiselect("Status", statuses, default=statuses)

    filtered = df.copy()
    if selected_platforms:
        filtered = filtered[filtered["platform"].isin(selected_platforms)]
    if selected_statuses:
        filtered = filtered[filtered["status"].isin(selected_statuses)]

    if "period_start" in filtered.columns and filtered["period_start"].notna().any():
        min_date = filtered["period_start"].min().date()
        max_date = filtered["period_end"].max().date()
        date_range = st.sidebar.date_input("Period", value=(min_date, max_date))
        if len(date_range) == 2:
            start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            filtered = filtered[
                (filtered["period_start"] <= end) & (filtered["period_end"] >= start)
            ]

    return filtered


def render_kpis(summary):
    columns = st.columns(6)
    columns[0].metric("Spend", format_idr(summary["spend"]))
    columns[1].metric("Revenue", format_idr(summary["revenue"]))
    columns[2].metric("ROAS", format_ratio(summary["roas"]))
    columns[3].metric("ACOS", format_ratio(summary["acos"] * 100, "%"))
    columns[4].metric("Conversions", "{:,.0f}".format(summary["conversions"]))
    columns[5].metric("CPA", format_idr(summary["cpa"]))


def render_charts(df):
    st.subheader("Performance")
    ad_data = aggregate_by_ad(df)
    left, right = st.columns(2)

    with left:
        top_spend = ad_data.sort_values("spend", ascending=False).head(10)
        fig = px.bar(
            top_spend,
            x="spend",
            y="ad_name",
            color="platform",
            orientation="h",
            title="Top Spend Ads",
            labels={"spend": "Spend", "ad_name": "Ad"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
        st.plotly_chart(fig, width="stretch")

    with right:
        top_roas = ad_data[ad_data["spend"] > 0].sort_values("roas", ascending=False).head(10)
        fig = px.bar(
            top_roas,
            x="roas",
            y="ad_name",
            color="platform",
            orientation="h",
            title="Top ROAS Ads",
            labels={"roas": "ROAS", "ad_name": "Ad"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
        st.plotly_chart(fig, width="stretch")

    if df["granularity"].eq("daily").any() and "date" in df.columns:
        daily = (
            df.dropna(subset=["date"])
            .groupby(["date", "platform"], as_index=False)
            .agg({"spend": "sum", "revenue": "sum", "conversions": "sum"})
        )
        daily["roas"] = daily["revenue"] / daily["spend"].replace(0, pd.NA)
        fig = px.line(
            daily,
            x="date",
            y="spend",
            color="platform",
            title="Daily Spend Trend",
            markers=True,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.caption("Daily trend charts will appear when daily imports are uploaded.")


def render_recommendations(df):
    st.subheader("Recommendations")
    recommendations = build_recommendations(df)
    st.dataframe(
        recommendations[
            [
                "action",
                "priority",
                "platform",
                "ad_name",
                "status",
                "spend",
                "revenue",
                "conversions",
                "roas",
                "acos",
                "reason",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    return recommendations


def render_chat(df, recommendations, ai_settings):
    st.subheader("Guarded Analytics Chat")
    st.caption("Ask about ads performance, spend, ROAS, ACOS, CPA, conversions, or optimization.")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "I can help analyze this ads data and recommend what to pause, review, scale, or monitor.",
            }
        ]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    prompt = st.chat_input("Ask about your ads data")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    if not is_in_scope(prompt):
        response = "I can only help with ads performance and analytics for this dashboard."
    else:
        response = answer_question(prompt, df, recommendations, ai_settings)

    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.write(response)


def render_dashboard(df, ai_settings):
    if df.empty:
        empty_state()
        return

    filtered = render_filters(df)

    if filtered.empty:
        st.warning("No rows match the current filters.")
        return

    summary = build_summary(filtered)
    render_kpis(summary)
    render_charts(filtered)
    recommendations = render_recommendations(filtered)

    st.subheader("Imported Rows")
    st.dataframe(filtered, width="stretch", hide_index=True)

    render_chat(filtered, recommendations, ai_settings)


def _editor_frame(df):
    editor_df = df.copy()
    if editor_df.empty:
        editor_df = pd.DataFrame(columns=["delete", "id"] + TABLE_COLUMNS)
    else:
        editor_df.insert(0, "delete", False)

    for column in ["date", "period_start", "period_end"]:
        if column in editor_df.columns:
            editor_df[column] = pd.to_datetime(editor_df[column], errors="coerce").dt.strftime("%Y-%m-%d")
            editor_df[column] = editor_df[column].fillna("")

    ordered_columns = ["delete", "id"] + TABLE_COLUMNS
    for column in ordered_columns:
        if column not in editor_df.columns:
            editor_df[column] = ""
    return editor_df[ordered_columns]


def render_import_tools(db_path):
    st.subheader("Import")
    import_left, import_right = st.columns([2, 1])

    with import_left:
        uploaded_files = st.file_uploader(
            "Upload CSV/XLSX files into saved data",
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            key="manager_upload",
        )
        if uploaded_files and st.button("Import uploaded files", type="primary"):
            imported_df, errors = load_ads_files(uploaded_files)
            for error in errors:
                st.warning(error)
            if imported_df is not None:
                rows = import_ads(db_path, imported_df, "uploaded files")
                st.success("Imported {:,.0f} rows.".format(rows))
                st.rerun()

    with import_right:
        st.write("")
        st.write("")
        if st.button("Load bundled Shopee sample", disabled=not SAMPLE_FILE.exists()):
            sample_df, errors = load_sample_file(SAMPLE_FILE)
            for error in errors:
                st.warning(error)
            if sample_df is not None:
                rows = import_ads(db_path, sample_df, SAMPLE_FILE.name)
                st.success("Imported {:,.0f} sample rows.".format(rows))
                st.rerun()

    if TEMPLATE_FILE.exists():
        with open(TEMPLATE_FILE, "rb") as file:
            st.download_button(
                "Download import template",
                data=file,
                file_name="ads_import_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="manager_template_download",
            )


def render_data_editor(db_path):
    st.subheader("Spreadsheet Editor")
    saved_df = get_ads(db_path)
    editor_df = _editor_frame(saved_df)

    edited_df = st.data_editor(
        editor_df,
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        disabled=["id", "source_file", "roas", "acos", "cpa", "ctr", "conversion_rate"],
        column_config={
            "delete": st.column_config.CheckboxColumn("Delete", default=False),
            "id": st.column_config.NumberColumn("ID"),
            "spend": st.column_config.NumberColumn("Spend", min_value=0),
            "revenue": st.column_config.NumberColumn("Revenue", min_value=0),
            "impressions": st.column_config.NumberColumn("Impressions", min_value=0),
            "clicks": st.column_config.NumberColumn("Clicks", min_value=0),
            "conversions": st.column_config.NumberColumn("Conversions", min_value=0),
            "roas": st.column_config.NumberColumn("ROAS"),
            "acos": st.column_config.NumberColumn("ACOS"),
            "cpa": st.column_config.NumberColumn("CPA"),
            "ctr": st.column_config.NumberColumn("CTR"),
            "conversion_rate": st.column_config.NumberColumn("Conversion rate"),
        },
        key="ads_data_editor",
    )

    button_cols = st.columns([1, 1, 1, 4])
    with button_cols[0]:
        if st.button("Save changes", type="primary"):
            updated, inserted = save_editor_rows(db_path, edited_df)
            st.success("Saved {:,.0f} edited rows and {:,.0f} new rows.".format(updated, inserted))
            st.rerun()

    selected_for_delete = edited_df[edited_df["delete"].fillna(False)]
    with button_cols[1]:
        delete_confirmed = st.checkbox("Confirm delete")
    with button_cols[2]:
        if st.button("Delete selected", disabled=selected_for_delete.empty or not delete_confirmed):
            deleted = soft_delete_rows(db_path, selected_for_delete["id"].dropna().tolist())
            st.success("Deleted {:,.0f} rows from active data.".format(deleted))
            st.rerun()

    if not saved_df.empty:
        csv_bytes = saved_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export saved data as CSV",
            data=csv_bytes,
            file_name="ads_saved_data.csv",
            mime="text/csv",
        )


def render_danger_zone(db_path):
    with st.expander("Danger zone"):
        st.caption("Clear active rows uses soft delete. Existing rows are removed from the dashboard but kept in the SQLite database with deleted metadata.")
        confirm = st.checkbox("I understand this will remove all active rows from the dashboard")
        if st.button("Clear active data", disabled=not confirm):
            deleted = clear_active_rows(db_path)
            st.success("Cleared {:,.0f} active rows.".format(deleted))
            st.rerun()


def render_import_history(db_path):
    history = get_import_batches(db_path)
    if not history.empty:
        st.subheader("Import History")
        st.dataframe(history, width="stretch", hide_index=True)


def render_data_manager(db_path):
    render_import_tools(db_path)
    render_data_editor(db_path)
    render_danger_zone(db_path)
    render_import_history(db_path)


def main():
    init_db(DB_FILE)
    st.title("Ads Performance Dashboard")
    render_sidebar()
    ai_settings = render_ai_settings()

    dashboard_tab, manager_tab = st.tabs(["Dashboard", "Data Manager"])

    with dashboard_tab:
        render_dashboard(get_ads(DB_FILE), ai_settings)

    with manager_tab:
        render_data_manager(DB_FILE)


if __name__ == "__main__":
    main()
