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

iptables -t nat -A PREROUTING -j DNAT --to-destination 192.168.12.77:80
iptables -t nat -A POSTROUTING -p tcp -d 192.168.12.77 --dport 80 -j SNAT --to-source 192.168.12.87

iptables -t nat -A POSTROUTING -o output-ids -j MASQUERADE
iptables -A FORWARD -i input -o output-ids -j ACCEPT