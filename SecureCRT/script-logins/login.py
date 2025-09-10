# $language = "Python3"
# $interface = "1.0"
import os
import csv

crt.Screen.Synchronous = True

def Login(username, password, enable_pwd, timeout_sec):
    try:
        # Retroactive check: Get the current prompt where the cursor is
        current_row = crt.Screen.CurrentRow
        current_col = crt.Screen.CurrentColumn
        # Get the text on the current row up to the cursor position (the prompt)
        prompt = crt.Screen.Get(current_row, 1, current_row, current_col - 1).strip()
        prompt_lower = prompt.lower()
        
        sent_username = False
        sent_password = False
        
        # Lowercase variations for robust matching
        username_variations = ["username:", "login:", "user:", "login as:", "user name:", "userid:", "name:", "logon:"]
        password_variations = ["password:", "passcode:", "passwd:", "secret:", "enable password:", "enable secret:", "pin:", "code:"]
        
        # Check if current prompt matches a password variation (endswith for precision)
        if any(prompt_lower.endswith(var) for var in password_variations):
            crt.Screen.Send(password + "\r")
            sent_password = True
        # Check for username variation
        elif any(prompt_lower.endswith(var) for var in username_variations):
            crt.Screen.Send(username + "\r")
            sent_username = True
        
        # If we sent username retroactively, wait for the follow-up password prompt
        if sent_username and not sent_password:
            password_prompts = ["Password:", "password:", "Passcode:", "passcode:", "Passwd:", "passwd:", "Secret:", "secret:", 
                                "Enable password:", "enable password:", "Enable secret:", "enable secret:", "PIN:", "pin:", "Code:", "code:"]
            if crt.Screen.WaitForStrings(password_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No password prompt after retroactive username send.")
                return
            crt.Screen.Send(password + "\r")
            sent_password = True
        
        # If no retroactive action taken, proceed with waiting for initial prompts
        if not sent_username and not sent_password:
            username_prompts = ["Username:", "username:", "Login:", "login:", "User:", "user:", "Login as:", "login as:", 
                                "User name:", "user name:", "Userid:", "userid:", "Name:", "name:", "Logon:", "logon:"]
            password_prompts = ["Password:", "password:", "Passcode:", "passcode:", "Passwd:", "passwd:", "Secret:", "secret:", 
                                "Enable password:", "enable password:", "Enable secret:", "enable secret:", "PIN:", "pin:", "Code:", "code:"]
            initial_prompts = username_prompts + password_prompts
            
            result = crt.Screen.WaitForStrings(initial_prompts, timeout_sec)
            if result == 0:
                crt.Dialog.MessageBox("Timeout: No username or password prompt found.")
                return
            
            num_username = len(username_prompts)
            if result <= num_username:  # Username-like prompt detected
                crt.Screen.Send(username + "\r")
                if crt.Screen.WaitForStrings(password_prompts, timeout_sec) == 0:
                    crt.Dialog.MessageBox("Timeout: No password prompt after username.")
                    return
                crt.Screen.Send(password + "\r")
            else:  # Password prompt directly
                crt.Screen.Send(password + "\r")
        
        # After credentials, wait for shell prompt or error
        shell_prompts = ["#", ">", "% Access denied", "Access denied", "% Authentication failed", "Authentication failed", 
                         "% Login invalid", "Login invalid", "% Bad passwords", "Bad passwords", "% Bad secrets", "Bad secrets", 
                         "incorrect", "authentication failure"]
        result = crt.Screen.WaitForStrings(shell_prompts, timeout_sec)
        if result == 0:
            crt.Dialog.MessageBox("Timeout: No response after credentials.")
            return
        elif result >= 3:  # Error strings detected (indices 3+)
            crt.Dialog.MessageBox("Login failed: Authentication error detected.")
            return
        elif result == 1:  # Already at privileged mode (#)
            return  # Exit script, session remains
        elif result == 2:  # User mode (>)
            crt.Screen.Send("en\r")  # Use "en" abbreviation for enable
            # Wait for enable password prompt
            enable_prompts = ["Password:", "password:", "Passcode:", "passcode:", "Passwd:", "passwd:", "Secret:", "secret:", 
                              "Enable password:", "enable password:", "Enable secret:", "enable secret:"]
            if crt.Screen.WaitForStrings(enable_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No enable password prompt.")
                return
            crt.Screen.Send(enable_pwd + "\r")
            if not crt.Screen.WaitForString("#", timeout_sec):
                crt.Dialog.MessageBox("Timeout: Failed to reach privileged mode.")
                return
        return  # Exit script, session remains
    except Exception as e:
        crt.Dialog.MessageBox("Script error: " + str(e))

def Main():
    timeout_sec = 10  # General timeout for waits
    
    # Locate the CSV file (fixed path initially)
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
    enable_pwd = creds[key]['enable_password']
    
    Login(username, password, enable_pwd, timeout_sec)

Main()