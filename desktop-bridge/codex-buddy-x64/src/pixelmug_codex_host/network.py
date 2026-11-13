from __future__ import annotations

import ipaddress
import socket
import sys

from .constants import BROADCAST_ADDR


def _usable_ipv4(value: str) -> ipaddress.IPv4Address | None:
    try:
        ip = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return None
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return None
    return ip


def _broadcast_for(ip: ipaddress.IPv4Address, prefix: int) -> str | None:
    if prefix <= 0 or prefix >= 31:
        return None
    try:
        network = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
    except ValueError:
        return None
    broadcast = network.broadcast_address
    if broadcast == ip:
        return None
    return str(broadcast)


def _windows_ipv4_broadcasts() -> list[str]:
    if sys.platform != "win32":
        return []

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []

    class SocketAddress(ctypes.Structure):
        _fields_ = [
            ("lpSockaddr", ctypes.c_void_p),
            ("iSockaddrLength", ctypes.c_int),
        ]

    class SockaddrIn(ctypes.Structure):
        _fields_ = [
            ("sin_family", ctypes.c_ushort),
            ("sin_port", ctypes.c_ushort),
            ("sin_addr", ctypes.c_ubyte * 4),
            ("sin_zero", ctypes.c_ubyte * 8),
        ]

    class AdapterUnicastAddress(ctypes.Structure):
        pass

    AdapterUnicastAddressPtr = ctypes.POINTER(AdapterUnicastAddress)
    AdapterUnicastAddress._fields_ = [
        ("Length", wintypes.ULONG),
        ("Flags", wintypes.DWORD),
        ("Next", AdapterUnicastAddressPtr),
        ("Address", SocketAddress),
        ("PrefixOrigin", ctypes.c_int),
        ("SuffixOrigin", ctypes.c_int),
        ("DadState", ctypes.c_int),
        ("ValidLifetime", wintypes.ULONG),
        ("PreferredLifetime", wintypes.ULONG),
        ("LeaseLifetime", wintypes.ULONG),
        ("OnLinkPrefixLength", ctypes.c_ubyte),
    ]

    class AdapterAddresses(ctypes.Structure):
        pass

    AdapterAddressesPtr = ctypes.POINTER(AdapterAddresses)
    AdapterAddresses._fields_ = [
        ("Length", wintypes.ULONG),
        ("IfIndex", wintypes.DWORD),
        ("Next", AdapterAddressesPtr),
        ("AdapterName", ctypes.c_char_p),
        ("FirstUnicastAddress", AdapterUnicastAddressPtr),
        ("FirstAnycastAddress", ctypes.c_void_p),
        ("FirstMulticastAddress", ctypes.c_void_p),
        ("FirstDnsServerAddress", ctypes.c_void_p),
        ("DnsSuffix", ctypes.c_wchar_p),
        ("Description", ctypes.c_wchar_p),
        ("FriendlyName", ctypes.c_wchar_p),
        ("PhysicalAddress", ctypes.c_ubyte * 8),
        ("PhysicalAddressLength", wintypes.DWORD),
        ("Flags", wintypes.DWORD),
        ("Mtu", wintypes.DWORD),
        ("IfType", wintypes.DWORD),
        ("OperStatus", ctypes.c_int),
        ("Ipv6IfIndex", wintypes.DWORD),
        ("ZoneIndices", wintypes.DWORD * 16),
        ("FirstPrefix", ctypes.c_void_p),
    ]

    get_adapters_addresses = ctypes.windll.iphlpapi.GetAdaptersAddresses
    get_adapters_addresses.argtypes = [
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        AdapterAddressesPtr,
        ctypes.POINTER(wintypes.ULONG),
    ]
    get_adapters_addresses.restype = wintypes.ULONG

    af_inet = 2
    error_buffer_overflow = 111
    error_success = 0
    flags = 0x0002 | 0x0004 | 0x0008
    if_oper_status_up = 1

    size = wintypes.ULONG(15 * 1024)
    buffer = ctypes.create_string_buffer(size.value)
    result = get_adapters_addresses(af_inet, flags, None, ctypes.cast(buffer, AdapterAddressesPtr), ctypes.byref(size))
    if result == error_buffer_overflow:
        buffer = ctypes.create_string_buffer(size.value)
        result = get_adapters_addresses(af_inet, flags, None, ctypes.cast(buffer, AdapterAddressesPtr), ctypes.byref(size))
    if result != error_success:
        return []

    targets: list[str] = []
    adapter = ctypes.cast(buffer, AdapterAddressesPtr)
    while adapter:
        current = adapter.contents
        if current.OperStatus == if_oper_status_up:
            unicast = current.FirstUnicastAddress
            while unicast:
                current_unicast = unicast.contents
                address = current_unicast.Address
                if address.lpSockaddr and address.iSockaddrLength >= ctypes.sizeof(SockaddrIn):
                    sockaddr = ctypes.cast(address.lpSockaddr, ctypes.POINTER(SockaddrIn)).contents
                    if sockaddr.sin_family == af_inet:
                        ip = _usable_ipv4(".".join(str(part) for part in sockaddr.sin_addr))
                        if ip:
                            target = _broadcast_for(ip, int(current_unicast.OnLinkPrefixLength))
                            if target:
                                targets.append(target)
                unicast = current_unicast.Next
        adapter = current.Next
    return targets


def _hostname_ipv4_broadcasts() -> list[str]:
    targets: list[str] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return targets
    for info in infos:
        ip = _usable_ipv4(info[4][0])
        if not ip:
            continue
        target = _broadcast_for(ip, 24)
        if target:
            targets.append(target)
    return targets


def broadcast_targets() -> list[str]:
    """Return UDP discovery broadcast destinations for this host.

    Windows machines with many virtual adapters can route 255.255.255.255 away
    from the Wi-Fi network. Directed broadcasts make the intended subnet clear.
    """
    targets = [BROADCAST_ADDR]
    try:
        targets.extend(_windows_ipv4_broadcasts())
    except Exception:
        pass
    if len(targets) == 1:
        targets.extend(_hostname_ipv4_broadcasts())

    seen: set[str] = set()
    unique: list[str] = []
    for target in targets:
        if target not in seen:
            seen.add(target)
            unique.append(target)
    return unique
