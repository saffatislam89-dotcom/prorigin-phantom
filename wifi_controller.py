"""
WiFi Controller Module for Windows 10/11
Controls WiFi adapter state using netsh commands via subprocess module.
Provides enable, disable, and status checking functionality with auto-detection
of WiFi interface names.
"""

import subprocess
import ctypes
import sys
from typing import Optional


# Global variable to cache detected WiFi interface name
_WIFI_INTERFACE_NAME = None


def _is_admin() -> bool:
    """
    Check if the script is running with administrator privileges.
    
    Returns:
        bool: True if running as admin, False otherwise
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _run_netsh_command(command: str) -> tuple:
    """
    Execute a netsh command and return the result.
    
    Args:
        command (str): The netsh command to execute
        
    Returns:
        tuple: (success, output) where success is True if command executed
               without error, output contains command result/error message
    """
    if not _is_admin():
        return False, "Administrator privileges required"
    
    try:
        # Run command with elevated privileges (requires admin)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        return False, "Command execution timed out"
    except Exception as e:
        return False, f"Error executing command: {str(e)}"


def _detect_wifi_interface() -> Optional[str]:
    """
    Auto-detect the WiFi interface name by parsing netsh output.
    
    Searches for 'Wi-Fi' or 'Wireless' in the interface list.
    
    Returns:
        Optional[str]: The name of the WiFi interface, or None if not found
    """
    global _WIFI_INTERFACE_NAME
    
    # Return cached interface name if already detected
    if _WIFI_INTERFACE_NAME:
        return _WIFI_INTERFACE_NAME
    
    try:
        result = subprocess.run(
            "netsh interface show interface",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return None
        
        output = result.stdout
        lines = output.split('\n')
        
        # Parse interface list
        for line in lines:
            line_lower = line.lower()
            # Look for Wi-Fi or Wireless interface
            if 'wi-fi' in line_lower or 'wireless' in line_lower:
                # Extract interface name from the line
                # Format is typically: "Enabled/Disabled  Connected/Disconnected  InterfaceName  Type"
                parts = line.split()
                if len(parts) >= 3:
                    # Get the interface name (usually the 3rd or 4th column)
                    for part in parts:
                        if 'Wi-Fi' in part or 'Wireless' in part or 'wifi' in part.lower():
                            _WIFI_INTERFACE_NAME = part.strip()
                            return _WIFI_INTERFACE_NAME
                    
                    # If not found by keyword, try to get name from line
                    # The interface name is typically before "Wireless" or "Wi-Fi"
                    for i, part in enumerate(parts):
                        if 'wireless' in part.lower() or 'wi-fi' in part.lower():
                            if i > 0:
                                _WIFI_INTERFACE_NAME = parts[i-1].strip()
                                return _WIFI_INTERFACE_NAME
        
        return None
        
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        return None


def _get_last_known_ssid() -> Optional[str]:
    """
    Retrieve the last known WiFi network SSID that this computer has connected to.
    
    Returns:
        Optional[str]: The SSID of the last known network, or None if not found
    """
    try:
        # Get list of known networks
        result = subprocess.run(
            "netsh wlan show profiles",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return None
        
        output = result.stdout
        lines = output.split('\n')
        
        # Extract SSID names from the profiles list
        ssids = []
        for line in lines:
            if 'All User Profile' in line:
                # Extract SSID from line like: "    All User Profile     : NetworkName"
                parts = line.split(':')
                if len(parts) >= 2:
                    ssid = parts[1].strip()
                    if ssid:
                        ssids.append(ssid)
        
        # Return the last SSID (most recent)
        if ssids:
            return ssids[-1]
        
        return None
        
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"Error getting last known SSID: {str(e)}")
        return None


def enable_wifi() -> bool:
    """
    Enable WiFi by reconnecting to the last known network (Soft Toggle).
    
    Uses netsh wlan connect to reconnect to the last known SSID.
    The physical WiFi adapter remains active.
    
    Returns:
        bool: True if WiFi reconnected successfully, False otherwise
    
    Note:
        Requires administrator privileges to execute successfully.
    """
    if not _is_admin():
        print("Error: Administrator privileges required to enable WiFi")
        return False
    
    # Get the last known SSID
    ssid = _get_last_known_ssid()
    
    if not ssid:
        print("Error: Could not find a known WiFi network to reconnect to")
        return False
    
    # Connect to the last known network
    command = f'netsh wlan connect name="{ssid}"'
    
    success, output = _run_netsh_command(command)
    
    if success:
        print(f"WiFi reconnected to '{ssid}' successfully")
        return True
    else:
        print(f"Failed to reconnect WiFi: {output}")
        return False


def disable_wifi() -> bool:
    """
    Disable WiFi by disconnecting from the network (Soft Toggle).
    
    Uses netsh wlan disconnect to disconnect from the current network.
    The physical WiFi adapter remains active.
    
    Returns:
        bool: True if WiFi disconnected successfully, False otherwise
    
    Note:
        Requires administrator privileges to execute successfully.
    """
    if not _is_admin():
        print("Error: Administrator privileges required to disable WiFi")
        return False
    
    # Disconnect from the current network
    command = 'netsh wlan disconnect'
    
    success, output = _run_netsh_command(command)
    
    if success:
        print("WiFi disconnected successfully")
        return True
    else:
        print(f"Failed to disconnect WiFi: {output}")
        return False


def get_wifi_status() -> Optional[str]:
    """
    Get current WiFi adapter status on Windows 10/11.
    
    Returns:
        Optional[str]: Status string - "connected", "enabled", "disabled", or None if unable to determine
    """
    try:
        # Detect WiFi interface name
        interface_name = _detect_wifi_interface()
        
        if not interface_name:
            print("Error: Could not detect WiFi interface")
            return None
        
        # Check WiFi adapter status using WLAN commands
        result = subprocess.run(
            "netsh wlan show interfaces",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            output = result.stdout.lower()
            
            # Check connection status
            if "connected" in output and "ssid" in output:
                return "connected"
            elif "disconnected" in output:
                return "enabled"
            else:
                return "disabled"
        else:
            # Fallback to interface status
            result = subprocess.run(
                "netsh interface show interface",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout.lower()
            
            if "enabled" in output and interface_name.lower() in output:
                return "enabled"
            elif "disabled" in output and interface_name.lower() in output:
                return "disabled"
            else:
                return None
            
    except subprocess.TimeoutExpired:
        print("Error: Command execution timed out")
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None


def main():
    """
    Main function demonstrating usage of WiFi controller functions.
    """
    # Check admin privileges
    if not _is_admin():
        print("=" * 60)
        print("ERROR: This script requires Administrator privileges!")
        print("=" * 60)
        print("\nPlease run this script as Administrator:")
        print("1. Right-click on Command Prompt or PowerShell")
        print("2. Select 'Run as administrator'")
        print("3. Navigate to the script directory")
        print("4. Run: python wifi_controller.py")
        sys.exit(1)
    
    print("=" * 60)
    print("WiFi Controller - Windows 10/11")
    print("=" * 60)
    
    # Check current status
    print("\n[1] Checking WiFi status...")
    status = get_wifi_status()
    if status:
        print(f"    Current Status: {status.upper()}")
    else:
        print("    Failed to retrieve WiFi status")
    
    # Enable WiFi
    print("\n[2] Attempting to enable WiFi...")
    if enable_wifi():
        print("    SUCCESS")
    else:
        print("    FAILED")
    
    # Check status after enable
    print("\n[3] Checking WiFi status after enable...")
    status = get_wifi_status()
    if status:
        print(f"    Current Status: {status.upper()}")
    else:
        print("    Failed to retrieve WiFi status")
    
    # Disable WiFi
    print("\n[4] Attempting to disable WiFi...")
    if disable_wifi():
        print("    SUCCESS")
    else:
        print("    FAILED")
    
    # Check status after disable
    print("\n[5] Checking WiFi status after disable...")
    status = get_wifi_status()
    if status:
        print(f"    Current Status: {status.upper()}")
    else:
        print("    Failed to retrieve WiFi status")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
