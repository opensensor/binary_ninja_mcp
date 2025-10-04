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
# Multi-Binary Configuration
# ──────────────────────────────────────────────────────────────────────────────
BINJA_BASE_URL = "http://localhost"
BINJA_BASE_PORT = 9009
MAX_SERVERS = 10
CONNECT_TIMEOUT = 1.0
READ_TIMEOUT = 8.0
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 0.2  # seconds
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000   # protect the UI & SSE
CACHE_TTL = 3.0   # seconds for volatile lists

# ──────────────────────────────────────────────────────────────────────────────
# Multi-Binary Server Discovery and Management
# ──────────────────────────────────────────────────────────────────────────────

class BinaryServerRegistry:
    """Registry to discover and manage multiple Binary Ninja server instances."""
    
    def __init__(self):
        self.servers: Dict[str, Dict[str, Any]] = {}  # binary_id -> server_info
        self.last_discovery = 0
        self.discovery_interval = 30.0  # seconds
        
    def discover_servers(self) -> None:
        """Discover available Binary Ninja MCP servers."""
        now = time.time()
        if now - self.last_discovery < self.discovery_interval:
            return
            
        logger.info("Discovering Binary Ninja MCP servers...")
        discovered = {}
        
        for port_offset in range(MAX_SERVERS):
            port = BINJA_BASE_PORT + port_offset
            url = f"{BINJA_BASE_URL}:{port}"
            
            try:
                response = requests.get(f"{url}/status", timeout=2.0)
                if response.status_code == 200:
                    status = response.json()
                    if status.get("loaded"):
                        binary_id = f"port_{port}"
                        discovered[binary_id] = {
                            "url": url,
                            "port": port,
                            "filename": status.get("filename", "unknown"),
                            "status": status,
                            "last_seen": now
                        }
                        logger.info(f"Found server at {url}: {status.get('filename', 'unknown')}")
            except Exception:
                # Server not available on this port
                continue
                
        self.servers = discovered
        self.last_discovery = now
        logger.info(f"Discovery complete. Found {len(self.servers)} active servers.")
        
    def get_servers(self) -> Dict[str, Dict[str, Any]]:
        """Get all discovered servers, refreshing if needed."""
        self.discover_servers()
        return self.servers.copy()
        
    def get_server_by_id(self, binary_id: str) -> Optional[Dict[str, Any]]:
        """Get server info by binary ID."""
        self.discover_servers()
        return self.servers.get(binary_id)
        
    def get_default_server(self) -> Optional[Dict[str, Any]]:
        """Get the first available server as default."""
        servers = self.get_servers()
        return next(iter(servers.values())) if servers else None

# Global registry instance
server_registry = BinaryServerRegistry()

# ──────────────────────────────────────────────────────────────────────────────
# MCP app (synchronous)
# ──────────────────────────────────────────────────────────────────────────────
from fastmcp import FastMCP

mcp = FastMCP("binja-multi-mcp")

def _now() -> float:
    return time.monotonic()

