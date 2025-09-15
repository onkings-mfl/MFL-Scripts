# $language = "python"
# $interface = "1.0"

import os
import csv
import re

crt.Screen.Synchronous = True

def Login(tab, username, password, enable_pwd, timeout_sec):
    try:
        # Retroactive check: Get the current prompt where the cursor is
        current_row = tab.Screen.CurrentRow
        current_col = tab.Screen.CurrentColumn
        # Get the text on the current row up to the cursor position (the prompt)
        prompt = tab.Screen.Get(current_row, 1, current_row, current_col - 1).strip()
        prompt_lower = prompt.lower()
        
        sent_username = False
        sent_password = False
        
        # Lowercase variations for robust matching
        username_variations = ["username:", "login:", "user:", "login as:", "user name:", "userid:", "name:", "logon:"]
        password_variations = ["password:", "passcode:", "passwd:", "secret:", "enable password:", "enable secret:", "pin:", "code:"]
        
        # Check if current prompt matches a password variation (endswith for precision)
        if any(prompt_lower.endswith(var) for var in password_variations):
            tab.Screen.Send(password + "\r")
            sent_password = True
        # Check for username variation
        elif any(prompt_lower.endswith(var) for var in username_variations):
            tab.Screen.Send(username + "\r")
            sent_username = True
        
        # If we sent username retroactively, wait for the follow-up password prompt
        if sent_username and not sent_password:
            password_prompts = ["Password:", "password:", "Passcode:", "passcode:", "Passwd:", "passwd:", "Secret:", "secret:", 
                                "Enable password:", "enable password:", "Enable secret:", "enable secret:", "PIN:", "pin:", "Code:", "code:"]
            if tab.Screen.WaitForStrings(password_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No password prompt after retroactive username send.")
                return False
            tab.Screen.Send(password + "\r")
            sent_password = True
        
        # If no retroactive action taken, proceed with waiting for initial prompts
        if not sent_username and not sent_password:
            username_prompts = ["Username:", "username:", "Login:", "login:", "User:", "user:", "Login as:", "login as:", 
                                "User name:", "user name:", "Userid:", "userid:", "Name:", "name:", "Logon:", "logon:"]
            password_prompts = ["Password:", "password:", "Passcode:", "passcode:", "Passwd:", "passwd:", "Secret:", "secret:", 
                                "Enable password:", "enable password:", "Enable secret:", "enable secret:", "PIN:", "pin:", "Code:", "code:"]
            initial_prompts = username_prompts + password_prompts
            
            result = tab.Screen.WaitForStrings(initial_prompts, timeout_sec)
            if result == 0:
                crt.Dialog.MessageBox("Timeout: No username or password prompt found.")
                return False
            
            num_username = len(username_prompts)
            if result <= num_username:  # Username-like prompt detected
                tab.Screen.Send(username + "\r")
                if tab.Screen.WaitForStrings(password_prompts, timeout_sec) == 0:
                    crt.Dialog.MessageBox("Timeout: No password prompt after username.")
                    return False
                tab.Screen.Send(password + "\r")
            else:  # Password prompt directly
                tab.Screen.Send(password + "\r")
        
        # After credentials, wait for shell prompt or error
        shell_prompts = ["#", ">", "% Access denied", "Access denied", "% Authentication failed", "Authentication failed", 
                         "% Login invalid", "Login invalid", "% Bad passwords", "Bad passwords", "% Bad secrets", "Bad secrets", 
                         "incorrect", "authentication failure"]
        result = tab.Screen.WaitForStrings(shell_prompts, timeout_sec)
        if result == 0:
            crt.Dialog.MessageBox("Timeout: No response after credentials.")
            return False
        elif result >= 3:  # Error strings detected (indices 3+)
            crt.Dialog.MessageBox("Login failed: Authentication error detected.")
            return False
        elif result == 1:  # Already at privileged mode (#)
            return True  # Success
        elif result == 2:  # User mode (>)
            tab.Screen.Send("en\r")  # Use "en" abbreviation for enable
            # Wait for enable password prompt
            enable_prompts = ["Password:", "password:", "Passcode:", "passcode:", "Passwd:", "passwd:", "Secret:", "secret:", 
                              "Enable password:", "enable password:", "Enable secret:", "enable secret:"]
            if tab.Screen.WaitForStrings(enable_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No enable password prompt.")
                return False
            tab.Screen.Send(enable_pwd + "\r")
            if not tab.Screen.WaitForString("#", timeout_sec):
                crt.Dialog.MessageBox("Timeout: Failed to reach privileged mode.")
                return False
        return True  # Success
    except Exception as e:
        crt.Dialog.MessageBox("Script error: " + str(e))
        return False

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
    csv_path = None

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
                        creds_selected = True

                    # Hop to core via SSH from current device
                    current_tab.Screen.Send(f"ssh -l {username} {core_ip}\n")
                    if not Login(current_tab, username, password, enable_pass, 10):
                        return

                    # Set terminal length 0 after login
                    current_tab.Screen.Send("terminal length 0\n")
                    current_tab.Screen.WaitForString("#", 10)

                    is_core = True
                    continue  # Retry MAC lookup on core
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

                # Select credentials if not already
                if not creds_selected:
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
                    creds_selected = True

                # Hop to neighbor via SSH from current device
                current_tab.Screen.Send(f"ssh -l {username} {neigh_ip}\n")
                if not Login(current_tab, username, password, enable_pass, 10):
                    return

                # Set terminal length 0 after login
                current_tab.Screen.Send("terminal length 0\n")
                current_tab.Screen.WaitForString("#", 10)

                is_core = False  # Neighbors are likely not core

    # Output the path
    full_path = f"Path for MAC {mac}:\n" + "".join(path)
    crt.Dialog.MessageBox(full_path)

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
                port = parts[-1]  # Last field is port
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