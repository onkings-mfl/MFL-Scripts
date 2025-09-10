# $language = "Python3"
# $interface = "1.0"

import os
import csv

crt.Screen.Synchronous = True

def Login(username, password, enable_pwd, timeout_sec):
    try:
        # First, read the existing screen buffer to check for prompts retroactively
        rows = crt.Screen.Rows
        cols = crt.Screen.Columns
        screen_content = crt.Screen.Get2(1, 1, rows, cols).lower()  # Get entire screen, case-insensitive for matching
        
        # To make it more robust, extract the last few lines where the prompt is likely to be
        screen_lines = screen_content.splitlines()
        recent_content = "\n".join(screen_lines[-5:])  # Check last 5 lines to avoid banner matches
        
        sent_username = False
        sent_password = False

        # Expanded prompt variations for retroactive check
        password_variations = ["password:", "passcode:", "passwd:", "secret:", "enable password:"]
        username_variations = ["username:", "login:", "user:", "login as:", "user name:"]

        # Check for password prompt first (if already past username)
        if any(var in recent_content for var in password_variations):
            crt.Screen.Send(password + "\r")
            sent_password = True
        # Then check for username prompt
        elif any(var in recent_content for var in username_variations):
            crt.Screen.Send(username + "\r")
            sent_username = True

        # If we sent username retroactively, wait for the follow-up password prompt with variations
        if sent_username and not sent_password:
            password_prompts = [var.split(':')[0][1:] + ":" for var in password_variations]  # Partials like "assword:", "asscode:"
            if crt.Screen.WaitForStrings(password_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No password prompt after retroactive username send.")
                return
            crt.Screen.Send(password + "\r")
            sent_password = True

        # If no retroactive action taken, proceed with waiting for initial prompts with expanded variations
        if not sent_username and not sent_password:
            # Partials for more flexibility: e.g., "sername:", "ogin:", "assword:", etc.
            initial_prompts = ["sername:", "ogin:", "ser:", "ser name:", "assword:", "asscode:", "asswd:", "ecret:", "nable password:"]
            result = crt.Screen.WaitForStrings(initial_prompts, timeout_sec)
            
            if result == 0:
                crt.Dialog.MessageBox("Timeout: No username or password prompt found.")
                return
            
            # Group results: first half for username variations, second for password
            num_username_vars = len(initial_prompts) // 2 + 1  # Adjust based on list
            if result <= num_username_vars:  # Username-like prompt detected
                crt.Screen.Send(username + "\r")
                if crt.Screen.WaitForStrings(initial_prompts[num_username_vars:], timeout_sec) == 0:  # Wait for password variations
                    crt.Dialog.MessageBox("Timeout: No password prompt after username.")
                    return
                crt.Screen.Send(password + "\r")
            
            else:  # Password prompt directly
                crt.Screen.Send(password + "\r")

        # After credentials, wait for shell prompt or error (expanded errors for robustness)
        shell_prompts = ["#", ">", "denied", "failed", "invalid", "bad", "incorrect", "authentication failure"]
        result = crt.Screen.WaitForStrings(shell_prompts, timeout_sec)
        
        if result == 0:
            crt.Dialog.MessageBox("Timeout: No response after credentials.")
            return
        
        elif result >= 3:  # Error strings detected (indices 3+)
            crt.Dialog.MessageBox("Login failed: Authentication error detected.")
            return
        
        elif result == 1:  # Already at privileged mode (#)
            return  # Script exits here, session remains connected
        
        elif result == 2:  # User mode (>)
            crt.Screen.Send("en\r")  # Or "enable" if configured differently, but "en" is common abbreviation
            # Wait for enable password prompt with variations
            enable_prompts = [var.split(':')[0][1:] + ":" for var in password_variations]
            if crt.Screen.WaitForStrings(enable_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No enable password prompt.")
                return
            crt.Screen.Send(enable_pwd + "\r")
            if not crt.Screen.WaitForString("#", timeout_sec):
                crt.Dialog.MessageBox("Timeout: Failed to reach privileged mode.")
                return
            return  # Script exits here, session remains connected

    except Exception as e:
        crt.Dialog.MessageBox("Script error: " + str(e))

def Main():
    timeout_sec = 10  # General timeout for waits
    
    # Locate the CSV file
    csv_path = "credentials.csv"
    if not os.path.exists(csv_path):
        csv_path = crt.Dialog.Prompt("Enter the path to credentials.csv:", "File Not Found", "")
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

    MenuChoice = crt.Dialog.Prompt ("[1] ad_account\n\n[2] tac_NetEng\n\n[3] tac_DNAC01\n\n[4] local_NetEng\n" , "LOGON MENU", "")
    match MenuChoice:
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
    enable_pwd = creds[key]['enable_password']
    Login(username, password, enable_pwd, timeout_sec)

Main()