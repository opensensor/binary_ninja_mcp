#!/usr/bin/env python3
from __future__ import annotations
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

# Set up logging to help debug connection issues
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Tunables
# ──────────────────────────────────────────────────────────────────────────────
BINJA_URL = "http://localhost:9009"
CONNECT_TIMEOUT = 1.0
READ_TIMEOUT = 8.0
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 0.2  # seconds
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000   # protect the UI & SSE
CACHE_TTL = 3.0   # seconds for volatile lists

# ──────────────────────────────────────────────────────────────────────────────
# MCP app (synchronous)
# ──────────────────────────────────────────────────────────────────────────────
from fastmcp import FastMCP

mcp = FastMCP("binja-mcp")

def _now() -> float:
    return time.monotonic()

def _request(
    method: str,
    endpoint: str,
    *,
    params: Dict[str, Any] | None = None,
    data: Dict[str, Any] | str | None = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """Wrapped request with retries and error handling."""
    session = requests.Session()
    session.timeout = (CONNECT_TIMEOUT, READ_TIMEOUT)

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            url = f"{BINJA_URL}/{endpoint}"
            if method == "GET":
                r = session.get(url, params=params)
            else:
                r = session.post(url, data=data)

            if 200 <= r.status_code < 300:
                # Try JSON; fall back to text split-lines
                try:
                    return r.json(), None
                except json.JSONDecodeError:
                    txt = r.text.strip()
                    if txt.startswith("{") or txt.startswith("["):
                        return json.loads(txt), None
                    return txt.splitlines(), None
            return None, f"{r.status_code} {r.reason}"
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_BASE * (attempt + 1))
            logger.warning(f"Request attempt {attempt + 1} failed: {last_err}")
    return None, last_err or "unknown error"

def _clamp_paging(offset: int | None, limit: int | None) -> Tuple[int, int]:
    o = max(0, int(offset or 0))
    l = min(MAX_LIMIT, max(1, int(limit or DEFAULT_LIMIT)))
    return o, l

# ──────────────────────────────────────────────────────────────────────────────
# Simple TTL cache for volatile list endpoints
# ──────────────────────────────────────────────────────────────────────────────
class TTLCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self.store: Dict[Tuple[str, Tuple[Tuple[str, Any], ...]], Tuple[float, Any]] = {}

    def _key(self, name: str, params: Dict[str, Any]) -> Tuple[str, Tuple[Tuple[str, Any], ...]]:
        return (name, tuple(sorted(params.items())))

    def get(self, name: str, params: Dict[str, Any]) -> Optional[Any]:
        k = self._key(name, params)
        item = self.store.get(k)
        if not item:
            return None
        t, val = item
        if _now() - t > self.ttl:
            self.store.pop(k, None)
            return None
        return val

    def set(self, name: str, params: Dict[str, Any], value: Any) -> None:
        k = self._key(name, params)
        self.store[k] = (_now(), value)

ttl_cache = TTLCache(CACHE_TTL)

def _list_endpoint(
    endpoint: str,
    *,
    offset: int,
    limit: int,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Generic reader with TTL caching and uniform envelope."""
    params = {"offset": offset, "limit": limit, **(extra or {})}
    cached = ttl_cache.get(endpoint, params)
    if cached is not None:
        return cached

    data, err = _request("GET", endpoint, params=params)
    if err:
        resp = {"ok": False, "error": err, "items": [], "hasMore": False}
        ttl_cache.set(endpoint, params, resp)
        return resp

    # Accept list or JSON dicts from the bridge, normalize to {"items": [...]}.
    if isinstance(data, dict) and "items" in data:
        items = data.get("items", [])
        has_more = bool(data.get("hasMore", False))
    elif isinstance(data, list):
        items = data
        # If bridge can't tell, infer hasMore by requesting +1 (optional).
        has_more = len(items) >= limit  # heuristic
    else:
        items = [data]
        has_more = False

    resp = {"ok": True, "items": items, "hasMore": has_more}
    ttl_cache.set(endpoint, params, resp)
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# Tools (synchronous)
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def health():
    """
    Cheap health probe for agents. Returns bridge reachability and basic status.
    """
    try:
        status, err = _request("GET", "status")
        return {
            "ok": err is None,
            "error": err,
            "status": status if isinstance(status, (str, dict)) else None,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"ok": False, "error": str(e), "status": None}

@mcp.tool()
def list_entities(kind: str, offset: int = 0, limit: int = 100, query: str = ""):
    """
    List entities with optional substring filter (where supported by the bridge).
    Valid kinds: methods, classes, segments, imports, exports, data, namespaces
    """
    try:
        # Validate kind parameter
        valid_kinds = ["methods", "classes", "segments", "imports", "exports", "data", "namespaces"]
        if kind not in valid_kinds:
            return {
                "ok": False,
                "error": f"Invalid kind. Must be one of: {', '.join(valid_kinds)}",
                "items": [],
                "hasMore": False
            }

        o, l = _clamp_paging(offset, limit)
        endpoint = kind  # Use kind directly since we validated it

        extra = {}
        # If your bridge has a separate search endpoint for functions:
        if query and kind == "methods":
            # Prefer a dedicated search endpoint
            return _list_endpoint("searchFunctions", offset=o, limit=l, extra={"query": query})
        elif query:
            # If other endpoints eventually support filtering, pass-through
            extra["query"] = query

        return _list_endpoint(endpoint, offset=o, limit=l, extra=extra)
    except Exception as e:
        logger.error(f"Error in list_entities: {e}")
        return {"ok": False, "error": str(e), "items": [], "hasMore": False}

@mcp.tool()
def decompile_function(name: str):
    """
    Decompile a function by exact name.
    """
    try:
        if not name or not name.strip():
            return {"ok": False, "error": "Function name cannot be empty"}

        data, err = _request("POST", "decompile", data=name.strip())
        if err:
            return {"ok": False, "error": err}
        # Normalize to JSON
        code = data if isinstance(data, str) else json.dumps(data)
        return {"ok": True, "code": code}
    except Exception as e:
        logger.error(f"Error in decompile_function: {e}")
        return {"ok": False, "error": str(e)}

# Add a simple overview tool to match your config
@mcp.tool()
def overview():
    """
    Get an overview of the loaded binary.
    """
    try:
        data, err = _request("GET", "overview")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "overview": data}
    except Exception as e:
        logger.error(f"Error in overview: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def get_binary_status():
    """
    Get the current binary status and basic information.
    """
    try:
        data, err = _request("GET", "binary")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "binary": data}
    except Exception as e:
        logger.error(f"Error in get_binary_status: {e}")
        return {"ok": False, "error": str(e)}

# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint (SSE)
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting Binary Ninja MCP SSE Server (synchronous)...")
    print("SSE URL: http://localhost:8010/sse")

    # Test connection on startup
    try:
        logger.info("Testing connection to Binary Ninja bridge...")
        response = requests.get(f"{BINJA_URL}/status", timeout=5.0)
        if response.status_code == 200:
            logger.info("✓ Successfully connected to Binary Ninja bridge")
        else:
            logger.warning(f"⚠ Binary Ninja bridge returned status {response.status_code}")
    except Exception as e:
        logger.error(f"✗ Failed to connect to Binary Ninja bridge: {e}")
        logger.info("Server will start anyway - connection will be retried on first request")

    mcp.run(transport="sse", host="0.0.0.0", port=8010)