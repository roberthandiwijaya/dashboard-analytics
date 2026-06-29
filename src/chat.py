import os

import requests

from src.metrics import aggregate_by_ad, build_summary


GUARDRAIL_SYSTEM_PROMPT = (
    "You are a guarded ads analytics assistant. Only answer questions about "
    "this dashboard's ads data, spend, ROAS, ACOS, CPA, CTR, conversions, "
    "revenue, platforms, campaigns, products, and optimization. If the user "
    "asks anything unrelated, answer exactly: I can only help with ads "
    "performance and analytics for this dashboard. Use only the provided "
    "context. Do not invent rows, platforms, or external facts. Recommend "
    "pausing ads only as a recommendation requiring human approval."
)


SCOPE_KEYWORDS = {
    "ad",
    "ads",
    "advertising",
    "iklan",
    "campaign",
    "campaigns",
    "platform",
    "spend",
    "biaya",
    "budget",
    "performance",
    "roas",
    "acos",
    "cpa",
    "cpc",
    "ctr",
    "conversion",
    "conversions",
    "konversi",
    "click",
    "clicks",
    "impression",
    "impressions",
    "revenue",
    "sales",
    "gmv",
    "omzet",
    "pause",
    "turn off",
    "scale",
    "recommend",
    "recommendation",
    "optimize",
    "shopee",
    "meta",
    "google",
    "tiktok",
    "linkedin",
    "product",
    "produk",
    "dashboard",
    "data",
}


BLOCKED_KEYWORDS = {
    "weather",
    "recipe",
    "movie",
    "politics",
    "dating",
    "health",
    "medical",
    "legal",
    "homework",
    "poem",
    "song",
    "travel",
    "sports",
}


def is_in_scope(question):
    text = question.lower()
    if any(keyword in text for keyword in BLOCKED_KEYWORDS):
        return False
    return any(keyword in text for keyword in SCOPE_KEYWORDS)


def _money(value):
    return "IDR {:,.0f}".format(float(value))


def _ratio(value):
    return "{:,.2f}x".format(float(value))


def _percent(value):
    return "{:,.2f}%".format(float(value) * 100)


def _format_ad_line(row):
    return (
        "- {ad}: spend {spend}, revenue {revenue}, ROAS {roas}, "
        "conversions {conversions:.0f}, action {action}"
    ).format(
        ad=row["ad_name"],
        spend=_money(row["spend"]),
        revenue=_money(row["revenue"]),
        roas=_ratio(row["roas"]),
        conversions=row["conversions"],
        action=row["action"],
    )


def _compact_context(df, recommendations):
    summary = build_summary(df)
    top_recommendations = recommendations.head(8).to_dict(orient="records")
    top_ads = (
        aggregate_by_ad(df)
        .sort_values("spend", ascending=False)
        .head(12)
        .to_dict(orient="records")
    )
    return {
        "summary": summary,
        "recommendations": top_recommendations,
        "top_ads_by_spend": top_ads,
    }


def _messages(question, df, recommendations):
    return [
        {
            "role": "system",
            "content": GUARDRAIL_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": "Context: {}\n\nQuestion: {}".format(
                _compact_context(df, recommendations), question
            ),
        },
    ]


def _setting(settings, key, env_key=None, default=""):
    if settings and settings.get(key) not in (None, ""):
        return str(settings.get(key)).strip()
    return os.getenv(env_key or key.upper(), default).strip()


