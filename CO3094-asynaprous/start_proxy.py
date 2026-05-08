"""Entry point for launching the proxy server."""

import argparse
import re

from daemon import create_proxy

PROXY_PORT = 8080


def parse_virtual_hosts(config_file):
    """Parse config/proxy.conf into {host: (proxy_passes, policy)}."""
    with open(config_file, "r", encoding="utf-8") as file_obj:
        config_text = file_obj.read()

    routes = {}
    host_blocks = re.findall(r'host\s+"([^"]+)"\s*\{(.*?)\}', config_text, re.DOTALL)
    for host, block in host_blocks:
        proxy_passes = re.findall(r"proxy_pass\s+http://([^\s;]+);", block)
        policy_match = re.search(r"dist_policy\s+([\w-]+)", block)
        policy = policy_match.group(1) if policy_match else "round-robin"
        routes[host] = (proxy_passes[0] if len(proxy_passes) == 1 else proxy_passes, policy)

    for key, value in routes.items():
        print(f"[ProxyConfig] {key} -> {value}")
    return routes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Proxy", epilog="Proxy daemon")
    parser.add_argument("--server-ip", default="0.0.0.0")
    parser.add_argument("--server-port", type=int, default=PROXY_PORT)
    parser.add_argument("--config", default="config/proxy.conf")
    args = parser.parse_args()

    create_proxy(args.server_ip, args.server_port, parse_virtual_hosts(args.config))
