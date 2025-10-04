#!/usr/bin/env python3
"""
Example script demonstrating multi-binary analysis with Binary Ninja MCP.

This script shows how to:
1. Discover available Binary Ninja servers
2. Select specific binaries for analysis
3. Perform comparative analysis across multiple binaries
4. Use the routing functionality effectively

Prerequisites:
- Binary Ninja running with multiple binaries loaded
- MCP servers started for each binary
- Multi-binary bridge running (bn_mcp_bridge_multi_http.py)
"""

import json
from typing import List, Dict, Any


def discover_binaries():
    """Discover all available Binary Ninja servers."""
    print("=== Discovering Available Binaries ===")
    
    # In a real MCP client, this would be an MCP tool call
    # For this example, we'll simulate the expected response
    servers = {
        "ok": True,
        "servers": [
            {
                "binary_id": "port_9009",
                "filename": "/path/to/malware1.exe",
                "basename": "malware1.exe",
                "port": 9009,
                "arch": "x86_64",
                "platform": "windows",
                "function_count": 245
            },
            {
                "binary_id": "port_9010", 
                "filename": "/path/to/malware2.exe",
                "basename": "malware2.exe",
                "port": 9010,
                "arch": "x86_64",
                "platform": "windows",
                "function_count": 189
            },
            {
                "binary_id": "port_9011",
                "filename": "/path/to/goodware.exe", 
                "basename": "goodware.exe",
                "port": 9011,
                "arch": "x86_64",
                "platform": "windows",
                "function_count": 1024
            }
        ],
        "count": 3
    }
    
    if servers["ok"]:
        print(f"Found {servers['count']} binary servers:")
        for server in servers["servers"]:
            print(f"  - {server['basename']} ({server['arch']}) - {server['function_count']} functions")
            print(f"    ID: {server['binary_id']}, Port: {server['port']}")
        return servers["servers"]
    else:
        print("No binary servers found!")
        return []


def select_binary_by_name(servers: List[Dict], name: str) -> str:
    """Select a binary by filename."""
    print(f"\n=== Selecting Binary: {name} ===")
    
    for server in servers:
        if name.lower() in server["basename"].lower():
            print(f"Selected: {server['basename']} (ID: {server['binary_id']})")
            return server["binary_id"]
    
    print(f"Binary '{name}' not found!")
    return ""


def analyze_binary_overview(binary_id: str, name: str):
    """Get overview information for a specific binary."""
    print(f"\n=== Analyzing {name} Overview ===")
    
    # Simulate MCP tool calls
    # In real usage: overview(binary_id=binary_id)
    overview_data = {
        "ok": True,
        "overview": {
            "filename": f"/path/to/{name}",
            "size": "2.1 MB",
            "entry_point": "0x401000",
            "sections": ["text", "data", "rdata", "idata"],
            "imports": 45,
            "exports": 12
        }
    }
    
    if overview_data["ok"]:
        overview = overview_data["overview"]
        print(f"  File: {overview['filename']}")
        print(f"  Size: {overview['size']}")
        print(f"  Entry Point: {overview['entry_point']}")
        print(f"  Sections: {', '.join(overview['sections'])}")
        print(f"  Imports: {overview['imports']}, Exports: {overview['exports']}")


def get_function_list(binary_id: str, name: str, limit: int = 10) -> List[str]:
    """Get list of functions from a specific binary."""
    print(f"\n=== Getting Functions from {name} ===")
    
    # Simulate MCP tool call
    # In real usage: list_entities(kind="methods", binary_id=binary_id, limit=limit)
    functions_data = {
        "ok": True,
        "items": [
            {"name": "main", "address": "0x401000"},
            {"name": "WinMain", "address": "0x401050"},
            {"name": "sub_401100", "address": "0x401100"},
            {"name": "decrypt_string", "address": "0x401200"},
            {"name": "network_connect", "address": "0x401300"},
            {"name": "file_operations", "address": "0x401400"},
            {"name": "registry_modify", "address": "0x401500"},
            {"name": "anti_debug", "address": "0x401600"},
            {"name": "payload_execute", "address": "0x401700"},
            {"name": "cleanup", "address": "0x401800"}
        ][:limit]
    }
    
    if functions_data["ok"]:
        function_names = [func["name"] for func in functions_data["items"]]
        print(f"  Found {len(function_names)} functions:")
        for func in functions_data["items"]:
            print(f"    - {func['name']} @ {func['address']}")
        return function_names
    else:
        print("  Failed to get function list")
        return []


