#!/bin/sh
# Tests for src/WireGuard/resolvconf-shim.
#
# The shim is what decides whether the network's DNS survives a tunnel: on "up"
# it replaces /etc/resolv.conf with the tunnel's nameservers, on "down" it has
# to put the original back. These tests pin the cases that used to leave the VPN
# DNS behind for good.
#
# The shim is copied into a sandbox with its three absolute paths rewritten, so
# the real /etc/resolv.conf is never touched.
#
# Usage: sh tests/test-resolvconf-shim.sh

set -u

SHIM_SRC="$(dirname "$0")/../src/WireGuard/resolvconf-shim"
SANDBOX="$(mktemp -d)"
SHIM="$SANDBOX/shim"
RESOLV="$SANDBOX/etc/resolv.conf"
BACKUP="$SANDBOX/etc/enigma2/wg-simple-resolv.conf.backup"
BACKUP_LEGACY="$SANDBOX/tmp/wg-simple-resolv.conf.backup"

SYSTEM_DNS="nameserver 192.168.1.1"
VPN_DNS="nameserver 10.64.0.1"

failures=0

cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

mkdir -p "$SANDBOX/etc/enigma2" "$SANDBOX/tmp"
sed -e "s|^RESOLV=/etc/resolv.conf|RESOLV=$RESOLV|" \
    -e "s|^BACKUP=/etc/enigma2/|BACKUP=$SANDBOX/etc/enigma2/|" \
    -e "s|^BACKUP_LEGACY=/tmp/|BACKUP_LEGACY=$SANDBOX/tmp/|" \
    "$SHIM_SRC" > "$SHIM"

shim() { sh "$SHIM" "$@"; }

# up <dns-line> - what wg-quick does on "wg-quick up"
up() { printf '%s\n' "$1" | shim -a wg0 -m 0 -x; }

# down - what wg-quick does on "wg-quick down"
down() { shim -d wg0; }

reset_state() {
    printf '%s\n' "$SYSTEM_DNS" > "$RESOLV"
    rm -f "$BACKUP" "$BACKUP_LEGACY"
}

check() {
    name="$1"
    expected="$2"
    actual="$(cat "$RESOLV" 2>/dev/null)"
    if [ "$actual" = "$expected" ]; then
        echo "ok   - $name"
    else
        echo "FAIL - $name"
        echo "       expected: [$expected]"
        echo "       actual:   [$actual]"
        failures=$((failures + 1))
    fi
}

check_no_vpn_dns() {
    name="$1"
    if grep -q "10.64.0" "$RESOLV" 2>/dev/null; then
        echo "FAIL - $name (VPN DNS still present)"
        failures=$((failures + 1))
    else
        echo "ok   - $name"
    fi
}

# --- up replaces the system DNS and marks the file as ours ----------------
reset_state
up "$VPN_DNS"
if head -n 1 "$RESOLV" | grep -q '^# WG_SIMPLE_DNS wg0$' && grep -q "^$VPN_DNS$" "$RESOLV"; then
    echo "ok   - up writes marker + tunnel DNS"
else
    echo "FAIL - up writes marker + tunnel DNS"
    failures=$((failures + 1))
fi

# --- down restores the system DNS -----------------------------------------
down
check "down restores the system DNS" "$SYSTEM_DNS"

# --- down leaves no backup behind -----------------------------------------
if [ -f "$BACKUP" ]; then
    echo "FAIL - down consumes the backup"
    failures=$((failures + 1))
else
    echo "ok   - down consumes the backup"
fi

# --- backup lost (reboot wiped /tmp, or never written) --------------------
# Regression: the old shim silently did nothing here, so the tunnel's DNS
# stayed in the network settings forever.
reset_state
up "$VPN_DNS"
rm -f "$BACKUP"
down
check_no_vpn_dns "down without backup still drops the tunnel DNS"

# --- two ups in a row (a down that never ran) -----------------------------
# Regression: the old shim backed up whatever was there, so the second up
# stored the tunnel's own DNS as the "system" backup.
reset_state
up "$VPN_DNS"
up "nameserver 10.64.0.2"
check_backup="$(cat "$BACKUP" 2>/dev/null)"
if [ "$check_backup" = "$SYSTEM_DNS" ]; then
    echo "ok   - second up keeps the original backup"
else
    echo "FAIL - second up keeps the original backup"
    echo "       expected: [$SYSTEM_DNS]"
    echo "       actual:   [$check_backup]"
    failures=$((failures + 1))
fi
down
check "down after two ups restores the system DNS" "$SYSTEM_DNS"

# --- a backup written by the old shim in /tmp is still honoured ------------
reset_state
printf '# WG_SIMPLE_DNS wg0\n%s\n' "$VPN_DNS" > "$RESOLV"
printf 'nameserver 192.168.178.1\n' > "$BACKUP_LEGACY"
down
check "legacy /tmp backup is migrated" "nameserver 192.168.178.1"

# --- the private restore entry point is a no-op on a system resolv.conf ---
reset_state
shim --wg-simple-restore
check "--wg-simple-restore leaves a system resolv.conf alone" "$SYSTEM_DNS"

# --- ...but cleans up ours ------------------------------------------------
reset_state
up "$VPN_DNS"
shim --wg-simple-restore
check "--wg-simple-restore undoes the tunnel DNS" "$SYSTEM_DNS"

# --- unknown arguments must never break wg-quick --------------------------
if shim --some-unknown-flag && shim -l; then
    echo "ok   - unknown/query invocations exit 0"
else
    echo "FAIL - unknown/query invocations exit 0"
    failures=$((failures + 1))
fi

echo
if [ "$failures" -eq 0 ]; then
    echo "All resolvconf-shim tests passed."
    exit 0
fi
echo "$failures resolvconf-shim test(s) failed."
exit 1
