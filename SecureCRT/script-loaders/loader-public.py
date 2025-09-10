# $language = "Python3"
# $interface = "1.0"

import urllib.request

# Replace with your GitHub raw script URL
url = "https://raw.githubusercontent.com/onkings-mfl/MFL-Scripts/34611dc505dfddc85523bcd4aa2ac1dff8e9fd35/SecureCRT/script-logins/login.py"

try:
    with urllib.request.urlopen(url) as response:
        code = response.read().decode('utf-8')
    exec(code)
except Exception as e:
    crt.Dialog.MessageBox(f"Error fetching or executing script: {str(e)}")