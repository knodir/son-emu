import time
import subprocess
import logging

from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint

from mininet.log import setLogLevel, info
from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.net import Containernet
from mininet.node import Controller, Docker, OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink, Link


# def prepareDC():
#     """ Prepares physical topology to place chains. """
#     net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
#     # add 3 data centers
#     client_dc = net.addDatacenter('client-dc')
#     chain_dc = net.addDatacenter('chain-dc')
#     server_dc = net.addDatacenter('server-dc')
# 
#     # connect data centers with switches
#     s1 = net.addSwitch('s1')
#     s2 = net.addSwitch('s2')
# 
#     # link data centers and switches
#     net.addLink(client_dc, s1)
#     net.addLink(s1, chain_dc)
#     net.addLink(chain_dc, s2)
#     net.addLink(s2, server_dc)
# 
#     # create REST API endpoint
#     api = RestApiEndpoint("0.0.0.0", 5001)
# 
#     # connect API endpoint to containernet
#     api.connectDCNetwork(net)
# 
#     # connect data centers to the endpoint
#     api.connectDatacenter(client_dc)
#     api.connectDatacenter(chain_dc)
#     api.connectDatacenter(server_dc)
# 
#     return (api, net, [client_dc, chain_dc, server_dc])


def nodeUpgrade():
    """ Implements node-upgrade scenario. TBD. """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add one data center
    dc = net.addDatacenter('dc1', metadata={'node-upgrade'})

    # create REST API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)

    # connect API endpoint to containernet
    api.connectDCNetwork(net)

    # connect data centers to the endpoint
    api.connectDatacenter(dc)

    # start API and containernet
    api.start()
    net.start()
 
    # create client with one interface
    client = dc.startCompute("client", image='knodir/client',
            network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = dc.startCompute("nat", image='knodir/nat',
            network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                {'id': 'output', 'ip': '10.0.1.4/24'}])
    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
    # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
    fw = dc.startCompute("fw", image='knodir/sonata-fw-vnf',
            network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                {'id': 'output-ids1', 'ip': '10.0.1.60/24'},
                {'id': 'output-ids2', 'ip': '10.0.1.61/24'},
                {'id': 'output-vpn', 'ip': '10.0.1.62/24'}])
    # create ids VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    ids1 = dc.startCompute("ids1", image='knodir/snort-trusty',
            network=[{'id': 'input', 'ip': '10.0.1.70/24'},
                {'id': 'output', 'ip': '10.0.1.80/24'}])
    ids2 = dc.startCompute("ids2", image='knodir/snort-xenial',
            network=[{'id': 'input', 'ip': '10.0.1.71/24'},
                {'id': 'output', 'ip': '10.0.1.81/24'}])
 
    # create VPN VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    vpn = dc.startCompute("vpn", image='knodir/vpn-client',
            network=[{'id': 'input-ids1', 'ip': '10.0.1.90/24'},
                {'id': 'input-ids2', 'ip': '10.0.1.91/24'},
                {'id': 'input-fw', 'ip': '10.0.1.92/24'},
                {'id': 'output', 'ip': '10.0.10.2/24'}])
    # create server VNF with one interface. Do not change assigned 10.0.10.10/24
    # address of the server. It is the address VPN clients use to connect to the
    # server and this address is hardcoded inside client.ovpn of the vpn-client
    # Docker image. We also remove the injected routing table entry for this
    # address. So, if you change this address make sure it is changed inside
    # client.ovpn file as well as subprocess mn.vpn route injection call below.
    server = dc.startCompute("server", image='knodir/vpn-server',
            network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])

    # execute /start.sh script inside firewall Docker image. It starts Ryu
    # controller and OVS with proper configuration.
    cmd = 'sudo docker exec -i mn.fw /bin/bash /root/start.sh &'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from fw start.sh start (0 is success)' % execStatus)
    print('> sleeping 10s to wait ryu controller initialize')
    time.sleep(10)
    print('< wait complete')
    print('fw start done')

    # execute /start.sh script inside ids image. It bridges input and output
    # interfaces with br0, and starts ids process listering on br0.
    cmd = 'sudo docker exec -i mn.ids1 /bin/bash -c "sh /start.sh"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from ids1 start.sh start (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.ids2 /bin/bash -c "sh /start.sh"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from ids2 start.sh start (0 is success)' % execStatus)

    # execute /start.sh script inside nat image. It attaches both input
    # and output interfaces to OVS bridge to enable packet forwarding.
    cmd = 'sudo docker exec -i mn.nat /bin/bash /start.sh'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from nat start.sh start (0 is success)' % execStatus)

    # chain 'client <-> nat <-> fw <-> ids <-> vpn <-> server'
    net.setChain('client', 'nat', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('nat', 'fw', 'output', 'input', bidirectional=True,
                 cmd='add-flow')

    net.setChain('fw', 'ids1', 'output-ids1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fw', 'ids2', 'output-ids2', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fw', 'vpn', 'output-vpn', 'input-fw', bidirectional=True,
                 cmd='add-flow')
 
    net.setChain('ids1', 'vpn', 'output', 'input-ids1', bidirectional=True,
                 cmd='add-flow')
    net.setChain('ids2', 'vpn', 'output', 'input-ids2', bidirectional=True,
                 cmd='add-flow')
    net.setChain('vpn', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    # start openvpn server and related services inside openvpn server
    cmd = 'sudo docker exec -i mn.server /bin/bash -c "ufw enable"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server ufw enable (0 is success)' % execStatus)

    # open iperf3 port (5201) on firewall (ufw)
    cmd = 'sudo docker exec -i mn.server /bin/bash -c "ufw allow 5201"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server ufw allow 5201 (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.server /bin/bash -c "ufw status"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server ufw status (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.server /bin/bash -c "service openvpn start"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server openvpn start (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.server /bin/bash -c "service openvpn status"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server openvpn status (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.server /bin/bash -c "service rsyslog start"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server rsyslog start (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.server /bin/bash -c "service rsyslog status"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from server rsyslog status (0 is success)' % execStatus)

    # execute /start.sh script inside VPN client to connect to VPN server.
    cmd = 'sudo docker exec -i mn.vpn /bin/bash /start.sh &'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from vpn start.sh start (0 is success)' % execStatus)
    print('> sleeping 60s to VPN client initialize...')
    time.sleep(60)
    print('< wait complete')
    print('VPN client VNF started')

    # manually add routing table entries on VNFs
    cmd = 'sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.0.0/16 dev intf1"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to client (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.client /bin/bash -c "route add -net 10.8.0.0/24 dev intf1"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to client (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.nat /bin/bash -c "route add -net 10.0.10.0/24 dev output"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to nat (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.nat /bin/bash -c "ip route add 10.8.0.0/24 dev output"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to nat (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.0.0/24 dev input-ids1"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to VPN for ids1 (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.0.0/24 dev input-ids2"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to VPN for ids2 (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.vpn /bin/bash -c "ip route del 10.0.10.10/32"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route del to VPN (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from route add to server (0 is success)' % execStatus)

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server], timeout=5))

    net.CLI()
    net.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    # logging.basicConfig(level=logging.INFO)

    nodeUpgrade()
    cleanup()