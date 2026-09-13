import asyncio
import httpx
import re

async def test():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", follow_redirects=True) as c:
        # 1. Get sign-in page for CSRF token
        r1 = await c.get("/sign-in")
        print("Sign-in page status:", r1.status_code)

        m = re.search(r'name="_csrf_token" value="([^"]+)"', r1.text)
        csrf = m.group(1) if m else ""
        print("CSRF found:", bool(csrf))

        # 2. POST sign-in
        r2 = await c.post("/sign-in", data={
            "_csrf_token": csrf,
            "email": "alex@decodelabs.dev",
            "password": "Password123!",
        })
        print("After sign-in status:", r2.status_code, "URL:", str(r2.url))

        checks = {
            "150.00": "Total spent $150.00",
            "Domain Registration": "Domain Registration expense",
            "Cloud Server": "Cloud Server expense",
            "API Gateway": "API Gateway expense",
            "Input Stream": "Pipeline - Input Stream",
            "SYSTEM READY": "Topbar SYSTEM READY",
            "Expense Dashboard": "Dashboard title",
            "list[float]": "Data structure badge",
        }
        for key, label in checks.items():
            found = key in r2.text
            print(f"  [{'+' if found else 'MISSING'}] {label}")

        # 3. Test transactions page
        r3 = await c.get("/transactions")
        print("\nTransactions page status:", r3.status_code, "URL:", str(r3.url))
        tx_checks = {
            "Transaction History": "Transaction History title",
            "Total Transactions": "Total Transactions stat card",
            "Total Spent": "Total Spent stat card",
            "Runtime Session State": "Runtime Session State card",
            "INPUT - ACCUMULATOR": "Process method column",
            "Accumulator Sum": "Bottom audit card",
        }
        for key, label in tx_checks.items():
            found = key in r3.text
            print(f"  [{'+' if found else 'MISSING'}] {label}")

        # 4. Test CSV export
        r4 = await c.get("/transactions/export/csv")
        print("\nCSV export status:", r4.status_code)
        print("  Content-Type:", r4.headers.get("content-type", ""))
        print("  Has header row:", "Sequence,Transaction ID" in r4.text)
        print("  Has expense data:", "Domain Registration" in r4.text)

        # 5. Test JSON export
        r5 = await c.get("/transactions/export/json")
        print("\nJSON export status:", r5.status_code)
        data = r5.json()
        print("  Transaction count:", data.get("count"))
        print("  All VERIFIED:", all(t["status"] == "VERIFIED" for t in data.get("transactions", [])))

asyncio.run(test())
