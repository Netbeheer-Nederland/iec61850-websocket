import requests

class BffClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def request(self, method: str, path: str, json=None, params=None, headers=None):
        url = f"{self.base_url}{path}"

        response = requests.request(
            method=method,
            url=url,
            json=json,
            params=params,
            headers=headers or {},
            timeout=5
        )

        response.raise_for_status()

        try:
            return response.json()
        except Exception:
            return response.text