def _request(
    method: str,
    endpoint: str,
    *,
    params: Dict[str, Any] | None = None,
    data: Dict[str, Any] | str | None = None,
    binary_id: str | None = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """Wrapped request with retries and error handling, supporting multiple servers."""
    
    # Determine target server
    if binary_id:
        server_info = server_registry.get_server_by_id(binary_id)
        if not server_info:
            return None, f"Binary server '{binary_id}' not found"
        base_url = server_info["url"]
    else:
        # Use default server
        server_info = server_registry.get_default_server()
        if not server_info:
            return None, "No Binary Ninja servers available"
        base_url = server_info["url"]
    
    session = requests.Session()
    session.timeout = (CONNECT_TIMEOUT, READ_TIMEOUT)

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            url = f"{base_url}/{endpoint}"
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
    binary_id: str | None = None,
) -> Dict[str, Any]:
    """Generic reader with TTL caching and uniform envelope."""
    params = {"offset": offset, "limit": limit, **(extra or {})}
    
    # Include binary_id in cache key
    cache_key = f"{endpoint}_{binary_id or 'default'}"
    cached = ttl_cache.get(cache_key, params)
    if cached is not None:
        return cached

    data, err = _request("GET", endpoint, params=params, binary_id=binary_id)
    if err:
        resp = {"ok": False, "error": err, "items": [], "hasMore": False}
        ttl_cache.set(cache_key, params, resp)
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
    ttl_cache.set(cache_key, params, resp)
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# Tools (synchronous) - Multi-Binary Support
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_binary_servers():
    """
    List all available Binary Ninja MCP servers and their loaded binaries.
    """
    try:
        servers = server_registry.get_servers()
        server_list = []

        for binary_id, info in servers.items():
            # Get enhanced binary info
            binary_info, err = _request("GET", "binary/info", binary_id=binary_id)
            if not err and isinstance(binary_info, dict):
                enhanced_info = {
                    "binary_id": binary_id,
                    "port": info["port"],
                    "url": info["url"],
                    "last_seen": info["last_seen"],
                    **binary_info
                }
            else:
                enhanced_info = {
                    "binary_id": binary_id,
                    "filename": info["filename"],
                    "port": info["port"],
                    "url": info["url"],
                    "last_seen": info["last_seen"],
                    "loaded": True
                }
            server_list.append(enhanced_info)

        return {
            "ok": True,
            "servers": server_list,
            "count": len(server_list)
        }
    except Exception as e:
        logger.error(f"Error listing servers: {e}")
        return {"ok": False, "error": str(e), "servers": []}

