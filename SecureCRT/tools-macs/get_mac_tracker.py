# $language = "python"
# $interface = "1.0"
import re
import os
import csv
import urllib.request

def main():
    tab = crt.GetScriptTab()
    tab.Screen.Synchronous = True
    # Get clipboard content
    clip_mac = crt.Clipboard.Text.strip()
    # Prompt for MAC with clipboard default
    mac_input = crt.Dialog.Prompt("Enter MAC address:", "MAC", clip_mac)
    if not mac_input:
        return
    # Normalize MAC
    mac = normalize_mac(mac_input)
    if not mac:
        crt.Dialog.MessageBox("Invalid MAC address format.")
        return
    # No credentials selected yet
    creds_selected = False
    username = None
    password = None
    enable_pass = None
    # Start with local tab
    current_tab = tab
    is_core = False
    # Assume already in enable mode for current session
    current_tab.Screen.Send("\n")
    current_tab.Screen.WaitForString("#", 10)
    # Set terminal length 0
    current_tab.Screen.Send("terminal length 0\n")
    current_tab.Screen.WaitForString("#")
    # Start tracing
    path = []
    found = False
    while not found:
        current_device = get_device_name(current_tab)
        path.append(current_device)
        # Check MAC address table
        cmd = f"show mac address-table address {mac}"
        output = send_command(current_tab, cmd, timeout=30)
        entries = parse_mac_table(output, mac)
        if len(entries) == 0:
            # Check for explicit "no entries" message
            if "no entries present" in output.lower() or "total mac addresses for this criterion: 0" in output.lower():
                if is_core:
                    # Check ARP on core/L3
                    cmd_arp = f"show ip arp | include {mac}"
                    output_arp = send_command(current_tab, cmd_arp, timeout=30)
                    arp_entries = parse_arp(output_arp)
                    if arp_entries:
                        result_str = "MAC found in ARP but not in MAC table (may be inactive):\n"
                        for entry in arp_entries:
                            result_str += f"IP: {entry['ip']} Age: {entry['age']} Interface: {entry['interface']}\n"
                        full_path = f"On {current_device}:\n{result_str}"
                        crt.Dialog.MessageBox(full_path)
                        return
                    else:
                        crt.Dialog.MessageBox("MAC not found anywhere.")
                        return
                else:
                    # Prompt for core IP
                    core_ip = crt.Dialog.Prompt("MAC not found locally. Enter core switch IP (or cancel to exit):", "Core IP", "")
                    if not core_ip:
                        crt.Dialog.MessageBox("MAC not found.")
                        return
                    # Load and select credentials if not already
                    if not creds_selected:
                        if not load_credentials_code():
                            return
                        if not select_credentials():
                            return
                        creds_selected = True
                    # Hop to core via SSH from current device
                    success = False
                    while not success:
                        current_tab.Screen.Send(f"ssh -l {username} {core_ip}\n")
                        # Handle possible host key verification
                        if current_tab.Screen.WaitForString("continue connecting (yes/no", 10):
                            current_tab.Screen.Send("yes\n")
                        # Handle password prompt
                        if current_tab.Screen.WaitForString("Password:", 10):
                            current_tab.Screen.Send(password + "\n")
                        # Check if login succeeded
                        prompt_idx = current_tab.Screen.WaitForStrings(["#", ">", "% Access denied", "Access denied", "% Authentication failed", "Authentication failed",
                         "% Login invalid", "Login invalid", "% Bad passwords", "Bad passwords", "% Bad secrets", "Bad secrets",
                         "incorrect", "authentication failure"], 30)
                        if prompt_idx == 1 or prompt_idx == 2: # # or >
                            success = True
                            if prompt_idx == 2: # >
                                current_tab.Screen.Send("enable\n")
                                if current_tab.Screen.WaitForString("Password:", 5):
                                    current_tab.Screen.Send(enable_pass + "\n")
                                if not current_tab.Screen.WaitForString("#", 10):
                                    crt.Dialog.MessageBox("Enable failed.")
                                    return
                        else:
                            crt.Dialog.MessageBox("Login failed. Re-select credentials.")
                            if not load_credentials_code():
                                return
                            if not select_credentials():
                                return
                    # Set terminal length 0 after login
                    current_tab.Screen.Send("terminal length 0\n")
                    current_tab.Screen.WaitForString("#", 10)
                    is_core = True
                    continue # Retry MAC lookup on core
        elif len(entries) > 1:
            crt.Dialog.MessageBox("Multiple matches found for the MAC address. Cannot proceed.")
            return
        else:
            # Single entry found
            entry = entries[0]
            port = entry['port']
            path.append(f" -> {port}")
            # Handle port-channel
            neigh_port = port
            if port.lower().startswith('po') or port.lower().startswith('port-channel'):
                po_num = re.search(r'\d+', port).group(0)
                os_type = get_os_type(current_tab)
                if os_type == "unknown":
                    crt.Dialog.MessageBox("Unknown OS type. Assuming IOS XE for port-channel command.")
                    os_type = "iosxe"
                if os_type == "iosxe":
                    cmd_ec = f"show etherchannel {po_num} summary"
                elif os_type == "nxos":
                    cmd_ec = f"show port-channel summary interface port-channel {po_num}"
               
                output_ec = send_command(current_tab, cmd_ec, timeout=30)
                members = parse_etherchannel(output_ec)
                if not members:
                    crt.Dialog.MessageBox("No bundled members found for port-channel.")
                    return
                neigh_port = members[0]
            neigh_port = normalize_port(neigh_port)
            # Check for neighbor (uplink/trunk)
            cmd_cdp = f"show cdp neighbors {neigh_port} detail"
            output_cdp = send_command(current_tab, cmd_cdp, timeout=30)
            neighbor = parse_cdp(output_cdp)
            if not neighbor:
                # Try LLDP if CDP fails
                cmd_lldp = f"show lldp neighbors {neigh_port} detail"
                output_lldp = send_command(current_tab, cmd_lldp, timeout=30)
                neighbor = parse_lldp(output_lldp)
            if not neighbor:
                # No neighbor, assume access port
                path.append(" (access port)")
                found = True
            else:
                # Has neighbor, add to path and connect
                neigh_ip = neighbor['ip']
                neigh_host = neighbor['hostname']
                path.append(f" -> {neigh_host}")
                # Load and select credentials if not already
                if not creds_selected:
                    if not load_credentials_code():
                        return
                    if not select_credentials():
                        return
                    creds_selected = True
                # Hop to neighbor via SSH from current device
                success = False
                while not success:
                    current_tab.Screen.Send(f"ssh -l {username} {neigh_ip}\n")
                    # Handle possible host key verification
                    if current_tab.Screen.WaitForString("continue connecting (yes/no", 10):
                        current_tab.Screen.Send("yes\n")
                    # Handle password prompt
                    if current_tab.Screen.WaitForString("Password:", 10):
                        current_tab.Screen.Send(password + "\n")
                    # Check if login succeeded
                    prompt_idx = current_tab.Screen.WaitForStrings(["#", ">", "% Access denied", "Access denied", "% Authentication failed", "Authentication failed",
                         "% Login invalid", "Login invalid", "% Bad passwords", "Bad passwords", "% Bad secrets", "Bad secrets",
                         "incorrect", "authentication failure"], 30)
                    if prompt_idx == 1 or prompt_idx == 2: # # or >
                        success = True
                        if prompt_idx == 2: # >
                            current_tab.Screen.Send("enable\n")
                            if current_tab.Screen.WaitForString("Password:", 5):
                                current_tab.Screen.Send(enable_pass + "\n")
                            if not current_tab.Screen.WaitForString("#", 10):
                                crt.Dialog.MessageBox("Enable failed.")
                                return
                    else:
                        crt.Dialog.MessageBox("Login failed. Re-select credentials.")
                        if not load_credentials_code():
                            return
                        if not select_credentials():
                            return
                # Set terminal length 0 after login
                current_tab.Screen.Send("terminal length 0\n")
                current_tab.Screen.WaitForString("#", 10)
                is_core = False # Neighbors are likely not core
    # Output the path
    full_path = f"Path for MAC {mac}:\n" + "".join(path)
    crt.Dialog.MessageBox(full_path)

