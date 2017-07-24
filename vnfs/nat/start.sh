#! /bin/bash

echo "Setting up NAT VNF"

echo "configuring IPv4 and ARP forwarding ..."
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv4/conf/all/proxy_arp
sysctl -p /etc/sysctl.conf
echo "forwarding configuration complete"

echo "configuring iptables ..."
iptables -t nat -A POSTROUTING -o output -j MASQUERADE
iptables -A FORWARD -i output -o input -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i input -o output -j ACCEPT
echo "iptables configuration complete"

echo "NAT VNF ready"
