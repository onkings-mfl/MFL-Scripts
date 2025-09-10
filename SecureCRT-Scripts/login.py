# $language = "Python3"
# $interface = "1.0"

crt.Screen.Synchronous = True

def Login(tacacsuser, tacacspwd, enable_pwd, timeout_sec):
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
            crt.Screen.Send(tacacspwd + "\r")
            sent_password = True
        # Then check for username prompt
        elif any(var in recent_content for var in username_variations):
            crt.Screen.Send(tacacsuser + "\r")
            sent_username = True

        # If we sent username retroactively, wait for the follow-up password prompt with variations
        if sent_username and not sent_password:
            password_prompts = [var.split(':')[0][1:] + ":" for var in password_variations]  # Partials like "assword:", "asscode:"
            if crt.Screen.WaitForStrings(password_prompts, timeout_sec) == 0:
                crt.Dialog.MessageBox("Timeout: No password prompt after retroactive username send.")
                return
            crt.Screen.Send(tacacspwd + "\r")
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
                crt.Screen.Send(tacacsuser + "\r")
                if crt.Screen.WaitForStrings(initial_prompts[num_username_vars:], timeout_sec) == 0:  # Wait for password variations
                    crt.Dialog.MessageBox("Timeout: No password prompt after username.")
                    return
                crt.Screen.Send(tacacspwd + "\r")
            
            else:  # Password prompt directly
                crt.Screen.Send(tacacspwd + "\r")

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

    MenuChoice = crt.Dialog.Prompt ("[1] UBUNTU Login\n\n[2] CCF TACACS\n\n[3] CCF TACACS LOCAL\n\n[4] CCF LOCAL\n" , "LOGON MENU", "")
    match MenuChoice:
        case "1":
            # Placeholder for UBUNTU credentials - replace with actual
            tacacsuser = "ubuntu_username"  # e.g., "username_here"
            tacacspwd = "ubuntu_password"   # e.g., "password_here"
            enable_pwd = tacacspwd  # Assume same for enable, or replace if different
            Login(tacacsuser, tacacspwd, enable_pwd, timeout_sec)
            return
        case "2":
            # Placeholder for CCF TACACS credentials - replace with actual
            tacacsuser = "ccf_tacacs_username"
            tacacspwd = "ccf_tacacs_password"
            enable_pwd = "ccf_tacacs_enable_password"  # Different enable password as specified
            Login(tacacsuser, tacacspwd, enable_pwd, timeout_sec)
            return
        case "3":
            # Placeholder for CCF TACACS LOCAL credentials - replace with actual
            tacacsuser = "ccf_tacacs_local_username"
            tacacspwd = "ccf_tacacs_local_password"
            enable_pwd = tacacspwd  # Assume same for enable, or replace if different
            Login(tacacsuser, tacacspwd, enable_pwd, timeout_sec)
            return
        case "4":
            # Placeholder for CCF LOCAL credentials - replace with actual
            tacacsuser = "ccf_local_username"
            tacacspwd = "ccf_local_password"
            enable_pwd = tacacspwd  # Assume same for enable, or replace if different
            Login(tacacsuser, tacacspwd, enable_pwd, timeout_sec)
            return
        case _:
            crt.Dialog.MessageBox("Exiting..", "Menu options")
            return

Main()