def load_credentials_code():
    try:
        github_url = "https://raw.githubusercontent.com/onkings-mfl/MFL-Scripts/main/SecureCRT/script-logins/login.py"
        with urllib.request.urlopen(github_url) as response:
            cred_code = response.read().decode('utf-8')
        exec(cred_code, globals())
    except Exception as e:
        crt.Dialog.MessageBox(f"Failed to download or execute credential script from GitHub: {str(e)}")
        return False
    return True

def normalize_mac(input_mac):
    mac = re.sub(r'[:.-]', '', input_mac.lower())
    if len(mac) != 12 or not all(c in '0123456789abcdef' for c in mac):
        return None
    return f"{mac[0:4]}.{mac[4:8]}.{mac[8:12]}"

def normalize_port(port):
    port = port.replace(' ', '')
    m = re.match(r'([A-Za-z]+)(.*)', port)
    if not m:
        return port
    prefix = m.group(1)
    rest = m.group(2)
    mappings = {
        'GigabitEthernet': 'Gi',
        'Gig': 'Gi',
        'Gi': 'Gi',
        'TenGigabitEthernet': 'Te',
        'Ten': 'Te',
        'Te': 'Te',
        'TwentyFiveGigabitEthernet': 'Twe',
        'TwentyFiveGigE': 'Twe',
        'Twe': 'Twe',
        'FortyGigabitEthernet': 'Fo',
        'Fo': 'Fo',
        'HundredGigabitEthernet': 'Hu',
        'Hu': 'Hu',
        'FastEthernet': 'Fa',
        'Fa': 'Fa',
        'Ethernet': 'Eth',
        'Eth': 'Eth',
        'FiveGigabitEthernet': 'Fi',
        'Fiv': 'Fi',
        'Fi': 'Fi',
        'TwoPointFiveGigabitEthernet': 'Tw',
        'Two': 'Tw',
        'Tw': 'Tw',
        'MultigigabitEthernet': 'Mg',
        'Mg': 'Mg',
        'Portchannel': 'Po',
        'Port-channel': 'Po',
        'Po': 'Po'
    }
    if prefix in mappings:
        return mappings[prefix] + rest
    return port

