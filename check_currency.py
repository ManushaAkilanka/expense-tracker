import httpx
import re

c = httpx.Client(base_url="http://127.0.0.1:8000", follow_redirects=True)
r1 = c.get("/sign-in")
csrf = re.search(r'name="_csrf_token" value="([^"]+)"', r1.text).group(1)
r2 = c.post("/sign-in", data={"_csrf_token": csrf, "email": "alex@decodelabs.dev", "password": "Password123!"})

print("=== DASHBOARD CURRENCY HIGHLIGHTS ===")
for line in r2.text.splitlines():
    if any(k in line for k in ["Rs.", "LKR", "Quick Presets", "Expense Amount"]):
        print(" ", line.strip())

r3 = c.get("/transactions")
print("\n=== TRANSACTIONS CURRENCY HIGHLIGHTS ===")
for line in r3.text.splitlines():
    if any(k in line for k in ["Rs.", "LKR", "Output verified"]):
        print(" ", line.strip())
