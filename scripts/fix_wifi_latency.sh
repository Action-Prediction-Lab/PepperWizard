#!/bin/bash

# valid_bssid="AA:BB:CC:DD:EE:FF" # REPLACE THIS with your actual Router BSSID

function usage() {
    echo "Usage: sudo $0 [options]"
    echo "Options:"
    echo "  --lock <BSSID>   Lock WiFi to a specific BSSID to prevent roaming."
    echo "  --unlock         Remove BSSID lock (allow roaming)."
    echo "  --status         Show current power save and BSSID status."
    echo "  --fix            Disable Power Management (run this on boot)."
    exit 1
}

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit
fi

case "$1" in
    --fix)
        echo "Disabling WiFi Power Management..."
        nmcli connection modify id "PepperHotspot" 802-11-wireless.powersave 2
        iw dev wlan0 set power_save off
        echo "Power Management: OFF"
        ;;
    --lock)
        if [ -z "$2" ]; then
            echo "Error: BSSID required."
            echo "Try: sudo iwgetid -a -r"
            exit 1
        fi
        echo "Locking info BSSID: $2..."
        nmcli connection modify id "PepperHotspot" 802-11-wireless.bssid "$2"
        nmcli connection up id "PepperHotspot"
        ;;
    --unlock)
        echo "Unlocking BSSID..."
        nmcli connection modify id "PepperHotspot" 802-11-wireless.bssid ""
        nmcli connection up id "PepperHotspot"
        ;;
    --status)
        iw dev wlan0 get power_save
        nmcli -f 802-11-wireless.bssid connection show "PepperHotspot"
        ;;
    *)
        usage
        ;;
esac
