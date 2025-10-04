from dataclasses import dataclass
from typing import Optional, Dict, List
import threading


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 9009
    debug: bool = False


@dataclass
class MultiBinaryServerConfig:
    host: str = "localhost"
    base_port: int = 9009
    max_servers: int = 10
    debug: bool = False

    def get_port_for_index(self, index: int) -> int:
        """Get the port number for a server at the given index."""
        return self.base_port + index


@dataclass
class BinaryNinjaConfig:
    api_version: Optional[str] = None
    log_level: str = "INFO"


class Config:
    def __init__(self):
        self.server = ServerConfig()
        self.multi_binary = MultiBinaryServerConfig()
        self.binary_ninja = BinaryNinjaConfig()


class MultiBinaryRegistry:
    """Registry to track multiple binary servers and their assignments."""

    def __init__(self):
        self._lock = threading.Lock()
        self._servers: Dict[str, Dict] = {}  # binary_id -> server_info
        self._port_to_binary: Dict[int, str] = {}  # port -> binary_id
        self._next_port_index = 0

    def register_binary(self, binary_id: str, binary_view, server_instance, port: int) -> None:
        """Register a binary with its server instance."""
        with self._lock:
            self._servers[binary_id] = {
                'binary_view': binary_view,
                'server': server_instance,
                'port': port,
                'filename': binary_view.file.filename if binary_view else None
            }
            self._port_to_binary[port] = binary_id

    def unregister_binary(self, binary_id: str) -> None:
        """Unregister a binary and its server."""
        with self._lock:
            if binary_id in self._servers:
                port = self._servers[binary_id]['port']
                del self._servers[binary_id]
                if port in self._port_to_binary:
                    del self._port_to_binary[port]

    def get_binary_info(self, binary_id: str) -> Optional[Dict]:
        """Get information about a registered binary."""
        with self._lock:
            return self._servers.get(binary_id)

    def get_binary_by_port(self, port: int) -> Optional[str]:
        """Get binary ID by port number."""
        with self._lock:
            return self._port_to_binary.get(port)

    def list_binaries(self) -> List[Dict]:
        """List all registered binaries."""
        with self._lock:
            return [
                {
                    'binary_id': binary_id,
                    'filename': info['filename'],
                    'port': info['port']
                }
                for binary_id, info in self._servers.items()
            ]

    def get_next_port(self, config: MultiBinaryServerConfig) -> int:
        """Get the next available port."""
        with self._lock:
            while self._next_port_index < config.max_servers:
                port = config.get_port_for_index(self._next_port_index)
                if port not in self._port_to_binary:
                    self._next_port_index += 1
                    return port
                self._next_port_index += 1
            raise RuntimeError(f"No available ports (max {config.max_servers} servers)")

    def is_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        with self._lock:
            return port not in self._port_to_binary
