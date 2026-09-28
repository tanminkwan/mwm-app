import requests
import json
import sys

class MwServerTester:
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.access_token = None
        self.headers = {'Content-Type': 'application/json'}

    def login(self):
        print(f"Logging in to {self.base_url}...")
        login_url = f"{self.base_url}/api/v1/security/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": "db",
            "refresh": True
        }
        try:
            response = requests.post(login_url, json=payload, headers=self.headers)
            response.raise_for_status()
            self.access_token = response.json().get('access_token')
            self.headers['Authorization'] = f'Bearer {self.access_token}'
            print("Login successful.")
            return True
        except Exception as e:
            print(f"Login failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return False

    def list_servers(self, host_id=None):
        url = f"{self.base_url}/api/v1/mw_server/list"
        params = {'host_id': host_id} if host_id else None
        response = requests.get(url, headers=self.headers, params=params)
        try:
            return response.status_code, response.json()
        except Exception:
            print(f"Failed to decode JSON. Status: {response.status_code}")
            print(f"Response text: {response.text}")
            raise

    def add_server(self, server_data):
        url = f"{self.base_url}/api/v1/mw_server/add"
        response = requests.post(url, headers=self.headers, json=server_data)
        return response.status_code, response.json()

    def edit_server(self, host_id, server_data):
        url = f"{self.base_url}/api/v1/mw_server/edit/{host_id}"
        response = requests.put(url, headers=self.headers, json=server_data)
        return response.status_code, response.json()

    def delete_server(self, host_id):
        url = f"{self.base_url}/api/v1/mw_server/delete/{host_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code, response.json()

if __name__ == "__main__":
    # Usage Example
    import os
    tester = MwServerTester(
        os.getenv('MWM_URL', 'http://127.0.0.1:8000'),
        os.getenv('MWM_USER', 'admin'),
        os.getenv('MWM_PASSWORD', ''),
    )
    
    if not tester.login():
        sys.exit(1)

    # Example Check: List specific server
    target_host = os.getenv("MWM_TARGET_HOST", "example-host-01")
    status, result = tester.list_servers(target_host)
    
    if status == 200:
        print(f"Server {target_host} already exists. Updating...")
        status, result = tester.edit_server(target_host, {"server_name": "Updated Server Name"})
    else:
        print(f"Server {target_host} not found. Adding...")
        new_server = {
            "host_id": target_host,
            "server_name": f"New Server {target_host}",
            "landscape": "PROD",
            "os_type": "LINUX",
            "ip_address": "10.0.0.1",
            "use_yn": "YES"
        }
        status, result = tester.add_server(new_server)
    
    print(f"Result (Status {status}): {json.dumps(result, indent=2, ensure_ascii=False)}")

    # Final Check: List all
    # status, servers = tester.list_servers()
    # print(f"Registered Servers: {len(servers)}")
