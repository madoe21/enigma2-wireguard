#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# routing.py - Domain-Ausnahmen und Policy-Routing
#
# Löst Domain-Namen auf und leitet deren IPs direkt über das
# Standard-Gateway (am VPN vorbei). Nützlich für lokale Feeds,
# IPTV-Streams etc. die keine feste IP haben.
#

import os
import socket
import subprocess
import re
from .wireguard import run_cmd, run_cmd_async

# Tag für unsere Route-Kommentare (zum späteren Aufräumen)
ROUTE_COMMENT_TAG = "wg-simple-exception"
EXCEPTION_TABLE = "200"
EXCEPTION_FWMARK = "0x100"


def get_default_gateway():
    """Ermittelt das aktuelle Default-Gateway und Interface."""
    rc, out, _ = run_cmd("ip route show default")
    if rc != 0 or not out:
        return None, None

    # "default via 192.168.1.1 dev eth0 ..."
    match = re.search(r"default via (\S+) dev (\S+)", out)
    if match:
        return match.group(1), match.group(2)
    return None, None


def resolve_domain(domain):
    """Löst einen Domain-Namen zu IPv4-Adressen auf."""
    try:
        results = socket.getaddrinfo(domain.strip(), None, socket.AF_INET)
        ips = list(set(r[4][0] for r in results))
        return ips
    except Exception:
        return []


def resolve_domain_v6(domain):
    """Löst einen Domain-Namen zu IPv6-Adressen auf."""
    try:
        results = socket.getaddrinfo(domain.strip(), None, socket.AF_INET6)
        ips = list(set(r[4][0] for r in results))
        return ips
    except Exception:
        return []


def parse_domain_list(domain_string):
    """Parst eine komma- oder zeilengetrennte Liste von Domains."""
    if not domain_string:
        return []
    domains = []
    for d in re.split(r"[,\n\r;]+", domain_string):
        d = d.strip()
        # Kommentare entfernen
        if "#" in d:
            d = d[:d.index("#")].strip()
        if d and not d.startswith("#"):
            domains.append(d)
    return domains


def add_bypass_route(ip, gateway, dev):
    """Fügt eine Route hinzu die eine IP am VPN vorbeileitet."""
    # Verwende metric 100 um Priorität zu geben
    cmd = "ip route add %s via %s dev %s metric 100 2>/dev/null || true" % (ip, gateway, dev)
    run_cmd(cmd)


def remove_bypass_routes():
    """Entfernt alle vom Plugin gesetzten Bypass-Routen."""
    # Wir merken uns die IPs in einer Datei
    marker_file = "/tmp/wg-simple-routes.txt"
    if not os.path.isfile(marker_file):
        return

    gateway, dev = get_default_gateway()
    with open(marker_file, "r") as f:
        for line in f:
            ip = line.strip()
            if ip:
                run_cmd("ip route del %s 2>/dev/null || true" % ip)

    try:
        os.remove(marker_file)
    except Exception:
        pass


def apply_domain_exceptions(domain_string, callback=None):
    """
    Löst alle konfigurierten Domains auf und setzt Bypass-Routen.
    Wird VOR wg-quick up aufgerufen damit die Routen die VPN-Routen überleben.

    WICHTIG: wg-quick setzt beim 'up' AllowedIPs korrekt via Policy-Routing.
    Unsere expliziten Bypass-Routen haben durch metric 100 Priorität vor der
    WireGuard-Routing-Tabelle für diese spezifischen IPs.
    """
    from twisted.internet.threads import deferToThread

    def _do_apply():
        domains = parse_domain_list(domain_string)
        if not domains:
            return [], []

        gateway, dev = get_default_gateway()
        if not gateway:
            return [], ["Kein Default-Gateway gefunden"]

        resolved = []
        failed = []
        all_ips = []

        for domain in domains:
            ips = resolve_domain(domain)
            ips6 = resolve_domain_v6(domain)
            all_found = ips + ips6

            if all_found:
                resolved.append("%s → %s" % (domain, ", ".join(all_found)))
                all_ips.extend(ips)  # Nur IPv4 für ip route add
            else:
                failed.append(domain)

        # Routen setzen
        saved = []
        for ip in all_ips:
            add_bypass_route(ip, gateway, dev)
            saved.append(ip)

        # IPs in Datei speichern für späteres Aufräumen
        with open("/tmp/wg-simple-routes.txt", "w") as f:
            f.write("\n".join(saved))

        return resolved, failed

    if callback:
        d = deferToThread(_do_apply)
        d.addCallback(lambda result: callback(*result))
        return d
    else:
        return _do_apply()


def refresh_domain_exceptions(domain_string, interface_name, callback=None):
    """
    Aktualisiert Bypass-Routen für Domains (Refresh-Funktion für Timer).
    Entfernt alte Routen und setzt neue.
    """
    remove_bypass_routes()
    return apply_domain_exceptions(domain_string, callback)
