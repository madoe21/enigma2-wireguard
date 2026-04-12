#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from Plugins.Plugin import PluginDescriptor
from Components.config import config
from Tools.Directories import SCOPE_PLUGINS, resolveFilename

from . import _
from .screens import WireGuardMainScreen

# True: load aspect-ratio-specific transparent icon files.
# False: always use plugin.png.
USE_ASPECT_ICON_VARIANTS = True


def main(session, **kwargs):
    session.open(WireGuardMainScreen)


def _icon_file_for_aspect_ratio():
    try:
        from enigma import getDesktop

        size = getDesktop(0).size()
        width = int(size.width())
        height = int(size.height())
        if height > 0:
            ratio = float(width) / float(height)
            if ratio < 1.5:
                return "plugin_4x3.png"
            if ratio < 1.7:
                return "plugin_16x10.png"
            return "plugin_16x9.png"
    except Exception:
        pass
    return "plugin_16x9.png"


def _resolve_plugin_icon_path():
    if not USE_ASPECT_ICON_VARIANTS:
        return resolveFilename(SCOPE_PLUGINS, "Extensions/WireGuard/res/plugin.png")

    icon_name = _icon_file_for_aspect_ratio()
    icon_path = resolveFilename(SCOPE_PLUGINS, "Extensions/WireGuard/res/%s" % icon_name)
    if os.path.exists(icon_path):
        return icon_path
    return resolveFilename(SCOPE_PLUGINS, "Extensions/WireGuard/res/plugin.png")


def autostart(reason, **kwargs):
    from .wireguard import wg_manager
    from .routing import apply_domain_exceptions, remove_bypass_routes

    if reason == 0:
        # Enigma2 startet – VPN verbinden falls Autostart aktiv
        if config.plugins.wireguardsimple.autostart.value:
            interface = config.plugins.wireguardsimple.config_file.value
            if not interface:
                # Erste verfügbare Config nehmen
                configs = wg_manager.get_configs()
                if configs:
                    interface = configs[0]

            if interface:
                # Domain-Ausnahmen setzen, dann verbinden
                domains_cfg = config.plugins.wireguardsimple.domain_exceptions.value
                if domains_cfg.strip():
                    apply_domain_exceptions(domains_cfg)

                def on_connect(success, msg):
                    if success:
                        print("[WireGuard Simple] Autostart: verbunden mit", interface)
                    else:
                        print("[WireGuard Simple] Autostart fehlgeschlagen:", msg)

                wg_manager.connect(interface, callback=on_connect)

    elif reason == 1:
        active = wg_manager.get_active_interface()
        if active:
            print("[WireGuard Simple] Shutdown: trenne", active)
            remove_bypass_routes()
            wg_manager.disconnect(active)


def Plugins(**kwargs):
    plugin_icon = _resolve_plugin_icon_path()
    return [
        PluginDescriptor(
            name=_("WireGuard VPN"),
            description=_("WireGuard VPN - Config-Datei basiert"),
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon=plugin_icon,
            fnc=main,
        ),
        PluginDescriptor(
            name=_("WireGuard VPN"),
            description=_("WireGuard VPN - Config-Datei basiert"),
            where=PluginDescriptor.WHERE_EXTENSIONSMENU,
            fnc=main,
        ),
        PluginDescriptor(
            name=_("WireGuard VPN"),
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=autostart,
        ),
    ]
