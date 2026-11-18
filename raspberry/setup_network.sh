#!/usr/bin/env bash
# BioReactor AI — network laptop <-> Pi WITHOUT internet (NetworkManager: Raspberry Pi OS Bookworm, Debian 13 trixie).
#
#   sudo ./setup_network.sh cable      MAIN: direct Ethernet cable, Pi = 192.168.50.2, laptop gets 192.168.50.x by DHCP (no gateway)
#   sudo ./setup_network.sh hotspot [test]  own Wi-Fi "BioReactor-Pi" (WPA2, Pi = 10.42.0.1, digits-only password typed
#                                      in) + the service bioreactor-wifi: phone near -> stay on it; gone 45 s -> own Wi-Fi
#   sudo ./setup_network.sh hotspot-password | hotspot-test [minutes] | hotspot-remove
#   sudo ./setup_network.sh status
#
# The cable profile does not touch Wi-Fi; the Wi-Fi part never touches the cable.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo" >&2
  exit 1
fi
if ! command -v nmcli >/dev/null; then
  echo "nmcli not found: this script needs NetworkManager (Raspberry Pi OS Bookworm or newer)." >&2
  echo "Older systems: add to /etc/dhcpcd.conf:  interface eth0 / static ip_address=192.168.50.2/24" >&2
  exit 1
fi

case "${1:-}" in
  cable)
    # Pi = 192.168.50.2 and hands the laptop an address by DHCP (NetworkManager "shared" = its own dnsmasq).
    # NO default gateway and NO DNS are sent: the laptop keeps its internet on Wi-Fi, the cable is only for the Pi.
    # Wi-Fi of the Pi is not touched. The Debian 13 netplan profile "netplan-eth0" stays; ours wins by priority.
    # Safety: if the cable link is up, the change is rolled back after 3 min unless someone confirms over the cable:
    #   ssh bio@192.168.50.2 "touch /tmp/bioreactor-net-ok"
    mkdir -p /etc/NetworkManager/dnsmasq-shared.d
    cat > /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf <<'CONF'
