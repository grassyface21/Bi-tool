import json
import pandas as pd
import numpy as np
from typing import Any


def _get_semantic_type(series: pd.Series) -> str:
    """Determine semantic type: categorical, numeric, datetime, or text."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    # For object dtype, distinguish categorical vs free text
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

        else:  # text
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
    """Convert numpy types to Python native types for JSON serialization."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


def generate_schema_json(dataframes: dict[str, pd.DataFrame]) -> str:
    """Generate compact JSON string with all DataFrame schemas."""
    schemas = {}
    for name, df in dataframes.items():
        schemas[name] = analyze_dataframe(df, name)
    return json.dumps(schemas, default=str)


def generate_starter_questions(schema: dict[str, Any]) -> list[str]:
    """Generate 4-6 relevant starter questions based on schema."""
    questions = []

    for df_name, df_info in schema.items():
        numeric_cols = df_info.get("numeric_columns", [])
        date_cols = df_info.get("date_columns", [])
        categorical_cols = df_info.get("categorical_columns", [])

        # Metric questions for numeric columns
        for col in numeric_cols[:2]:
            col_display = col.replace("_", " ")
            questions.append(f"What is the total {col_display}?")
            if len(questions) >= 2:
                break

        # Distribution by category
        if numeric_cols and categorical_cols:
            num_col = numeric_cols[0].replace("_", " ")
            cat_col = categorical_cols[0].replace("_", " ")
            questions.append(f"Show me {num_col} by {cat_col} as a chart")

        # Time series if date columns exist
        if date_cols and numeric_cols:
            num_col = numeric_cols[0].replace("_", " ")
            date_col = date_cols[0].replace("_", " ")
            questions.append(f"How has {num_col} changed over time?")

        # Top N question
        if numeric_cols and categorical_cols:
            cat_col = categorical_cols[0].replace("_", " ")
            num_col = numeric_cols[0].replace("_", " ")
            questions.append(f"What are the top 10 {cat_col} by {num_col}?")

        # Summary dashboard
        if len(numeric_cols) >= 2:
            questions.append("Give me a summary dashboard of the key metrics")

        # Distribution chart
        if categorical_cols:
            cat_col = categorical_cols[0].replace("_", " ")
            questions.append(f"Show the distribution of {cat_col}")

    # Deduplicate and cap at 6
    seen: set[str] = set()
    unique_questions = []
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
