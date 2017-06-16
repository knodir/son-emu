#!/bin/bash


echo "starting rsyslog, ufw, and openvpn..."
service rsyslog start
service rsyslog status
ufw enable
ufw status
service openvpn start
service openvpn status
echo "rsyslog, ufw, openvpn started."

echo "configuring IPv4 and ARP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv4/conf/all/proxy_arp
echo "forwarding configuration complete"

echo "execute route -n to see routing table"
route -n

echo 'VPN server VNF is ready.'
