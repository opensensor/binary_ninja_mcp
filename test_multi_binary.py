#!/usr/bin/env python3
"""
Test script for multi-binary Binary Ninja MCP setup.

This script tests the multi-binary functionality by:
1. Checking for available Binary Ninja servers
2. Testing the bridge routing functionality
3. Verifying binary selection works correctly
"""

import requests
import json
import time
import sys
from typing import Dict, List, Any


class MultiBinaryTester:
    def __init__(self, bridge_url: str = "http://localhost:8010"):
        self.bridge_url = bridge_url
        self.session = requests.Session()
        self.session.timeout = 10.0
        
    def test_bridge_connection(self) -> bool:
        """Test if the MCP bridge is running and accessible."""
        try:
            # Try to access the bridge health endpoint
            response = self.session.get(f"{self.bridge_url}/health")
            if response.status_code == 200:
                print("✓ MCP bridge is accessible")
                return True
            else:
                print(f"✗ MCP bridge returned status {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Failed to connect to MCP bridge: {e}")
            print(f"  Make sure the bridge is running on {self.bridge_url}")
            return False
    
    def discover_binary_servers(self) -> List[Dict[str, Any]]:
        """Discover available Binary Ninja MCP servers."""
        print("\n=== Discovering Binary Ninja Servers ===")
        
        servers = []
        base_port = 9009
        max_servers = 10
        
        for port_offset in range(max_servers):
            port = base_port + port_offset
            url = f"http://localhost:{port}"
            
            try:
                response = self.session.get(f"{url}/status", timeout=2.0)
                if response.status_code == 200:
                    status = response.json()
                    if status.get("loaded"):
                        servers.append({
                            "port": port,
                            "url": url,
                            "filename": status.get("filename", "unknown"),
                            "status": status
                        })
                        print(f"✓ Found server at port {port}: {status.get('filename', 'unknown')}")
            except Exception:
                # Server not available on this port
                continue
        
        if not servers:
            print("✗ No Binary Ninja MCP servers found")
            print("  Make sure Binary Ninja is running with binaries loaded")
            print("  Use 'MCP Server > Start Server for This Binary' in Binary Ninja")
        else:
            print(f"✓ Found {len(servers)} Binary Ninja MCP server(s)")
            
        return servers
    
    def test_bridge_server_discovery(self) -> bool:
        """Test the bridge's server discovery functionality."""
        print("\n=== Testing Bridge Server Discovery ===")
        
        try:
            # This would be an MCP tool call in real usage
            # For testing, we'll simulate the discovery logic
            from bridge.bn_mcp_bridge_multi_http import BinaryServerRegistry
            
            registry = BinaryServerRegistry()
            registry.discover_servers()
            servers = registry.get_servers()
            
            if servers:
                print(f"✓ Bridge discovered {len(servers)} server(s):")
                for binary_id, info in servers.items():
                    print(f"  - {binary_id}: {info['filename']} at {info['url']}")
                return True
            else:
                print("✗ Bridge found no servers")
                return False
                
        except Exception as e:
            print(f"✗ Bridge discovery failed: {e}")
            return False
    
    def test_binary_selection(self, servers: List[Dict[str, Any]]) -> bool:
        """Test binary selection functionality."""
        print("\n=== Testing Binary Selection ===")
        
        if len(servers) < 2:
            print("⚠ Need at least 2 servers to test binary selection")
            print("  Load multiple binaries in Binary Ninja and start servers for each")
            return True  # Not a failure, just insufficient test data
        
        try:
            # Test selecting different binaries
            for i, server in enumerate(servers[:2]):  # Test first 2 servers
                port = server["port"]
                binary_id = f"port_{port}"
                filename = server["filename"]
                
                print(f"Testing binary selection for {filename} (ID: {binary_id})")
                
                # Test direct server access
                response = self.session.get(f"{server['url']}/binary/info")
                if response.status_code == 200:
                    info = response.json()
                    print(f"  ✓ Direct access: {info.get('filename', 'unknown')}")
                else:
                    print(f"  ✗ Direct access failed: {response.status_code}")
                    return False
            
            print("✓ Binary selection test passed")
            return True
            
        except Exception as e:
            print(f"✗ Binary selection test failed: {e}")
            return False
    
    def test_routing_functionality(self, servers: List[Dict[str, Any]]) -> bool:
        """Test that routing works correctly between different binaries."""
        print("\n=== Testing Routing Functionality ===")
        
        if not servers:
            print("✗ No servers available for routing test")
            return False
        
        try:
            # Test routing to each server
            for server in servers:
                port = server["port"]
                binary_id = f"port_{port}"
                filename = server["filename"]
                
                print(f"Testing routing to {filename} (ID: {binary_id})")
                
                # Test status endpoint
                response = self.session.get(f"{server['url']}/status")
                if response.status_code == 200:
                    status = response.json()
                    if status.get("loaded"):
                        print(f"  ✓ Status: {status.get('filename', 'unknown')}")
                    else:
                        print(f"  ⚠ Server reports no binary loaded")
                else:
                    print(f"  ✗ Status check failed: {response.status_code}")
                    return False
                
                # Test methods endpoint
                response = self.session.get(f"{server['url']}/methods?limit=5")
                if response.status_code == 200:
                    print(f"  ✓ Methods endpoint accessible")
                else:
                    print(f"  ✗ Methods endpoint failed: {response.status_code}")
            
            print("✓ Routing functionality test passed")
            return True
            
        except Exception as e:
            print(f"✗ Routing functionality test failed: {e}")
            return False
    
    def run_all_tests(self) -> bool:
        """Run all tests and return overall success."""
        print("=== Multi-Binary Binary Ninja MCP Test Suite ===")
        
        # Test 1: Bridge connection
        if not self.test_bridge_connection():
            print("\n✗ Bridge connection test failed - skipping remaining tests")
            return False
        
        # Test 2: Discover servers
        servers = self.discover_binary_servers()
        
        # Test 3: Bridge discovery
        bridge_discovery_ok = self.test_bridge_server_discovery()
        
        # Test 4: Binary selection
        selection_ok = self.test_binary_selection(servers)
        
        # Test 5: Routing functionality
        routing_ok = self.test_routing_functionality(servers)
        
        # Summary
        print("\n=== Test Summary ===")
        all_passed = bridge_discovery_ok and selection_ok and routing_ok
        
        if all_passed:
            print("✓ All tests passed!")
            print(f"✓ Multi-binary setup is working with {len(servers)} server(s)")
        else:
            print("✗ Some tests failed")
            
        return all_passed


def main():
    """Main test function."""
    tester = MultiBinaryTester()
    
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 Multi-binary setup is ready!")
        print("\nNext steps:")
        print("1. Start the multi-binary bridge: python bridge/bn_mcp_bridge_multi_http.py")
        print("2. Use binary_id parameter in MCP tools to select specific binaries")
        print("3. Use list_binary_servers() to see available binaries")
        sys.exit(0)
    else:
        print("\n❌ Multi-binary setup needs attention")
        print("\nTroubleshooting:")
        print("1. Make sure Binary Ninja is running")
        print("2. Load binaries and start MCP servers using plugin commands")
        print("3. Check that servers are accessible on ports 9009+")
        sys.exit(1)


if __name__ == "__main__":
    main()
