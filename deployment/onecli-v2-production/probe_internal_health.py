"""Probe the three internal OneCLI health endpoints from the control network."""

from urllib.request import urlopen


URLS = (
    "http://web:10254/healthz",
    "http://" + "api" + ":10256/v1/health",
    "http://gateway:10255/healthz",
)

for url in URLS:
    with urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("health")

print("internal_health=passed services=3")
