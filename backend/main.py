import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, MAX_FILES_PER_UPLOAD, SESSION_CLEANUP_INTERVAL
from models.schemas import QueryRequest, QueryResponse, UploadResponse
from services.claude_service import process_query, inject_result_into_message
from services.code_executor import execute_sql_query
from services.parser import parse_file
from services.schema_analyzer import (
    analyze_dataframe,
    build_sqlite_db,
    generate_sql_schema_prompt,
    generate_starter_questions,
)
from services.session_store import session_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Light-theme enforcement
# All artifact HTML is post-processed to guarantee light theme regardless of
# what the LLM generates. Map every known dark-palette hex → light-palette hex.
# ---------------------------------------------------------------------------
_DARK_TO_LIGHT: list[tuple[str, str]] = [
    # backgrounds / surfaces
    ("#0a0b0f", "#f5f7fa"),
    ("#111318", "#ffffff"),
    ("#0d0e12", "#f5f7fa"),
    # accent (yellow-green → indigo)
    ("#e8ff47", "#6366f1"),
    ("#f5ff8a", "#818cf8"),
    ("#d4f53c", "#6366f1"),
    # text (near-white → near-black)
    ("#f0f2f8", "#111827"),
    ("#e8eaf2", "#111827"),
    # muted
    ("#7a8099", "#6b7280"),
    ("#8a90a8", "#6b7280"),
    # borders
    ("#1f2937", "#e5e7eb"),
    ("#2a2f3d", "#e5e7eb"),
    # shadows
    ("rgba(0,0,0,.4)", "rgba(0,0,0,.07)"),
    ("rgba(0,0,0,0.4)", "rgba(0,0,0,0.07)"),
    ("rgba(0,0,0,.6)", "rgba(0,0,0,.10)"),
]

# Additional CSS block injected into <head> as a hard override
_LIGHT_THEME_CSS = """
<style id="__light_override__">
  html, body {
    background: #f5f7fa !important;
    color: #111827 !important;
  }
  /* Card surfaces */
  .card, .kpi, [class*="card"], [class*="kpi"] {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    box-shadow: 0 2px 12px rgba(0,0,0,.07) !important;
  }
  /* Ensure text on white cards is readable */
  .kpi-label, [class*="label"] { color: #6b7280 !important; }
  .kpi-value, [class*="value"] { color: #6366f1 !important; }
  /* Chart grid lines */
  canvas { background: transparent !important; }
  /* Table rows */
  table { background: #ffffff !important; color: #111827 !important; }
  th { background: #f3f4f6 !important; color: #6b7280 !important; }
  td { border-color: #e5e7eb !important; color: #111827 !important; }
  tr:hover td { background: #f5f3ff !important; }
</style>
"""


def _enforce_light_theme(html: str) -> str:
    """Replace all dark-palette colors in generated HTML with light-palette equivalents."""
    # 1. String-replace every known dark hex (case-insensitive)
    lower = html.lower()
    result = html
    for dark, light in _DARK_TO_LIGHT:
        # replace lowercase variant
        result = result.replace(dark, light)
        # replace uppercase variant
        result = result.replace(dark.upper(), light)
        # replace mixed-case via regex for safety
        result = re.sub(re.escape(dark), light, result, flags=re.IGNORECASE)

    # 2. Inject the override <style> block just before </head>
    if "</head>" in result:
        result = result.replace("</head>", _LIGHT_THEME_CSS + "</head>", 1)
    else:
        # No <head> tag — prepend the style block
        result = _LIGHT_THEME_CSS + result

    return result


async def periodic_cleanup():
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        try:
            count = session_store.cleanup_expired_sessions()
            if count > 0:
                logger.info(f"Cleaned up {count} expired sessions")
        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("BI Tool API starting up")
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("BI Tool API shut down")


app = FastAPI(
    title="BI Tool API",
    description="AI-Powered Business Intelligence Tool API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_sessions": session_store.session_count(),
    }


@app.post("/api/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...)):
    """
    Upload one or more CSV/XLSX files.
    Parses each file, loads all tables into a single in-memory SQLite database,
    and returns a session_id, schema summary, and starter questions.
    """
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=422,
            detail=f"Too many files. Maximum is {MAX_FILES_PER_UPLOAD}.",
        )

    dataframes = {}
    files_processed = []

    for upload in files:
        filename = upload.filename or "unnamed"

        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid file type '{ext}' for '{filename}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        file_bytes = await upload.read()

        if len(file_bytes) > MAX_FILE_SIZE:
            size_mb = len(file_bytes) / (1024 * 1024)
            raise HTTPException(
                status_code=422,
                detail=f"File '{filename}' is too large ({size_mb:.1f}MB). Maximum is 100MB.",
            )

        df = await parse_file(file_bytes, filename)

        base = Path(filename).stem
        key = "df_" + re.sub(r"[^a-z0-9]", "_", base.lower()).strip("_")

        dataframes[key] = df
        files_processed.append(filename)
        logger.info(f"Parsed '{filename}': {len(df)} rows, {len(df.columns)} columns")

    if not dataframes:
        raise HTTPException(status_code=422, detail="No valid files were uploaded")

    # ── Create session and store DataFrames ──
    session_id = session_store.create_session()
    session_store.add_dataframes(session_id, dataframes)

    # ── Build pandas schema (for starter questions) ──
    schema = {}
    for key, df in dataframes.items():
        schema[key] = analyze_dataframe(df, key)
    session_store.set_schema(session_id, schema)

    # ── Build SQLite database from all uploaded DataFrames ──
    sqlite_conn = build_sqlite_db(dataframes)

    # ── Generate rich SQL schema prompt for the LLM ──
    sql_schema = generate_sql_schema_prompt(sqlite_conn, dataframes)

    # ── Store SQLite connection + schema string in session ──
    session_store.set_sqlite(session_id, sqlite_conn, sql_schema)

    starter_questions = generate_starter_questions(schema)

    logger.info(
        f"Session {session_id} created: {len(dataframes)} table(s), "
        f"SQLite loaded with {sum(len(df) for df in dataframes.values()):,} total rows"
    )

    return UploadResponse(
        session_id=session_id,
        files_processed=files_processed,
        schema_summary=schema,
        suggested_questions=starter_questions,
    )


