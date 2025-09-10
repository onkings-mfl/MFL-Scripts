import urllib.request
from urllib.request import Request

url = "https://raw.githubusercontent.com/yourusername/yourrepo/main/yourscript.py"
req = Request(url)
req.add_header("Authorization", "token YOUR_PAT_HERE")
with urllib.request.urlopen(req) as response:
    code = response.read().decode('utf-8')