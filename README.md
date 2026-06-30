# Ads Performance Dashboard

Python dashboard for tracking ad spend and performance across platforms, starting with Shopee Ads CSV exports.

## Features

- Upload CSV or XLSX ad performance files.
- Auto-detect Shopee Indonesia Product Ads exports.
- Normalize platform data into one reporting format.
- Track spend, revenue, ROAS, ACOS, CPA, CTR, conversion rate, and conversions.
- Recommend ads to pause, review, scale, or monitor.
- Guarded analytics chat that only answers questions related to ad performance and this project.
- Import template XLSX for daily or monthly data.
- Optional AI chat through Ollama or OpenAI-compatible endpoints such as DeepSeek.
- Spreadsheet-style Data Manager backed by SQLite.

## Tech Stack

- Streamlit for the dashboard UI.
- Pandas for data cleaning and analytics.
- Plotly for charts.
- OpenPyXL / XlsxWriter for Excel import template generation.

## Quick Start

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\generate_template.py
streamlit run app.py
```

If PowerShell blocks venv activation, run:

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

## Docker

Build and run with Docker:

```powershell
docker build -t ads-dashboard .
docker run --rm -p 8501:8501 --env-file .env ads-dashboard
```

If you do not have a `.env` file yet, create an empty one or omit `--env-file .env`.

Run with Docker Compose:

```powershell
docker compose up --build
```

Compose mounts `./data` into the container so the SQLite database survives container restarts.
On Docker Desktop for Windows, the service runs as root inside the container so SQLite can write to the bind-mounted `./data` folder.

Open:

```text
http://localhost:8501
```

For Ollama running on your host machine from Docker Desktop, use this in `.env`:

```text
AI_PROVIDER=ollama
AI_MODEL=llama3.1
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

For DeepSeek or another hosted OpenAI-compatible endpoint, the same `.env` values work inside Docker:

```text
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=your_api_key_here
AI_MODEL=deepseek-v4-flash
AI_TEMPERATURE=0.2
```

## Data Import

The app supports:

- Native Shopee Ads CSV exports like `Data-+Semua-Iklan-Produk-01_06_2026-29_06_2026.csv`.
- Shopee on-platform XLSX reports with a `By Campaign Type` sheet.
- The generated template at `data/templates/ads_import_template.xlsx`.

Daily data is recommended for trend charts, alerts, and better AI analysis. Monthly data is useful for summaries and reconciliation.

## Data Manager

Open the **Data Manager** tab to manage saved ads data.

You can:

- Import Shopee CSV exports or template XLSX files.
- Load the bundled Shopee sample.
- Edit rows in a spreadsheet-style table.
- Add rows directly in the table.
- Select rows for deletion and confirm before deleting.
- Clear active data with confirmation.
- Export saved rows as CSV.

The dashboard reads from the saved SQLite database at:

```text
data/ads_dashboard.sqlite
```

Calculated fields such as ROAS, ACOS, CPA, CTR, and conversion rate are recalculated when rows are saved.

## Guardrails

The analytics assistant only responds to questions about:

- Ads spend and performance.
- Campaigns, ad groups, ads, products, and platforms.
- ROAS, ACOS, CPA, CTR, conversion rate, revenue, and conversions.
- Budget, pause, review, scale, and optimization recommendations.

Unrelated questions are rejected.

## Optional AI Chat

The dashboard works without any LLM by using deterministic analytics rules. To enable richer local AI answers with an open-source model:

```powershell
ollama pull llama3.1
@"
AI_PROVIDER=ollama
AI_MODEL=llama3.1
OLLAMA_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
"@ | Set-Content .env
```

Then restart Streamlit.

To use an OpenAI-compatible endpoint such as DeepSeek:

```powershell
@"
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=your_api_key_here
AI_MODEL=deepseek-v4-flash
AI_TEMPERATURE=0.2
"@ | Set-Content .env
```

The app sends only the compact selected ads context and the user's analytics question to the configured endpoint. Keep `AI_PROVIDER` blank if you want the fully local rule-based assistant.

You can also change the AI provider from the dashboard sidebar under **AI Settings**. Sidebar settings override `.env` for the current Streamlit session and are not saved to disk. Use `.env` when you want persistent Docker or production settings.