@app.post("/api/query", response_model=QueryResponse)
async def query_data(request: QueryRequest):
    """
    Process a natural language query against the uploaded data.
    Uses Text-to-SQL: LLM generates a SQL SELECT, executed against the
    session's in-memory SQLite database.
    """
    session = session_store.get_session(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session expired or not found. Please re-upload your files.",
        )

    if not session.dataframes:
        raise HTTPException(
            status_code=422,
            detail="No data found in session. Please re-upload your files.",
        )

    if session.sqlite_conn is None:
        raise HTTPException(
            status_code=500,
            detail="Database not initialised for this session. Please re-upload your files.",
        )

    table_names = list(session.dataframes.keys())
    query = request.query.strip()

    if not query:
        raise HTTPException(status_code=422, detail="Query cannot be empty.")

    # ── Step 1: Ask the LLM for SQL + response structure ──
    try:
        claude_response = await process_query(
            query=query,
            sql_schema=session.sql_schema,
            conversation_history=session.conversation_history,
            table_names=table_names,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"AI parsing error: {e}")
    except Exception as e:
        logger.error(f"Claude service error: {e}")
        raise HTTPException(status_code=500, detail="AI service error. Please try again.")

    sql_query = claude_response.get("sql_query")

    # ── Step 2: Execute SQL query/queries against SQLite ──
    execution_bundle: dict | None = None
    execution_error: str | None = None

    if sql_query:
        bundle = execute_sql_query(sql_query, session.sqlite_conn, session.sqlite_lock)
        if bundle.get("has_error"):
            # Collect error messages
            errors = [
                r["error"]
                for r in bundle["results"].values()
                if r.get("type") == "error"
            ]
            execution_error = "; ".join(errors)
            logger.warning(f"SQL execution error(s): {execution_error}")
        else:
            execution_bundle = bundle

    # ── Step 3: Inject real data into chat_message (RESULT_VALUE) ──
    chat_message = inject_result_into_message(
        claude_response.get("chat_message", ""), execution_bundle
    )

    # ── Step 4: Inject real data into artifact HTML ──
    artifact = claude_response.get("artifact")
    if artifact and isinstance(artifact, dict) and execution_bundle:
        content = artifact.get("content", "")
        results = execution_bundle.get("results", {})

        if "__default__" in results:
            result = results["__default__"]
            data = result.get("data", [])
            # Wrap scalar in a list so HTML can always do DATA[0]
            if result.get("type") == "scalar":
                data = [{"value": result.get("data")}]
            content = content.replace(
                "__SQL_RESULT_JSON__", json.dumps(data, default=str)
            )
        else:
            # Numbered queries for dashboard: __SQL_RESULT_0__, __SQL_RESULT_1__, …
            for key, result in results.items():
                # key is "__0__", "__1__", …
                idx = key.strip("_")
                placeholder = f"__SQL_RESULT_{idx}__"
                data = result.get("data", [])
                if result.get("type") == "scalar":
                    data = [{"value": result.get("data")}]
                content = content.replace(
                    placeholder, json.dumps(data, default=str)
                )

        # Force light theme on the final HTML regardless of LLM output
        artifact["content"] = _enforce_light_theme(content)

    # ── Step 5: Store conversation history ──
    session_store.add_message(request.session_id, "user", {"text": query})
    session_store.add_message(
        request.session_id,
        "assistant",
        {
            "chat_message": chat_message,
            "output_type": claude_response.get("output_type", "text"),
            "insight": claude_response.get("insight", ""),
        },
    )

    # ── Step 6: Build artifact response object ──
    artifact_obj = None
    if artifact and isinstance(artifact, dict) and artifact.get("content"):
        from models.schemas import ArtifactContent
        artifact_obj = ArtifactContent(
            type=artifact.get("type", "html"),
            content=artifact["content"],
        )

    # ── Step 7: Build execution_result summary for the frontend ──
    execution_result = None
    if execution_bundle:
        results = execution_bundle.get("results", {})
        if "__default__" in results:
            execution_result = results["__default__"]
        else:
            execution_result = {k: v for k, v in results.items()}

    return QueryResponse(
        output_type=claude_response.get("output_type", "text"),
        render_mode=claude_response.get("render_mode", "chat"),
        sql_query=sql_query,
        chat_message=chat_message,
        artifact=artifact_obj,
        insight=claude_response.get("insight", ""),
        execution_result=execution_result,
        execution_error=execution_error,
    )
