#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# leaktest.py - IP-Adress- und DNS-Leak-Test
#
# Testet:
# 1. IPv4-Adresse nach außen (via VPN?)
# 2. IPv6-Adresse nach außen
# 3. Welche DNS-Server werden genutzt (DNS-Leak)
# 4. Ping zu externen Hosts
#

import re
import os
import socket
from twisted.internet.threads import deferToThread
from .wireguard import run_cmd

# Mullvad-spezifische APIs
MULLVAD_CONNECTED_URL = "https://am.i.mullvad.net/connected"
MULLVAD_IP_URL = "https://am.i.mullvad.net/ip"

# APIs für IP-Ermittlung (mehrere als Fallback)
IPV4_APIS = [
    "https://api4.my-ip.io/ip",
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://checkip.amazonaws.com",
]

IPV6_APIS = [
    "https://api6.my-ip.io/ip",
    "https://ipv6.icanhazip.com",
    "https://api6.ipify.org",
]

DNS_LEAK_SERVERS = [
    # DNS leak test hosts - antworten mit der IP des anfragenden DNS-Servers
    "whoami.ds.akahelp.net",
    "o-o.myaddr.l.google.com",
]

PING_HOSTS = [
    ("8.8.8.8", "Google DNS (IPv4)"),
    ("1.1.1.1", "Cloudflare DNS (IPv4)"),
    ("2001:4860:4860::8888", "Google DNS (IPv6)"),
    ("2606:4700:4700::1111", "Cloudflare DNS (IPv6)"),
]


def fetch_url_simple(url, timeout=8):
    """Einfacher HTTP-Client ohne externe Abhängigkeiten via curl."""
    rc, out, err = run_cmd("curl -s -4 --max-time %d '%s' 2>/dev/null" % (timeout, url), timeout=timeout+2)
    if rc == 0 and out:
        return out.strip()
    return None


def fetch_url_v6(url, timeout=8):
    """Wie fetch_url_simple aber erzwingt IPv6."""
    rc, out, err = run_cmd("curl -s -6 --max-time %d '%s' 2>/dev/null" % (timeout, url), timeout=timeout+2)
    if rc == 0 and out:
        return out.strip()
    return None


def is_valid_ip(s):
    """Prüft ob ein String eine gültige IPv4 oder IPv6-Adresse ist."""
    if not s:
        return False
    s = s.strip()
    # IPv4
    try:
        socket.inet_pton(socket.AF_INET, s)
        return True
    except Exception:
        pass
    # IPv6
    try:
        socket.inet_pton(socket.AF_INET6, s)
        return True
    except Exception:
        pass
    return False


def check_mullvad_connection():
    """
    Prüft via Mullvad-API ob der Traffic über Mullvad läuft.
    Gibt ein dict zurück: {"connected": bool, "ip": str, "message": str}
    """
    result = {"connected": False, "ip": None, "message": "Nicht erreichbar"}
    # IP ermitteln
    ip = fetch_url_simple(MULLVAD_IP_URL)
    if ip and is_valid_ip(ip):
        result["ip"] = ip.strip()
    # Verbindungsstatus
    msg = fetch_url_simple(MULLVAD_CONNECTED_URL)
    if msg:
        result["message"] = msg.strip()
        result["connected"] = msg.strip().lower().startswith("you are connected to mullvad")
    return result


def get_my_ipv4():
    """Ermittelt die eigene IPv4-Adresse."""
    for api in IPV4_APIS:
        result = fetch_url_simple(api)
        if result and is_valid_ip(result):
            return result.strip()
    return None


def get_my_ipv6():
    """Ermittelt die eigene IPv6-Adresse."""
    for api in IPV6_APIS:
        result = fetch_url_v6(api)
        if result and is_valid_ip(result):
            return result.strip()
    # Kein IPv6? Prüfe ob überhaupt vorhanden
    rc, out, _ = run_cmd("ip -6 addr show scope global")
    if rc != 0 or not out.strip():
        return "IPv6 nicht konfiguriert"
    return "Nicht erreichbar (möglicher Block)"


