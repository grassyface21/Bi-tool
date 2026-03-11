import json
import sqlite3
import pandas as pd
import numpy as np
from typing import Any


def _get_semantic_type(series: pd.Series) -> str:
    """Determine semantic type: categorical, numeric, datetime, or text."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if series.dtype == object:
        unique_ratio = series.nunique() / max(len(series), 1)
        if unique_ratio < 0.5 or series.nunique() <= 20:
            return "categorical"
        return "text"
    return "categorical"


def analyze_dataframe(df: pd.DataFrame, filename: str) -> dict[str, Any]:
    """Extract schema information from a DataFrame."""
    columns_info = []
    for col in df.columns:
        series = df[col].dropna()
        semantic_type = _get_semantic_type(df[col])
        null_pct = round(df[col].isnull().sum() / max(len(df), 1) * 100, 2)
        unique_count = int(df[col].nunique())

        col_info: dict[str, Any] = {
            "name": col,
            "dtype": str(df[col].dtype),
            "semantic_type": semantic_type,
            "null_percentage": null_pct,
            "unique_count": unique_count,
        }

        if semantic_type == "numeric":
            col_info["numeric_stats"] = {
                "min": _safe_val(series.min()),
                "max": _safe_val(series.max()),
                "mean": _safe_val(series.mean()),
            }
            col_info["sample_values"] = [_safe_val(v) for v in series.head(3).tolist()]
        elif semantic_type == "categorical":
            top_values = series.value_counts().head(5).index.tolist()
            col_info["top_values"] = [str(v) for v in top_values]
            col_info["sample_values"] = [str(v) for v in series.head(3).tolist()]
        elif semantic_type == "datetime":
            col_info["sample_values"] = [str(v) for v in series.head(3).tolist()]
        else:
            col_info["sample_values"] = [str(v)[:100] for v in series.head(3).tolist()]

        columns_info.append(col_info)

    numeric_cols = [c["name"] for c in columns_info if c["semantic_type"] == "numeric"]
    date_cols = [c["name"] for c in columns_info if c["semantic_type"] == "datetime"]
    categorical_cols = [c["name"] for c in columns_info if c["semantic_type"] == "categorical"]

    return {
        "filename": filename,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "numeric_columns": numeric_cols,
        "date_columns": date_cols,
        "categorical_columns": categorical_cols,
        "column_info": columns_info,
    }


def _safe_val(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


def generate_schema_json(dataframes: dict[str, pd.DataFrame]) -> str:
    schemas = {}
    for name, df in dataframes.items():
        schemas[name] = analyze_dataframe(df, name)
    return json.dumps(schemas, default=str)


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def build_sqlite_db(dataframes: dict[str, pd.DataFrame]) -> sqlite3.Connection:
    """
    Load all DataFrames into a single in-memory SQLite database.
    Each DataFrame becomes a table named after its key.
    Returns the open connection (check_same_thread=False for FastAPI).
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    for table_name, df in dataframes.items():
        df_copy = df.copy()
        # Convert datetime → ISO strings (SQLite has no native datetime type)
        for col in df_copy.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
            df_copy[col] = df_copy[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        # Convert remaining object columns: NaN → None, everything → str
        for col in df_copy.select_dtypes(include=["object"]).columns:
            df_copy[col] = df_copy[col].where(df_copy[col].notna(), other=None)
        df_copy.to_sql(table_name, conn, if_exists="replace", index=False)
    conn.commit()
    return conn


def generate_sql_schema_prompt(
    conn: sqlite3.Connection,
    dataframes: dict[str, pd.DataFrame],
) -> str:
    """
    Generate a rich SQL schema context string for the LLM prompt.
    Includes:
      - CREATE TABLE (exact SQLite DDL so the LLM knows real column names/types)
      - Per-column statistics (min/max/mean for numerics, top values for categoricals)
      - 5 sample rows of actual data
    """
    parts: list[str] = []

    for table_name, df in dataframes.items():
        # --- CREATE TABLE from SQLite (authoritative column names & types) ---
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        create_sql = row[0] if row else f'CREATE TABLE "{table_name}" ( ... )'

        # --- Row count ---
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]

        # --- Column stats ---
        schema_info = analyze_dataframe(df, table_name)
        stats_lines: list[str] = []
        for ci in schema_info["column_info"]:
            col = ci["name"]
            null_note = f", nulls={ci['null_percentage']}%" if ci["null_percentage"] > 0 else ""
            if ci["semantic_type"] == "numeric" and "numeric_stats" in ci:
                s = ci["numeric_stats"]
                mean_str = f"{round(s['mean'], 4)}" if s["mean"] is not None else "N/A"
                stats_lines.append(
                    f"--   {col}  [NUMERIC]  min={s['min']}, max={s['max']}, mean={mean_str}{null_note}"
                )
            elif ci["semantic_type"] == "categorical" and "top_values" in ci:
                tv = ", ".join(repr(v) for v in ci["top_values"][:6])
                stats_lines.append(f"--   {col}  [CATEGORICAL]  top_values=[{tv}]{null_note}")
            elif ci["semantic_type"] == "datetime":
                samples = ci.get("sample_values", [])[:2]
                stats_lines.append(f"--   {col}  [DATETIME]  sample={samples}{null_note}")
            else:
                samples = ci.get("sample_values", [])[:2]
                stats_lines.append(f"--   {col}  [TEXT]  sample={samples}{null_note}")

        # --- Sample rows (5 rows, aligned) ---
        cur = conn.execute(f'SELECT * FROM "{table_name}" LIMIT 5')
        col_names = [d[0] for d in cur.description]
        sample_rows = cur.fetchall()

        # Build aligned text table
        widths = [
            max(len(str(c)), max((len(str(r[i])[:28]) for r in sample_rows), default=0))
            for i, c in enumerate(col_names)
        ]
        header = " | ".join(str(c).ljust(w) for c, w in zip(col_names, widths))
        sep = "-+-".join("-" * w for w in widths)
        rows_formatted = [
            " | ".join(str(v)[:28].ljust(w) for v, w in zip(r, widths))
            for r in sample_rows
        ]
        sample_block = (
            f"-- {header}\n-- {sep}\n"
            + "\n".join(f"-- {line}" for line in rows_formatted)
        )

        parts.append(
            f"-- ═══ Table: {table_name}  ({row_count:,} rows) ═══\n"
            f"{create_sql};\n\n"
            f"-- Column statistics:\n"
            + "\n".join(stats_lines)
            + f"\n\n-- Sample data (5 rows):\n{sample_block}\n"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Starter questions (unchanged logic)
# ---------------------------------------------------------------------------

def generate_starter_questions(schema: dict[str, Any]) -> list[str]:
    """Generate 4-6 relevant starter questions based on schema."""
    questions: list[str] = []

    for df_name, df_info in schema.items():
        numeric_cols = df_info.get("numeric_columns", [])
        date_cols = df_info.get("date_columns", [])
        categorical_cols = df_info.get("categorical_columns", [])

        for col in numeric_cols[:2]:
            col_display = col.replace("_", " ")
            questions.append(f"What is the total {col_display}?")
            if len(questions) >= 2:
                break

        if numeric_cols and categorical_cols:
            num_col = numeric_cols[0].replace("_", " ")
            cat_col = categorical_cols[0].replace("_", " ")
            questions.append(f"Show me {num_col} by {cat_col} as a chart")

        if date_cols and numeric_cols:
            num_col = numeric_cols[0].replace("_", " ")
            date_col = date_cols[0].replace("_", " ")
            questions.append(f"How has {num_col} changed over {date_col}?")

        if numeric_cols and categorical_cols:
            cat_col = categorical_cols[0].replace("_", " ")
            num_col = numeric_cols[0].replace("_", " ")
            questions.append(f"What are the top 10 {cat_col} by {num_col}?")

        if len(numeric_cols) >= 2:
            questions.append("Give me a summary dashboard of the key metrics")

        if categorical_cols:
            cat_col = categorical_cols[0].replace("_", " ")
            questions.append(f"Show the distribution of {cat_col}")

    seen: set[str] = set()
    unique_questions: list[str] = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique_questions.append(q)

    return unique_questions[:6] if unique_questions else [
        "What are the key statistics in this dataset?",
        "Show me an overview of the data",
        "What are the top values?",
        "Give me a summary dashboard",
    ]
