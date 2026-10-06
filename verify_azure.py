import sys
import os
import requests
import time

BASE_URL = "http://localhost:8000"
client = requests.Session()

def main():
    print("Registering/Logging in...")
    try:
        client.post(f"{BASE_URL}/auth/register", json={
            "email": "azure-test@test.com",
            "password": "password123",
            "name": "Azure Tester"
        })
    except Exception as e:
        pass
        
    res = client.post(f"{BASE_URL}/auth/login", data={
        "username": "azure-test@test.com",
        "password": "password123"
    })
    if res.status_code != 200:
        print("Login failed:", res.text)
        return
        
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    
    print("Adding Azure Account...")
    res = client.post(f"{BASE_URL}/accounts/", json={
        "name": "Azure Demo",
        "provider": "azure",
        "tenant_id": "dummy",
        "client_id": "dummy",
        "client_secret": "dummy",
        "subscription_id": "dummy"
    })
    if res.status_code >= 400:
        print(f"Failed to add account: {res.text}")
        return
        
    print("Waiting for background sync (15s)...")
    time.sleep(15)
    
    res = client.get(f"{BASE_URL}/costs/summary")
    print("\n=== Cost Summary ===")
    print(res.json())
    
    res = client.get(f"{BASE_URL}/recommendations/")
    print("\n=== Recommendations ===")
    recs = res.json()
    has_ri = False
    has_azure_vm = False
    for r in recs:
        print(f"[{r['service_type']}] {r['issue']} -> {r['action']} (Savings: ${r['potential_savings_usd']:.2f})")
        if r['action'] == 'Purchase Reserved VM Instance':
            has_ri = True
        if r['service_type'] == 'AzureVM':
            has_azure_vm = True
            
    if not has_ri:
        print("ERROR: Missing 'Purchase Reserved VM Instance' action")
        sys.exit(1)
    if not has_azure_vm:
        print("ERROR: Missing AzureVM recommendations")
        sys.exit(1)
        
    print("\nSUCCESS: Azure Demo mode fully working.")

if __name__ == "__main__":
    main()
