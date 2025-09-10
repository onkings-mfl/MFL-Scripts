# SecureCRT Python Script to extract MAC address table and save to CSV
# Compatible with SecureCRT 9.6.3, Python 3.13.7 x64
# Works for Cisco ISR4431, ISR1001X, Catalyst 3850, 9300, 9410, 9606, 4510

import os
import csv
import re
import tempfile

# Get the script tab and screen
tab = crt.GetScriptTab()
scr = tab.Screen
scr.Synchronous = True

# Set terminal length to 0 to avoid paging
tab.Send("terminal length 0\n")
scr.WaitForString("terminal length 0\n")

# Get hostname
tab.Send("show running-config | include hostname\n")
scr.WaitForString("show running-config | include hostname\n")
# Read the line after 'hostname '
scr.WaitForString("hostname ")
hostname = scr.ReadString("\n").strip()

# Wait for prompt
scr.WaitForString(hostname + "#")

# Create temporary log files
temp_dir = tempfile.gettempdir()
mac_log = os.path.join(temp_dir, "mac_table.txt")
desc_log = os.path.join(temp_dir, "interfaces_desc.txt")

# Log MAC address table
crt.Session.LogFileName = mac_log
crt.Session.Log(True)
tab.Send("show mac address-table\n")
scr.WaitForString(hostname + "#")
crt.Session.Log(False)

# Log interfaces descriptions
crt.Session.LogFileName = desc_log
crt.Session.Log(True)
tab.Send("show interfaces description\n")
scr.WaitForString(hostname + "#")
crt.Session.Log(False)

# Read MAC output
with open(mac_log, 'r') as f:
    mac_lines = f.readlines()

# Read descriptions output
with open(desc_log, 'r') as f:
    desc_lines = f.readlines()

# Parse descriptions into dict (port -> desc)
port_desc = {}
desc_re = re.compile(r'^(\S+)\s+(\S+(?:\s+\S+)?)\s+(up|down)\s*(.*)$')
for line in desc_lines:
    line = line.strip()
    if not line:
        continue
    m = desc_re.match(line)
    if m:
        intf = m.group(1)
        desc = m.group(4).strip()
        port_desc[intf] = desc

# Function to abbreviate port names
def abbreviate_port(port):
    mappings = {
        "GigabitEthernet": "Gi",
        "TenGigabitEthernet": "Te",
        "TwentyFiveGigabitEthernet": "Twe",
        "FortyGigabitEthernet": "Fo",
        "HundredGigabitEthernet": "Hu",
        "FastEthernet": "Fa",
        "Ethernet": "Eth",
        "FiveGigabitEthernet": "Fi",  # Assuming for 5G
        "TwoPointFiveGigabitEthernet": "Tp"  # Assuming for 2.5G
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
    if not line:
        continue
    parts = line.split()
    if len(parts) in [4, 5] and len(parts) > 1 and mac_pattern.match(parts[1]):
        vlan = parts[0]
        mac = parts[1]
        typ = parts[2]
        if len(parts) == 5:
            port = parts[4]
        else:
            port = parts[3]
        # Skip if VLAN not numeric
        if not vlan.isdigit():
            continue
        # Ignore disallowed ports
        port_lower = port.lower()
        if any(keyword in port_lower for keyword in ["cpu", "switch", "vl", "po", "port-channel"]):
            continue
        # Add to entries
        entries.append((vlan, mac, port))

# Prompt for CSV save location and name
default_filename = hostname + "_mac_table.csv"
save_path = crt.Dialog.FileOpenDialog("Save MAC Table CSV", "Save", default_filename, "CSV Files (*.csv)|*.csv||")
if not save_path:
    crt.Dialog.MessageBox("Save canceled.")
else:
    with open(save_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Switch Name", "MAC", "Port", "VLAN", "Port Description"])
        for vlan, mac, port in entries:
            abbrev_port = abbreviate_port(port)
            desc = port_desc.get(abbrev_port, port_desc.get(port, ""))
            writer.writerow([hostname, mac, port, vlan, desc])

# Clean up temp files (optional)
os.remove(mac_log)
os.remove(desc_log)

# Reset synchronous
scr.Synchronous = False