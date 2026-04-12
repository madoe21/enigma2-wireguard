#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.config import config
from Tools.Directories import SCOPE_PLUGINS, resolveFilename
from enigma import eTimer

from .wireguard import wg_manager, WG_CONFIG_DIR
from .routing import apply_domain_exceptions, remove_bypass_routes, parse_domain_list
from .leaktest import run_full_leak_test

SUPPORT_TEXT = "Buy me a coffee: https://buymeacoffee.com/madoe21"


# ─────────────────────────────────────────────────────────────────────────────
# Haupt-Screen
# ─────────────────────────────────────────────────────────────────────────────

class WireGuardMainScreen(Screen):
    """Hauptscreen - Verbindungsübersicht und schnelle Aktionen."""

    skin = """
    <screen name="WireGuardMainScreen" position="center,center" size="820,560" title="WireGuard VPN">
        <widget name="status_label" position="10,10" size="800,44"
            font="Regular;28" halign="center" valign="center"
            backgroundColor="#1a1a2e" foregroundColor="#00cc77"/>
        <widget name="interface_label" position="10,58" size="800,30"
            font="Regular;20" halign="center" valign="center"
            foregroundColor="#aaaaaa"/>
        <widget name="info_box" position="10,96" size="800,310"
            font="Regular;18" valign="top"
            backgroundColor="#12122a" foregroundColor="#dddddd"/>
        <widget name="hint_label" position="10,414" size="800,28"
            font="Regular;16" halign="center" valign="center"
            foregroundColor="#888888"/>
        <widget source="support" render="Label" position="10,448" size="800,22"
            font="Regular;16" halign="center" valign="center"
            foregroundColor="#555577"/>
        <ePixmap position="10,488" size="188,40" pixmap="skin_default/buttons/red.png" alphatest="on"/>
        <ePixmap position="214,488" size="188,40" pixmap="skin_default/buttons/green.png" alphatest="on"/>
        <ePixmap position="418,488" size="188,40" pixmap="skin_default/buttons/yellow.png" alphatest="on"/>
        <ePixmap position="622,488" size="188,40" pixmap="skin_default/buttons/blue.png" alphatest="on"/>
        <widget source="key_red" render="Label" position="10,488" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_green" render="Label" position="214,488" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_yellow" render="Label" position="418,488" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_blue" render="Label" position="622,488" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.title = "WireGuard VPN"

        self["status_label"] = Label("Status wird geladen...")
        self["interface_label"] = Label("")
        self["info_box"] = ScrollLabel("")
        self["hint_label"] = Label("")
        self["support"] = StaticText(SUPPORT_TEXT)

        self["key_red"] = StaticText("Trennen")
        self["key_green"] = StaticText("Verbinden")
        self["key_yellow"] = StaticText("Einstellungen")
        self["key_blue"] = StaticText("Info")

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions", "DirectionActions"], {
            "ok": self.connect_or_select,
            "cancel": self.close,
            "red": self.disconnect,
            "green": self.connect_or_select,
            "yellow": self.open_settings,
            "blue": self.open_info,
            "menu": self.open_leak_test,
            "up": self["info_box"].pageUp,
            "down": self["info_box"].pageDown,
            "left": self["info_box"].pageUp,
            "right": self["info_box"].pageDown,
        }, -1)

        self._refresh_timer = eTimer()
        self._refresh_timer.callback.append(self.refresh_status)

        self.onShow.append(self.refresh_status)
        self.onClose.append(self._refresh_timer.stop)

    def refresh_status(self):
        active = wg_manager.get_active_interface()
        connected = active is not None

        if connected:
            self["status_label"].setText("VERBUNDEN")
            self["interface_label"].setText("Interface: %s" % active)
            self["key_red"].setText("Trennen")
            self["key_green"].setText("Neu verbinden")

            # WireGuard-Status laden
            status = wg_manager.get_status(active)
            if status:
                lines = []
                for peer in status.get("peers", []):
                    if peer.get("endpoint"):
                        lines.append("Endpoint:    %s" % peer["endpoint"])
                    if peer.get("allowed_ips"):
                        lines.append("AllowedIPs:  %s" % peer["allowed_ips"])
                    if peer.get("handshake"):
                        lines.append("Handshake:   %s" % peer["handshake"])
                    if peer.get("transfer"):
                        lines.append("Transfer:    %s" % peer["transfer"])
                self["info_box"].setText("\n".join(lines) if lines else "Peer-Details nicht verfügbar")
            else:
                self["info_box"].setText("Status nicht verfügbar")

            domains_cfg = config.plugins.wireguardsimple.domain_exceptions.value
            if domains_cfg.strip():
                domains = parse_domain_list(domains_cfg)
                self["hint_label"].setText("Domain-Ausnahmen aktiv: %d Einträge  |  MENU = Leak-Test" % len(domains))
            else:
                self["hint_label"].setText("MENU = IP/DNS Leak-Test")

        else:
            # Nicht verbunden
            selected_cfg = config.plugins.wireguardsimple.config_file.value
            configs = wg_manager.get_configs()

            self["status_label"].setText("GETRENNT")
            self["key_red"].setText("---")
            self["key_green"].setText("Verbinden")

            if selected_cfg:
                self["interface_label"].setText("Config: %s" % selected_cfg)
                self["info_box"].setText(
                    "Konfiguration: %s\n\nDrücke Grün zum Verbinden.\n\nConfig-Pfad: %s/%s.conf" % (
                        selected_cfg, WG_CONFIG_DIR, selected_cfg
                    )
                )
            elif configs:
                self["interface_label"].setText("%d Config(s) verfügbar" % len(configs))
                self["info_box"].setText(
                    "Verfügbare Configs:\n%s\n\nDrücke Grün um eine auszuwählen und zu verbinden." % (
                        "\n".join("  • " + c for c in configs)
                    )
                )
            else:
                self["interface_label"].setText("Keine Configs gefunden")
                self["info_box"].setText(
                    "Keine WireGuard-Configs in %s gefunden.\n\n"
                    "Lege eine .conf Datei in diesem Verzeichnis ab\n"
                    "und drücke dann Grün.\n\n"
                    "Drücke Gelb für Einstellungen." % WG_CONFIG_DIR
                )
            self["hint_label"].setText("Drücke Gelb für Einstellungen  |  MENU = Leak-Test")

        # Timer für Auto-Refresh
        self._refresh_timer.stop()
        if connected:
            self._refresh_timer.start(30000, True)  # alle 30s

    def connect_or_select(self):
        """Verbindet oder zeigt Config-Auswahl."""
        selected_cfg = config.plugins.wireguardsimple.config_file.value
        configs = wg_manager.get_configs()

        if not configs:
            self.session.open(
                MessageBox,
                "Keine WireGuard-Configs in %s gefunden.\n\nBitte lege eine .conf Datei dort ab." % WG_CONFIG_DIR,
                MessageBox.TYPE_ERROR,
                timeout=8
            )
            return

        if len(configs) == 1:
            self._do_connect(configs[0])
        elif selected_cfg and selected_cfg in configs:
            self._do_connect(selected_cfg)
        else:
            # Auswahl-Liste anzeigen
            self.session.openWithCallback(
                self._config_selected,
                WireGuardConfigSelectScreen,
                configs
            )

    def _config_selected(self, interface_name):
        if interface_name:
            config.plugins.wireguardsimple.config_file.value = interface_name
            config.plugins.wireguardsimple.config_file.save()
            self._do_connect(interface_name)

    def _do_connect(self, interface_name):
        """Führt die Verbindung durch."""
        self["status_label"].setText("Verbinde mit %s..." % interface_name)
        self["info_box"].setText("WireGuard wird gestartet...\nBitte warten.")

        # Domain-Ausnahmen VOR dem VPN-Start setzen
        domains_cfg = config.plugins.wireguardsimple.domain_exceptions.value
        if domains_cfg.strip():
            self["hint_label"].setText("Löse Domain-Ausnahmen auf...")
            apply_domain_exceptions(domains_cfg, callback=lambda resolved, failed: self._on_exceptions_applied(interface_name, resolved, failed))
        else:
            self._start_wireguard(interface_name)

    def _on_exceptions_applied(self, interface_name, resolved, failed):
        info = ""
        if resolved:
            info = "Domain-Ausnahmen gesetzt:\n" + "\n".join(resolved[:5])
            if len(resolved) > 5:
                info += "\n... und %d weitere" % (len(resolved) - 5)
        if failed:
            info += "\nNicht auflösbar: " + ", ".join(failed)
        self["info_box"].setText(info + "\n\nStarte WireGuard...")
        self._start_wireguard(interface_name)

    def _start_wireguard(self, interface_name):
        wg_manager.connect(interface_name, callback=self._on_connect_result)

    def _on_connect_result(self, success, msg):
        if success:
            self["status_label"].setText("VERBUNDEN")
            self.refresh_status()
        else:
            self["status_label"].setText("Fehler beim Verbinden")
            self["info_box"].setText("Fehler:\n%s\n\nPrüfe die Config-Datei und ob wg-quick installiert ist." % msg)
            self["hint_label"].setText("Drücke Gelb für Einstellungen")

    def disconnect(self):
        """Trennt die Verbindung."""
        active = wg_manager.get_active_interface()
        if not active:
            return

        self["status_label"].setText("Trenne...")
        self["info_box"].setText("WireGuard wird beendet...")

        def on_disconnect(success, msg):
            remove_bypass_routes()  # Domain-Ausnahmen aufräumen
            if success:
                self["status_label"].setText("GETRENNT")
            else:
                self["status_label"].setText("Fehler beim Trennen")
            self.refresh_status()

        wg_manager.disconnect(active, callback=on_disconnect)

    def open_leak_test(self):
        self.session.open(WireGuardLeakTestScreen)

    def open_settings(self):
        self.session.openWithCallback(self.refresh_status, WireGuardSettingsScreen)

    def open_info(self):
        self.session.open(WireGuardInfoScreen)


# ─────────────────────────────────────────────────────────────────────────────
# Config-Auswahl Screen
# ─────────────────────────────────────────────────────────────────────────────

class WireGuardConfigSelectScreen(Screen):
    """Listet verfügbare WireGuard-Configs zur Auswahl."""

    skin = """
    <screen name="WireGuardConfigSelectScreen" position="center,center" size="620,440"
        title="WireGuard Config auswählen">
        <widget name="config_list" position="10,10" size="600,340"
            scrollbarMode="showOnDemand"
            font="Regular;22"/>
        <widget source="support" render="Label" position="10,360" size="600,22"
            font="Regular;16" halign="center" valign="center"
            foregroundColor="#555577"/>
        <ePixmap position="10,390" size="188,40" pixmap="skin_default/buttons/red.png" alphatest="on"/>
        <ePixmap position="422,390" size="188,40" pixmap="skin_default/buttons/green.png" alphatest="on"/>
        <widget source="key_red" render="Label" position="10,390" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_green" render="Label" position="422,390" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
    </screen>"""

    def __init__(self, session, configs):
        Screen.__init__(self, session)
        self.title = "WireGuard Config auswählen"

        list_entries = [(c, c) for c in configs]
        self["config_list"] = MenuList(list_entries)
        self["support"] = StaticText(SUPPORT_TEXT)
        self["key_red"] = StaticText("Abbrechen")
        self["key_green"] = StaticText("Auswählen")

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self._select,
            "cancel": self._cancel,
            "red": self._cancel,
            "green": self._select,
        }, -1)

    def _select(self):
        current = self["config_list"].getCurrent()
        if current:
            self.close(current[1])
        else:
            self.close(None)

    def _cancel(self):
        self.close(None)


# ─────────────────────────────────────────────────────────────────────────────
# Einstellungs-Screen
# ─────────────────────────────────────────────────────────────────────────────

class WireGuardSettingsScreen(Screen):
    """
    Einstellungen: Config-Auswahl, Autostart, Domain-Ausnahmen.
    Verwendet eine einfache MenuList statt ConfigList für bessere Kontrolle.
    """

    skin = """
    <screen name="WireGuardSettingsScreen" position="center,center" size="820,580"
        title="WireGuard Einstellungen">
        <widget name="menu" position="10,10" size="800,430"
            scrollbarMode="showOnDemand"
            font="Regular;20"/>
        <widget name="hint" position="10,450" size="800,28"
            font="Regular;17" halign="center" valign="center"
            foregroundColor="#888888"/>
        <widget source="support" render="Label" position="10,484" size="800,22"
            font="Regular;16" halign="center" valign="center"
            foregroundColor="#555577"/>
        <ePixmap position="10,516" size="188,40" pixmap="skin_default/buttons/red.png" alphatest="on"/>
        <ePixmap position="622,516" size="188,40" pixmap="skin_default/buttons/green.png" alphatest="on"/>
        <widget source="key_red" render="Label" position="10,516" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_green" render="Label" position="622,516" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
    </screen>"""

    # Menü-Einträge als Konstanten
    ITEM_CONFIG    = "config"
    ITEM_AUTOSTART = "autostart"
    ITEM_DOMAINS   = "domains"
    ITEM_REFRESH   = "refresh"

    def __init__(self, session):
        Screen.__init__(self, session)
        self.title = "WireGuard Einstellungen"

        self["menu"] = MenuList([])
        self["hint"] = Label("OK = ändern  |  Grün = speichern & schließen")
        self["support"] = StaticText(SUPPORT_TEXT)
        self["key_red"] = StaticText("Abbrechen")
        self["key_green"] = StaticText("Speichern")

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self._edit_current,
            "cancel": self.close,
            "red": self.close,
            "green": self._save,
        }, -1)

        self._rebuild_menu()

    def _rebuild_menu(self):
        """Baut die Menüliste mit aktuellen Werten auf."""
        configs = wg_manager.get_configs()
        selected = config.plugins.wireguardsimple.config_file.value or "(keine)"
        autostart_val = "Ja ✓" if config.plugins.wireguardsimple.autostart.value else "Nein"
        domains = config.plugins.wireguardsimple.domain_exceptions.value or "(keine)"
        # Domains kürzen für Anzeige
        if len(domains) > 40:
            domains = domains[:37] + "..."
        refresh = str(config.plugins.wireguardsimple.exception_refresh_interval.value) + " min"

        entries = [
            ("  Config-Datei:          %s" % selected,       self.ITEM_CONFIG),
            ("  Autostart beim Boot:   %s" % autostart_val,   self.ITEM_AUTOSTART),
            ("  Domain-Ausnahmen:      %s" % domains,         self.ITEM_DOMAINS),
            ("  Ausnahmen-Refresh:     %s" % refresh,         self.ITEM_REFRESH),
        ]

        # Autostart-Info-Zeile
        if config.plugins.wireguardsimple.autostart.value:
            autostart_config = config.plugins.wireguardsimple.config_file.value
            if not autostart_config and configs:
                autostart_config = configs[0] + " (erste verfügbare)"
            entries.insert(2, (
                "    → startet mit: %s" % (autostart_config or "keine Config gesetzt!"),
                None  # nicht editierbar
            ))

        self["menu"].setList(entries)

    def _edit_current(self):
        """Bearbeitet den aktuell markierten Eintrag."""
        current = self["menu"].getCurrent()
        if not current or current[1] is None:
            return

        item_id = current[1]

        if item_id == self.ITEM_CONFIG:
            configs = wg_manager.get_configs()
            if not configs:
                self.session.open(
                    MessageBox,
                    "Keine .conf Dateien in /etc/wireguard/ gefunden.\n\nBitte lege zuerst eine WireGuard-Config dort ab.",
                    MessageBox.TYPE_INFO,
                    timeout=6
                )
                return
            self.session.openWithCallback(
                self._on_config_selected,
                WireGuardConfigSelectScreen,
                configs
            )

        elif item_id == self.ITEM_AUTOSTART:
            # Toggle
            config.plugins.wireguardsimple.autostart.value = \
                not config.plugins.wireguardsimple.autostart.value
            self._rebuild_menu()

        elif item_id == self.ITEM_DOMAINS:
            self.session.openWithCallback(
                self._on_domains_entered,
                VirtualKeyBoard,
                title="Domain-Ausnahmen (kommagetrennt)",
                text=config.plugins.wireguardsimple.domain_exceptions.value
            )

        elif item_id == self.ITEM_REFRESH:
            # Einfache Auswahl aus vordefinierten Intervallen
            choices = [
                ("5 Minuten",   5),
                ("15 Minuten",  15),
                ("30 Minuten",  30),
                ("60 Minuten",  60),
                ("120 Minuten", 120),
                ("Nie (0)",     0),
            ]
            current_val = config.plugins.wireguardsimple.exception_refresh_interval.value
            choice_list = [(label, val) for label, val in choices]
            self.session.openWithCallback(
                self._on_refresh_selected,
                _SimpleChoiceScreen,
                "Refresh-Intervall",
                choice_list,
                current_val
            )

    def _on_config_selected(self, interface_name):
        if interface_name:
            config.plugins.wireguardsimple.config_file.value = interface_name
        self._rebuild_menu()

    def _on_domains_entered(self, text):
        if text is not None:
            config.plugins.wireguardsimple.domain_exceptions.value = text
        self._rebuild_menu()

    def _on_refresh_selected(self, value):
        if value is not None:
            config.plugins.wireguardsimple.exception_refresh_interval.value = value
        self._rebuild_menu()

    def _save(self):
        config.plugins.wireguardsimple.config_file.save()
        config.plugins.wireguardsimple.autostart.save()
        config.plugins.wireguardsimple.domain_exceptions.save()
        config.plugins.wireguardsimple.exception_refresh_interval.save()
        config.save()

        # Einstellungen in die Datei für das Init-Script schreiben
        # (damit wg-quick beim nächsten Boot VOR Enigma2 starten kann)
        from .wireguard import sync_settings_to_file
        sync_settings_to_file()

        # Feedback-Meldung mit Zusammenfassung
        selected = config.plugins.wireguardsimple.config_file.value or "(keine)"
        autostart_val = "Ja" if config.plugins.wireguardsimple.autostart.value else "Nein"
        msg = "Einstellungen gespeichert.\n\nConfig: %s\nAutostart: %s" % (selected, autostart_val)
        if config.plugins.wireguardsimple.autostart.value:
            msg += "\n\nBeim nächsten Systemstart wird WireGuard\nautomatisch verbunden."

        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=4)
        self.close()


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsdialog: einfache Auswahlliste
# ─────────────────────────────────────────────────────────────────────────────

class _SimpleChoiceScreen(Screen):
    """Generischer Auswahl-Dialog für eine Liste von (Label, Wert) Paaren."""

    skin = """
    <screen name="_SimpleChoiceScreen" position="center,center" size="420,380"
        title="Auswahl">
        <widget name="list" position="10,10" size="400,300"
            scrollbarMode="showOnDemand"
            font="Regular;22"/>
        <widget source="support" render="Label" position="10,318" size="400,22"
            font="Regular;15" halign="center" valign="center"
            foregroundColor="#555577"/>
        <ePixmap position="10,348" size="188,40" pixmap="skin_default/buttons/red.png" alphatest="on"/>
        <ePixmap position="222,348" size="188,40" pixmap="skin_default/buttons/green.png" alphatest="on"/>
        <widget source="key_red" render="Label" position="10,348" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_green" render="Label" position="222,348" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
    </screen>"""

    def __init__(self, session, title, choices, current_value=None):
        Screen.__init__(self, session)
        self.title = title

        self["list"] = MenuList(choices)
        self["support"] = StaticText(SUPPORT_TEXT)
        self["key_red"] = StaticText("Abbrechen")
        self["key_green"] = StaticText("OK")

        # Aktuellen Wert vorauswählen
        if current_value is not None:
            for i, (label, val) in enumerate(choices):
                if val == current_value:
                    self["list"].moveToIndex(i)
                    break

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self._select,
            "cancel": self._cancel,
            "red": self._cancel,
            "green": self._select,
        }, -1)

    def _select(self):
        current = self["list"].getCurrent()
        if current:
            self.close(current[1])
        else:
            self.close(None)

    def _cancel(self):
        self.close(None)


# ─────────────────────────────────────────────────────────────────────────────
# Leak-Test Screen
# ─────────────────────────────────────────────────────────────────────────────

class WireGuardLeakTestScreen(Screen):
    """Zeigt Mullvad-Verbindungsstatus, IP-Adresse, DNS-Server und Ping-Ergebnisse."""

    skin = """
    <screen name="WireGuardLeakTestScreen" position="center,center" size="820,580"
        title="Mullvad VPN - Verbindungstest">
        <widget name="status" position="10,10" size="800,34"
            font="Regular;22" halign="center" valign="center"
            foregroundColor="#ffaa00"/>
        <widget name="result_box" position="10,52" size="800,418"
            font="Regular;18" valign="top"
            backgroundColor="#0d0d1f" foregroundColor="#eeeeee"/>
        <widget source="support" render="Label" position="10,476" size="800,22"
            font="Regular;16" halign="center" valign="center"
            foregroundColor="#555577"/>
        <ePixmap position="10,508" size="188,40" pixmap="skin_default/buttons/red.png" alphatest="on"/>
        <ePixmap position="316,508" size="188,40" pixmap="skin_default/buttons/green.png" alphatest="on"/>
        <widget source="key_red" render="Label" position="10,508" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
        <widget source="key_green" render="Label" position="316,508" size="188,40"
            font="Regular;18" halign="center" valign="center" transparent="1"/>
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.title = "Mullvad VPN - Verbindungstest"

        self["status"] = Label("Tests werden durchgeführt...")
        self["result_box"] = ScrollLabel("Bitte warten, Tests laufen...\n\nDies kann einige Sekunden dauern.")
        self["support"] = StaticText(SUPPORT_TEXT)
        self["key_red"] = StaticText("Schließen")
        self["key_green"] = StaticText("Erneut testen")

        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "DirectionActions"],
            {
                "ok": self.close,
                "cancel": self.close,
                "red": self.close,
                "green": self._run_test,
                "up": self["result_box"].pageUp,
                "down": self["result_box"].pageDown,
                "left": self["result_box"].pageUp,
                "right": self["result_box"].pageDown,
            },
            -1,
        )

        self.onShow.append(self._run_test)

    def _run_test(self):
        self["status"].setText("Tests laufen... bitte warten")
        self["result_box"].setText("Ermittle IP-Adressen und teste DNS...\n\nDies kann 10-20 Sekunden dauern.")
        run_full_leak_test(self._on_results)

    def _on_results(self, results):
        """Verarbeitet und zeigt die Test-Ergebnisse."""
        lines = []
        connected = wg_manager.get_active_interface() is not None

        # Mullvad-Verbindungsstatus (primärer Check)
        mullvad = results.get("mullvad") or {}
        mullvad_connected = mullvad.get("connected", False)
        mullvad_ip = mullvad.get("ip")
        mullvad_msg = mullvad.get("message", "Nicht erreichbar")

        if mullvad_connected:
            lines.append(">>> VERBUNDEN mit Mullvad VPN <<<")
        else:
            lines.append(">>> NICHT über Mullvad verbunden <<<")
        lines.append(mullvad_msg)
        if mullvad_ip:
            lines.append("Externe IP: %s" % mullvad_ip)
        lines.append("")

        # WireGuard-Interface
        vpn_status = "WireGuard Interface: AKTIV" if connected else "WireGuard Interface: INAKTIV"
        lines.append(vpn_status)
        lines.append("")

        # IPv4
        ipv4 = results.get("ipv4", "Nicht ermittelbar")
        lines.append("IPv4-Adresse: %s" % ipv4)

        # IPv6
        ipv6 = results.get("ipv6", "Nicht ermittelbar")
        lines.append("IPv6-Adresse: %s" % ipv6)
        lines.append("")

        # DNS
        dns = results.get("dns", {})
        configured = dns.get("configured", [])
        actual = dns.get("actual_resolver", [])

        lines.append("-- DNS-Server --")
        if configured:
            lines.append("  Konfiguriert:  " + ", ".join(configured))
        else:
            lines.append("  Konfiguriert:  Keine gefunden")

        if actual:
            lines.append("  Tatsächlich:   " + ", ".join(actual))
            if configured and actual:
                configured_set = set(configured)
                actual_set = set(actual)
                if not configured_set.intersection(actual_set):
                    lines.append("  WARNUNG: DNS-Leak möglich! Anfragen gehen an anderen Server.")
                else:
                    lines.append("  OK: DNS-Server stimmt überein")
        else:
            lines.append("  Tatsächlich:   Nicht ermittelbar (dig/nslookup fehlt?)")
        lines.append("")

        # Ping-Tests
        lines.append("-- Ping-Tests --")
        ping_results = results.get("ping", [])
        for p in ping_results:
            icon = "OK" if p["success"] else "XX"
            rtt_str = ("%.1f ms" % p["rtt"]) if p.get("rtt") else "---"
            lines.append("  [%s] %-32s %s" % (icon, p["label"], rtt_str))
            if not p["success"] and p.get("msg") != "OK":
                lines.append("       -> %s" % p["msg"])

        # Gesamtbewertung
        lines.append("")
        lines.append("-- Bewertung --")
        if mullvad_connected:
            lines.append("OK  Traffic läuft über Mullvad VPN")
        elif connected:
            lines.append("WARN WireGuard aktiv, aber KEIN Mullvad-Traffic erkannt")
        else:
            lines.append("INFO Kein VPN aktiv - Daten zeigen echte IP")

        if connected:
            ipv6_ok = ipv6 and not any(x in ipv6 for x in ["nicht", "Nicht", "Block", "Fehler"])
            if "nicht konfiguriert" in ipv6.lower():
                lines.append("INFO IPv6 nicht konfiguriert (kein Leak-Risiko)")
            elif ipv6_ok:
                lines.append("OK  IPv6 läuft über VPN")
            else:
                lines.append("WARN IPv6 Leak möglich! Prüfe AllowedIPs in der Config.")

        result_text = "\n".join(lines)
        self["result_box"].setText(result_text)
        status_text = "Verbunden mit Mullvad" if mullvad_connected else "NICHT über Mullvad verbunden!"
        self["status"].setText(status_text)