def get_device_name(tab):
    tab.Screen.Send("\n")
    tab.Screen.WaitForString("#")
    row = tab.Screen.CurrentRow
    col = tab.Screen.CurrentColumn
    prompt = tab.Screen.Get(row, 1, row, col - 1).strip()
    return prompt.rstrip('#> ')

def send_command(tab, cmd, timeout=30):
    tab.Screen.Send(cmd + "\n")
    output = tab.Screen.ReadString("#", timeout)
    return output.strip()

def parse_mac_table(output, mac):
    entries = []
    lines = output.splitlines()
    for line in lines:
        lower_line = line.lower()
        if mac in lower_line and "dynamic" in lower_line:
            parts = re.split(r'\s+', line.strip())
            if len(parts) >= 4:
                port = parts[-1] # Last field is port
                entries.append({
                    'vlan': parts[0],
                    'mac': parts[1],
                    'port': port
                })
    return entries

def parse_arp(output):
    entries = []
    lines = output.splitlines()
    for line in lines:
        parts = re.split(r'\s+', line)
        if len(parts) >= 6 and parts[4] == 'ARPA':
            entries.append({
                'ip': parts[1],
                'age': parts[2],
                'interface': parts[5]
            })
    return entries

def parse_cdp(output):
    match_host = re.search(r'Device ID:\s*(\S+)', output)
    match_ip = re.search(r'IP address:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
    if match_host and match_ip:
        return {'hostname': match_host.group(1), 'ip': match_ip.group(1)}
    return None

def parse_lldp(output):
    match_host = re.search(r'System Name:\s*(\S+)', output)
    match_ip = re.search(r'Management Address:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
    if match_host and match_ip:
        return {'hostname': match_host.group(1), 'ip': match_ip.group(1)}
    return None

def parse_etherchannel(output):
    # Find bundled ports like Twe1/5/0/6(P) or Eth1/1(P)
    matches = re.findall(r'([A-Za-z0-9/-]+)\(P\)', output)
    return matches

def get_os_type(tab):
    cmd = "show etherchannel summary"
    output = send_command(tab, cmd, timeout=10)
    if not output:
        crt.Dialog.MessageBox("Timeout on OS detection command, assuming IOS XE.")
        return "iosxe"
    if "Invalid input" in output or "% Invalid command" in output:
        return "nxos"
    else:
        return "iosxe"

main()