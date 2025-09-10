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

# Function to normalize port names using match/case
def normalize_port(port):
    port = port.replace(' ', '')
    match port.split('/', 1)[0]:
        case p if p.startswith(('Gi', 'Gig')):
            return 'Gi' + port[len(p):]
        case p if p.startswith(('Te', 'Ten')):
            return 'Te' + port[len(p):]
        case p if p.startswith(('Twe', 'TwentyFiveGigE', 'TwentyFiveGigabitEthernet')):
            return 'Twe' + port[len(p):]
        case p if p.startswith('Fo'):
            return 'Fo' + port[len(p):]
        case p if p.startswith('Hu'):
            return 'Hu' + port[len(p):]
        case p if p.startswith('Fa'):
            return 'Fa' + port[len(p):]
        case p if p.startswith('Eth'):
            return 'Eth' + port[len(p):]
        case p if p.startswith(('Fi', 'Fiv', 'FiveGigabitEthernet')):
            return 'Fi' + port[len(p):]
        case p if p.startswith(('Tw', 'Two', 'TwoPointFiveGigabitEthernet')):
            return 'Tw' + port[len(p):]
        case p if p.startswith(('Mg', 'MultigigabitEthernet')):
            return 'Mg' + port[len(p):]
        case p if p.startswith(('Po', 'Port-channel')):
            return 'Po' + port[len(p):]
        case p if p.startswith('GigabitEthernet'):
            return 'Gi' + port[len('GigabitEthernet'):]
        case p if p.startswith('TenGigabitEthernet'):
            return 'Te' + port[len('TenGigabitEthernet'):]
        case p if p.startswith('TwentyFiveGigabitEthernet'):
            return 'Twe' + port[len('TwentyFiveGigabitEthernet'):]
        case p if p.startswith('FortyGigabitEthernet'):
            return 'Fo' + port[len('FortyGigabitEthernet'):]
        case p if p.startswith('HundredGigabitEthernet'):
            return 'Hu' + port[len('HundredGigabitEthernet'):]
        case p if p.startswith('FastEthernet'):
            return 'Fa' + port[len('FastEthernet'):]
        case p if p.startswith('Ethernet'):
            return 'Eth' + port[len('Ethernet'):]
        case p if p.startswith('FiveGigabitEthernet'):
            return 'Fi' + port[len('FiveGigabitEthernet'):]
        case p if p.startswith('TwoPointFiveGigabitEthernet'):
            return 'Tw' + port[len('TwoPointFiveGigabitEthernet'):]
        case p if p.startswith('MultigigabitEthernet'):
            return 'Mg' + port[len('MultigigabitEthernet'):]
        case _:
            return port

# Parse descriptions using column positions (robust for different status formats)
port_desc = {}
header_line = None
for line in desc_lines:
    stripped = line.strip()
    if 'Interface' in stripped and 'Status' in stripped and 'Protocol' in stripped and 'Description' in stripped:
        header_line = line  # Use raw line for positions
        break

if header_line:
    pos_status = header_line.find('Status')
    pos_protocol = header_line.find('Protocol', pos_status)
    pos_desc = header_line.find('Description', pos_protocol)
    for line in desc_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('---') or line == header_line:
            continue
        intf = line[0:pos_status].strip() if pos_status > 0 else ''
        status = line[pos_status:pos_protocol].strip() if pos_protocol > pos_status else ''
        protocol = line[pos_protocol:pos_desc].strip() if pos_desc > pos_protocol else ''
        desc = line[pos_desc:].strip() if pos_desc > 0 else ''
        if intf:
            norm_intf = normalize_port(intf)
            port_desc[norm_intf] = desc
else:
    # Fallback to regex if no header (unlikely, but for completeness)
    desc_re = re.compile(r'^(\S+)\s+(.*?)\s+(up|down|notconnect|testing|dormant|unknown|notpresent|admin down)\s*(.*)$')
    for line in desc_lines:
        line = line.strip()
        if not line or line.startswith('Interface') or line.startswith('---'):
            continue
        m = desc_re.match(line)
        if m:
            intf = m.group(1)
            norm_intf = normalize_port(intf)
            desc = m.group(4).strip()
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
    # Parse after for capabilities, platform, port ID
    after_parts = re.split(r'\s+', after)
    k = 0
    known_caps = set(['R', 'T', 'B', 'S', 'H', 'I', 'r', 'P', 'D', 'C', 'M'])
    caps = []
    while k < len(after_parts) and (after_parts[k] in known_caps or after_parts[k].endswith(',')):
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
        writer.writerow(["Switch Name", "MAC", "Port", "VLAN", "Port Description", "CDP Neighbor", "LLDP Neighbor", "Platform"])
        for vlan, mac, port in entries:
            norm_port = normalize_port(port)
            desc = port_desc.get(norm_port, "")
            neighbor_cdp = ', '.join(d['device'] for d in cdp_dict.get(norm_port, []))
            neighbor_lldp = ', '.join(d['device'] for d in lldp_dict.get(norm_port, []))
            platforms = ', '.join(d['platform'] for d in cdp_dict.get(norm_port, []) if d['platform'])
            writer.writerow([hostname, mac, port, vlan, desc, neighbor_cdp, neighbor_lldp, platforms])

# Log files are preserved for debugging - no os.remove() calls

# Reset synchronous
scr.Synchronous = False