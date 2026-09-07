import ipaddress
import json
import subprocess
import time
import urllib.error
import urllib.request


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def verify():
    project = "snp-final-review"
    network = f"{project}_default"
    backend = f"{project}-backend-1"
    frontend = f"{project}-frontend-1"
    url = "http://127.0.0.1:3101/api/health"
    details = json.loads(docker("network", "inspect", network))[0]
    containers = details["Containers"].values()
    original = next(c["IPv4Address"].split("/")[0] for c in containers if c["Name"] == backend)
    subnet = ipaddress.ip_network(details["IPAM"]["Config"][0]["Subnet"])
    replacement = str(subnet.network_address + 200)
    assert replacement not in {c["IPv4Address"].split("/")[0] for c in containers}
    started = docker("inspect", frontend, "--format", "{{.State.StartedAt}}")
    with urllib.request.urlopen(url, timeout=3) as response:
        assert response.status == 200
    docker("network", "disconnect", network, backend)
    try:
        docker("network", "connect", "--ip", replacement, "--alias", "backend", network, backend)
        deadline = time.monotonic() + 15
        recovered = False
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    recovered = response.status == 200
                if recovered:
                    break
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.5)
        assert recovered, "API did not recover after backend IP changed without restarting nginx"
        assert docker("inspect", frontend, "--format", "{{.State.StartedAt}}") == started
        print("PASS: API recovered after backend IP changed without restarting nginx")
    finally:
        connected = json.loads(docker("inspect", backend))[0]["NetworkSettings"]["Networks"]
        if network in connected:
            docker("network", "disconnect", network, backend)
        docker("network", "connect", "--ip", original, "--alias", "backend", network, backend)


if __name__ == "__main__":
    verify()
