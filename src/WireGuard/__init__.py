# -*- coding: utf-8 -*-
from __future__ import absolute_import

import gettext

from Components.Language import language
from Tools.Directories import SCOPE_PLUGINS, resolveFilename

PLUGIN_DOMAIN = "WireGuard"
PLUGIN_PATH = "Extensions/WireGuard/locale"

_DE_FALLBACK = {
    "WireGuard VPN": "WireGuard VPN",
    "WireGuard VPN - Config-Datei basiert": "WireGuard VPN - Config-Datei basiert",
    "WireGuard VPN - Info": "WireGuard VPN - Info",
    "Information": "Information",
    "Settings": "Einstellungen",
    "Close": "Schließen",
    "Save": "Speichern",
    "Cancel": "Abbrechen",
    "Connect": "Verbinden",
    "Disconnect": "Trennen",
    "IP/DNS Leak Test": "IP/DNS Leak Test",
    "Select config": "Config auswählen",
    "Back": "Zurück",
    "OK": "OK",
}


def localeInit():
    gettext.bindtextdomain(PLUGIN_DOMAIN, resolveFilename(SCOPE_PLUGINS, PLUGIN_PATH))
    try:
        gettext.bind_textdomain_codeset(PLUGIN_DOMAIN, "UTF-8")
    except Exception:
        pass


def _(txt):
    translated = gettext.dgettext(PLUGIN_DOMAIN, txt)
    if translated != txt:
        return translated
    try:
        lang = language.getLanguage()[:2]
    except Exception:
        lang = "en"
    if lang == "de":
        return _DE_FALLBACK.get(txt, txt)
    return txt


localeInit()
try:
    language.addCallback(localeInit)
except Exception:
    pass
