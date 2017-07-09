import time
import subprocess
import logging

from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint

from mininet.log import setLogLevel, info
from mininet.node import RemoteController
from mininet.clean import cleanup
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM, UpbOverprovisioningCloudDcRM
import os


def prepareDC():
    """ Prepares physical topology to place chains. """

    # net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # # add one data center
    # dc = net.addDatacenter('dc1', metadata={'node-upgrade'})

    # # create REST API endpoint
    # api = RestApiEndpoint("0.0.0.0", 5001)

    # # connect API endpoint to containernet
    # api.connectDCNetwork(net)

    # # connect data centers to the endpoint
    # api.connectDatacenter(dc)

    # # start API and containernet
    # api.start()
    # net.start()

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add 3 data centers
    client_dc = net.addDatacenter('client-dc')
    chain_dc = net.addDatacenter('chain-dc')
    server_dc = net.addDatacenter('server-dc')

    # connect data centers with switches
    s1 = net.addSwitch('s1')
    # s2 = net.addSwitch('s2')

    # link data centers and switches
    net.addLink(client_dc, s1)
    net.addLink(chain_dc, s1)
    net.addLink(server_dc, s1)

    # create REST API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)

    # connect API endpoint to containernet
    api.connectDCNetwork(net)

    # connect data centers to the endpoint
    api.connectDatacenter(client_dc)
    api.connectDatacenter(chain_dc)
    api.connectDatacenter(server_dc)

    # start API and containernet
    api.start()
    net.start()

    return (net, api, [client_dc, chain_dc, server_dc])
    # return (net, dc, api)


def scaleOut():
    """ Implements node-upgrade scenario. TBD. """

    cmds = []
    net, api, dcs = prepareDC()
    off_cloud_c, cs1, off_cloud_s = dcs[0], dcs[1], dcs[2]
    fl = "large"

    # create client with one interface
    client = off_cloud_c.startCompute("client", image='knodir/client',
                                      flavor_name=fl,
                                      network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
    client.sendCmd('sudo ifconfig intf1 hw ether 00:00:00:00:00:1')
    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = cs1.startCompute("nat", image='knodir/nat',
                           flavor_name=fl,
                           network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                    {'id': 'output', 'ip': '10.0.1.4/24'}])
    nat.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:2')
    nat.sendCmd('sudo ifconfig output hw ether 00:00:00:00:00:3')

    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
    # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
    fw = cs1.startCompute("fw", image='knodir/sonata-fw-vnf',
                          flavor_name="xlarge",
                          network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                                   {'id': 'output-ids1', 'ip': '10.0.1.60/24'},
                                   # {'id': 'output-ids2', 'ip': '10.0.1.61/24'},
                                   {'id': 'output-vpn', 'ip': '10.0.1.62/24'}])
    fw.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:4')
    fw.sendCmd('sudo ifconfig output-ids1 hw ether 00:00:00:00:00:5')
    fw.sendCmd('sudo ifconfig output-vpn hw ether 00:00:00:00:00:6')

    # create ids VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    ids1 = cs1.startCompute("ids1", image='knodir/snort-trusty',
                            flavor_name=fl,
                            network=[{'id': 'input', 'ip': '10.0.1.70/24'},
                                     {'id': 'output', 'ip': '10.0.1.80/24'}])
    # ids2 = cs1.startCompute("ids2", image='knodir/snort-xenial',
    #                         flavor_name=fl,
    #                         network=[{'id': 'input', 'ip': '10.0.1.71/24'},
    #                                  {'id': 'output', 'ip': '10.0.1.81/24'}])
    ids1.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:7')
    ids1.sendCmd('sudo ifconfig output hw ether 00:00:00:00:00:8')
    # create VPN VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    vpn = cs1.startCompute("vpn", image='knodir/vpn-client',
                           flavor_name=fl,
                           network=[{'id': 'input-ids1', 'ip': '10.0.1.90/24'},
                                    # {'id': 'input-ids2', 'ip': '10.0.1.91/24'},
                                    {'id': 'input-fw', 'ip': '10.0.1.92/24'},
                                    {'id': 'output', 'ip': '10.0.10.2/24'}])
    vpn.sendCmd('sudo ifconfig input-ids1 hw ether 00:00:00:00:00:9')
    vpn.sendCmd('sudo ifconfig input-fw hw ether 00:00:00:00:00:10')
    vpn.sendCmd('sudo ifconfig output hw ether 00:00:00:00:00:11')
    # create server VNF with one interface. Do not change assigned 10.0.10.10/24
    # address of the server. It is the address VPN clients use to connect to the
    # server and this address is hardcoded inside client.ovpn of the vpn-client
    # Docker image. We also remove the injected routing table entry for this
    # address. So, if you change this address make sure it is changed inside
    # client.ovpn file as well as subprocess mn.vpn route injection call below.
    server = off_cloud_s.startCompute("server", image='knodir/vpn-server',
                                      flavor_name="small",
                                      network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])
    server.sendCmd('sudo ifconfig intf2 hw ether 00:00:00:00:00:12')
    # net.stop()
    # return

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

    # cmd = 'sudo docker exec -i mn.ids2 /bin/bash -c "sh /start.sh"'
    # execStatus = subprocess.call(cmd, shell=True)
    # print('returned %d from ids2 start.sh start (0 is success)' % execStatus)

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
    # net.setChain('fw', 'ids2', 'output-ids2', 'input', bidirectional=True,
    #              cmd='add-flow')
    net.setChain('fw', 'vpn', 'output-vpn', 'input-fw', bidirectional=True,
                 cmd='add-flow')

    net.setChain('ids1', 'vpn', 'output', 'input-ids1', bidirectional=True,
                 cmd='add-flow')
    # net.setChain('ids2', 'vpn', 'output', 'input-ids2', bidirectional=True,
    #              cmd='add-flow')
    net.setChain('vpn', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    # start openvpn server and related services inside openvpn server
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "ufw enable"')
    # open iperf3 port (5201) on firewall (ufw)
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "ufw allow 5201"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "ufw allow 5202"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "ufw status"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "service openvpn start"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "service openvpn status"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "service rsyslog start"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "service rsyslog status"')
    # execute /start.sh script inside VPN client to connect to VPN server.
    cmds.append('sudo docker exec -i mn.vpn /bin/bash /start.sh &')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    print('> sleeping 20s to VPN client initialize...')
    time.sleep(20)
    print('< wait complete')
    print('VPN client VNF started')

    # manually chain routing table entries on VNFs
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.0.0/16 dev intf1"')
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "route add -net 10.8.0.0/24 dev intf1"')
    cmds.append('sudo docker exec -i mn.nat /bin/bash -c "route add -net 10.0.10.0/24 dev output"')
    cmds.append('sudo docker exec -i mn.nat /bin/bash -c "ip route add 10.8.0.0/24 dev output"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.0.0/24 dev input-ids1"')
    # cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.0.0/24 dev input-ids2"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "ip route del 10.0.10.10/32"')
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"')

    cmds.append('sudo docker exec -i mn.client /bin/bash -c " ping -i 0.1 -c 10 10.0.10.10"')
    cmds.append('sudo docker exec -i mn.client /bin/bash -c " ping -i 0.1 -c 10 10.8.0.1"')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server], timeout=5))

    os.system('sudo docker cp ../traces/output.pcap mn.client:/')
    os.system('sudo docker cp ../traces/ftp.ready.pcap mn.client:/')
    net.CLI()
    net.stop()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    scaleOut()
    cleanup()
    os.system("sudo ../clean-stale.sh")
