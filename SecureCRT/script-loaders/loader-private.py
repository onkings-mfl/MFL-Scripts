import urllib.request
from urllib.request import Request

url = "https://raw.githubusercontent.com/onkings-mfl/MFL-Scripts/refs/heads/main/SecureCRT/script-logins/login.py"
req = Request(url)
req.add_header("Authorization", "token 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")
with urllib.request.urlopen(req) as response:
    code = response.read().decode('utf-8')