#!/bin/sh
# 53-bg-clock — start the hero-banner wallpaper generator at boot
# (webosbrew init.d runs scripts in filename order, after 52-home-overlay)
pkill -f '[b]g-generator' 2>/dev/null
sleep 1
nohup python3 /media/developer/apps/usr/palm/applications/tld.my.customhome/bg-generator.py >/dev/null 2>&1 &
echo "bg-generator started"
