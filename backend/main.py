import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, MAX_FILES_PER_UPLOAD, SESSION_CLEANUP_INTERVAL
from models.schemas import QueryRequest, QueryResponse, UploadResponse
from services.claude_service import process_query
from services.code_executor import execute_pandas_code
from services.parser import parse_file
from services.schema_analyzer import analyze_dataframe, generate_schema_json, generate_starter_questions
from services.session_store import session_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def periodic_cleanup():
    """Background task to clean up expired sessions every hour."""
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
    version="1.0.0",
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
    Returns a session_id, schema summary, and starter questions.
    """
    # Validate file count
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=422,
            detail=f"Too many files. Maximum is {MAX_FILES_PER_UPLOAD}.",
        )

    dataframes = {}
    files_processed = []

    for upload in files:
        filename = upload.filename or "unnamed"

        # Validate extension
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid file type '{ext}' for '{filename}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        # Read file bytes
        file_bytes = await upload.read()

        # Validate size
        if len(file_bytes) > MAX_FILE_SIZE:
            size_mb = len(file_bytes) / (1024 * 1024)
            raise HTTPException(
                status_code=422,
                detail=f"File '{filename}' is too large ({size_mb:.1f}MB). Maximum is 100MB.",
            )

        # Parse file
        df = await parse_file(file_bytes, filename)

        # Use sanitized base name as key (e.g., "sales.csv" → "df_sales")
        base = Path(filename).stem
        # Sanitize: lowercase, replace non-alphanumeric with underscore
        import re
        key = "df_" + re.sub(r"[^a-z0-9]", "_", base.lower()).strip("_")

        dataframes[key] = df
        files_processed.append(filename)
        logger.info(f"Parsed '{filename}': {len(df)} rows, {len(df.columns)} columns")

    if not dataframes:
        raise HTTPException(status_code=422, detail="No valid files were uploaded")

    # Create session
    session_id = session_store.create_session()
    session_store.add_dataframes(session_id, dataframes)

    # Generate schema
    schema = {}
    for key, df in dataframes.items():
        schema[key] = analyze_dataframe(df, key)
    session_store.set_schema(session_id, schema)

    # Generate starter questions
    starter_questions = generate_starter_questions(schema)

    logger.info(f"Session {session_id} created with {len(dataframes)} DataFrames")

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
    Returns structured response with optional artifact HTML.
    """
    # Retrieve session
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

    dataframe_names = list(session.dataframes.keys())
    query = request.query.strip()

    if not query:
        raise HTTPException(status_code=422, detail="Query cannot be empty.")

    # ── Step 1: Ask Claude for the response structure + aggregation code ──
    try:
        claude_response = await process_query(
            query=query,
            schema=session.schema,
            conversation_history=session.conversation_history,
            dataframe_names=dataframe_names,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"AI parsing error: {e}")
    except Exception as e:
        logger.error(f"Claude service error: {e}")
        raise HTTPException(status_code=500, detail="AI service error. Please try again.")

    # ── Step 2: Execute aggregation code ──
    execution_result = None
    execution_error = None
    aggregation_code = claude_response.get("aggregation_code")

    if aggregation_code:
        exec_result = execute_pandas_code(aggregation_code, session.dataframes)
        if exec_result.get("type") == "error":
            execution_error = exec_result.get("error")
            logger.warning(f"Code execution error: {execution_error}")
        else:
            execution_result = exec_result

    # ── Step 3: Inject real computed value into chat_message (metrics) ──
    from services.claude_service import _inject_result_value
    chat_message = _inject_result_value(
        claude_response.get("chat_message", ""), execution_result
    )

    # ── Step 4: Store conversation history ──
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

    # ── Step 5: Build artifact ──
    artifact = claude_response.get("artifact")
    artifact_obj = None
    if artifact and isinstance(artifact, dict) and artifact.get("content"):
        from models.schemas import ArtifactContent
        artifact_obj = ArtifactContent(
            type=artifact.get("type", "html"),
            content=artifact["content"],
        )

    return QueryResponse(
        output_type=claude_response.get("output_type", "text"),
        render_mode=claude_response.get("render_mode", "chat"),
        aggregation_code=aggregation_code,
        chat_message=chat_message,
        artifact=artifact_obj,
        insight=claude_response.get("insight", ""),
        execution_result=execution_result,
        execution_error=execution_error,
    )
