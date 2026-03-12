import json
import logging
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from config import AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, BEDROCK_MODEL_ID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bedrock client
# ---------------------------------------------------------------------------

def _get_bedrock_client():
    kwargs: dict[str, Any] = {"service_name": "bedrock-runtime", "region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
    if AWS_SECRET_ACCESS_KEY:
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    if AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = AWS_SESSION_TOKEN
    return boto3.client(**kwargs)


def call_bedrock(messages: list[dict], system_prompt: str, retries: int = 3) -> str:
    client = _get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "system": system_prompt,
        "messages": messages,
    }
    last_error: Exception = Exception("Unknown error")
    for attempt in range(retries):
        try:
            response = client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            return json.loads(response["body"].read())["content"][0]["text"]
        except ClientError as e:
            last_error = e
            code = e.response["Error"]["Code"]
            if code in ("ThrottlingException", "ServiceUnavailableException"):
                wait = 2 ** attempt
                logger.warning(f"Bedrock throttled (attempt {attempt+1}), retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"Bedrock ClientError: {e}")
                raise
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            logger.warning(f"Bedrock error (attempt {attempt+1}): {e}, retrying in {wait}s")
            time.sleep(wait)
    raise last_error


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are an expert Business Intelligence analyst. You answer questions by writing \
SQL queries (SQLite dialect) against the user's data and presenting results clearly.

════════════════════════════════════════════════════════
OUTPUT FORMAT — MANDATORY
════════════════════════════════════════════════════════
Your ENTIRE response must be ONE valid JSON object.
- No text before or after the JSON
- No markdown fences, no explanations outside the JSON
- All values must be JSON literals (strings, numbers, booleans, null, arrays, objects)

JSON SCHEMA:
{{
  "output_type": "metric | text | table | chart | dashboard | followup",
  "render_mode": "chat | artifact",
  "sql_query": "<SQL string> | [<SQL string>, ...] | null",
  "chat_message": "<plain English — 1-3 sentences>",
  "artifact": {{ "type": "html", "content": "<complete HTML string>" }} | null,
  "insight": "<exactly 2 sentences>"
}}

════════════════════════════════════════════════════════
DECISION RULES
════════════════════════════════════════════════════════

1. output_type
   metric    → single computed number (sum, count, average, %)
   text      → qualitative / factual answer, no computation needed
   table     → list, comparison, ranked result, multi-row output
   chart     → one visualisation
   dashboard → KPI cards + one or more charts combined
   followup  → query is ambiguous — ask for clarification

2. render_mode
   chat     → metric, short text, tables < 5 rows
   artifact → chart, dashboard, table ≥ 5 rows, formatted reports

3. sql_query rules
   - Write SQLite-dialect SELECT (or WITH … SELECT) statements
   - Available tables: {table_names}
   - ALWAYS compute aggregates correctly — e.g. revenue = SUM(price * quantity)
   - For dates: use strftime('%Y-%m', date_col) for month grouping
   - For top-N: add ORDER BY … DESC LIMIT N
   - For string columns: use LOWER() / TRIM() when comparing user input
   - Single query  → sql_query is a string     → placeholder: __SQL_RESULT_JSON__
   - Multiple queries (dashboard) → sql_query is an array → placeholders: __SQL_RESULT_0__, __SQL_RESULT_1__, …
   - Set null only for pure text answers that need zero computation

4. RESULT_VALUE placeholder  (metric only)
   - Write RESULT_VALUE in chat_message where the number belongs
   - The backend replaces it with the real computed value
   - Example: "Total revenue across all stores is RESULT_VALUE."

5. __SQL_RESULT_JSON__ / __SQL_RESULT_N__ placeholders  (chart, table, dashboard)
   - In artifact HTML embed: const DATA = __SQL_RESULT_JSON__;
   - For dashboard arrays embed: const DATA0 = __SQL_RESULT_0__; const DATA1 = __SQL_RESULT_1__;
   - The backend replaces the placeholder with the real JSON array at runtime
   - Build ALL Chart.js code using DATA — NEVER hardcode data values in the HTML
   - Dashboard KPI query returns ONE row with named columns; use DATA[0].column_name

6. insight
   - Exactly 2 sentences
   - Sentence 1: what the data shows
   - Sentence 2: one actionable business recommendation

════════════════════════════════════════════════════════
ARTIFACT HTML STYLE GUIDE
════════════════════════════════════════════════════════
- Complete self-contained HTML — no external data fetches
- CDN: https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js
- Fonts: https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap
- Color palette: background #f5f7fa | surface #ffffff | accent #6366f1 | text #111827 | muted #6b7280 | border #e5e7eb
- Fonts: headings → Bebas Neue  |  body → DM Sans  |  numbers/code → DM Mono
- Charts: maintainAspectRatio: false, explicit container height in CSS
- Cards: border-radius 12px, background #ffffff, border 1px solid #e5e7eb — NO box-shadow on cards or KPI boxes
- Dashboards: CSS grid, KPI cards on top row, charts below
- Tables: styled <table> with sticky header, hover rows, number columns right-aligned

════════════════════════════════════════════════════════
DATABASE SCHEMA
════════════════════════════════════════════════════════
{schema}

════════════════════════════════════════════════════════
EXAMPLES
════════════════════════════════════════════════════════

── METRIC ──
Query: "What is total revenue?"
{{
  "output_type": "metric",
  "render_mode": "chat",
  "sql_query": "SELECT SUM(price * quantity) AS total_revenue FROM df_sales",
  "chat_message": "The total revenue across all products and stores is RESULT_VALUE.",
  "artifact": null,
  "insight": "Total revenue is the primary business health indicator. Monitoring monthly trends against this figure will surface growth opportunities and early warning signs."
}}

── TABLE ──
Query: "List all items with total revenue over 10000"
{{
  "output_type": "table",
  "render_mode": "artifact",
  "sql_query": "SELECT product_id, product_name, category, subcategory, ROUND(SUM(price * quantity), 2) AS total_revenue FROM df_sales GROUP BY product_id, product_name, category, subcategory HAVING total_revenue > 10000 ORDER BY total_revenue DESC",
  "chat_message": "Here is the full list of products with total revenue exceeding $10,000, sorted highest to lowest.",
  "artifact": {{
    "type": "html",
    "content": "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>High-Revenue Items</title><link href='https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap' rel='stylesheet'><style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#f5f7fa;color:#111827;font-family:'DM Sans',sans-serif;padding:24px}}.card{{background:#ffffff;border-radius:12px;padding:24px;border:1px solid #e5e7eb}}.title{{font-family:'Bebas Neue',sans-serif;font-size:28px;color:#6366f1;margin-bottom:16px}}table{{width:100%;border-collapse:collapse}}th{{background:#e5e7eb;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;padding:10px 14px;text-align:left}}td{{padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:14px}}.num{{font-family:'DM Mono',monospace;text-align:right;color:#6366f1}}tr:hover td{{background:rgba(232,255,71,.04)}}.badge{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600;background:#e5e7eb}}</style></head><body><div class='card'><div class='title'>Items with Total Revenue &gt; $10,000</div><table id='tbl'><thead><tr><th>#</th><th>Product ID</th><th>Product Name</th><th>Category</th><th>Subcategory</th><th style='text-align:right'>Total Revenue</th></tr></thead><tbody id='tbody'></tbody></table></div><script>const DATA=__SQL_RESULT_JSON__;const tbody=document.getElementById('tbody');DATA.forEach((r,i)=>{{const tr=document.createElement('tr');tr.innerHTML=`<td style='color:#6b7280'>${{i+1}}</td><td style='font-family:DM Mono,monospace'>${{r.product_id||''}}</td><td style='font-weight:500'>${{r.product_name||''}}</td><td><span class='badge'>${{r.category||''}}</span></td><td style='color:#6b7280'>${{r.subcategory||''}}</td><td class='num'>${{Number(r.total_revenue).toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}})}}</td>`;tbody.appendChild(tr);}});</script></body></html>"
  }},
  "insight": "The top revenue-generating products span multiple categories, indicating a diversified customer base. Prioritising stock availability and targeted promotions for these items will protect and grow the highest-value revenue streams."
}}

── CHART ──
Query: "Show revenue by category as a bar chart"
{{
  "output_type": "chart",
  "render_mode": "artifact",
  "sql_query": "SELECT category, ROUND(SUM(price * quantity), 2) AS revenue FROM df_sales GROUP BY category ORDER BY revenue DESC",
  "chat_message": "Here is revenue broken down by category, sorted from highest to lowest.",
  "artifact": {{
    "type": "html",
    "content": "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>Revenue by Category</title><link href='https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap' rel='stylesheet'><script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'><\\/script><style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#f5f7fa;color:#111827;font-family:'DM Sans',sans-serif;padding:24px}}.card{{background:#ffffff;border-radius:12px;padding:24px;border:1px solid #e5e7eb}}.title{{font-family:'Bebas Neue',sans-serif;font-size:28px;color:#6366f1;margin-bottom:16px}}.chart-wrap{{position:relative;height:400px}}</style></head><body><div class='card'><div class='title'>Revenue by Category</div><div class='chart-wrap'><canvas id='c'></canvas></div></div><script>const DATA=__SQL_RESULT_JSON__;new Chart(document.getElementById('c'),{{type:'bar',data:{{labels:DATA.map(d=>d.category),datasets:[{{data:DATA.map(d=>d.revenue),backgroundColor:'#6366f1',borderRadius:6,hoverBackgroundColor:'#818cf8'}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>'$'+c.parsed.y.toLocaleString()}}}}}},scales:{{y:{{grid:{{color:'#e5e7eb'}},ticks:{{color:'#6b7280',callback:v=>'$'+Number(v).toLocaleString()}}}},x:{{grid:{{display:false}},ticks:{{color:'#6b7280'}}}}}}}}}});<\\/script></body></html>"
  }},
  "insight": "The leading category contributes disproportionately to total revenue, suggesting strong category loyalty. Replicating its product mix and pricing strategy in lower-performing categories could unlock significant incremental growth."
}}

── DASHBOARD ──
Query: "Give me a summary dashboard"
{{
  "output_type": "dashboard",
  "render_mode": "artifact",
  "sql_query": [
    "SELECT COUNT(*) AS total_orders, ROUND(SUM(price * quantity),2) AS total_revenue, ROUND(AVG(price * quantity),2) AS avg_order_value, COUNT(DISTINCT product_id) AS unique_products FROM df_sales",
    "SELECT category, ROUND(SUM(price * quantity),2) AS revenue FROM df_sales GROUP BY category ORDER BY revenue DESC LIMIT 6"
  ],
  "chat_message": "Here is a summary dashboard with key KPIs and a revenue breakdown by category.",
  "artifact": {{
    "type": "html",
    "content": "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>Dashboard</title><link href='https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap' rel='stylesheet'><script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'><\\/script><style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#f5f7fa;color:#111827;font-family:'DM Sans',sans-serif;padding:24px;display:flex;flex-direction:column;gap:20px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}}.kpi{{background:#ffffff;border-radius:12px;padding:20px;border:1px solid #e5e7eb}}.kpi-label{{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em}}.kpi-value{{font-family:'DM Mono',monospace;font-size:26px;color:#6366f1;margin-top:6px}}.card{{background:#ffffff;border-radius:12px;padding:24px;border:1px solid #e5e7eb}}.title{{font-family:'Bebas Neue',sans-serif;font-size:24px;color:#6366f1;margin-bottom:16px}}.chart-wrap{{position:relative;height:320px}}</style></head><body><div class='grid' id='kpis'></div><div class='card'><div class='title'>Revenue by Category</div><div class='chart-wrap'><canvas id='c'></canvas></div></div><script>const DATA0=__SQL_RESULT_0__;const DATA1=__SQL_RESULT_1__;const m=DATA0[0]||{{}};const fmt=v=>v==null?'N/A':Number(v).toLocaleString('en-US',{{maximumFractionDigits:0}});const fmtC=v=>v==null?'N/A':'$'+Number(v).toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});const kpis=[['Total Revenue',fmtC(m.total_revenue)],['Total Orders',fmt(m.total_orders)],['Avg Order Value',fmtC(m.avg_order_value)],['Unique Products',fmt(m.unique_products)]];const grid=document.getElementById('kpis');kpis.forEach(([l,v])=>{{const d=document.createElement('div');d.className='kpi';d.innerHTML=`<div class='kpi-label'>${{l}}</div><div class='kpi-value'>${{v}}</div>`;grid.appendChild(d);}});new Chart(document.getElementById('c'),{{type:'bar',data:{{labels:DATA1.map(d=>d.category),datasets:[{{data:DATA1.map(d=>d.revenue),backgroundColor:'#6366f1',borderRadius:6,hoverBackgroundColor:'#818cf8'}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>'$'+c.parsed.y.toLocaleString()}}}}}},scales:{{y:{{grid:{{color:'#e5e7eb'}},ticks:{{color:'#6b7280',callback:v=>'$'+Number(v).toLocaleString()}}}},x:{{grid:{{display:false}},ticks:{{color:'#6b7280'}}}}}}}}}});<\\/script></body></html>"
  }},
  "insight": "Revenue is concentrated in a small number of top categories, indicating strong category leadership. Expanding mid-tier categories with targeted promotions could diversify revenue risk and improve overall margins."
}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(sql_schema: str, table_names: list[str]) -> str:
    table_names_str = ", ".join(table_names) if table_names else "none"
    return SYSTEM_PROMPT_TEMPLATE.format(schema=sql_schema, table_names=table_names_str)


def _build_messages(conversation_history: list[dict], query: str) -> list[dict]:
    messages = []
    for item in conversation_history:
        role = item.get("role", "user")
        content = item.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content)
        messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": query})
    return messages


def _repair_json(raw: str) -> str:
    """
    Fix the most common LLM JSON issue: literal newlines / tabs / control
    characters inside string values (which makes json.loads raise
    'Invalid control character').  Walks the string char-by-char, tracks
    whether we are inside a JSON string, and escapes any bare control chars.
    """
    result: list[str] = []
    in_string = False
    escape_next = False

    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue

        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue

        if ch == '"':
            result.append(ch)
            in_string = not in_string
            continue

        if in_string:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            elif ord(ch) < 0x20:
                # Other control characters — drop them
                pass
            else:
                result.append(ch)
        else:
            result.append(ch)

    return "".join(result)


def _parse_response(raw: str) -> tuple[dict[str, Any], bool]:
    """
    Parse the LLM response string into a structured dict.
    Returns (parsed_dict, success: bool).
    """
    raw = raw.strip()

    # Strip markdown fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        raw = "\n".join(inner).strip()

    # Extract the outermost JSON object — handles preamble text
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start: end + 1]

    # First attempt: parse as-is
    try:
        data = json.loads(raw)
        return _with_defaults(data), True
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed ({e}). Attempting repair…")

    # Second attempt: repair control characters then parse
    try:
        data = json.loads(_repair_json(raw))
        logger.info("JSON repaired and parsed successfully.")
        return _with_defaults(data), True
    except json.JSONDecodeError as e:
        logger.warning(f"JSON repair failed ({e}). Raw[:400]: {raw[:400]}")
        return _with_defaults({}), False


