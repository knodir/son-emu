

def init_source(vnf_name):
    cmds = []
    # rewrite client VNF MAC addresses for tcpreplay
    cmds.append('sudo docker exec mn.%s ifconfig intf1 hw ether 00:00:00:00:00:01' % vnf_name)
    # manually chain routing table entries on VNFs
    cmds.append('sudo docker exec mn.%s route add -net 10.0.0.0/16 dev intf1' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.8.0.0/24 dev intf1' % vnf_name)
    return cmds


def init_nat(vnf_name):
    cmds = []
    # rewrite NAT VNF MAC addresses for tcpreplay
    cmds.append('sudo docker exec mn.%s ifconfig input hw ether 00:00:00:00:00:02' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.0.10.0/24 dev output' % vnf_name)
    cmds.append('sudo docker exec mn.%s ip route add 10.8.0.0/24 dev output' % vnf_name)
    cmds.append('sudo docker exec mn.%s ./start.sh' % vnf_name)
    return cmds


def init_fw(vnf_name):
    cmds = []
    cmds.append('sudo docker exec mn.%s ./start.sh' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.0.10.0/24 dev output-ids' % vnf_name)
    cmds.append('sudo docker exec mn.%s route del -net 10.0.1.0/24 dev output-ids' % vnf_name)
    cmds.append('sudo docker exec mn.%s route del -net 10.0.1.0/24 dev input' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.8.0.0/24 dev output-ids' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.0.0.0/24 dev input' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.0.1.0/26 dev input' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.0.1.0/24 dev output-ids' % vnf_name)
    return cmds


def init_ids(vnf_name):
    cmds = []
    cmds.append('sudo docker exec mn.%s sh ./start.sh' % vnf_name)
    return cmds


def init_vpn(vnf_name):
    cmds = []
    # execute /start.sh script inside VPN client to connect to VPN server.
    cmds.append('sudo docker exec mn.%s /bin/bash /start.sh &' % vnf_name)
    cmds.append('sudo docker exec mn.%s route add -net 10.0.0.0/24 input-ids' % vnf_name)
    # cmds.append('sudo docker exec mn.%s /echo 1 > /proc/sys/net/ipv4/ip_forward"' % vnf_name)
    # cmds.append('sudo docker exec mn.%s echo 1 > /proc/sys/net/ipv4/conf/all/proxy_arp"' % vnf_name)
    cmds.append('sudo docker exec mn.%s /bin/bash -c "sleep 5 && route del 10.0.10.10"' % vnf_name)
    return cmds


def init_sink(vnf_name):
    cmds = []
    cmds.append('sudo docker exec mn.%s route add -net 10.0.0.0/8 dev intf2' % vnf_name)
    # start openvpn server and related services inside openvpn server
    cmds.append('sudo docker exec mn.%s ufw enable' % vnf_name)
    # open iperf3 port (5201) on firewall (ufw)
    cmds.append('sudo docker exec mn.%s ufw allow 5201' % vnf_name)
    cmds.append('sudo docker exec mn.%s ufw status' % vnf_name)
    cmds.append('sudo docker exec mn.%s service openvpn start' % vnf_name)
    cmds.append('sudo docker exec mn.%s service openvpn status' % vnf_name)
    cmds.append('sudo docker exec mn.%s service rsyslog start' % vnf_name)
    cmds.append('sudo docker exec mn.%s service rsyslog status' % vnf_name)
    return cmds
