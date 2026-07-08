# Codebase map (onboarding 2026-07-08)

**enigma2-wireguard** — Enigma2 (OpenATV 7.6) plugin: manage WireGuard VPN
tunnels on the receiver (up/down, config, leak test). Python. ~1800 LOC.

## Layout
- `src/WireGuard/plugin.py` — entry.
- `src/WireGuard/wireguard.py` (~423 LOC) — tunnel control: shells out to
  `wg`/`wg-quick`, parses status, manages configs. **Core control layer**
  (OS/root-level, not GUI-bound).
- `src/WireGuard/leaktest.py` (~263) — DNS/IP leak test.
- `src/WireGuard/screens.py` (~796) — enigma2 GUI.
- `src/init.d/` — boot autostart script. `res/`, `control/`, `build/`.

## Conventions
- Enigma2 Py3. Runs privileged shell commands — validate/escape all inputs
  (tunnel names, paths); never interpolate untrusted strings into shell.
- Tunnel control is OS-level; keep it independent of the GUI framework.

## Kodi portability: **monolithic — deferred (config schema tangled in)**
`wireguard.py` (~423 LOC) has **12 enigma2 refs**: it defines the enigma2
`config.plugins.wireguardsimple` ConfigSubsection INLINE and reads
`config.plugins...value` throughout the tunnel control. So it can't just be
moved — the portable subprocess logic (wg/wg-quick calls) must first be
**separated from the enigma2 config schema** (inject a settings object).
`leaktest.py` is already clean. NOT refactored in the 2026-07-08 Kodi pass
(unlike the other plugins) — this one needs a real decoupling of config vs.
control before a `core/` split. Follow-up.
