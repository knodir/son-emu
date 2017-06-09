import logging
from mininet.log import setLogLevel, info
from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.api.sonata import SonataDummyGatekeeperEndpoint
from mininet.node import RemoteController

import os
import time
from mininet.clean import cleanup
import subprocess
from mininet.net import Containernet
from mininet.node import Controller, Docker, OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink, Link


def runSDNChainingMultiService():
    """
    This function is copied from src/emuvim/test/unittests/test_emulator.py
    Create a two data centers and interconnect them with additional
    switches between them.
    Uses Ryu SDN controller.
    Setup 2 services and setup isolated paths between them
    Delete only the first service, and check that other one still works
    """
    # create network
    testTop = SimpleTestTopology()
    # SimpleTestTopology.createNet(
    testTop.createNet(
        nswitches=3, ndatacenter=2, nhosts=0, ndockers=0,
        autolinkswitches=True,
        controller=RemoteController,
        enable_learning=False)

    # setup links
    self.net.addLink(self.dc[0], self.s[0])
    self.net.addLink(self.s[2], self.dc[1])
    # start Mininet network
    self.startNet()

    # First Service
    # add compute resources
    vnf1 = self.dc[0].startCompute("vnf1", network=[{'id': 'intf1', 'ip': '10.0.10.1/24'}])
    vnf2 = self.dc[1].startCompute("vnf2", network=[{'id': 'intf2', 'ip': '10.0.10.2/24'}])
    # setup links
    self.net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=1)
    # check connectivity by using ping
    self.assertTrue(self.net.ping([vnf1, vnf2]) <= 0.0)

    # Second Service
    # add compute resources
    vnf11 = self.dc[0].startCompute("vnf11", network=[{'id': 'intf1', 'ip': '10.0.20.1/24'}])
    vnf22 = self.dc[1].startCompute("vnf22", network=[{'id': 'intf2', 'ip': '10.0.20.2/24'}])

    # check number of running nodes
    self.assertTrue(len(self.getContainernetContainers()) == 4)
    self.assertTrue(len(self.net.hosts) == 4)
    self.assertTrue(len(self.net.switches) == 5)

    # setup links
    self.net.setChain('vnf11', 'vnf22', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=2)
    # check connectivity by using ping
    self.assertTrue(self.net.ping([vnf11, vnf22]) <= 0.0)
    # check first service cannot ping second service
    self.assertTrue(self.net.ping([vnf1, vnf22]) > 0.0)
    self.assertTrue(self.net.ping([vnf2, vnf11]) > 0.0)

    # delete the first service chain
    self.net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='del-flows', cookie=1)
    # check connectivity of first service is down
    self.assertTrue(self.net.ping([vnf1, vnf2]) > 0.0)
    # time.sleep(100)
    # check connectivity of second service is still up
    self.assertTrue(self.net.ping([vnf11, vnf22]) <= 0.0)

    # stop Mininet network
    self.stopNet()


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
    devnull = open(os.devnull, 'wb')
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

    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'snort' VNF.
    fw = dc.startCompute("fw", image='knodir/sonata-fw-vnf',
                         network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                  {'id': 'output', 'ip': '10.0.0.4/24'}])

    # create snort VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    snort = dc.startCompute("snort", image='sonatanfv/sonata-snort-ids-vnf',
                            network=[{'id': 'input', 'ip': '10.0.0.5/24'},
                                     {'id': 'output', 'ip': '10.0.0.6/24'}])

    # create server VNF with one interface
    server = dc.startCompute("server",
                             network=[{'id': 'intf2', 'ip': '10.0.0.7/24'}])

    print('ping client -> server before explicit chaining. Packet drop %s%%' %
          net.ping([client, server]))

    # execute /start.sh script inside firewall Docker image. It start Ryu
    # controller and OVS with proper configuration.
    devnull = open(os.devnull, 'wb')
    print(subprocess.call('sudo docker exec -i mn.fw /bin/bash /root/start.sh &', shell=True))
    print('> sleeping 10s to wait ryu controller initialize')
    time.sleep(10)
    print('< wait complete')
    print('fw start done')

    # execute /start.sh script inside snort image. It bridges input and output
    # interfaces with br0, and starts snort process listering on br0.
    print(subprocess.call('sudo docker exec -i mn.snort /bin/bash -c "sh /start.sh"', shell=True))
    print('snort start done')

    # chain 'client <-> fw <-> snort <-> server'
    net.setChain('client', 'fw', 'intf1', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('fw', 'snort', 'output', 'input', bidirectional=True,
                 cmd='add-flow')
    net.setChain('snort', 'server', 'output', 'intf2', bidirectional=True,
                 cmd='add-flow')

    # TODO(nodir): the first packet in the chain always drops. It is not because
    # of Ryu OpenFlow controller's traditional first-packet-drop behaviour since
    # the first packet does not fail when Firewall tried separately (in
    # runFirewallOnly()). Sleeping extra 5s before ping does not help. Find out
    # why it happends.

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server], timeout=5))

    net.CLI()
    net.stop()


def flatNet():
    "Create a network with some docker containers acting as hosts."

    net = Containernet(controller=Controller)

    info('*** Adding controller\n')
    net.addController('c0')

    info('*** Adding hosts\n')
    # h1 = net.addHost('h1')
    # h2 = net.addHost('h2')

    info('*** Adding docker containers\n')
    d1 = net.addDocker('d1', ip='10.0.0.251', dimage="jasonish/snort")
    d2 = net.addDocker('d2', ip='10.0.0.252', dimage="ubuntu:trusty", cpu_period=50000, cpu_quota=25000)
    d3 = net.addHost(
        'd3', ip='11.0.0.253', cls=Docker, dimage="ubuntu:trusty", cpu_shares=20)
    # d5 = net.addDocker('d5', dimage="ubuntu:trusty", volumes=["/:/mnt/vol1:rw"])

    info('*** Adding switch\n')
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2', cls=OVSSwitch)
    # s3 = net.addSwitch('s3')

    info('*** Creating links\n')
    net.addLink(d1, s1)
    net.addLink(s1, d2)
    net.addLink(d2, s2)
    net.addLink(s2, d3)

    # net.addLink(s1, d1)
    # net.addLink(h2, s2)
    # net.addLink(d2, s2)
    # net.addLink(s1, s2)
    # #net.addLink(s1, s2, cls=TCLink, delay="100ms", bw=1, loss=10)
    # # try to add a second interface to a docker container
    # net.addLink(d2, s3, params1={"ip": "11.0.0.254/8"})
    # net.addLink(d3, s3)

    info('*** Starting network\n')
    net.start()

    net.ping([d1, d2])

    # our extended ping functionality
    # net.ping([d1], manualdestip="10.0.0.252")
    # net.ping([d2, d3], manualdestip="11.0.0.254")

    info('*** Dynamically add a container at runtime\n')
    d4 = net.addDocker('d4', dimage="ubuntu:trusty")
    # we have to specify a manual ip when we add a link at runtime
    net.addLink(d4, s1, params1={"ip": "10.0.0.254/8"})
    # other options to do this
    # d4.defaultIntf().ifconfig("10.0.0.254 up")
    # d4.setIP("10.0.0.254")

    # net.ping([d1], manualdestip="10.0.0.254")

    info('*** Running CLI\n')
    CLI(net)

    info('*** Stopping network')
    net.stop()


if __name__ == '__main__':
    # runSDNChainingMultiService()
    logging.basicConfig(level=logging.DEBUG)

    # basicTest()
    # runIDSOnly()
    # runFirewallOnly()
    # flatNet()
    nodeUpgrade()

    cleanup()
