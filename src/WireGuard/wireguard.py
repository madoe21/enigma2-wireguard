#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# wireguard.py - WireGuard Verbindungsverwaltung
#
# Verwendet wg-quick für vollwertiges Routing via AllowedIPs.
# wg-quick setzt automatisch Policy-Routing-Tabellen, sodass AllowedIPs
# korrekt respektiert wird - kein manuelles Routing nötig.
#

import os
import socket
import subprocess
import re
from twisted.internet import reactor, defer
from Components.config import config, ConfigSubsection, ConfigText, ConfigYesNo, ConfigInteger

WG_CONFIG_DIR = "/etc/wireguard"
SETTINGS_FILE = "/etc/enigma2/wireguardsimple.conf"
ENDPOINT_ROUTES_FILE = "/tmp/wg-simple-endpoint-routes.txt"

# Plugin-Konfiguration

# Erweiterung: IP-Modus (IPv4/IPv6/beides)
from Components.config import ConfigSelection
config.plugins.wireguardsimple = ConfigSubsection()
config.plugins.wireguardsimple.config_file = ConfigText(default="", fixed_size=False)
config.plugins.wireguardsimple.domain_exceptions = ConfigText(default="", fixed_size=False)
config.plugins.wireguardsimple.exception_refresh_interval = ConfigInteger(default=30, limits=(5, 1440))
config.plugins.wireguardsimple.autostart = ConfigYesNo(default=False)
config.plugins.wireguardsimple.ip_mode = ConfigSelection(default="both", choices=[
    ("ipv4", "Nur IPv4"),
    ("ipv6", "Nur IPv6"),
    ("both", "IPv4 und IPv6")
])


def sync_settings_to_file():
    """
    Schreibt aktuelle Plugin-Einstellungen in /etc/enigma2/wireguardsimple.conf.
    Diese Datei wird vom Init-Script beim frühen Boot gelesen, BEVOR
    Enigma2 startet - damit wg-quick vor Enigma2 hochkommen kann.
    """
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            f.write("# WireGuard Simple - automatisch generiert\n")
            f.write("autostart=%s\n" % ("true" if config.plugins.wireguardsimple.autostart.value else "false"))
            f.write("config_file=%s\n" % config.plugins.wireguardsimple.config_file.value)
            f.write("domain_exceptions=%s\n" % config.plugins.wireguardsimple.domain_exceptions.value)
            f.write("exception_refresh_interval=%d\n" % config.plugins.wireguardsimple.exception_refresh_interval.value)
    except Exception as e:
        print("[WireGuard Simple] Fehler beim Schreiben der Settings-Datei:", e)


def run_cmd(cmd, timeout=15):
    """Führt einen Shell-Befehl synchron aus. Gibt (returncode, stdout, stderr) zurück."""
    try:
        result = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout nach %ds" % timeout
    except Exception as e:
        return -1, "", str(e)


def run_cmd_async(cmd, callback, timeout=15):
    """Führt einen Shell-Befehl asynchron aus via Twisted."""
    from twisted.internet.threads import deferToThread
    d = deferToThread(run_cmd, cmd, timeout)
    d.addCallback(lambda result: callback(*result))
    return d


