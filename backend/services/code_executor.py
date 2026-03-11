import json
import logging
import re
import sqlite3
import threading
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security — only read-only SELECT queries are permitted
# ---------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|ATTACH|DETACH)\b",
    re.IGNORECASE,
)
_PRAGMA = re.compile(r"\bPRAGMA\b", re.IGNORECASE)


def _validate_sql(sql: str) -> str | None:
    """
    Return an error string if the SQL is not safe, else None.
    Allows SELECT and WITH … SELECT (CTEs).
    """
    stripped = sql.strip().lstrip(";").strip()
    first_word = stripped.split()[0].upper() if stripped.split() else ""
    if first_word not in ("SELECT", "WITH"):
        return "Only SELECT (or WITH … SELECT) queries are permitted."
    if _FORBIDDEN.search(stripped):
        return "Forbidden SQL keyword detected in query."
    if _PRAGMA.search(stripped):
        return "PRAGMA statements are not allowed."
    return None


# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------

def _run_single_query(
    sql: str,
    conn: sqlite3.Connection,
    lock: threading.Lock,
) -> dict[str, Any]:
    """Execute one validated SQL SELECT and return a typed result dict."""
    sql = sql.strip().rstrip(";")

    err = _validate_sql(sql)
    if err:
        return {"type": "error", "error": err}

    try:
        with lock:
            cursor = conn.execute(sql)
            description = cursor.description or []
            columns = [d[0] for d in description]
            rows = cursor.fetchall()

        if not rows:
            return {"type": "empty", "data": [], "columns": columns}

        # Single cell → scalar (for metric queries)
        if len(rows) == 1 and len(columns) == 1:
            val = rows[0][0]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return {"type": "scalar", "data": float(val)}
            return {"type": "scalar", "data": val}

        # Multiple rows/columns → tabular result
        records: list[dict] = []
        for row in rows:
            record: dict = {}
            for col, val in zip(columns, row):
                # Ensure every value is JSON-serialisable
                if isinstance(val, (int, float, str, bool)) or val is None:
                    record[col] = val
                else:
                    record[col] = str(val)
            records.append(record)

        return {
            "type": "dataframe",
            "data": records,
            "columns": columns,
            "row_count": len(records),
        }

    except sqlite3.OperationalError as e:
        return {"type": "error", "error": f"SQL error: {e}"}
    except Exception as e:
        return {"type": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Public API — handles single string OR list of strings
# ---------------------------------------------------------------------------

def execute_sql_query(
    sql_query: str | list[str],
    conn: sqlite3.Connection,
    lock: threading.Lock,
) -> dict[str, Any]:
    """
    Execute one or more SQL SELECT statements.

    - Single string  → result keyed as "__default__"
    - List of strings → results keyed as "__0__", "__1__", …

    Returns:
        {
          "results": {
              "__default__": { "type": ..., "data": ... },
              # OR "__0__", "__1__", …
          },
          "has_error": bool,
        }
    """
    if isinstance(sql_query, str):
        result = _run_single_query(sql_query, conn, lock)
        return {
            "results": {"__default__": result},
            "has_error": result["type"] == "error",
        }

    # List of queries (for dashboards with multiple data needs)
    results: dict[str, Any] = {}
    has_error = False
    for i, sql in enumerate(sql_query):
        r = _run_single_query(sql, conn, lock)
        results[f"__{i}__"] = r
        if r["type"] == "error":
            has_error = True

    return {"results": results, "has_error": has_error}