# BioReactor AI: DHCP on the Pi cable gives only an address. Empty value = option is NOT sent.
dhcp-option=3
dhcp-option=6
CONF
    nmcli con delete bioreactor-cable >/dev/null 2>&1 || true
    nmcli con add type ethernet ifname eth0 con-name bioreactor-cable \
      ipv4.method shared ipv4.addresses 192.168.50.2/24 ipv4.never-default yes \
      ipv6.method disabled connection.autoconnect yes connection.autoconnect-priority 10
    if [[ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" == "1" ]]; then
      rm -f /tmp/bioreactor-net-ok
      systemctl stop bioreactor-net-rollback.timer >/dev/null 2>&1 || true
      systemd-run --quiet --on-active=180 --unit=bioreactor-net-rollback /bin/sh -c \
        'test -f /tmp/bioreactor-net-ok || { nmcli con delete bioreactor-cable; rm -f /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf; logger "bioreactor: cable profile rolled back (not confirmed)"; }'
      nmcli con up bioreactor-cable
      echo "Cable profile is up. NOT confirmed within 3 min -> rolled back automatically."
      echo "Confirm from the laptop over the cable:  ssh bio@192.168.50.2 \"touch /tmp/bioreactor-net-ok\""
    else
      echo "Cable not plugged in: profile saved, it comes up by itself when the cable is connected (no rollback timer)."
    fi
    echo "Pi: 192.168.50.2. Laptop: Ethernet adapter on automatic (DHCP) gets 192.168.50.x, no gateway, no DNS."
    echo "Laptop pi_url: http://192.168.50.2:8780.  Undo: sudo nmcli con delete bioreactor-cable"
    ;;
  hotspot|hotspot-password|hotspot-test)
    # hotspot [test]     install (or re-install) the own Wi-Fi «BioReactor-Pi» + the service bioreactor-wifi;
    #                    with «test»: right after it, test mode (below)
    # hotspot-password   only change the password
    # hotspot-test [min] test mode: the Pi leaves the phone network NOW and keeps BioReactor-Pi up for <min> minutes
    #                    (default 20), whatever happens; then the normal rules again. Use it with the cable connected.
    #
    # Windows-friendly settings: WPA2-PSK only (no WPA3/SAE), AES-CCMP only, PMF off, WPS off, 2.4 GHz, channel 6,
    # no power saving. Pi = 10.42.0.1, the laptop gets 10.42.0.x by DHCP with no gateway and no DNS.
    # The password: digits only, 8-63 — typed here, written only into the root-only NetworkManager profile on the Pi.
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    KEYFILE=/etc/NetworkManager/system-connections/bioreactor-hotspot.nmconnection

    ask_password() {
      while true; do
        read -rsp "New password for the Wi-Fi BioReactor-Pi (DIGITS ONLY, 8 or more): " PASSWORD; echo
        if [[ ! "$PASSWORD" =~ ^[0-9]{8,63}$ ]]; then echo "Digits only, at least 8. Again."; continue; fi
        read -rsp "The same digits again: " PASSWORD2; echo
        if [[ "$PASSWORD" != "$PASSWORD2" ]]; then echo "Not the same. Again."; continue; fi
        break
      done
    }
    store_password() {
      # through an environment variable, never on a command line that «ps» could show
      grep -v '^psk=' "$KEYFILE" | PSK="$PASSWORD" awk '{ print } /^\[wifi-security\]$/ { print "psk=" ENVIRON["PSK"] }' > "$KEYFILE.new"
      chmod 600 "$KEYFILE.new"
      mv "$KEYFILE.new" "$KEYFILE"
      unset PASSWORD PASSWORD2
      nmcli con reload
      if [[ -z "$(nmcli -s -g 802-11-wireless-security.psk con show bioreactor-hotspot 2>/dev/null)" ]]; then
        echo "The password was not stored in the profile — stop." >&2
        exit 1
      fi
    }
    start_test() {
      local minutes="${1:-20}"
      mkdir -p /run/bioreactor-wifi
      echo $(( $(date +%s) + minutes * 60 )) > /run/bioreactor-wifi/hold-until
      echo "Test mode: the Pi leaves the phone network and keeps BioReactor-Pi for ${minutes} min."
      nmcli --wait 30 con up bioreactor-hotspot >/dev/null && echo "BioReactor-Pi is ON (10.42.0.1). Connect the laptop to it now." \
        || { echo "BioReactor-Pi did NOT start: journalctl -u NetworkManager -n 40" >&2; exit 1; }
    }

    if [[ "$1" == "hotspot-test" ]]; then
      nmcli -t -f NAME con show | grep -qx bioreactor-hotspot || { echo "Not installed: sudo $0 hotspot" >&2; exit 1; }
      start_test "${2:-20}"
      exit 0
    fi
    if [[ "$1" == "hotspot-password" ]]; then
      [[ -f "$KEYFILE" ]] || { echo "Not installed: sudo $0 hotspot" >&2; exit 1; }
      ask_password
      store_password
      if nmcli -t -f NAME con show --active | grep -qx bioreactor-hotspot; then
        nmcli --wait 30 con up bioreactor-hotspot >/dev/null   # restart with the new password
      fi
      echo "Password changed."
      exit 0
    fi

    PHONE_CON="$(nmcli -t -f NAME,TYPE,AUTOCONNECT con show | awk -F: '$2=="802-11-wireless" && $3=="yes" && $1!="bioreactor-hotspot" {print $1; exit}')"
    if [[ -z "$PHONE_CON" ]]; then
      echo "No phone Wi-Fi profile with autoconnect found (nmcli con show)." >&2
      exit 1
    fi
    ask_password
    mkdir -p /etc/NetworkManager/dnsmasq-shared.d /etc/bioreactor-pi
    if [[ ! -f /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf ]]; then
      printf '# BioReactor AI: DHCP of the Pi gives only an address. Empty value = option is NOT sent.\ndhcp-option=3\ndhcp-option=6\n' \
        > /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf
    fi
    nmcli con delete bioreactor-hotspot >/dev/null 2>&1 || true
    nmcli con add type wifi ifname wlan0 con-name bioreactor-hotspot autoconnect no ssid BioReactor-Pi \
      802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 802-11-wireless.powersave 2 \
      ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv4.never-default yes ipv6.method disabled \
      wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
      wifi-sec.pmf disable wifi-sec.wps-method disabled >/dev/null
    if [[ ! -f "$KEYFILE" ]] || ! grep -q '^\[wifi-security\]' "$KEYFILE"; then
      echo "Profile file $KEYFILE not found — stop." >&2
      exit 1
    fi
    store_password
    printf 'PHONE_CON="%s"\nHOTSPOT_CON="bioreactor-hotspot"\nLOST_S=45\nRETRY_PHONE_S=300\n' "$PHONE_CON" > /etc/default/bioreactor-wifi
    install -m 755 "$HERE/wifi/bioreactor-wifi-watch.sh" /usr/local/sbin/bioreactor-wifi-watch
    install -m 755 "$HERE/wifi/bioreactor-wifi-rollback.sh" /usr/local/sbin/bioreactor-wifi-rollback
    install -m 644 "$HERE/wifi/bioreactor-wifi.service" /etc/systemd/system/bioreactor-wifi.service
    touch /etc/bioreactor-pi/hotspot-unconfirmed
    systemctl daemon-reload
    systemctl enable bioreactor-wifi.service >/dev/null
    systemctl restart bioreactor-wifi.service
    echo "Wi-Fi BioReactor-Pi installed (WPA2-PSK, AES, PMF off, 2.4 GHz ch 6, Pi = 10.42.0.1, no internet). Phone: ${PHONE_CON}."
    echo "Rules: phone near -> the Pi stays on it; phone gone 45 s -> BioReactor-Pi; no rollback while the cable is connected."
    if [[ "${2:-}" == "test" ]]; then
      start_test 20
    fi
    ;;
  hotspot-remove)
    systemctl disable --now bioreactor-wifi.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/bioreactor-wifi.service /usr/local/sbin/bioreactor-wifi-watch /usr/local/sbin/bioreactor-wifi-rollback \
      /etc/default/bioreactor-wifi /etc/bioreactor-pi/hotspot-unconfirmed /run/bioreactor-wifi/hold-until
    systemctl daemon-reload
    nmcli con delete bioreactor-hotspot >/dev/null 2>&1 || true
    echo "Own Wi-Fi removed; the phone network and the cable are unchanged."
    ;;
  status)
    nmcli -f NAME,DEVICE,STATE con show --active
    ip -4 -br addr
    systemctl is-active bioreactor-wifi 2>/dev/null | sed 's/^/bioreactor-wifi: /'
    [[ -f /etc/bioreactor-pi/hotspot-unconfirmed ]] && echo "own Wi-Fi: on probation (not confirmed yet)"
    nmcli -g 802-11-wireless.band,802-11-wireless.channel,802-11-wireless-security.key-mgmt,802-11-wireless-security.proto,802-11-wireless-security.pairwise,802-11-wireless-security.pmf \
      con show bioreactor-hotspot 2>/dev/null | tr '\n' ' ' | sed 's/^/own Wi-Fi settings (band ch key proto pairwise pmf): /'; echo
    /usr/sbin/iw dev wlan0 station dump 2>/dev/null | grep -c '^Station' | sed 's/^/devices on the own Wi-Fi: /'
    true
    ;;
  *)
    echo "usage: sudo $0 cable | hotspot [test] | hotspot-password | hotspot-test [minutes] | hotspot-remove | status" >&2
    exit 1
    ;;
esac
