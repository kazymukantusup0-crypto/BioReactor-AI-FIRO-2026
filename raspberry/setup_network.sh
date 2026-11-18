#!/usr/bin/env bash
# BioReactor AI — network laptop <-> Pi WITHOUT internet (NetworkManager: Raspberry Pi OS Bookworm, Debian 13 trixie).
#
#   sudo ./setup_network.sh cable      MAIN: direct Ethernet cable, Pi = 192.168.50.2, laptop gets 192.168.50.x by DHCP (no gateway)
#   sudo ./setup_network.sh hotspot    BACKUP: the Pi makes its own Wi-Fi "BioReactor-Pi", Pi = 10.42.0.1
#   sudo ./setup_network.sh status
#
# The cable profile does not touch Wi-Fi. The hotspot takes over wlan0 (the Pi leaves your Wi-Fi network);
# to go back: sudo nmcli con down bioreactor-hotspot
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
  hotspot)
    PASSWORD="${2:-bioreactor2026}"
    nmcli con delete bioreactor-hotspot >/dev/null 2>&1 || true
    nmcli con add type wifi ifname wlan0 con-name bioreactor-hotspot autoconnect no ssid BioReactor-Pi \
      802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"
    nmcli con up bioreactor-hotspot
    echo "Wi-Fi 'BioReactor-Pi', password '$PASSWORD'. Pi: 10.42.0.1 -> pi_url \"http://10.42.0.1:8780\""
    ;;
  status)
    nmcli -f NAME,DEVICE,STATE con show --active
    ip -4 -br addr
    ;;
  *)
    echo "usage: sudo $0 cable | hotspot [password] | status" >&2
    exit 1
    ;;
esac
