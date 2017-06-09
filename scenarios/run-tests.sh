#!/bin/sh
set -x
sudo tcpdump -i any host 10.0.0.2 -w testdump.pcap &
export tcpdump_id=$!
sudo python node-upgrade.py
sudo killall tcpdump
sudo ./clean-stale.sh
