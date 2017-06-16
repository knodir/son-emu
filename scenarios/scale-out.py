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


def scaleOut():
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

    print('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server], timeout=5))
    # The native mininet function does not work, we are missing telnet.
    # print('bandwidth client -> server after explicit chaining. Packet drop %s%%' %
    #       net.iperf([client, server]))

    # test iPerf
    # print(subprocess.call('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s"', shell=True))
    # print(subprocess.call('sudo docker exec -i mn.client /bin/bash -c "iperf3 -c 10.0.10.9 -t 10"', shell=True))

    links = net.links
    for l in links:
        print(l)
        l.intf1.config(**{'bw': 1})
        l.intf2.config(**{'bw': 1})


    # test iPerf
    # print(subprocess.call('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s"', shell=True))
    # print(subprocess.call('sudo docker exec -i mn.client /bin/bash -c "iperf3 -c 10.0.10.9 -t 10"', shell=True))
    net.CLI()
    net.stop()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    scaleOut()
    cleanup()