def decompile_function(binary_id: str, function_name: str, binary_name: str):
    """Decompile a specific function."""
    print(f"\n=== Decompiling {function_name} from {binary_name} ===")
    
    # Simulate MCP tool call
    # In real usage: decompile_function(function_name, binary_id=binary_id)
    decompile_data = {
        "ok": True,
        "code": f"""
// Decompiled {function_name} from {binary_name}
int {function_name}()
{{
    // Function implementation would appear here
    // This is simulated output for demonstration
    return 0;
}}
"""
    }
    
    if decompile_data["ok"]:
        print("  Decompilation successful:")
        print(decompile_data["code"])
    else:
        print("  Decompilation failed")


def compare_function_lists(servers: List[Dict]):
    """Compare function lists across multiple binaries."""
    print("\n=== Comparing Function Lists Across Binaries ===")
    
    all_functions = {}
    
    for server in servers:
        binary_id = server["binary_id"]
        name = server["basename"]
        functions = get_function_list(binary_id, name, limit=20)
        all_functions[name] = set(functions)
    
    # Find common functions
    if len(all_functions) >= 2:
        binary_names = list(all_functions.keys())
        common_functions = set.intersection(*all_functions.values())
        
        print(f"\nCommon functions across all binaries ({len(common_functions)}):")
        for func in sorted(common_functions):
            print(f"  - {func}")
        
        # Find unique functions per binary
        for name in binary_names:
            unique = all_functions[name] - set.union(*(all_functions[other] for other in binary_names if other != name))
            if unique:
                print(f"\nUnique to {name} ({len(unique)}):")
                for func in sorted(unique):
                    print(f"  - {func}")


def analyze_suspicious_functions(servers: List[Dict]):
    """Look for potentially suspicious function names across binaries."""
    print("\n=== Analyzing Suspicious Function Names ===")
    
    suspicious_keywords = [
        "decrypt", "encrypt", "obfuscate", "anti", "debug", "vm", "sandbox",
        "inject", "hook", "payload", "backdoor", "keylog", "steal", "hide"
    ]
    
    for server in servers:
        binary_id = server["binary_id"]
        name = server["basename"]
        functions = get_function_list(binary_id, name, limit=50)
        
        suspicious = []
        for func in functions:
            for keyword in suspicious_keywords:
                if keyword.lower() in func.lower():
                    suspicious.append(func)
                    break
        
        if suspicious:
            print(f"\nSuspicious functions in {name}:")
            for func in suspicious:
                print(f"  - {func}")
                # Could decompile these for further analysis
                # decompile_function(binary_id, func, name)


def main():
    """Main analysis workflow."""
    print("Multi-Binary Analysis Example")
    print("=" * 40)
    
    # Step 1: Discover available binaries
    servers = discover_binaries()
    if not servers:
        print("No binaries available for analysis!")
        return
    
    # Step 2: Analyze each binary individually
    for server in servers:
        binary_id = server["binary_id"]
        name = server["basename"]
        
        analyze_binary_overview(binary_id, name)
        get_function_list(binary_id, name, limit=5)
    
    # Step 3: Demonstrate binary selection
    malware_id = select_binary_by_name(servers, "malware1")
    if malware_id:
        decompile_function(malware_id, "main", "malware1.exe")
    
    # Step 4: Comparative analysis
    compare_function_lists(servers)
    
    # Step 5: Security-focused analysis
    analyze_suspicious_functions(servers)
    
    print("\n" + "=" * 40)
    print("Analysis complete!")
    print("\nThis example demonstrates:")
    print("- Multi-binary server discovery")
    print("- Binary selection and routing")
    print("- Individual binary analysis")
    print("- Comparative analysis across binaries")
    print("- Security-focused function analysis")


if __name__ == "__main__":
    main()
