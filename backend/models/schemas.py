from pydantic import BaseModel
from typing import Optional, Literal, Any


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    semantic_type: Literal["categorical", "numeric", "datetime", "text"]
    null_percentage: float
    unique_count: int
    numeric_stats: Optional[dict] = None
    top_values: Optional[list] = None
    sample_values: list = []


class DataFrameSchema(BaseModel):
    filename: str
    rows: int
    columns: int
    column_info: list[ColumnInfo]


class UploadResponse(BaseModel):
    session_id: str
    files_processed: list[str]
    schema_summary: dict[str, Any]
    suggested_questions: list[str]


class QueryRequest(BaseModel):
    session_id: str
    query: str


class ArtifactContent(BaseModel):
    type: Literal["html"]
    content: str


class QueryResponse(BaseModel):
    output_type: Literal["metric", "text", "table", "chart", "dashboard", "followup"]
    render_mode: Literal["chat", "artifact"]
    sql_query: Optional[Any] = None          # str | list[str] | None
    chat_message: str
    artifact: Optional[ArtifactContent] = None
    insight: str
    execution_result: Optional[Any] = None
    execution_error: Optional[str] = None