def _with_defaults(data: dict) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "output_type": "text",
        "render_mode": "chat",
        "sql_query": None,
        "chat_message": "",
        "artifact": None,
        "insight": "",
    }
    for k, v in defaults.items():
        data.setdefault(k, v)
    return data


def inject_result_into_message(chat_message: str, execution_bundle: dict | None) -> str:
    """Replace RESULT_VALUE in chat_message with the real scalar from __default__ query."""
    if "RESULT_VALUE" not in chat_message or execution_bundle is None:
        return chat_message

    results = execution_bundle.get("results", {})
    result = results.get("__default__")
    if result is None:
        return chat_message

    result_type = result.get("type")
    value = result.get("data")

    if result_type == "scalar" and value is not None:
        if isinstance(value, float) and value == int(value):
            formatted = f"{int(value):,}"
        elif isinstance(value, float):
            formatted = f"{value:,.2f}"
        elif isinstance(value, int):
            formatted = f"{value:,}"
        else:
            formatted = str(value)
    else:
        return chat_message

    return chat_message.replace("RESULT_VALUE", formatted)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def process_query(
    query: str,
    sql_schema: str,
    conversation_history: list[dict],
    table_names: list[str],
    max_parse_retries: int = 2,
) -> dict[str, Any]:
    """
    Call Bedrock and parse the response.
    If JSON parsing fails, automatically retries up to max_parse_retries times
    before returning a fallback error message — so the user never sees the
    'trouble formatting' message due to a transient LLM output glitch.
    """
    system_prompt = _build_system_prompt(sql_schema, table_names)
    messages = _build_messages(conversation_history, query)

    last_parsed: dict[str, Any] = {}
    for attempt in range(1 + max_parse_retries):
        raw = call_bedrock(messages, system_prompt)
        parsed, ok = _parse_response(raw)
        if ok:
            return parsed
        last_parsed = parsed
        logger.warning(f"JSON parse failed on attempt {attempt + 1}, retrying…")

    # All retries exhausted — return a graceful fallback
    last_parsed["chat_message"] = (
        "I had trouble structuring my response. Please try again or rephrase your question."
    )
    return last_parsed