def get_dns_servers_in_use():
    """
    Ermittelt welche DNS-Server aktuell genutzt werden.
    Methode 1: /etc/resolv.conf
    Methode 2: WireGuard DNS aus Interface-Config
    Methode 3: DNS-Leak-Test via dig
    """
    dns_servers = []

    # Methode 1: resolv.conf
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        dns_servers.append(parts[1])
    except Exception:
        pass

    # Methode 2: Über dig/nslookup prüfen welcher Server tatsächlich antwortet
    actual_servers = []
    rc, out, _ = run_cmd("dig +short +time=5 whoami.ds.akahelp.net TXT 2>/dev/null", timeout=8)
    if rc == 0 and out:
        # Ausgabe enthält IP des DNS-Servers der die Anfrage bearbeitet hat
        matches = re.findall(r'"ns" "([^"]+)"', out)
        actual_servers.extend(matches)

    # Alternativ via nslookup
    if not actual_servers:
        rc, out, _ = run_cmd("nslookup -type=txt whoami.ds.akahelp.net 2>/dev/null", timeout=8)
        if rc == 0:
            matches = re.findall(r'ns = ([^\s]+)', out)
            actual_servers.extend(matches)

    return {
        "configured": dns_servers,
        "actual_resolver": actual_servers,
    }


def ping_host(host, count=3, timeout=5):
    """Pingt einen Host an. Gibt (success, rtt_ms, packet_loss) zurück."""
    # Erkenne IPv6
    is_v6 = ":" in host
    ping_cmd = "ping6" if is_v6 else "ping"

    cmd = "%s -c %d -W %d %s 2>&1" % (ping_cmd, count, timeout, host)
    rc, out, _ = run_cmd(cmd, timeout=(count * timeout) + 3)

    if rc != 0:
        # Prüfe ob überhaupt erreichbar
        if "Network is unreachable" in out or "connect: Network is unreachable" in out:
            return False, None, 100, "Netz nicht erreichbar"
        return False, None, 100, "Timeout / nicht erreichbar"

    # RTT parsen: "rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms"
    rtt_match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", out)
    rtt = float(rtt_match.group(1)) if rtt_match else None

    # Paketverlust parsen: "3 received, 0% packet loss"
    loss_match = re.search(r"(\d+)% packet loss", out)
    loss = int(loss_match.group(1)) if loss_match else 0

    return rc == 0 and loss < 100, rtt, loss, "OK" if loss == 0 else "%d%% Verlust" % loss


def run_full_leak_test(callback):
    """
    Führt alle Tests asynchron durch und ruft callback mit den Ergebnissen auf.
    callback(results_dict)
    """
    def _run_all():
        results = {
            "mullvad": None,
            "ipv4": None,
            "ipv6": None,
            "dns": None,
            "ping": [],
            "errors": [],
        }

        # 0. Mullvad-Verbindungscheck
        try:
            results["mullvad"] = check_mullvad_connection()
        except Exception as e:
            results["mullvad"] = {"connected": False, "ip": None, "message": "Fehler: %s" % str(e)}
            results["errors"].append("Mullvad: %s" % str(e))

        # 1. IPv4
        try:
            results["ipv4"] = get_my_ipv4() or "Nicht ermittelbar"
        except Exception as e:
            results["ipv4"] = "Fehler: %s" % str(e)
            results["errors"].append("IPv4: %s" % str(e))

        # 2. IPv6
        try:
            results["ipv6"] = get_my_ipv6() or "Nicht ermittelbar"
        except Exception as e:
            results["ipv6"] = "Fehler: %s" % str(e)

        # 3. DNS
        try:
            results["dns"] = get_dns_servers_in_use()
        except Exception as e:
            results["dns"] = {"configured": [], "actual_resolver": [], "error": str(e)}
            results["errors"].append("DNS: %s" % str(e))

        # 4. Ping-Tests
        for host, label in PING_HOSTS:
            try:
                success, rtt, loss, msg = ping_host(host, count=2, timeout=4)
                results["ping"].append({
                    "host": host,
                    "label": label,
                    "success": success,
                    "rtt": rtt,
                    "loss": loss,
                    "msg": msg,
                })
            except Exception as e:
                results["ping"].append({
                    "host": host,
                    "label": label,
                    "success": False,
                    "rtt": None,
                    "loss": 100,
                    "msg": "Fehler: %s" % str(e),
                })

        return results

    d = deferToThread(_run_all)
    d.addCallback(callback)
    return d
