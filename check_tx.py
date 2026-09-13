import asyncio
import httpx
import re

async def check():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", follow_redirects=True) as c:
        r1 = await c.get("/sign-in")
        m = re.search(r'_csrf_token.*?value="([^"]+)"', r1.text)
        csrf = m.group(1) if m else ""
        await c.post("/sign-in", data={"_csrf_token": csrf, "email": "alex@decodelabs.dev", "password": "Password123!"})
        r3 = await c.get("/transactions")
        # Check for stat card content
        for keyword in ["TOTAL TRANSACTIONS", "TOTAL SPENT", "RUNTIME SESSION STATE", "Total Spent", "Total Transactions", "Runtime"]:
            print(f"  {keyword}: {'FOUND' if keyword in r3.text else 'NOT FOUND'}")
        # Print a small context around the first stat card area
        idx = r3.text.find("stat")
        if idx > 0:
            print("\n--- SAMPLE around 'stat' ---")
            print(r3.text[idx:idx+300])

asyncio.run(check())
