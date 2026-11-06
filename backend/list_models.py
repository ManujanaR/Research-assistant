import os
from google import genai

key = os.environ.get("GEMINI_API_KEY")
if not key:
    for p in ("backend/.env", ".env"):
        if os.path.exists(p):
            for l in open(p):
                if l.startswith("GEMINI_API_KEY="): key = l.strip().split("=", 1)[1]
client = genai.Client(api_key=key)
for m in client.models.list():
    name = getattr(m, "name", "")
    if "flash" in name.lower() or "embed" in name.lower():
        print(name)
