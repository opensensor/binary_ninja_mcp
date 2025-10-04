import binaryninja as bn
from typing import Dict, Optional, List
import hashlib
import os
from .config import Config, MultiBinaryRegistry
from ..server.http_server import MCPServer


class MultiBinaryManager:
    """Manager for multiple Binary Ninja MCP servers, each handling a different binary."""
    
    def __init__(self):
        self.config = Config()
        self.registry = MultiBinaryRegistry()
        self._servers: Dict[str, MCPServer] = {}
        
    def _generate_binary_id(self, binary_view) -> str:
        """Generate a unique ID for a binary based on its filename and hash."""
        if not binary_view or not binary_view.file:
            return "unknown"
            
        filename = os.path.basename(binary_view.file.filename)
        # Use a simple hash of the filename and file size for uniqueness
        content = f"{filename}_{binary_view.length if hasattr(binary_view, 'length') else 0}"
        return hashlib.md5(content.encode()).hexdigest()[:8]
        
    def start_server_for_binary(self, binary_view) -> Optional[str]:
        """Start a new MCP server for the given binary view.
        
        Returns:
            The binary ID if successful, None if failed
        """
        try:
            binary_id = self._generate_binary_id(binary_view)
            
            # Check if this binary already has a server
            if binary_id in self._servers:
                bn.log_info(f"Server already running for binary {binary_id}")
                return binary_id
                
            # Get next available port
            port = self.registry.get_next_port(self.config.multi_binary)
            
            # Create a custom config for this server
            server_config = Config()
            server_config.server.port = port
            
            # Create and start the server
            server = MCPServer(server_config)
            server.binary_ops.current_view = binary_view
            server.start()
            
            # Register the server
            self._servers[binary_id] = server
            self.registry.register_binary(binary_id, binary_view, server, port)
            
            bn.log_info(
                f"MCP server started for binary '{binary_view.file.filename}' "
                f"(ID: {binary_id}) on port {port}"
            )
            
            return binary_id
            
        except Exception as e:
            bn.log_error(f"Failed to start MCP server for binary: {str(e)}")
            return None
            
    def stop_server_for_binary(self, binary_id: str) -> bool:
        """Stop the MCP server for the given binary ID.
        
        Returns:
            True if successful, False if failed
        """
        try:
            if binary_id not in self._servers:
                bn.log_warning(f"No server found for binary ID {binary_id}")
                return False
                
            server = self._servers[binary_id]
            server.stop()
            
            # Unregister the server
            del self._servers[binary_id]
            self.registry.unregister_binary(binary_id)
            
            bn.log_info(f"MCP server stopped for binary ID {binary_id}")
            return True
            
        except Exception as e:
            bn.log_error(f"Failed to stop MCP server for binary {binary_id}: {str(e)}")
            return False
            
    def stop_all_servers(self) -> None:
        """Stop all running MCP servers."""
        binary_ids = list(self._servers.keys())
        for binary_id in binary_ids:
            self.stop_server_for_binary(binary_id)
            
    def get_server_info(self, binary_id: str) -> Optional[Dict]:
        """Get information about a server for the given binary ID."""
        return self.registry.get_binary_info(binary_id)
        
    def list_active_servers(self) -> List[Dict]:
        """List all active servers and their binary information."""
        return self.registry.list_binaries()
        
    def get_binary_id_for_view(self, binary_view) -> Optional[str]:
        """Get the binary ID for a given binary view if it has a server."""
        target_id = self._generate_binary_id(binary_view)
        return target_id if target_id in self._servers else None
        
    def is_server_running_for_binary(self, binary_view) -> bool:
        """Check if a server is already running for the given binary."""
        binary_id = self._generate_binary_id(binary_view)
        return binary_id in self._servers
