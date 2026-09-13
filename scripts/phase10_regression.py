import sys
import urllib.request
import urllib.parse
import http.cookiejar
import json
import re

BASE_URL = "http://127.0.0.1:8000"

def run_regression():
    print("[*] Starting Phase 10 Functional Regression Test...")
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def get_csrf(html):
        match = re.search(r'name=["\'](_?csrf_token)["\']\s+value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(2)
        match = re.search(r'value=["\']([^"\']+)["\']\s+name=["\'](_?csrf_token)["\']', html)
        if match:
            return match.group(1)
        return None

    # Step 1: Open Sign-in page
    print("\n[Step 1] Loading /sign-in...")
    req = urllib.request.Request(f"{BASE_URL}/sign-in")
    resp = opener.open(req)
    assert resp.status == 200, f"Sign-in page returned {resp.status}"
    signin_html = resp.read().decode('utf-8')
    csrf_token = get_csrf(signin_html)
    assert csrf_token, "CSRF token missing from sign-in page"
    print(" -> Sign-in page loaded successfully. CSRF obtained.")

    # Step 2: Sign in with valid credentials
    print("\n[Step 2] Authenticating as alex@decodelabs.dev...")
    login_data = urllib.parse.urlencode({
        "_csrf_token": csrf_token,
        "email": "alex@decodelabs.dev",
        "password": "Password123!"
    }).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/sign-in", data=login_data, method="POST")
    resp = opener.open(req)
    assert resp.status == 200, f"Dashboard redirect failed, status {resp.status}"
    dashboard_html = resp.read().decode('utf-8')
    assert "Expense Dashboard" in dashboard_html, "Dashboard title not found"
    print(" -> Sign in successful. Authenticated session active.")

    # Step 3: Check Dashboard initial elements
    print("\n[Step 3] Verifying Dashboard visual & data structure...")
    assert "input stream" in dashboard_html.lower(), "Pipeline Input Stream missing"
    assert "core process" in dashboard_html.lower(), "Pipeline Core Process missing"
    assert "ledger output" in dashboard_html.lower(), "Pipeline Ledger Output missing"
    assert "+$10" in dashboard_html and "+$25" in dashboard_html and "+$50" in dashboard_html and "+$100" in dashboard_html, "Quick preset buttons missing"
    print(" -> Pipeline and Quick Presets verified.")

    def get_total_spent(html):
        match = re.search(r'Total Spent.*?\$?([0-9,]+\.[0-9]{2})', html, re.DOTALL)
        if match:
            return float(match.group(1).replace(',', ''))
        return 0.0

    initial_total = get_total_spent(dashboard_html)
    print(f" -> Current initial total: ${initial_total:.2f}")

    # Step 4: Add $10 expense
    print("\n[Step 4] Adding $10.00 expense via POST /expenses...")
    csrf_token = get_csrf(dashboard_html)
    expense_data = urllib.parse.urlencode({
        "_csrf_token": csrf_token,
        "amount": "10.00",
        "description": "API Test Cloud Compute $10"
    }).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/expenses", data=expense_data, method="POST")
    resp = opener.open(req)
    assert resp.status == 200, f"Expense creation failed: status {resp.status}"
    post_10_html = resp.read().decode('utf-8')
    new_total_1 = get_total_spent(post_10_html)
    print(f" -> New Total after $10: ${new_total_1:.2f} (Expected: ${initial_total + 10.00:.2f})")
    assert abs(new_total_1 - (initial_total + 10.00)) < 0.01, f"Total mismatch after $10: {new_total_1}"

    # Step 5: Add $25 expense
    print("\n[Step 5] Adding $25.00 expense via POST /expenses...")
    csrf_token = get_csrf(post_10_html)
    expense_data_2 = urllib.parse.urlencode({
        "_csrf_token": csrf_token,
        "amount": "25.00",
        "description": "API Test Domain Renewal $25"
    }).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/expenses", data=expense_data_2, method="POST")
    resp = opener.open(req)
    assert resp.status == 200, f"Expense creation 2 failed: status {resp.status}"
    post_25_html = resp.read().decode('utf-8')
    new_total_2 = get_total_spent(post_25_html)
    print(f" -> New Total after $25: ${new_total_2:.2f} (Expected: ${new_total_1 + 25.00:.2f})")
    assert abs(new_total_2 - (new_total_1 + 25.00)) < 0.01, f"Total mismatch after $25: {new_total_2}"

    # Step 6: Open Transactions page
    print("\n[Step 6] Navigating to /transactions...")
    req = urllib.request.Request(f"{BASE_URL}/transactions")
    resp = opener.open(req)
    assert resp.status == 200, f"Transactions page failed: {resp.status}"
    tx_html = resp.read().decode('utf-8')
    assert "Session Transaction Ledger" in tx_html, "Ledger title not found"
    assert "DATABASE STATE: SYNCHRONIZED" in tx_html, "Truthful audit state missing"
    assert "LEDGER INTEGRITY: 100% SHA256 VALID" not in tx_html, "Fake SHA256 security claim still present!"
    assert "API Test Domain Renewal $25" in tx_html, "Newly added transaction not visible in table"
    print(" -> Transactions ledger and truthful audit state verified.")

    # Step 7: Test Search functionality
    print("\n[Step 7] Testing search query filter on /transactions?q=Renewal...")
    req = urllib.request.Request(f"{BASE_URL}/transactions?q=Renewal")
    resp = opener.open(req)
    assert resp.status == 200
    search_html = resp.read().decode('utf-8')
    assert "API Test Domain Renewal $25" in search_html, "Matching item not found in search"
    print(" -> Search query filtering verified.")

    # Step 8: Test CSV Export
    print("\n[Step 8] Testing CSV Export (/transactions/export/csv)...")
    req = urllib.request.Request(f"{BASE_URL}/transactions/export/csv")
    resp = opener.open(req)
    assert resp.status == 200
    csv_content = resp.read().decode('utf-8')
    assert "Transaction ID" in csv_content or "Amount" in csv_content or "Description" in csv_content
    assert "API Test Domain Renewal $25" in csv_content
    print(" -> CSV export verified. Correct content headers and data rows.")

    # Step 9: Test JSON Export
    print("\n[Step 9] Testing JSON Export (/transactions/export/json)...")
    req = urllib.request.Request(f"{BASE_URL}/transactions/export/json")
    resp = opener.open(req)
    assert resp.status == 200
    json_data = json.loads(resp.read().decode('utf-8'))
    assert isinstance(json_data, (list, dict)), "JSON export is not a valid JSON structure"
    print(" -> JSON export verified. Valid JSON structure returned.")

    # Step 10: Test Logout
    print("\n[Step 10] Testing Logout (/logout)...")
    csrf_token = get_csrf(tx_html)
    logout_data = urllib.parse.urlencode({"_csrf_token": csrf_token}).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/logout", data=logout_data, method="POST")
    resp = opener.open(req)
    assert resp.status == 200
    logout_html = resp.read().decode('utf-8')
    assert "Sign In" in logout_html or "signed out" in logout_html.lower(), "Logout redirect failed"
    print(" -> Logout verified successfully.")

    # Step 11: Verify Protected Route without session
    print("\n[Step 11] Verifying /dashboard redirect after logout...")
    req = urllib.request.Request(f"{BASE_URL}/dashboard")
    resp = opener.open(req)
    assert "/sign-in" in resp.geturl(), "Protected route did not redirect to sign-in after logout"
    print(" -> Protected route redirection verified.")

    print("\n==================================================")
    print(">>> ALL 12 FUNCTIONAL REGRESSION STEPS PASSED! <<<")
    print("==================================================")

if __name__ == "__main__":
    try:
        run_regression()
    except Exception as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(1)
