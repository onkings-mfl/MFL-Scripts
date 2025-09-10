import urllib.request
from urllib.request import Request

url = "https://raw.githubusercontent.com/onkings-mfl/MFL-Scripts/refs/heads/main/SecureCRT/script-logins/login.py"
req = Request(url)
req.add_header("Authorization", "token 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")
with urllib.request.urlopen(req) as response:
    code = response.read().decode('utf-8')