# ─────────────────────────────────────────────────────────────────────────────
# Info-Screen
# ─────────────────────────────────────────────────────────────────────────────

class WireGuardInfoScreen(Screen):
    """Info-Screen mit Plugin-Beschreibung und Buy-Me-A-Coffee QR-Code."""

    skin = """
    <screen name="WireGuardInfoScreen" position="center,center" size="1000,620"
        title="WireGuard VPN - Info">
        <widget source="title" render="Label" position="20,10" size="960,40"
            font="Regular;34"/>
        <widget name="body" position="20,58" size="680,500"
            font="Regular;22" scrollbarMode="showOnDemand"/>
        <widget name="qr" position="720,80" size="256,256" alphatest="blend"/>
        <widget source="support" render="Label" position="20,564" size="960,24"
            font="Regular;18" foregroundColor="#555577"/>
        <ePixmap position="20,594" size="188,40" pixmap="skin_default/buttons/red.png" alphatest="on"/>
        <widget source="key_red" render="Label" position="20,594" size="188,40"
            font="Regular;22" halign="center" valign="center" transparent="1"/>
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self["title"] = StaticText("WireGuard VPN")
        self["key_red"] = StaticText("Schließen")
        self["support"] = StaticText(SUPPORT_TEXT)
        self["body"] = ScrollLabel(self._build_info_text())
        self["qr"] = Pixmap()
        self.onLayoutFinish.append(self._load_qr_png)

        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {
                "cancel": self.close,
                "ok": self.close,
                "red": self.close,
                "up": self["body"].pageUp,
                "down": self["body"].pageDown,
                "left": self["body"].pageUp,
                "right": self["body"].pageDown,
            },
            -1,
        )

    def _build_info_text(self):
        lines = [
            "WireGuard Simple Plugin",
            "Version 1.0",
            "",
            "Schlichtes Plugin zum Verwalten von",
            "WireGuard-Verbindungen via .conf Dateien.",
            "",
            "Features:",
            "- Verbindung per wg-quick up/down",
            "- Korrekte AllowedIPs-Behandlung",
            "- Policy-Routing via AllowedIPs",
            "- Domain-Ausnahmen (Bypass-Routen)",
            "- IP/DNS-Leak-Test",
            "- Autostart beim Systemstart",
            "",
            "WireGuard Configs ablegen unter:",
            "  /etc/wireguard/*.conf",
            "",
            "Alle Peers mit AllowedIPs werden",
            "korrekt per Policy-Routing behandelt.",
            "",
            "Ben\u00f6tigt: wireguard-tools",
            "",
            "Buy me a coffee: https://buymeacoffee.com/madoe21",
            "GitHub: https://github.com/madoe21/enigma2-wireguard",
        ]
        return "\n".join(lines)

    def _load_qr_png(self):
        candidate_paths = [
            resolveFilename(SCOPE_PLUGINS, "Extensions/WireGuard/res/qr_buymeacoffee.png"),
            os.path.join(os.path.dirname(__file__), "res", "qr_buymeacoffee.png"),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                try:
                    self["qr"].instance.setPixmapFromFile(path)
                    return
                except Exception:
                    pass
