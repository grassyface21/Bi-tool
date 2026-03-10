import ast
import json
import logging
import multiprocessing
import time
from typing import Any

import numpy as np
import pandas as pd

from config import CODE_EXECUTION_TIMEOUT, MAX_RESULT_ROWS

logger = logging.getLogger(__name__)

# Whitelisted top-level imports
ALLOWED_IMPORTS = {"pandas", "numpy", "datetime", "json", "math", "re", "collections"}

# Blacklisted names / builtins
BLACKLISTED_NAMES = {
    "os", "sys", "subprocess", "eval", "exec", "open", "__import__",
    "compile", "globals", "locals", "vars", "dir", "getattr", "setattr",
    "delattr", "hasattr", "importlib", "builtins", "socket", "requests",
    "urllib", "http", "shutil", "pathlib", "pickle", "shelve",
}


class SecurityError(Exception):
    pass


def _validate_ast(code: str) -> None:
    """Parse and walk AST to enforce security rules."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SyntaxError(f"Syntax error in generated code: {e}")

    for node in ast.walk(tree):
        # Block dangerous imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module not in ALLOWED_IMPORTS:
                    raise SecurityError(f"Import not allowed: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_module = node.module.split(".")[0]
                if top_module not in ALLOWED_IMPORTS:
                    raise SecurityError(f"Import not allowed: {node.module}")

        # Block dangerous name references
        elif isinstance(node, ast.Name):
            if node.id in BLACKLISTED_NAMES:
                raise SecurityError(f"Forbidden reference: {node.id}")

        # Block attribute access that starts with dunder
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SecurityError(f"Dunder attribute access not allowed: {node.attr}")


def _execute_in_subprocess(
    code: str,
    dataframes_serialized: dict[str, str],
    result_queue: multiprocessing.Queue,
) -> None:
    """Worker function that runs inside a subprocess."""
    try:
        import io
        import json
        import pandas as pd
        import numpy as np

        # Reconstruct DataFrames
        namespace: dict[str, Any] = {}
        for name, json_str in dataframes_serialized.items():
            df = pd.read_json(io.StringIO(json_str), orient="records")
            namespace[name] = df

        # Execute code
        exec(code, {"pd": pd, "np": np, "json": json, **namespace})  # noqa: S102

        result = namespace.get("result")

        # Serialize result
        if isinstance(result, pd.DataFrame):
            if len(result) > 10000:
                truncated = True
                result = result.head(10000)
            else:
                truncated = False
            result_queue.put({
                "type": "dataframe",
                "data": result.to_dict(orient="records"),
                "columns": list(result.columns),
                "truncated": truncated,
                "total_rows": len(result) + (result.shape[0] if not truncated else 0),
            })
        elif isinstance(result, pd.Series):
            result_queue.put({
                "type": "series",
                "data": result.to_dict(),
                "name": result.name,
            })
        elif isinstance(result, (dict, list)):
            result_queue.put({"type": "raw", "data": result})
        elif isinstance(result, (int, float, np.integer, np.floating)):
            result_queue.put({"type": "scalar", "data": float(result)})
        elif result is None:
            result_queue.put({"type": "none", "data": None})
        else:
            result_queue.put({"type": "raw", "data": str(result)})

    except Exception as e:
        result_queue.put({"type": "error", "error": str(e)})


def execute_pandas_code(code: str, dataframes: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """
    Validate and execute pandas code in a sandboxed subprocess.
    Returns a result dict with type and data.
    """
    # Step 1: AST security validation
    try:
        _validate_ast(code)
    except SecurityError as e:
        logger.warning(f"Security violation blocked: {e}")
        return {"type": "error", "error": f"Security error: {e}"}
    except SyntaxError as e:
        return {"type": "error", "error": str(e)}

    # Step 2: Serialize DataFrames for subprocess
    dataframes_serialized: dict[str, str] = {}
    for name, df in dataframes.items():
        try:
            dataframes_serialized[name] = df.head(MAX_RESULT_ROWS).to_json(
                orient="records", date_format="iso", default_handler=str
            )
        except Exception as e:
            return {"type": "error", "error": f"Failed to serialize DataFrame '{name}': {e}"}

    # Step 3: Run in subprocess with timeout
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_execute_in_subprocess,
        args=(code, dataframes_serialized, result_queue),
        daemon=True,
    )
    proc.start()
    proc.join(timeout=CODE_EXECUTION_TIMEOUT)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        logger.warning("Code execution timed out")
        return {"type": "error", "error": f"Code execution timed out after {CODE_EXECUTION_TIMEOUT} seconds"}

    if result_queue.empty():
        return {"type": "error", "error": "Code execution produced no result"}

    result = result_queue.get_nowait()
    return result