@mcp.tool()
def select_binary_by_filename(filename: str):
    """
    Select a binary server by filename (or partial filename match).
    Returns the binary_id that can be used in other tools.
    """
    try:
        servers = server_registry.get_servers()
        matches = []

        for binary_id, info in servers.items():
            server_filename = info.get("filename", "")
            if filename.lower() in server_filename.lower():
                matches.append({
                    "binary_id": binary_id,
                    "filename": server_filename,
                    "port": info["port"],
                    "exact_match": filename.lower() == server_filename.lower()
                })

        if not matches:
            return {
                "ok": False,
                "error": f"No binary found matching filename '{filename}'",
                "available_binaries": [info["filename"] for info in servers.values()]
            }

        # Sort by exact match first, then alphabetically
        matches.sort(key=lambda x: (not x["exact_match"], x["filename"]))

        return {
            "ok": True,
            "matches": matches,
            "selected": matches[0]["binary_id"] if matches else None,
            "message": f"Found {len(matches)} match(es) for '{filename}'"
        }

    except Exception as e:
        logger.error(f"Error selecting binary: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def get_binary_info(binary_id: str):
    """
    Get detailed information about a specific binary server.
    """
    try:
        if not binary_id:
            return {"ok": False, "error": "binary_id is required"}

        server_info = server_registry.get_server_by_id(binary_id)
        if not server_info:
            return {"ok": False, "error": f"Binary server '{binary_id}' not found"}

        # Get enhanced binary info from the server
        binary_info, err = _request("GET", "binary/info", binary_id=binary_id)
        if err:
            return {"ok": False, "error": f"Failed to get binary info: {err}"}

        return {
            "ok": True,
            "binary_id": binary_id,
            "server_info": server_info,
            "binary_info": binary_info
        }

    except Exception as e:
        logger.error(f"Error getting binary info: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def health(binary_id: str = ""):
    """
    Cheap health probe for agents. Returns bridge reachability and basic status.
    If binary_id is provided, checks that specific server; otherwise checks default.
    """
    try:
        status, err = _request("GET", "status", binary_id=binary_id or None)
        return {
            "ok": err is None,
            "error": err,
            "status": status if isinstance(status, (str, dict)) else None,
            "binary_id": binary_id or "default"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"ok": False, "error": str(e), "status": None, "binary_id": binary_id or "default"}

@mcp.tool()
def list_entities(kind: str, offset: int = 0, limit: int = 100, query: str = "", binary_id: str = ""):
    """
    List entities with optional substring filter (where supported by the bridge).
    Valid kinds: methods, classes, segments, imports, exports, data, namespaces

    Parameters:
    - binary_id: ID of the binary server to query (empty for default)
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
            return _list_endpoint("searchFunctions", offset=o, limit=l, extra={"query": query}, binary_id=binary_id or None)
        elif query:
            # If other endpoints eventually support filtering, pass-through
            extra["query"] = query

        return _list_endpoint(endpoint, offset=o, limit=l, extra=extra, binary_id=binary_id or None)
    except Exception as e:
        logger.error(f"Error in list_entities: {e}")
        return {"ok": False, "error": str(e), "items": [], "hasMore": False}

@mcp.tool()
def list_data(offset: int = 0, limit: int = 100, query: str = "", filter_type: str = "", binary_id: str = ""):
    """
    List data items (variables, constants, arrays, etc.) in the binary.

    Parameters:
    - offset: Starting index for pagination (default: 0)
    - limit: Maximum number of items to return (default: 100, max: 1000)
    - query: Optional substring filter for data item names
    - filter_type: Optional filter by data type (e.g., "array", "string", "struct", "global")
    - binary_id: ID of the binary server to query (empty for default)

    Returns a dictionary with:
    - ok: Success status
    - items: List of data items with details (name, address, size, type, etc.)
    - hasMore: Whether more items are available
    - error: Error message if any
    """
    try:
        o, l = _clamp_paging(offset, limit)

        extra = {}
        if query:
            extra["query"] = query
        if filter_type:
            extra["type"] = filter_type

        # Use the data endpoint
        result = _list_endpoint("data", offset=o, limit=l, extra=extra, binary_id=binary_id or None)

        # Enhance the response with additional context if available
        if result.get("ok") and result.get("items"):
            # Add any additional processing or formatting of data items here
            for item in result["items"]:
                # Ensure consistent structure for data items
                if isinstance(item, dict):
                    # Add default fields if missing
                    item.setdefault("name", "unnamed")
                    item.setdefault("address", None)
                    item.setdefault("size", 0)
                    item.setdefault("type", "unknown")

        return result
    except Exception as e:
        logger.error(f"Error in list_data: {e}")
        return {"ok": False, "error": str(e), "items": [], "hasMore": False}

@mcp.tool()
def get_data_item(name: str = "", address: str = "", binary_id: str = ""):
    """
    Get detailed information about a specific data item.

    Parameters:
    - name: Name of the data item (if known)
    - address: Address of the data item (hex string, e.g., "0x401000")
    - binary_id: ID of the binary server to query (empty for default)

    At least one of name or address must be provided.

    Returns detailed information about the data item including:
    - name, address, size, type
    - value (if readable)
    - cross-references (functions that use this data)
    - section information
    """
    try:
        if not name and not address:
            return {"ok": False, "error": "Either name or address must be provided"}

        # Prepare the request
        params = {}
        if name:
            params["name"] = name.strip()
        if address:
            params["address"] = address.strip()

        # Request detailed data item information
        data, err = _request("GET", "data/item", params=params, binary_id=binary_id or None)

        if err:
            return {"ok": False, "error": err}

        # Normalize the response
        if isinstance(data, dict):
            return {"ok": True, **data}
        else:
            return {"ok": True, "data": data}

    except Exception as e:
        logger.error(f"Error in get_data_item: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def read_memory(address: str, size: int, format: str = "hex", binary_id: str = ""):
    """
    Read raw memory/data from the binary at a specific address.

    Parameters:
    - address: Starting address (hex string, e.g., "0x401000")
    - size: Number of bytes to read
    - format: Output format:
        - "hex": Hexadecimal string
        - "bytes": Raw byte array
        - "ascii": ASCII string (non-printable as dots)
        - "hexdump": Formatted hex dump with ASCII
    - binary_id: ID of the binary server to query (empty for default)

    Returns the memory content in the requested format.
    """
    try:
        if not address:
            return {"ok": False, "error": "Address is required"}
        if size <= 0 or size > 4096:  # Reasonable limit
            return {"ok": False, "error": "Size must be between 1 and 4096 bytes"}

        params = {
            "address": address.strip(),
            "size": size,
            "format": format
        }

        # Request raw memory read
        data, err = _request("GET", "memory", params=params, binary_id=binary_id or None)

        if err:
            return {"ok": False, "error": err}

        return {
            "ok": True,
            "address": address,
            "size": size,
            "format": format,
            "data": data,
            "binary_id": binary_id or "default"
        }

    except Exception as e:
        logger.error(f"Error in read_memory: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def search_data_references(address: str = "", pattern: str = "", binary_id: str = ""):
    """
    Search for references to data items in the binary.

    Parameters:
    - address: Address of the data item to find references to
    - pattern: Byte pattern to search for (hex string)
    - binary_id: ID of the binary server to query (empty for default)

    Returns a list of locations where the data is referenced.
    """
    try:
        if not address and not pattern:
            return {"ok": False, "error": "Either address or pattern must be provided"}

        params = {}
        if address:
            params["address"] = address.strip()
        if pattern:
            params["pattern"] = pattern.strip()

        data, err = _request("GET", "data/references", params=params, binary_id=binary_id or None)

        if err:
            return {"ok": False, "error": err}

        # Format the response
        if isinstance(data, list):
            return {"ok": True, "references": data, "binary_id": binary_id or "default"}
        elif isinstance(data, dict):
            return {"ok": True, "binary_id": binary_id or "default", **data}
        else:
            return {"ok": True, "references": [], "binary_id": binary_id or "default"}

    except Exception as e:
        logger.error(f"Error in search_data_references: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def decompile_function(name: str, binary_id: str = ""):
    """
    Decompile a function by exact name.

    Parameters:
    - name: Function name to decompile
    - binary_id: ID of the binary server to query (empty for default)
    """
    try:
        if not name or not name.strip():
            return {"ok": False, "error": "Function name cannot be empty"}

        data, err = _request("POST", "decompile", data=name.strip(), binary_id=binary_id or None)
        if err:
            return {"ok": False, "error": err}
        # Normalize to JSON
        code = data if isinstance(data, str) else json.dumps(data)
        return {"ok": True, "code": code, "binary_id": binary_id or "default"}
    except Exception as e:
        logger.error(f"Error in decompile_function: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def overview(binary_id: str = ""):
    """
    Get an overview of the loaded binary.

    Parameters:
    - binary_id: ID of the binary server to query (empty for default)
    """
    try:
        data, err = _request("GET", "overview", binary_id=binary_id or None)
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "overview": data, "binary_id": binary_id or "default"}
    except Exception as e:
        logger.error(f"Error in overview: {e}")
        return {"ok": False, "error": str(e)}

@mcp.tool()
def get_binary_status(binary_id: str = ""):
    """
    Get the current binary status and basic information.

    Parameters:
    - binary_id: ID of the binary server to query (empty for default)
    """
    try:
        data, err = _request("GET", "binary", binary_id=binary_id or None)
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "binary": data, "binary_id": binary_id or "default"}
    except Exception as e:
        logger.error(f"Error in get_binary_status: {e}")
        return {"ok": False, "error": str(e)}

# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint (SSE) - Multi-Binary Support
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting Binary Ninja Multi-Binary MCP SSE Server (synchronous)...")
    print("SSE URL: http://localhost:8010/sse")

    # Test connection and discover servers on startup
    try:
        logger.info("Discovering Binary Ninja MCP servers...")
        server_registry.discover_servers()
        servers = server_registry.get_servers()

        if servers:
            logger.info(f"✓ Found {len(servers)} Binary Ninja MCP servers:")
            for binary_id, info in servers.items():
                logger.info(f"  - {info['filename']} at {info['url']} (ID: {binary_id})")
        else:
            logger.warning("⚠ No Binary Ninja MCP servers found")
            logger.info("Make sure Binary Ninja is running with MCP servers started")
            logger.info("Server will start anyway - servers will be discovered on first request")

    except Exception as e:
        logger.error(f"✗ Failed to discover Binary Ninja servers: {e}")
        logger.info("Server will start anyway - discovery will be retried on first request")

    mcp.run(transport="sse", host="0.0.0.0", port=8010)
