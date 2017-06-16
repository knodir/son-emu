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


def basicTest():
    """ This basic test creates one data center and two VNFs with default
    ubuntu:xenial image, and checks if VNFs can ping each other. """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add one data center
    dc = net.addDatacenter('dc1', metadata={'node-upgrade'})
    # connect data center to API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)
    # connect DC to the network
    api.connectDCNetwork(net)
    # connect DC to the endpoint
    api.connectDatacenter(dc)

    print(net)
    print(api)

    # start API endpoint and network
    api.start()
    net.start()

    # create two VNFs
    vnf1 = dc.startCompute("vnf1", network=[{'id': 'intf1', 'ip': '10.0.10.1/24'}])
    vnf2 = dc.startCompute("vnf2", network=[{'id': 'intf2', 'ip': '10.0.10.2/24'}])
    print('ping vnfs before explicit chaining: %s' % net.ping([vnf1, vnf2]))

    # explcitly chain two VNFs
    net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=1)
    print('ping vnfs after explicit chaining: %s' % net.ping([vnf1, vnf2]))

    # prompt containernet CLI for further debugging
    net.CLI()
    # exit containernet when user types 'exit'
    net.stop()


def runIDSOnly():
    """ Put IDS between client and server to test its basic functionality. All
    VNFs reside on a single DC. """

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
    client = dc.startCompute("client",
                             network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])

    # create snort VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'server' VNF.
    snort = dc.startCompute("snort", image='sonatanfv/sonata-snort-ids-vnf',
                            network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                     {'id': 'output', 'ip': '10.0.0.4/24'}])

    # create server VNF with one interface
    server = dc.startCompute("server",
                             network=[{'id': 'intf2', 'ip': '10.0.0.5/24'}])
    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # execute /start.sh script inside snort image. It bridges input and output
    # interfaces with br0, and starts snort process listering on br0.
    print(subprocess.call('sudo docker exec -i mn.snort /bin/bash -c "sh /start.sh"', shell=True))
    print('snort start done')

    # chain 'client -> snort -> server'
    net.setChain('client', 'snort', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('snort', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # we currently do not need this
    net.CLI()
    net.stop()


def runFirewallOnly():
    """ Put Firewall between client and server to test its basic functionality.
    All VNFs reside on a single DC. """

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
    client = dc.startCompute("client",
                             network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])

    # create Firewall VNF with two interfaces. 'input' interface for 'client'
    # and 'output' interface for the 'server' VNF.
    fw = dc.startCompute("fw", image='knodir/sonata-fw-vnf',
                         network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                  {'id': 'output', 'ip': '10.0.0.4/24'}])

    # create server VNF with one interface
    server = dc.startCompute("server",
                             network=[{'id': 'intf2', 'ip': '10.0.0.5/24'}])
    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # execute /start.sh script inside firewall Docker image. It start Ryu
    # controller and OVS with proper configuration.
    print(subprocess.call('sudo docker exec -i mn.fw /bin/bash /root/start.sh &',
                          shell=True))
    print('fw start done')

    print('> sleeping 10s to wait ryu controller initialize')
    time.sleep(10)
    print('< wait complete')

    # chain 'client -> fw -> server'
    net.setChain('client', 'fw', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fw', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    net.CLI()
    net.stop()


def runDummyForwarderOnly():
    """ Put Dummy-Forwarder between client and server to check if packets sent
    by client passed through dummy-forwarder VNF and reach the server VNF. Here,
    each VNF is on a separate data center connected with a switch. """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add 3 data centers
    client_dc = net.addDatacenter('client-dc')
    chain_dc = net.addDatacenter('chain-dc')
    server_dc = net.addDatacenter('server-dc')

    # connect data centers with switches
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    # link data centers and switches
    net.addLink(client_dc, s1)
    net.addLink(s1, chain_dc)
    net.addLink(chain_dc, s2)
    net.addLink(s2, server_dc)

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

    # create client with one interface
    client = client_dc.startCompute("client",
                                    network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])

    # create dummy-forwarder (fwdr) VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    fwdr = chain_dc.startCompute("fwdr", image='knodir/dummy-forwarder',
                                 network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                          {'id': 'output', 'ip': '10.0.0.4/24'}])

    # create server VNF with one interface
    server = server_dc.startCompute("server",
                                    network=[{'id': 'intf2', 'ip': '10.0.0.10/24'}])

    # execute /start.sh script inside dummy-forwarder image. It bridges input
    # and output interfaces with br0 to enable packet forwarding.
    print(subprocess.call(
        'sudo docker exec -i mn.fwdr /bin/bash -c "sh /start.sh"', shell=True))
    print('dummy-forwarder VNF started')
    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # chain 'client -> dummy-forwarder -> server'
    net.setChain('client', 'fwdr', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fwdr', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # we currently do not need this
    net.CLI()
    net.stop()


def runDummyForwarderOVSOnly():
    """ This is the same example as above DummyForwarder, except here we bridge
    input and output interfaces with OVS instead of Linux bridges. """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add 3 data centers
    client_dc = net.addDatacenter('client-dc')
    chain_dc = net.addDatacenter('chain-dc')
    server_dc = net.addDatacenter('server-dc')

    # connect data centers with switches
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    # link data centers and switches
    net.addLink(client_dc, s1)
    net.addLink(s1, chain_dc)
    net.addLink(chain_dc, s2)
    net.addLink(s2, server_dc)

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

    # create client with one interface
    client = client_dc.startCompute("client",
                                    network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])

    # create VNF with two interfaces. Its 'input' interface faces the client and
    # output interface the server VNF.
    fwdr = chain_dc.startCompute("fwdr", image='knodir/dummy-forwarder-ovs',
                                 network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                          {'id': 'output', 'ip': '10.0.10.4/24'}])

    # create server VNF with one interface
    server = server_dc.startCompute("server",
                                    network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])

    print(subprocess.call(
        'sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.10.0/24 dev intf1"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"', shell=True))

    # execute /start.sh script inside forwarder image. It attaches both input
    # and output interfaces to OVS bridge to enable packet forwarding.
    print(subprocess.call('sudo docker exec -i mn.fwdr /bin/bash /start.sh',
                          shell=True))
    print('Forwarder VNF started')
    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # chain 'client -> forwarder -> server'
    net.setChain('client', 'fwdr', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fwdr', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    net.CLI()
    net.stop()


def runNATOnly():
    """ Put NAT between client and server to check if packets sent
    by client pass through NAT and reach the server. Here, each VNF is on a
    separate data center connected with a switch. """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add 3 data centers
    client_dc = net.addDatacenter('client-dc')
    chain_dc = net.addDatacenter('chain-dc')
    server_dc = net.addDatacenter('server-dc')

    # connect data centers with switches
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    # link data centers and switches
    net.addLink(client_dc, s1)
    net.addLink(s1, chain_dc)
    net.addLink(chain_dc, s2)
    net.addLink(s2, server_dc)

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

    # create client with one interface
    client = client_dc.startCompute("client",
                                    network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])

    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = chain_dc.startCompute("nat", image='knodir/nat',
                                network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                         {'id': 'output', 'ip': '10.0.10.4/24'}])

    # create server VNF with one interface
    server = server_dc.startCompute("server",
                                    network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])

    # add routing table entries on client and server
    print(subprocess.call(
        'sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.10.0/24 dev intf1"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"', shell=True))

    print(subprocess.call('sudo docker exec -i mn.nat /bin/bash /start.sh',
                          shell=True))

   # chain 'client -> nat -> server'
    net.setChain('client', 'nat', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('nat', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    net.CLI()
    net.stop()


def runVPNOnly():
    """ Test VPN VNF by putting it between client and server and check if
    packets pass through VPN VNF and reach the server VNF. Here, each VNF is on
    a separate data center connected with a switch. Also, the server is the VPN
    server and VPN VNF is just a client-vpn."""

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add 3 data centers
    client_dc = net.addDatacenter('client-dc')
    chain_dc = net.addDatacenter('chain-dc')
    server_dc = net.addDatacenter('server-dc')

    # connect data centers with switches
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    # link data centers and switches
    net.addLink(client_dc, s1)
    net.addLink(s1, chain_dc)
    net.addLink(chain_dc, s2)
    net.addLink(s2, server_dc)

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

    # create client with one interface
    client = client_dc.startCompute("client",
                                    network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])

    # create VPN VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    vpn = chain_dc.startCompute("vpn", image='knodir/vpn-client',
                            network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                     {'id': 'output', 'ip': '10.0.10.4/24'}])

    # create server VNF with one interface
    server = server_dc.startCompute("server", image='knodir/vpn-server',
                                    network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])

    print(subprocess.call(
        'sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.10.0/24 dev intf1"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"', shell=True))

    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # chain 'client -> vpn -> server'
    net.setChain('client', 'vpn', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('vpn', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    # start openvpn server and related services inside the server
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "ufw enable"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "ufw status"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "service openvpn start"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "service openvpn status"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "service rsyslog start"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "service rsyslog status"', shell=True))

    # execute /start.sh script inside VPN client.
    print(subprocess.call('sudo docker exec -i mn.vpn /bin/bash /start.sh &',
                          shell=True))
    print('> sleeping 60s to VPN client initialize...')
    time.sleep(60)
    print('< wait complete')
 
    print('NAT VNF started')

    print(subprocess.call(
        'sudo docker exec -i mn.client /bin/bash -c "ip route add 10.8.0.1/32 dev intf1"', shell=True))

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    net.CLI()
    net.stop()


def nodeUpgrade():
    """ TBD """

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
    client = dc.startCompute("client",
                             network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = dc.startCompute("nat", image='knodir/nat',
                          network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                   {'id': 'output', 'ip': '10.0.10.4/24'}])
    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'snort' VNF.
    fw = dc.startCompute("fw", image='knodir/sonata-fw-vnf',
                         network=[{'id': 'input', 'ip': '10.0.0.5/24'},
                                  {'id': 'output', 'ip': '10.0.0.6/24'}])

    # create snort VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    snort = dc.startCompute("snort", image='sonatanfv/sonata-snort-ids-vnf',
                            network=[{'id': 'input', 'ip': '10.0.0.7/24'},
                                     {'id': 'output', 'ip': '10.0.0.8/24'}])

    # create server VNF with one interface
    server = dc.startCompute("server",
                             network=[{'id': 'intf2', 'ip': '10.0.10.9/24'}])

    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # add routing table entries on client and server
    print(subprocess.call(
        'sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.10.0/24 dev intf1"', shell=True))
    print(subprocess.call(
        'sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"', shell=True))

    # execute /start.sh script inside firewall Docker image. It start Ryu
    # controller and OVS with proper configuration.
    print(subprocess.call('sudo docker exec -i mn.fw /bin/bash /root/start.sh &', shell=True))
    print('> sleeping 10s to wait ryu controller initialize')
    time.sleep(10)
    print('< wait complete')
    print('fw start done')

    # execute /start.sh script inside snort image. It bridges input and output
    # interfaces with br0, and starts snort process listering on br0.
    print(subprocess.call('sudo docker exec -i mn.snort /bin/bash -c "sh /start.sh"', shell=True))
    print('snort start done')

    # execute /start.sh script inside nat image. It attaches both input
    # and output interfaces to OVS bridge to enable packet forwarding.
    print(subprocess.call('sudo docker exec -i mn.nat /bin/bash /start.sh',
                          shell=True))
    print('nat start done')

    # chain 'client <-> nat <-> fw <-> snort <-> server'
    net.setChain('client', 'nat', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('nat', 'fw', 'output', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fw', 'snort', 'output', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('snort', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')
    # TODO(nodir): the first packet in the chain always drops. It is not because
    # of Ryu OpenFlow controller's traditional first-packet-drop behaviour since
    # the first packet does not fail when Firewall tried separately (in
    # runFirewallOnly()). Sleeping extra 5s before ping does not help. Find out
    # why it happens.

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server], timeout=5))

    net.CLI()
    net.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    # basicTest()
    # runDummyForwarderOnly()
    # runDummyForwarderOVSOnly()
    # runIDSOnly()
    # runFirewallOnly()
    # runNATOnly()
    runVPNOnly()
    # flatNet()
    # nodeUpgrade()
    cleanup()
