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

# Function to parse neighbors (for both CDP and LLDP)
def parse_neighbors(lines, is_cdp=False):
    neighbor_dict = defaultdict(list)
    in_table = False
    current_entry = []
    for line in lines:
        original_line = line
        line = line.strip()
        if not line:
            continue
        if "Device ID" in line and ("Local Intrfce" in line or "Local Intf" in line):
            in_table = True
            continue
        if not in_table:
            continue
        is_continuation = original_line[0].isspace() if len(original_line) > 0 else False
        if not is_continuation:
            if current_entry:
                process_entry(current_entry, neighbor_dict, is_cdp)
            current_entry = [line]
        else:
            current_entry.append(line)
    if current_entry:
        process_entry(current_entry, neighbor_dict, is_cdp)
    return neighbor_dict

def process_entry(entry, neighbor_dict, is_cdp=False):
    full = ' '.join(entry)
    match = re.search(r'\s(\d+)\s', full)
    if not match:
        return
    hold = match.group(1)
    pos = match.start()
    before = full[:pos].strip()
    after = full[pos + len(match.group()):].strip()
    # Split before into device and local
    # Handle no-space LLDP (e.g., "FL-WNN-02-AP013.cc.aGi4/26")
    port_re = re.compile(r'(Gi|Gig|Te|Ten|Twe|Fo|Hu|Fa|Eth|Fi|Fiv|Tw|Two|Mg|Po)[0-9]')
    m = port_re.search(before)
    if m:
        pos_port = m.start()
        device = before[:pos_port].strip()
        local = before[pos_port:].strip()
    else:
        # CDP style with space
        d_m = re.match(r'(\S+)\s+(.*)', before)
        if d_m:
            device = d_m.group(1)
            local = d_m.group(2)
        else:
            return
    # Clean up LLDP device IDs by removing trailing domain-like suffixes (e.g., .cc.a)
    if not is_cdp:
        device = re.sub(r'\.cc\..*$', '', device)
    # Parse after for capabilities, platform, port ID
    after_parts = re.split(r'\s+', after)
    k = 0
    known_caps = set(['R', 'T', 'B', 'S', 'H', 'I', 'r', 'P', 'D', 'C', 'M'])
    caps = []
    while k < len(after_parts) and (after_parts[k] in known_caps or after_parts[k].endswith(',') or ',' in after_parts[k]):
        caps.append(after_parts[k])
        k += 1
    platform = ''
    if is_cdp and len(after_parts) > k:
        # Platform is next, up to before last two (usually port ID)
        platform_end = len(after_parts) - 2 if len(after_parts) - k > 2 else len(after_parts)
        platform = ' '.join(after_parts[k:platform_end]).strip()
    norm_local = normalize_port(local)
    neighbor_dict[norm_local].append({
        'device': device,
        'platform': platform
    })

# Parse CDP and LLDP
cdp_dict = parse_neighbors(cdp_lines, is_cdp=True)
lldp_dict = parse_neighbors(lldp_lines, is_cdp=False)

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
debug_log = os.path.join(temp_dir, "debug.txt")
with open(debug_log, 'w') as f:
    f.write(f"Hostname: {hostname}\n")
    f.write(f"Port Descriptions (dict): {port_desc}\n\n")
    f.write(f"CDP Neighbors (dict): {cdp_dict}\n\n")
    f.write(f"LLDP Neighbors (dict): {lldp_dict}\n\n")
    f.write(f"MAC Entries (list length): {len(entries)}\n")
    f.write(f"Sample MAC Entry: {entries[0] if entries else 'None'}\n")

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