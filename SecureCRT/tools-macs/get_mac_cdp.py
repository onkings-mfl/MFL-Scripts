# SecureCRT Python Script to extract MAC address table and save to CSV
# Compatible with SecureCRT 9.6.3, Python 3.13.7 x64
# Works for Cisco ISR4431, ISR1001X, Catalyst 3850, 9300, 9410, 9606, 4510

import os
import csv
import re
import tempfile
from collections import defaultdict

# Get the script tab and screen
tab = crt.GetScriptTab()
scr = tab.Screen
scr.Synchronous = True

# Get the prompt
scr.Send("\r")
prompt = scr.ReadString("#").replace("\r\n", "").replace("\n", "").strip() + "#"
hostname = prompt[:-1].strip()

# Set terminal length to 0 to avoid paging
scr.Send("terminal length 0\r")
scr.WaitForString(prompt)

# Create temporary log files
temp_dir = tempfile.gettempdir()
mac_log = os.path.join(temp_dir, "mac_table.txt")
desc_log = os.path.join(temp_dir, "interfaces_desc.txt")
cdp_log = os.path.join(temp_dir, "cdp_neighbors.txt")
lldp_log = os.path.join(temp_dir, "lldp_neighbors.txt")

# Log MAC address table
tab.Session.LogFileName = mac_log
tab.Session.Log(True)
scr.Send("show mac address-table\r")
scr.WaitForString(prompt)
tab.Session.Log(False)

# Log interfaces descriptions
tab.Session.LogFileName = desc_log
tab.Session.Log(True)
scr.Send("show interfaces description\r")
scr.WaitForString(prompt)
tab.Session.Log(False)

# Log CDP neighbors
tab.Session.LogFileName = cdp_log
tab.Session.Log(True)
scr.Send("show cdp neighbors\r")
scr.WaitForString(prompt)
tab.Session.Log(False)

# Log LLDP neighbors
tab.Session.LogFileName = lldp_log
tab.Session.Log(True)
scr.Send("show lldp neighbors\r")
scr.WaitForString(prompt)
tab.Session.Log(False)

# Read MAC output
with open(mac_log, 'r') as f:
    mac_lines = f.readlines()

# Read descriptions output
with open(desc_log, 'r') as f:
    desc_lines = f.readlines()

# Read CDP output
with open(cdp_log, 'r') as f:
    cdp_lines = f.readlines()

# Read LLDP output
with open(lldp_log, 'r') as f:
    lldp_lines = f.readlines()

# Parse descriptions into dict (port -> desc)
port_desc = {}
desc_re = re.compile(r'^(\S+)\s+(.*?)\s+(up|down|notconnect|testing|dormant|unknown|notpresent)\s*(.*)$')
for line in desc_lines:
    line = line.strip()
    if not line or line.startswith('Interface') or line.startswith('---'):
        continue
    m = desc_re.match(line)
    if m:
        intf = m.group(1)
        desc = m.group(4).strip()
        port_desc[intf] = desc

# Function to parse neighbors (for both CDP and LLDP)
def parse_neighbors(lines):
    neighbor_dict = defaultdict(list)
    in_table = False
    current_entry = []
    for line in lines:
        original_line = line
        stripped = line.strip()
        if not stripped:
            continue
        if "Device ID" in stripped and ("Local Intrfce" in stripped or "Local Intf" in stripped):
            in_table = True
            continue
        if not in_table:
            continue
        is_continuation = original_line[0].isspace() if len(original_line) > 0 else False
        if not is_continuation:
            if current_entry:
                process_entry(current_entry, neighbor_dict)
            current_entry = [stripped]
        else:
            current_entry.append(stripped)
    if current_entry:
        process_entry(current_entry, neighbor_dict)
    return neighbor_dict

def process_entry(entry, neighbor_dict):
    full = ' '.join(entry)
    match = re.search(r'\s(\d+)\s', full)
    if match:
        pos = match.start()
        before = full[:pos].strip()
        d_m = re.match(r'(\S+)\s+(.*)', before)
        if d_m:
            device = d_m.group(1)
            local = d_m.group(2)
            if re.match(r'^(Gig|Ten|Twe|Fo|Hu|Fa|Eth|Fi|Tw|Mg|Po|Port-channel)\s', local, re.I):
                local = local.replace(' ', '')
                neighbor_dict[local].append(device)

# Parse CDP and LLDP
cdp_dict = parse_neighbors(cdp_lines)
lldp_dict = parse_neighbors(lldp_lines)

# Function to abbreviate port names
def abbreviate_port(port):
    mappings = {
        "GigabitEthernet": "Gi",
        "TenGigabitEthernet": "Te",
        "TwentyFiveGigE": "Twe",
        "TwentyFiveGigabitEthernet": "Twe",
        "FortyGigabitEthernet": "Fo",
        "HundredGigabitEthernet": "Hu",
        "FastEthernet": "Fa",
        "Ethernet": "Eth",
        "FiveGigabitEthernet": "Fi",
        "TwoPointFiveGigabitEthernet": "Tw",
        "MultigigabitEthernet": "Mg",
        "Port-channel": "Po"
    }
    for full, abbrev in mappings.items():
        if port.startswith(full):
            return abbrev + port[len(full):]
    return port

# Parse MAC table
entries = []
mac_pattern = re.compile(r'^[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}$')
for line in mac_lines:
    line = line.strip()
    if not line or line.startswith('Vlan') or line.startswith('----') or line.startswith('Unicast') or line.startswith('vlan'):
        continue
    parts = re.split(r'\s+', line)
    if len(parts) >= 4 and mac_pattern.match(parts[1]):
        vlan = parts[0]
        mac = parts[1]
        typ = parts[2]
        port_index = 3 if len(parts) == 4 else 4
        port = ' '.join(parts[port_index:]) if port_index + 1 < len(parts) else parts[port_index]
        if not vlan.isdigit():
            continue
        port_lower = port.lower()
        if any(keyword in port_lower for keyword in ["cpu", "switch", "vl", "vlan", "po", "port-channel"]):
            continue
        entries.append((vlan, mac, port))

# Prompt for CSV save location and name
default_filename = hostname + "_mac_table.csv"
save_path = crt.Dialog.FileOpenDialog("Save MAC Table CSV", "Save", default_filename, "CSV Files (*.csv)|*.csv||")
if not save_path:
    crt.Dialog.MessageBox("Save canceled.")
else:
    with open(save_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Switch Name", "MAC", "Port", "VLAN", "Port Description", "CDP Neighbor", "LLDP Neighbor"])
        for vlan, mac, port in entries:
            abbrev_port = abbreviate_port(port)
            desc = port_desc.get(abbrev_port, port_desc.get(port, ""))
            neighbor_cdp = ', '.join(cdp_dict.get(abbrev_port, cdp_dict.get(port, [])))
            neighbor_lldp = ', '.join(lldp_dict.get(abbrev_port, lldp_dict.get(port, [])))
            writer.writerow([hostname, mac, port, vlan, desc, neighbor_cdp, neighbor_lldp])

# Clean up temp files
os.remove(mac_log)
os.remove(desc_log)
os.remove(cdp_log)
os.remove(lldp_log)

# Reset synchronous
scr.Synchronous = False