import binaryninja as bn
from .core.config import Config
from .server.http_server import MCPServer
from .core.multi_binary_manager import MultiBinaryManager


class BinaryNinjaMCP:
    """Legacy single-binary MCP server for backward compatibility."""

    def __init__(self):
        self.config = Config()
        self.server = MCPServer(self.config)

    def start_server(self, bv):
        try:
            self.server.binary_ops.current_view = bv
            self.server.start()
            bn.log_info(
                f"MCP server started successfully on http://{self.config.server.host}:{self.config.server.port}"
            )
        except Exception as e:
            bn.log_error(f"Failed to start MCP server: {str(e)}")

    def stop_server(self, bv):
        try:
            self.server.binary_ops.current_view = None
            self.server.stop()
            bn.log_info("Binary Ninja MCP plugin stopped successfully")
        except Exception as e:
            bn.log_error(f"Failed to stop server: {str(e)}")


class MultiBinaryMCP:
    """Multi-binary MCP server manager."""

    def __init__(self):
        self.manager = MultiBinaryManager()

    def start_server_for_binary(self, bv):
        """Start a new MCP server for the current binary."""
        if not bv:
            bn.log_error("No binary view provided")
            return

        binary_id = self.manager.start_server_for_binary(bv)
        if binary_id:
            info = self.manager.get_server_info(binary_id)
            if info:
                bn.log_info(
                    f"MCP server started for '{info['filename']}' on port {info['port']} (ID: {binary_id})"
                )
        else:
            bn.log_error("Failed to start MCP server for binary")

    def stop_server_for_binary(self, bv):
        """Stop the MCP server for the current binary."""
        if not bv:
            bn.log_error("No binary view provided")
            return

        binary_id = self.manager.get_binary_id_for_view(bv)
        if binary_id:
            if self.manager.stop_server_for_binary(binary_id):
                bn.log_info(f"MCP server stopped for binary ID {binary_id}")
            else:
                bn.log_error(f"Failed to stop MCP server for binary ID {binary_id}")
        else:
            bn.log_warning("No MCP server found for this binary")

    def list_servers(self, bv):
        """List all active MCP servers."""
        servers = self.manager.list_active_servers()
        if not servers:
            bn.log_info("No MCP servers currently running")
            bn.log_info("Use 'Start Server for This Binary' to start a server for the current binary")
            return

        bn.log_info(f"Active MCP servers ({len(servers)} total):")
        for server in servers:
            bn.log_info(f"  - {server['filename']} (ID: {server['binary_id']}) on port {server['port']}")
        bn.log_info("\nTo connect from MCP bridge, use the binary_id parameter in tools")
        bn.log_info("Example: list_entities(kind='methods', binary_id='port_9009')")

    def stop_all_servers(self, bv):
        """Stop all MCP servers."""
        servers = self.manager.list_active_servers()
        if not servers:
            bn.log_info("No MCP servers currently running")
            return

        count = len(servers)
        self.manager.stop_all_servers()
        bn.log_info(f"Stopped {count} MCP server(s)")

    def show_server_status(self, bv):
        """Show detailed status of all servers and connection info."""
        servers = self.manager.list_active_servers()

        bn.log_info("=== Binary Ninja MCP Server Status ===")

        if not servers:
            bn.log_info("No MCP servers currently running")
            bn.log_info("\nTo start a server:")
            bn.log_info("1. Open a binary in Binary Ninja")
            bn.log_info("2. Use 'MCP Server > Start Server for This Binary'")
            bn.log_info("3. The server will start on an available port (9009+)")
            return

        bn.log_info(f"Active servers: {len(servers)}")
        bn.log_info("")

        for i, server in enumerate(servers, 1):
            bn.log_info(f"{i}. Binary: {server['filename']}")
            bn.log_info(f"   ID: {server['binary_id']}")
            bn.log_info(f"   Port: {server['port']}")
            bn.log_info(f"   URL: http://localhost:{server['port']}")
            bn.log_info("")

        bn.log_info("=== MCP Bridge Connection ===")
        bn.log_info("To use with MCP bridge:")
        bn.log_info("1. Start the multi-binary bridge:")
        bn.log_info("   python bridge/bn_mcp_bridge_multi_http.py")
        bn.log_info("2. Use binary_id parameter in tools to select binary")
        bn.log_info("3. Use list_binary_servers() to see available binaries")

    def restart_server_for_binary(self, bv):
        """Restart the MCP server for the current binary."""
        if not bv:
            bn.log_error("No binary view provided")
            return

        # Stop existing server if running
        binary_id = self.manager.get_binary_id_for_view(bv)
        if binary_id:
            bn.log_info(f"Stopping existing server for binary ID {binary_id}")
            self.manager.stop_server_for_binary(binary_id)

        # Start new server
        self.start_server_for_binary(bv)


# Create both plugin instances
legacy_plugin = BinaryNinjaMCP()
multi_binary_plugin = MultiBinaryMCP()

# Legacy commands for backward compatibility
bn.PluginCommand.register(
    "MCP Server\\Legacy\\Start MCP Server",
    "Start the Binary Ninja MCP server (single binary, legacy mode)",
    legacy_plugin.start_server,
)

bn.PluginCommand.register(
    "MCP Server\\Legacy\\Stop MCP Server",
    "Stop the Binary Ninja MCP server (legacy mode)",
    legacy_plugin.stop_server,
)

# New multi-binary commands - Main operations
bn.PluginCommand.register(
    "MCP Server\\Start Server for This Binary",
    "Start an MCP server for the current binary",
    multi_binary_plugin.start_server_for_binary,
)

bn.PluginCommand.register(
    "MCP Server\\Stop Server for This Binary",
    "Stop the MCP server for the current binary",
    multi_binary_plugin.stop_server_for_binary,
)

bn.PluginCommand.register(
    "MCP Server\\Restart Server for This Binary",
    "Restart the MCP server for the current binary",
    multi_binary_plugin.restart_server_for_binary,
)

# Management commands
bn.PluginCommand.register(
    "MCP Server\\Show Server Status",
    "Show detailed status of all MCP servers and connection info",
    multi_binary_plugin.show_server_status,
)

bn.PluginCommand.register(
    "MCP Server\\List Active Servers",
    "List all active MCP servers",
    multi_binary_plugin.list_servers,
)

bn.PluginCommand.register(
    "MCP Server\\Stop All Servers",
    "Stop all MCP servers",
    multi_binary_plugin.stop_all_servers,
)

bn.log_info("Binary Ninja MCP plugin loaded successfully (with multi-binary support)")