def _ollama_answer(question, df, recommendations, model, settings=None):
    base_url = _setting(
        settings, "ollama_base_url", "OLLAMA_BASE_URL", "http://localhost:11434"
    ).rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "messages": _messages(question, df, recommendations),
    }

    try:
        response = requests.post(
            "{}/api/chat".format(base_url), json=payload, timeout=20
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        return content or None
    except requests.RequestException:
        return None


def _openai_compatible_answer(question, df, recommendations, model, settings=None):
    base_url = _setting(settings, "base_url", "AI_BASE_URL").rstrip("/")
    api_key = _setting(settings, "api_key", "AI_API_KEY")
    if not base_url or not api_key:
        return None

    try:
        temperature = float(_setting(settings, "temperature", "AI_TEMPERATURE", "0.2"))
    except ValueError:
        temperature = 0.2

    payload = {
        "model": model,
        "messages": _messages(question, df, recommendations),
        "temperature": temperature,
    }
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            "{}/chat/completions".format(base_url),
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() or None
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


def _llm_answer(question, df, recommendations, settings=None):
    provider = _setting(settings, "provider", "AI_PROVIDER").lower()
    model = _setting(settings, "model", "AI_MODEL")

    if not provider and _setting(settings, "ollama_model", "OLLAMA_MODEL"):
        provider = "ollama"
        model = _setting(settings, "ollama_model", "OLLAMA_MODEL")

    if provider == "ollama" and model:
        return _ollama_answer(question, df, recommendations, model, settings)

    if provider in {"openai-compatible", "deepseek", "openrouter", "litellm"} and model:
        return _openai_compatible_answer(question, df, recommendations, model, settings)

    return None


def _summary_answer(df):
    summary = build_summary(df)
    return (
        "For the selected data: spend is {spend}, revenue is {revenue}, "
        "ROAS is {roas}, ACOS is {acos}, conversions are {conversions:,.0f}, "
        "and CPA is {cpa}."
    ).format(
        spend=_money(summary["spend"]),
        revenue=_money(summary["revenue"]),
        roas=_ratio(summary["roas"]),
        acos=_percent(summary["acos"]),
        conversions=summary["conversions"],
        cpa=_money(summary["cpa"]),
    )


def answer_question(question, df, recommendations, ai_settings=None):
    text = question.lower()
    ads = aggregate_by_ad(df)

    llm_response = _llm_answer(question, df, recommendations, ai_settings)
    if llm_response:
        return llm_response

    if any(word in text for word in ["pause", "turn off", "stop", "non performing", "bad", "worst"]):
        candidates = recommendations[
            recommendations["action"].isin(["Pause / investigate", "Review", "Already paused"])
        ].head(5)
        if candidates.empty:
            return "I do not see any ads that clearly need to be paused under the current rules. Keep monitoring CPA, ROAS, and ACOS."
        lines = [_format_ad_line(row) for _, row in candidates.iterrows()]
        return "These are the ads I would prioritize:\n\n" + "\n".join(lines)

    if any(word in text for word in ["best", "top", "scale", "winner", "strong"]):
        top = ads[ads["spend"] > 0].sort_values("roas", ascending=False).head(5)
        lines = []
        for _, row in top.iterrows():
            lines.append(
                "- {ad}: ROAS {roas}, revenue {revenue}, spend {spend}, conversions {conversions:.0f}".format(
                    ad=row["ad_name"],
                    roas=_ratio(row["roas"]),
                    revenue=_money(row["revenue"]),
                    spend=_money(row["spend"]),
                    conversions=row["conversions"],
                )
            )
        return "The strongest ads by ROAS are:\n\n" + "\n".join(lines)

    if any(word in text for word in ["spend", "biaya", "budget"]):
        top = ads.sort_values("spend", ascending=False).head(5)
        lines = []
        for _, row in top.iterrows():
            lines.append(
                "- {ad}: spend {spend}, revenue {revenue}, ROAS {roas}".format(
                    ad=row["ad_name"],
                    spend=_money(row["spend"]),
                    revenue=_money(row["revenue"]),
                    roas=_ratio(row["roas"]),
                )
            )
        return "Highest spend ads:\n\n" + "\n".join(lines)

    if any(word in text for word in ["summary", "overview", "performance", "how are", "report"]):
        return _summary_answer(df)

    if any(word in text for word in ["roas", "acos", "cpa", "ctr", "conversion"]):
        return _summary_answer(df) + " For detailed ad-level recommendations, ask which ads to pause or review."

    return (
        "I can help with this ads dataset. Try asking: "
        "'which ads should I pause?', 'what are the best ads?', or 'summarize performance'."
    )
