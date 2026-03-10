import io
import re
import chardet
import pandas as pd
from fastapi import HTTPException


def _sanitize_column_name(name: str) -> str:
    """Lowercase, strip whitespace, replace special chars with underscore."""
    name = str(name).strip().lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name or "column"


def _infer_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Attempt to convert columns to more specific dtypes."""
    for col in df.columns:
        if df[col].dtype == object:
            # Try datetime
            try:
                converted = pd.to_datetime(df[col], format='mixed', dayfirst=False)
                df[col] = converted
                continue
            except Exception:
                pass
            # Try numeric
            try:
                converted = pd.to_numeric(df[col])
                df[col] = converted
                continue
            except Exception:
                pass
    return df


async def parse_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV or XLSX bytes into a cleaned DataFrame."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "xlsx":
        df = _parse_xlsx(file_bytes)
    elif ext == "csv":
        df = _parse_csv(file_bytes)
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: .{ext}")

    # Sanitize column names
    df.columns = [_sanitize_column_name(c) for c in df.columns]

    # Handle duplicate column names
    seen: dict[str, int] = {}
    new_cols = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    df.columns = new_cols

    # Infer better dtypes
    df = _infer_dtypes(df)

    # Validate
    if df.empty or len(df.columns) == 0:
        raise HTTPException(status_code=422, detail="File contains no data")
    if len(df) == 0:
        raise HTTPException(status_code=422, detail="File contains no rows")

    return df


def _parse_csv(file_bytes: bytes) -> pd.DataFrame:
    """Parse CSV with encoding detection and delimiter sniffing."""
    # Detect encoding
    detected = chardet.detect(file_bytes)
    encoding = detected.get("encoding") or "utf-8"

    # Fallback encodings
    encodings_to_try = [encoding, "utf-8", "latin-1", "cp1252"]
    seen_encodings: set[str] = set()
    unique_encodings = []
    for e in encodings_to_try:
        if e and e.lower() not in seen_encodings:
            seen_encodings.add(e.lower())
            unique_encodings.append(e)

    last_error: Exception = Exception("Unknown parse error")
    for enc in unique_encodings:
        for delimiter in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    encoding=enc,
                    sep=delimiter,
                    engine="python",
                    on_bad_lines="skip",
                )
                if len(df.columns) > 1 or delimiter == ",":
                    return df
            except Exception as e:
                last_error = e

    raise HTTPException(status_code=422, detail=f"Failed to parse CSV: {last_error}")


def _parse_xlsx(file_bytes: bytes) -> pd.DataFrame:
    """Parse XLSX using openpyxl engine."""
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        return df
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse XLSX: {e}")
