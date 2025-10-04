# Multi-Binary Binary Ninja MCP Setup

This document describes how to set up and use the multi-binary functionality that allows you to work with multiple Binary Ninja instances simultaneously through the MCP bridge.

## Overview

The multi-binary setup extends the original single-binary MCP bridge to support:
- Multiple Binary Ninja instances running on different ports
- Automatic server discovery and routing
- Binary selection through MCP tools
- Concurrent analysis of multiple binaries

## Architecture

```
MCP Client (Claude Desktop, etc.)
    ↓
MCP Bridge (port 8010)
    ↓ (routing based on binary_id)
Multiple Binary Ninja Servers:
    - Binary A → port 9009
    - Binary B → port 9010  
    - Binary C → port 9011
    - etc.
```

## Setup Instructions

### 1. Install the Enhanced Plugin

The plugin now supports both legacy single-binary mode and new multi-binary mode.

### 2. Load Multiple Binaries in Binary Ninja

1. Open Binary Ninja
2. Load your first binary
3. Use `MCP Server > Start Server for This Binary`
4. Open a new Binary Ninja window (or tab)
5. Load your second binary
6. Use `MCP Server > Start Server for This Binary`
7. Repeat for additional binaries

Each binary will get its own MCP server on a unique port (9009, 9010, 9011, etc.).

### 3. Start the Multi-Binary Bridge

Use the new multi-binary bridge instead of the original:

```bash
python bridge/bn_mcp_bridge_multi_http.py
```

This bridge will:
- Automatically discover all running Binary Ninja MCP servers
- Provide routing to the correct server based on binary selection
- Expose enhanced tools for binary management

### 4. Configure Your MCP Client

Update your MCP client configuration to use the multi-binary bridge:

```json
{
  "mcpServers": {
    "binary_ninja_multi_mcp": {
      "command": "/path/to/venv/bin/python",
      "args": [
        "/path/to/binary_ninja_mcp/bridge/bn_mcp_bridge_multi_http.py"
      ]
    }
  }
}
```

## Usage

### Binary Selection

The multi-binary bridge provides several ways to select which binary to work with:

#### 1. List Available Binaries

```python
# List all available Binary Ninja servers
list_binary_servers()
```

This returns information about all running servers, including:
- `binary_id`: Unique identifier for the server
- `filename`: Name of the loaded binary
- `port`: Server port number
- Binary metadata (architecture, platform, etc.)

#### 2. Select Binary by Filename

```python
# Find a binary by filename (supports partial matches)
select_binary_by_filename("malware.exe")
```

#### 3. Use Binary ID in Tools

All MCP tools now accept an optional `binary_id` parameter:

```python
# List methods from a specific binary
list_entities(kind="methods", binary_id="port_9009")

# Decompile function from a specific binary  
decompile_function("main", binary_id="port_9010")

# Get data from a specific binary
list_data(binary_id="port_9011")
```

If no `binary_id` is provided, the bridge uses the first available server as default.

### Plugin Commands

The plugin provides several new commands for multi-binary management:

#### Main Operations
- `MCP Server > Start Server for This Binary` - Start server for current binary
- `MCP Server > Stop Server for This Binary` - Stop server for current binary  
- `MCP Server > Restart Server for This Binary` - Restart server for current binary

#### Management
- `MCP Server > Show Server Status` - Detailed status and connection info
- `MCP Server > List Active Servers` - Quick list of running servers
- `MCP Server > Stop All Servers` - Stop all MCP servers

#### Legacy (Backward Compatibility)
- `MCP Server > Legacy > Start MCP Server` - Original single-binary mode
- `MCP Server > Legacy > Stop MCP Server` - Stop legacy server

## Testing

Run the test script to verify your multi-binary setup:

```bash
python test_multi_binary.py
```

This will:
- Check bridge connectivity
- Discover available Binary Ninja servers
- Test binary selection functionality
- Verify routing works correctly

## Troubleshooting

### No Servers Found

If the bridge can't find any Binary Ninja servers:

1. Make sure Binary Ninja is running
2. Load at least one binary
3. Use `MCP Server > Start Server for This Binary`
4. Check that the server is accessible: `curl http://localhost:9009/status`

### Port Conflicts

If you get port conflicts:

1. Check what's running on ports 9009+: `netstat -an | grep 900`
2. Stop conflicting services
3. Restart Binary Ninja MCP servers

### Bridge Connection Issues

If the MCP client can't connect to the bridge:

1. Verify the bridge is running: `curl http://localhost:8010/health`
2. Check firewall settings
3. Ensure the bridge discovered servers: check startup logs

### Binary Selection Not Working

If binary selection isn't working:

1. Use `list_binary_servers()` to see available binaries
2. Check that `binary_id` values are correct
3. Verify the target server is still running

## Advanced Configuration

### Custom Port Ranges

You can modify the port range in `plugin/core/config.py`:

```python
@dataclass
class MultiBinaryServerConfig:
    host: str = "localhost"
    base_port: int = 9009  # Starting port
    max_servers: int = 10  # Maximum number of servers
```

### Bridge Discovery Settings

Modify discovery settings in `bridge/bn_mcp_bridge_multi_http.py`:

```python
BINJA_BASE_PORT = 9009      # Starting port to scan
MAX_SERVERS = 10            # Maximum servers to discover
discovery_interval = 30.0   # How often to rediscover (seconds)
```

## Migration from Single-Binary

If you're upgrading from the single-binary setup:

1. The original bridge (`bn_mcp_bridge_http.py`) still works for single-binary use
2. Use the new bridge (`bn_mcp_bridge_multi_http.py`) for multi-binary support
3. Legacy plugin commands are still available under `MCP Server > Legacy`
4. Your existing MCP client configuration will work with minor updates

## Examples

### Analyzing Multiple Malware Samples

```python
# List all loaded binaries
servers = list_binary_servers()

# Analyze each binary
for server in servers['servers']:
    binary_id = server['binary_id']
    filename = server['filename']
    
    print(f"Analyzing {filename}...")
    
    # Get overview
    overview(binary_id=binary_id)
    
    # List functions
    functions = list_entities(kind="methods", binary_id=binary_id, limit=10)
    
    # Decompile main function if it exists
    decompile_function("main", binary_id=binary_id)
```

### Comparing Binaries

```python
# Get function lists from two binaries
binary1_functions = list_entities(kind="methods", binary_id="port_9009")
binary2_functions = list_entities(kind="methods", binary_id="port_9010")

# Compare function names, signatures, etc.
```

This multi-binary setup enables powerful comparative analysis workflows that weren't possible with the single-binary approach.
