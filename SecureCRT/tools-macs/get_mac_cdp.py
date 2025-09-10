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

# Log CDP neighbors detail
tab.Session.LogFileName = cdp_log
tab.Session.Log(True)
scr.Send("show cdp neighbors detail\r")
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

# Function to normalize port names
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
    abbrev = mappings.get(prefix, prefix)
    return abbrev + rest

# Parse descriptions into dict (port -> desc)
port_desc = {}
for line in desc_lines:
    line = line.strip()
    if not line or line.startswith('---') or 'Interface' in line and 'Status' in line:
        continue
    parts = re.split(r'\s{2,}', line, maxsplit=3)
    if len(parts) >= 4:
        intf = parts[0].strip()
        status = parts[1].strip()
        protocol = parts[2].strip()
        desc = parts[3].strip()
        if intf:
            norm_intf = normalize_port(intf)
            port_desc[norm_intf] = desc

# Function to parse CDP neighbors detail
def parse_cdp_detail(lines):
    neighbor_dict = defaultdict(list)
    current_block = []
    for line in lines:
        line = line.strip()
        if line == '-------------------------':
            if current_block:
                process_cdp_block(current_block, neighbor_dict)
            current_block = []
        else:
            if line:
                current_block.append(line)
    if current_block:
        process_cdp_block(current_block, neighbor_dict)
    return neighbor_dict

def process_cdp_block(block, neighbor_dict):
    device = ''
    platform = ''
    local = ''
    for line in block:
        if line.startswith('Device ID: '):
            device = line[len('Device ID: '):].strip()
        elif line.startswith('Platform: '):
            platform = line[len('Platform: '):].rstrip(',').strip()
            # Filter platform to show only the model
            platform = re.sub(r',\s*Capabilities:.*', '', platform).replace('Cisco ', '').replace('cisco ', '').strip()
        elif line.startswith('Interface: '):
            local = line[len('Interface: '):].split(',', 1)[0].strip()
    if local and device:
        norm_local = normalize_port(local)
        neighbor_dict[norm_local].append({'device': device, 'platform': platform})

# Parse CDP
cdp_dict = parse_cdp_detail(cdp_lines)

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

# Deduplicate entries by MAC and port
entries = list(set(entries))

# Add debug output
#debug_log = os.path.join(temp_dir, "debug.txt")
#with open(debug_log, 'w') as f:
#    f.write(f"Hostname: {hostname}\n")
#    f.write(f"Port Descriptions (dict): {port_desc}\n\n")
#    f.write(f"CDP Neighbors (dict): {cdp_dict}\n\n")
#    f.write(f"MAC Entries (list length): {len(entries)}\n")
#    f.write(f"Sample MAC Entry: {entries[0] if entries else 'None'}\n")

# Prompt for CSV save location and name
default_filename = hostname + "_mac_table.csv"
save_path = crt.Dialog.FileOpenDialog("Save MAC Table CSV", "Save", default_filename, "CSV Files (*.csv)|*.csv||")
if not save_path:
    crt.Dialog.MessageBox("Save canceled.")
else:
    with open(save_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Switch Name", "MAC", "Port", "VLAN", "Port Description", "Device ID", "Platform"])
        for vlan, mac, port in entries:
            norm_port = normalize_port(port)
            desc = port_desc.get(norm_port, "")
            cdp_neighbors = cdp_dict.get(norm_port, [])
            device_id = ', '.join(d['device'] for d in cdp_neighbors) if cdp_neighbors else ""
            platform = ', '.join(d['platform'] for d in cdp_neighbors if d['platform']) if cdp_neighbors else ""
            writer.writerow([hostname, mac, port, vlan, desc, device_id, platform])

# Log files are preserved for debugging - no os.remove() calls

# Reset synchronous
scr.Synchronous = False