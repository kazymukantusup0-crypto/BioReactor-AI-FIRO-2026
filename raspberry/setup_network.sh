#!/usr/bin/env bash
# BioReactor AI — network laptop <-> Pi WITHOUT internet (Raspberry Pi OS Bookworm, NetworkManager).
#
#   sudo ./setup_network.sh cable      MAIN: direct Ethernet cable, Pi = 192.168.50.2, laptop = 192.168.50.1
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
    nmcli con delete bioreactor-cable >/dev/null 2>&1 || true
    nmcli con add type ethernet ifname eth0 con-name bioreactor-cable \
      ipv4.method manual ipv4.addresses 192.168.50.2/24 ipv6.method disabled connection.autoconnect yes
    nmcli con up bioreactor-cable || echo "(the profile becomes active when the cable is plugged in)"
    echo "Pi: 192.168.50.2. On the laptop set the Ethernet adapter to 192.168.50.1 / 255.255.255.0 (docs/raspberry_setup.md)."
    echo "Laptop config (data/config/reactor_hardware.json): \"mode\": \"pi\", \"pi_url\": \"http://192.168.50.2:8780\""
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