class WireGuardManager:
    """Verwaltet WireGuard-Verbindungen."""

    def __init__(self):
        self._active_interface = None

    def get_configs(self):
        """Gibt Liste aller .conf Dateien in /etc/wireguard zurück."""
        if not os.path.isdir(WG_CONFIG_DIR):
            return []
        configs = []
        for f in sorted(os.listdir(WG_CONFIG_DIR)):
            if f.endswith(".conf"):
                configs.append(f[:-5])  # Interface-Name ohne .conf
        return configs

    def get_active_interface(self):
        """Gibt den aktuell aktiven WireGuard-Interface-Namen zurück oder None."""
        rc, out, _ = run_cmd("wg show interfaces")
        if rc == 0 and out:
            interfaces = out.split()
            # Prüfe welches von unseren Configs aktiv ist
            our_configs = self.get_configs()
            for iface in interfaces:
                if iface in our_configs:
                    return iface
            # Gib erstes aktives zurück falls vorhanden
            if interfaces:
                return interfaces[0]
        return None

    def is_connected(self, interface=None):
        """Prüft ob WireGuard verbunden ist."""
        active = self.get_active_interface()
        if interface:
            return active == interface
        return active is not None

    def get_status(self, interface=None):
        """Gibt WireGuard-Statusinformationen zurück."""
        iface = interface or self.get_active_interface()
        if not iface:
            return None
        rc, out, err = run_cmd("wg show %s" % iface)
        if rc != 0:
            return None
        return self._parse_wg_show(out, iface)

    def _parse_wg_show(self, output, interface):
        """Parst die Ausgabe von 'wg show'."""
        info = {
            "interface": interface,
            "public_key": "",
            "listen_port": "",
            "peers": []
        }
        current_peer = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("public key:"):
                info["public_key"] = line.split(":", 1)[1].strip()
            elif line.startswith("listening port:"):
                info["listen_port"] = line.split(":", 1)[1].strip()
            elif line.startswith("peer:"):
                current_peer = {
                    "public_key": line.split(":", 1)[1].strip(),
                    "endpoint": "",
                    "allowed_ips": "",
                    "handshake": "",
                    "transfer": ""
                }
                info["peers"].append(current_peer)
            elif current_peer:
                if line.startswith("endpoint:"):
                    current_peer["endpoint"] = line.split(":", 1)[1].strip()
                elif line.startswith("allowed ips:"):
                    current_peer["allowed_ips"] = line.split(":", 1)[1].strip()
                elif line.startswith("latest handshake:"):
                    current_peer["handshake"] = line.split(":", 1)[1].strip()
                elif line.startswith("transfer:"):
                    current_peer["transfer"] = line.split(":", 1)[1].strip()
        return info

    def parse_config(self, interface_name):
        """Liest eine WireGuard-Config und gibt die AllowedIPs zurück."""
        conf_path = os.path.join(WG_CONFIG_DIR, interface_name + ".conf")
        if not os.path.isfile(conf_path):
            return None

        config_data = {
            "interface": {},
            "peers": []
        }
        current_section = None
        current_peer = None

        try:
            with open(conf_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line == "[Interface]":
                        current_section = "interface"
                        current_peer = None
                    elif line == "[Peer]":
                        current_section = "peer"
                        current_peer = {}
                        config_data["peers"].append(current_peer)
                    elif "=" in line and current_section:
                        key, val = line.split("=", 1)
                        key = key.strip().lower().replace(" ", "_")
                        val = val.strip()
                        if current_section == "interface":
                            config_data["interface"][key] = val
                        elif current_peer is not None:
                            current_peer[key] = val
        except Exception as e:
            return None

        return config_data

    def get_endpoints(self, interface_name):
        """
        Liest alle Endpoint-Adressen aus einer .conf und löst Hostnames zu IPs auf.
        Gibt eine Liste von (ip, family) Tupeln zurück, wobei family 4 oder 6 ist.
        """
        cfg = self.parse_config(interface_name)
        if not cfg:
            return []
        results = []
        for peer in cfg.get("peers", []):
            ep = peer.get("endpoint", "")
            if not ep:
                continue
            # Endpoint-Format: "host:port" oder "[ipv6]:port"
            host = ep
            if ep.startswith("["):
                # IPv6 literal
                end = ep.find("]")
                if end > 0:
                    host = ep[1:end]
            else:
                # "host:port" - letzten : als Port-Separator
                idx = ep.rfind(":")
                if idx > 0:
                    host = ep[:idx]
            host = host.strip()
            if not host:
                continue
            # Auflösen (auch falls es schon eine IP ist)
            try:
                for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
                    ip = sockaddr[0]
                    if family == socket.AF_INET:
                        pair = (ip, 4)
                    elif family == socket.AF_INET6:
                        pair = (ip, 6)
                    else:
                        continue
                    if pair not in results:
                        results.append(pair)
            except Exception:
                pass
        return results

    def _get_default_route(self, family=4):
        """Ermittelt (gateway, dev) für die Default-Route der angegebenen Familie."""
        proto = "-4" if family == 4 else "-6"
        rc, out, _ = run_cmd("ip %s route show default" % proto)
        if rc != 0 or not out:
            return None, None
        m = re.search(r"default\s+via\s+(\S+)\s+dev\s+(\S+)", out)
        if m:
            return m.group(1), m.group(2)
        return None, None

    def _add_endpoint_routes(self, interface_name):
        """
        Setzt /32 bzw. /128 Host-Routen zu allen Endpoints über das echte
        Default-Gateway. Das verhindert den Routing-Loop, wenn die .conf
        AllowedIPs hat, die (versehentlich) den Endpoint mit abdecken -
        typisch für Mullvad-Split-Configs.
        """
        endpoints = self.get_endpoints(interface_name)
        if not endpoints:
            return

        added = []
        for ip, family in endpoints:
            gw, dev = self._get_default_route(family)
            if not gw or not dev:
                continue
            # Schon vorhandene Route für diese IP ggf. entfernen, um Konflikte zu vermeiden
            proto = "-4" if family == 4 else "-6"
            run_cmd("ip %s route del %s 2>/dev/null" % (proto, ip))
            rc, _, err = run_cmd("ip %s route add %s via %s dev %s" % (proto, ip, gw, dev))
            if rc == 0:
                added.append(ip)
            else:
                print("[WireGuard Simple] Konnte Endpoint-Route nicht setzen: %s (%s)" % (ip, err))

        if added:
            try:
                with open(ENDPOINT_ROUTES_FILE, "w") as f:
                    f.write("\n".join(added))
            except Exception:
                pass

    def _remove_endpoint_routes(self):
        """Entfernt alle zuvor gesetzten Endpoint-Host-Routen."""
        if not os.path.isfile(ENDPOINT_ROUTES_FILE):
            return
        try:
            with open(ENDPOINT_ROUTES_FILE, "r") as f:
                for line in f:
                    ip = line.strip()
                    if not ip:
                        continue
                    proto = "-6" if ":" in ip else "-4"
                    run_cmd("ip %s route del %s 2>/dev/null" % (proto, ip))
        except Exception:
            pass
        try:
            os.remove(ENDPOINT_ROUTES_FILE)
        except Exception:
            pass

    def get_allowed_ips(self, interface_name):
        """Gibt alle AllowedIPs aus einer Config zurück."""
        cfg = self.parse_config(interface_name)
        if not cfg:
            return []
        ips = []
        for peer in cfg.get("peers", []):
            allowed = peer.get("allowedips", peer.get("allowed_ips", ""))
            if allowed:
                for ip in allowed.split(","):
                    ip = ip.strip()
                    if ip:
                        ips.append(ip)
        return ips

    def connect(self, interface_name, callback=None):
        """Verbindet mit WireGuard Interface via wg-quick up."""
        conf_path = os.path.join(WG_CONFIG_DIR, interface_name + ".conf")
        if not os.path.isfile(conf_path):
            if callback:
                callback(False, "Config nicht gefunden: %s" % conf_path)
            return

        # Wenn das Interface bereits läuft (z.B. vom init.d-Script beim Boot
        # hochgezogen), NICHT erneut wg-quick up rufen - das würde fehlschlagen
        # ("already exists") und im on_result-Rollback die Endpoint-Host-Routen
        # zerstören, wodurch das Routing in eine Schleife läuft.
        active = self.get_active_interface()
        if active == interface_name:
            self._active_interface = interface_name
            if callback:
                callback(True, "Bereits verbunden")
            return True

        # Anderes Interface läuft - erst herunterfahren
        if active and active != interface_name:
            run_cmd("wg-quick down %s" % active, timeout=10)
            self._remove_endpoint_routes()

        # Endpoint-Host-Routen VOR wg-quick up setzen, damit die
        # WireGuard-Handshake-Pakete am Tunnel vorbeigeroutet werden.
        # Nötig für Configs wie Mullvad-Split-Tunnel, wo AllowedIPs
        # den eigenen Endpoint mit abdecken würde (Routing-Loop).
        self._add_endpoint_routes(interface_name)

        def on_result(rc, out, err):
            success = rc == 0
            msg = out if success else (err or out or "Unbekannter Fehler")
            if success:
                self._active_interface = interface_name
            else:
                self._active_interface = None
                # Rollback: Endpoint-Routen wieder entfernen wenn Verbindung scheitert
                self._remove_endpoint_routes()
            if callback:
                callback(success, msg)

        if callback:
            run_cmd_async("wg-quick up %s" % interface_name, on_result, timeout=20)
        else:
            rc, out, err = run_cmd("wg-quick up %s" % interface_name, timeout=20)
            if rc == 0:
                self._active_interface = interface_name
            else:
                self._remove_endpoint_routes()
            return rc == 0

    def disconnect(self, interface_name=None, callback=None):
        """Trennt die WireGuard-Verbindung via wg-quick down."""
        iface = interface_name or self.get_active_interface()
        if not iface:
            if callback:
                callback(True, "Nicht verbunden")
            return

        def on_result(rc, out, err):
            success = rc == 0
            msg = out if success else (err or out or "Unbekannter Fehler")
            if success:
                self._active_interface = None
            # Endpoint-Host-Routen in jedem Fall aufräumen
            self._remove_endpoint_routes()
            if callback:
                callback(success, msg)

        if callback:
            run_cmd_async("wg-quick down %s" % iface, on_result, timeout=15)
        else:
            rc, out, err = run_cmd("wg-quick down %s" % iface, timeout=15)
            self._remove_endpoint_routes()
            return rc == 0

    def check_wg_available(self):
        """Prüft ob wg und wg-quick verfügbar sind."""
        rc1, _, _ = run_cmd("which wg")
        rc2, _, _ = run_cmd("which wg-quick")
        rc3, _, _ = run_cmd("which ip")
        return rc1 == 0, rc2 == 0, rc3 == 0

    def check_kernel_module(self):
        """Prüft ob das WireGuard Kernel-Modul geladen ist."""
        rc, out, _ = run_cmd("lsmod | grep wireguard")
        if rc == 0 and "wireguard" in out:
            return True
        # Versuche Modul zu laden
        rc2, _, _ = run_cmd("modprobe wireguard")
        if rc2 == 0:
            return True
        # Moderne Kernel haben WireGuard eingebaut
        rc3, out3, _ = run_cmd("grep wireguard /proc/modules 2>/dev/null || cat /sys/module/wireguard/version 2>/dev/null")
        return rc3 == 0


# Singleton
wg_manager = WireGuardManager()
