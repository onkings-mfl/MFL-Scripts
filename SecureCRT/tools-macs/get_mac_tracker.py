# $language = "python"
# $interface = "1.0"

import re
import os
import csv

def main():
    tab = crt.GetScriptTab()
    tab.Screen.Synchronous = True
    
    # Credential selection
    csv_path = r"C:\Users\dan\OneDrive - Cleveland Clinic\Documents\Network\SecureCRT\credentials.csv"
    if not os.path.exists(csv_path):
        csv_path = crt.Dialog.Prompt("Enter the path to the credentials CSV file:", "File Not Found", "")
        if not csv_path or not os.path.exists(csv_path):
            crt.Dialog.MessageBox("CSV file not found. Exiting.")
            return

    # Read the CSV into a dictionary
    creds = {}
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row['credentials'].strip()
                creds[key] = {
                    'username': row['username'].strip(),
                    'password': row['password'].strip()
                }
                # Use enable_password if present and not empty, else default to password
                enable_pwd = row.get('enable_password', '').strip()
                creds[key]['enable_password'] = enable_pwd if enable_pwd else row['password'].strip()
    except Exception as e:
        crt.Dialog.MessageBox("Error reading CSV: " + str(e))
        return

    # Prompt for credential selection
    menu_choice = crt.Dialog.Prompt("[1] AD Account\n\n[2] TAC NetEng\n\n[3] TAC DNAC\n\n[4] Local NetEng\n" , "LOGON MENU", "")
    match menu_choice:
        case "1":
            key = "ad_account"
        case "2":
            key = "tac_NetEng"
        case "3":
            key = "tac_DNAC01"
        case "4":
            key = "local_NetEng"
        case _:
            crt.Dialog.MessageBox("Exiting..", "Menu options")
            return

    if key not in creds:
        crt.Dialog.MessageBox("Credentials not found for " + key)
        return

    username = creds[key]['username']
    password = creds[key]['password']
    enable_pass = creds[key]['enable_password']

    # Prompt for core IP and MAC
    core_ip = crt.Dialog.Prompt("Enter core switch IP (optional, press enter to skip):", "Core IP", "")
    mac_input = crt.Dialog.Prompt("Enter MAC address:", "MAC", "")
    if not mac_input:
        return

    # Normalize MAC
    mac = normalize_mac(mac_input)
    if not mac:
        crt.Dialog.MessageBox("Invalid MAC address format.")
        return

    # Determine starting tab
    start_tab = tab
    is_core = False
    if core_ip:
        connect_str = f"/SSH2 /L {username} /PASSWORD {password} /ACCEPTHOSTKEYS {core_ip}"
        try:
            start_tab = crt.Session.ConnectInTab(connect_str)
            start_tab.Screen.Synchronous = True
            start_tab.Caption = f"Core {core_ip}"
            start_tab.Activate()
            is_core = True
        except Exception as e:
            crt.Dialog.MessageBox(f"Failed to connect to core: {str(e)}")
            return

    # Post-connection setup for new tab (if connected to core)
    current_tab = start_tab
    if core_ip:
        # Wait for prompt after connection
        current_tab.Screen.Send("\n")
        prompt_idx = current_tab.Screen.WaitForStrings([">", "#"], 10)
        if prompt_idx == 0:
            crt.Dialog.MessageBox("Connection timeout.")
            return
        elif prompt_idx == 1:  # user mode >
            current_tab.Screen.Send("enable\n")
            if enable_pass:
                if current_tab.Screen.WaitForString("Password:", 5):
                    current_tab.Screen.Send(enable_pass + "\n")
            current_tab.Screen.WaitForString("#", 10)
    else:
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
        current_hostname = get_hostname(current_tab)
        path.append(current_hostname)

        # Check MAC address table
        cmd = f"show mac address-table address {mac}"
        output = send_command(current_tab, cmd)
        entries = parse_mac_table(output, mac)

        if len(entries) == 0:
            # MAC not found in MAC table
            if is_core:
                # Check ARP on core/L3
                cmd_arp = f"show ip arp | include {mac}"
                output_arp = send_command(current_tab, cmd_arp)
                arp_entries = parse_arp(output_arp)
                if arp_entries:
                    result_str = "MAC found in ARP but not in MAC table (may be inactive):\n"
                    for entry in arp_entries:
                        result_str += f"IP: {entry['ip']} Age: {entry['age']} Interface: {entry['interface']}\n"
                    full_path = f"On {current_hostname}:\n{result_str}"
                    crt.Dialog.MessageBox(full_path)
                    return
                else:
                    crt.Dialog.MessageBox("MAC not found anywhere.")
                    return
            else:
                crt.Dialog.MessageBox("MAC not found on this switch. Provide core IP to check upstream L3.")
                return
        elif len(entries) > 1:
            crt.Dialog.MessageBox("Multiple matches found for the MAC address. Cannot proceed.")
            return
        else:
            # Single entry found
            entry = entries[0]
            port = entry['port']
            path.append(f" -> {port}")

            # Check for neighbor (uplink/trunk)
            cmd_cdp = f"show cdp neighbors {port} detail"
            output_cdp = send_command(current_tab, cmd_cdp)
            neighbor = parse_cdp(output_cdp)

            if not neighbor:
                # Try LLDP if CDP fails
                cmd_lldp = f"show lldp neighbors {port} detail"
                output_lldp = send_command(current_tab, cmd_lldp)
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

                # Connect to neighbor
                connect_str = f"/SSH2 /L {username} /PASSWORD {password} /ACCEPTHOSTKEYS {neigh_ip}"
                try:
                    new_tab = crt.Session.ConnectInTab(connect_str)
                    new_tab.Screen.Synchronous = True
                    new_tab.Caption = neigh_host
                    new_tab.Activate()
                except Exception as e:
                    crt.Dialog.MessageBox(f"Failed to connect to {neigh_host}: {str(e)}")
                    return

                # Post-connection setup for new tab
                new_tab.Screen.Send("\n")
                prompt_idx = new_tab.Screen.WaitForStrings([">", "#"], 10)
                if prompt_idx == 0:
                    crt.Dialog.MessageBox("Connection timeout to neighbor.")
                    return
                elif prompt_idx == 1:  # user mode
                    new_tab.Screen.Send("enable\n")
                    if enable_pass:
                        if new_tab.Screen.WaitForString("Password:", 5):
                            new_tab.Screen.Send(enable_pass + "\n")
                    new_tab.Screen.WaitForString("#", 10)

                # Set terminal length 0
                new_tab.Screen.Send("terminal length 0\n")
                new_tab.Screen.WaitForString("#")

                # Update current tab
                current_tab = new_tab
                is_core = False  # Neighbors are likely not core

    # Output the path
    full_path = f"Path for MAC {mac}:\n" + "".join(path)
    crt.Dialog.MessageBox(full_path)

def normalize_mac(input_mac):
    mac = re.sub(r'[:.]', '', input_mac.lower())
    if len(mac) != 12 or not all(c in '0123456789abcdef' for c in mac):
        return None
    return f"{mac[0:4]}.{mac[4:8]}.{mac[8:12]}"

def get_hostname(tab):
    output = send_command(tab, "show hostname")
    return output.strip()

def send_command(tab, cmd):
    tab.Screen.Send(cmd + "\n")
    output = tab.Screen.ReadString("#")
    return output.strip()

def parse_mac_table(output, mac):
    entries = []
    lines = output.splitlines()
    for line in lines:
        lower_line = line.lower()
        if mac in lower_line and "dynamic" in lower_line:  # Focus on dynamic entries
            parts = re.split(r'\s+', line)
            if len(parts) >= 4:
                entries.append({
                    'vlan': parts[0],
                    'mac': parts[1],
                    'type': parts[2],
                    'port': parts[3]
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

main()