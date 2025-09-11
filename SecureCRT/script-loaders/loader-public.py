# $language = "Python3"
# $interface = "1.0"

import urllib.request

# GitHub raw script URL
url = "https://raw.githubusercontent.com/onkings-mfl/MFL-Scripts/refs/heads/main/SecureCRT/script-logins/login.py"

try:
    with urllib.request.urlopen(url) as response:
        code = response.read().decode('utf-8')
    exec(code)
except Exception as e:
    crt.Dialog.MessageBox(f"Error fetching or executing script: {str(e)}")