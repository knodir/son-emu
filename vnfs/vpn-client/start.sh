#! /bin/bash

echo "Setting up VPN client VNF"

echo "configuring IPv4 and ARP forwarding ..."
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv4/conf/all/proxy_arp
echo "forwarding configuration complete"

echo "configuring iptables ..."
iptables -t nat -A POSTROUTING -o output -j MASQUERADE
iptables -A FORWARD -i output -o input-ids -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i input-ids -o output -j ACCEPT
echo "iptables configuration complete"

sleep 2

echo "starting openvpn to the server..."
sudo openvpn client.ovpn &
echo "sleep 30s to let openvpn finish config"
sleep 30
echo "execute ifconfig to see interface"
ifconfig
echo "execute route -n to see routing table"
route -n

echo "enable MASQUERADE for VPN ids-tun0 interface"
iptables -t nat -A POSTROUTING -o tun0 -j MASQUERADE
iptables -A FORWARD -i tun0 -o input-ids -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i input-ids -o tun0 -j ACCEPT

echo "enable MASQUERADE for VPN fw-tun0 interface"
iptables -t nat -A POSTROUTING -o tun0 -j MASQUERADE
iptables -A FORWARD -i tun0 -o input-fw -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i input-fw -o tun0 -j ACCEPT

echo "VPN client VNF ready."
