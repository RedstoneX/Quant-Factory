#!/usr/bin/env python3
"""Emit the current network namespace's IPv4 interfaces and default routes."""
import fcntl
import json
import socket
import struct

def parse_default_interfaces(route_lines):
    default_interfaces = []
    for line in route_lines:
        fields = line.split()
        if (
            len(fields) >= 8
            and fields[1] == "00000000"
            and fields[7] == "00000000"
            and int(fields[3], 16) & 3 == 3
        ):
            default_interfaces.append(fields[0])
    return default_interfaces


def render_topology(interface_addresses, route_lines):
    return json.dumps(
        {
            "interfaces": interface_addresses,
            "default_interfaces": parse_default_interfaces(route_lines),
        },
        sort_keys=True,
    )


def capture_interface_addresses():
    interfaces = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for _, name in socket.if_nameindex():
        if name == "lo":
            continue
        try:
            result = fcntl.ioctl(
                sock.fileno(), 0x8915, struct.pack("256s", name.encode()[:15])
            )
        except OSError:
            continue
        interfaces[name] = socket.inet_ntoa(result[20:24])
    return interfaces


def main():
    with open("/proc/net/route", encoding="ascii") as routes:
        route_lines = list(routes)[1:]
    print(render_topology(capture_interface_addresses(), route_lines))


if __name__ == "__main__":
    main()
