import time
import subprocess
import logging
import os
import sys
from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM
from emuvim.dcemulator.resourcemodel import ResourceModelRegistrar

from mininet.log import setLogLevel, info
from mininet.node import RemoteController
from mininet.node import DefaultController
from mininet.clean import cleanup
from optparse import OptionParser


def prepareDC():
    """ Prepares physical topology to place chains. """

    # We use Sonata data center construct to simulate physical servers (just
    # servers hereafter). The reason is that Sonata DC has CPU/RAM resource
    # constraints just like the servers. We also model the links between servers
    # with bandwidth constraints of Sonata switch-to-DC link.

    # The topology we create below is one rack with two servers. The rack has
    # ToR switches (Sonata switch called "tor1"), to place chain VNFs.

    # Similar to the paper story of middlebox-as-a-server, we will put client
    # and server (traffic source and sink) outside the DC.

    # Here is the reason why we do not use Sonata "host" to model the servers.
    # Sonata uses Mininet host construct as-is. Mininet "host" supports only CPU
    # resource constraint. Therefore, we do not use Sonata "host" construct.

    # Unless otherwise specified, we always use "server" for variables and
    # description instead of "DC". This should avoid confusion with terminology.

    # add resource model (rm) to limit cpu/ram available in each server. We
    # create one resource mode and use it for all servers, meaning all of our
    # servers are homogeneous. Create multiple RMs for heterogeneous servers
    # (with different amount of cpu,ram).
    MAX_CU = 8  # max compute units
    MAX_MU = 30000  # max memory units
    MAX_CU_NET = 24
    MAX_MU_NET = 400000
    # the cpu, ram resource above are consumed by VNFs with one of these
    # flavors. For some reason memory allocated for tiny flavor is 42 MB,
    # instead of 32 MB in this systems. Other flavors are multipliers of this
    # 42 MB (as expected).
    # "tiny",  {"compute": 0.5, "memory": 32, "disk": 1}
    # "small",  {"compute": 1.0, "memory": 128, "disk": 20}
    # "medium",  {"compute": 4.0, "memory": 256, "disk": 40}
    # "large",  {"compute": 8.0, "memory": 512, "disk": 80}
    # "xlarge",  {"compute": 16.0, "memory": 1024, "disk": 160}
    #
    # Note that all these container VNFs need at least 500 MB of memory to be
    # able to work. Firewall in particular, runs OVS, needs more than 1 GB to be
    # able to process packets. If you do not allocate sufficient CPU, system
    # behaves bad. In most cases all physical cores gets pinned (probably
    # because of the contention between OVS and cgroup mem limitation) and
    # Sonata VM OOM killer starts killing random processes.

    # net = DCNetwork(controller=RemoteController, monitor=False, enable_learning=False,
    #                 dc_emulation_max_cpu=MAX_CU_NET,
    #                 dc_emulation_max_mem=MAX_MU_NET)
    net = DCNetwork(controller=RemoteController, monitor=False, enable_learning=False)
    # reg = ResourceModelRegistrar(MAX_CU, MAX_MU)
    # rm1 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
    # rm2 = UpbSimpleCloudDcRM(MAX_CU * 2, MAX_MU * 2)
    # rm3 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)

    # reg.register("homogeneous_rm", rm)

    # add 3 servers
    off_cloud = net.addDatacenter('off-cloud')  # place client/server VNFs
    chain_server1 = net.addDatacenter('chain-server1')
    # chain_server2 = net.addDatacenter('chain-server2')

    # off_cloud.assignResourceModel(rm1)
    # chain_server1.assignResourceModel(rm2)
    # chain_server2.assignResourceModel(rm3)

    # connect data centers with switches
    tor1 = net.addSwitch('tor1')

    # link data centers and switches
    net.addLink(off_cloud, tor1)
    net.addLink(chain_server1, tor1)
    # net.addLink(chain_server2, tor1)

    # create REST API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)

    # connect API endpoint to containernet
    api.connectDCNetwork(net)

    # connect data centers to the endpoint
    api.connectDatacenter(off_cloud)
    api.connectDatacenter(chain_server1)
    # api.connectDatacenter(chain_server2)

    # start API and containernet
    api.start()
    net.start()

    return (net, api, [off_cloud, chain_server1])
    # return (net, dc, api)


def scaleOut():
    """ Implements scale-out scenario. TBD. """

    cmds = []
    net, api, dcs = prepareDC()
    off_cloud, cs1 = dcs[0], dcs[1]
    fl = "ids"

    # create client with one interface
    client = off_cloud.startCompute("client", image='knodir/client',
                                    # flavor_name=fl,
                                    network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
    client.sendCmd('sudo ifconfig intf1 hw ether 00:00:00:00:00:1')

    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = cs1.startCompute("nat", image='knodir/nat',
                           # flavor_name=fl,
                           network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                    {'id': 'output', 'ip': '10.0.1.4/24'}])
    nat.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:2')
    nat.sendCmd('sudo ifconfig output hw ether 00:00:00:00:00:3')

    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
    # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
    fw = cs1.startCompute("fw", image='knodir/sonata-fw-iptables',
                          # flavor_name=fl,
                          network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                                   {'id': 'output-ids', 'ip': '10.0.1.60/24'},
                                   # {'id': 'output-ids2', 'ip': '10.0.1.61/24'},
                                   {'id': 'output-vpn', 'ip': '10.0.2.4/24'}])
    fw.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:4')
    fw.sendCmd('sudo ifconfig output-ids hw ether 00:00:00:00:00:5')
    fw.sendCmd('sudo ifconfig output-vpn hw ether 00:00:00:00:00:6')

    # create ids VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    ids1 = cs1.startCompute("ids1", image='knodir/snort-trusty',
                            # flavor_name=fl,
                            network=[{'id': 'input', 'ip': '10.0.1.70/24'},
                                     {'id': 'output', 'ip': '10.0.1.80/24'}])
    # ids2 = cs1.startCompute("ids2", image='knodir/snort-xenial',
    #                         # flavor_name=fl,,
    #                         network=[{'id': 'input', 'ip': '10.0.1.71/24'},
    #                                  {'id': 'output', 'ip': '10.0.1.81/24'}])
    ids1.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:7')
    ids1.sendCmd('sudo ifconfig output hw ether 00:00:00:00:00:8')

    # create VPN VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    vpn = cs1.startCompute("vpn", image='knodir/vpn-client',
                           # flavor_name=fl,
                           network=[{'id': 'input-ids1', 'ip': '10.0.1.90/24'},
                                    # {'id': 'input-ids2', 'ip': '10.0.1.91/24'},
                                    {'id': 'input-fw', 'ip': '10.0.2.5/24'},
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
    server = off_cloud.startCompute("server", image='knodir/vpn-server',
                                    # flavor_name=fl,
                                    network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])
    server.sendCmd('sudo ifconfig intf2 hw ether 00:00:00:00:00:12')

    # execute /start.sh script inside firewall Docker image. It starts Ryu
    # controller and OVS with proper configuration.
    cmd = 'sudo docker exec -i mn.fw /bin/bash /root/start.sh &'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from fw start.sh start (0 is success)' % execStatus)

    # os.system("sudo docker update --cpus 64 --cpuset-cpus 0-63 mn.client mn.nat mn.fw mn.ids1 mn.vpn mn.server")
    # os.system("sudo docker update --cpus 8 --cpuset-cpus 0-7 mn.client mn.nat mn.fw mn.ids1 mn.vpn mn.server")
    # os.system("sudo docker update --cpu-shares 200000 mn.fw")

    print('> sleeping 2s to wait ryu controller initialize')
    time.sleep(2)
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

    net.setChain('fw', 'ids1', 'output-ids', 'input', bidirectional=True,
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

    print('> sleeping 5 to VPN client initialize...')
    time.sleep(5)
    print('< wait complete')
    print('VPN client VNF started')

    # manually chain routing table entries on VNFs
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "route add -net 10.0.0.0/16 dev intf1"')
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "route add -net 10.8.0.0/24 dev intf1"')

    cmds.append('sudo docker exec -i mn.nat /bin/bash -c "route add -net 10.0.10.0/24 dev output"')
    cmds.append('sudo docker exec -i mn.nat /bin/bash -c "ip route add 10.8.0.0/24 dev output"')

    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route add -net 10.0.10.0/24 dev output-ids"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route del -net 10.0.1.0/24 dev output-ids"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route del -net 10.0.1.0/24 dev input"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route add -net 10.8.0.0/24 dev output-ids"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route add -net 10.0.0.0/24 dev input"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route add -net 10.0.1.0/26 dev input"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "route add -net 10.0.1.0/24 dev output-ids"')

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
    return net


def set_bw(multiplier):
    low_bw = 1 * multiplier / 10
    high_bw = 2 * multiplier / 10
    print("Scaling up bandwidth by %d and %d" % (low_bw, high_bw))
    sys.stdout.flush()
    # Output DC1
    os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Output Client
    os.system('ovs-vsctl -- set Port dc1.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Input NAT
    os.system('ovs-vsctl -- set Port dc2.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Output NAT
    os.system('ovs-vsctl -- set Port dc2.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Input FW
    os.system('ovs-vsctl -- set Port dc2.s1-eth4 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Output FW-IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth5 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Output FW-VPN
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Input IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth7 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Output IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth8 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Input VPN-IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth9 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Input VPN-FW
    os.system('ovs-vsctl -- set Port dc2.s1-eth10 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Output VPN
    os.system('ovs-vsctl -- set Port dc2.s1-eth11 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Input Sink
    os.system('ovs-vsctl -- set Port dc1.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))


def scale_bw(multiplier):
    low_bw = 2 * multiplier / 10
    high_bw = 3 * multiplier / 10
    vpn_bw = 1 * multiplier / 10
    print("Scaling up bandwidth by %d and %d" % (low_bw, high_bw))
    sys.stdout.flush()
    # Output DC1
    os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Output Client
    os.system('ovs-vsctl -- set Port dc1.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Input NAT
    os.system('ovs-vsctl -- set Port dc2.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Output NAT
    os.system('ovs-vsctl -- set Port dc2.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Input FW
    os.system('ovs-vsctl -- set Port dc2.s1-eth4 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Output FW-IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth5 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Output FW-VPN
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(vpn_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(vpn_bw) + ' other-config:max-rate=' + str(vpn_bw))
    # Input IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth7 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Output IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth8 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Input VPN-IDS
    os.system('ovs-vsctl -- set Port dc2.s1-eth9 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    # Input VPN-FW
    os.system('ovs-vsctl -- set Port dc2.s1-eth10 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(vpn_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(vpn_bw) + ' other-config:max-rate=' + str(vpn_bw))
    # Output VPN
    os.system('ovs-vsctl -- set Port dc2.s1-eth11 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    # Input Sink
    os.system('ovs-vsctl -- set Port dc1.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))


def clean_stale(cmds):

    # kill existing iperf server
    # cmds.append('sudo docker exec -i mn.server /bin/bash -c "pkill iperf3"')
    # remove stale iperf output file (if any)
    # cmds.append('sudo docker exec -i mn.client /bin/bash -c "rm /tmp/iperf3.json"')
    # kill existing dstat
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "pkill tcpreplay"')
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "pkill python2"')
    cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "pkill python2"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "pkill python2"')
    # remove stale dstat output file (if any)
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "rm /tmp/dstat.csv"')
    cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "rm /tmp/dstat.csv"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "rm /tmp/dstat.csv"')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    print('wait 3s for iperf server and other stale processes cleanup')
    time.sleep(3)

    return cmds


def benchmark(multiplier, test_time, iperf):
    """ Start traffic generation. """
    # list of commands to execute one-by-one
    cmds = []
    # clean stale programs and remove old files
    print("Benchmarking %d Mbps...", multiplier / 10**6)

    if iperf:
        testname = "scaleout-iperf"
    else:
        testname = "scaleout"
    print(testname)
    print(str(multiplier / 10**6))
    cmd = 'sudo rm ./results/%s/%s-from-client.csv' % (testname, str(multiplier / 10**6))
    cmds.append(cmd)
    cmd = 'sudo rm ./results/%s/%s-from-ids.csv' % (testname, str(multiplier / 10**6))
    cmds.append(cmd)
    cmd = 'sudo rm ./results/%s/%s-from-vpn-fw.csv' % (testname, str(multiplier / 10**6))
    cmds.append(cmd)
    cmd = 'sudo rm ./results/%s/%s-from-vpn-ids.csv' % (testname, str(multiplier / 10**6))
    cmds.append(cmd)
    cmd = 'sudo rm ./results/%s/%s-from-server.csv' % (testname, str(multiplier / 10**6))
    cmds.append(cmd)
    cmds = clean_stale(cmds)

    # Set the initial bandwidth constraints of the system
    # set_bw(multiplier)
    time.sleep(3)
    cmds.append('mkdir ./results/%s' % testname)
    cmd = 'sudo timeout %s dstat --net --time -N dc1.s1-eth1 --nocolor --output ./results/%s/%s-from-client.csv &' % (
        str(test_time), testname, str((multiplier / 10**6)))
    cmds.append(cmd)
    cmd = 'sudo timeout %s dstat --net --time -N dc2.s1-eth7 --nocolor --output ./results/%s/%s-from-ids.csv &' % (
        str(test_time), testname, str((multiplier / 10**6)))
    cmds.append(cmd)
    cmd = 'sudo timeout %s dstat --net --time -N dc2.s1-eth9 --nocolor --output ./results/%s/%s-from-vpn-ids.csv &' % (
        str(test_time), testname, str((multiplier / 10**6)))
    cmds.append(cmd)
    cmd = 'sudo timeout %s dstat --net --time -N dc2.s1-eth10 --nocolor --output ./results/%s/%s-from-vpn-fw.csv &' % (
        str(test_time), testname, str((multiplier / 10**6)))
    cmds.append(cmd)
    if iperf:
        cmds.append('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s > iperf-log.txt" &')
        cmds.append('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s > iperf-log.txt -p 5202" &')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []
    # cmds.append('sudo timeout 70 dstat --net --time -N dc1.s1-eth2 --nocolor --output ./results/scaleout/' +
    #             str(multiplier / 10**6) + '-from-client.csv &')
    # cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth7 --nocolor --output ./results/scaleout/' +
    #             str(multiplier / 10**6) + '-from-ids1.csv &')
    # cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth9 --nocolor --output ./results/scaleout/' +
    #             str(multiplier / 10**6) + '-from-vpn-ids.csv &')
    # cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth10 --nocolor --output ./results/scaleout/' +
    #             str(multiplier / 10**6) + '-from-vpn-fw.csv &')
    # cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "dstat --net --time -N tun0 --bits --output /tmp/dstat.csv" &')
    time.sleep(3)
    if iperf:
        cmd = 'sudo docker exec -i mn.client /bin/bash -c "iperf3 --verbose --zerocopy \
        -b %dm -c 10.0.10.10 -t %d > iperf-log.txt" &' % ((multiplier / 10**7), test_time)
    else:
        cmd = 'sudo timeout %d  docker exec -i mn.client /bin/bash -c "tcpreplay --quiet --enable-file-cache \
        --loop=0 --mbps=%d -d 1 --intf1=intf1 /output.pcap" &' % (test_time, (multiplier / 10**7))
    execStatus = subprocess.call(cmd, shell=True)

    cmd = 'sudo timeout %d  docker exec -i mn.client /bin/bash -c "tcpreplay --quiet --enable-file-cache \
    --loop=0 --mbps=%d -d 1 --intf1=intf1 /ftp.ready.pcap" &' % (test_time, (multiplier / 10**7))
    execStatus = subprocess.call(cmd, shell=True)

    print("Generating traffic for %d seconds" % test_time)

    # start scaling up the bandwidth after 50% of the time
    time.sleep(test_time / 2)
    print("Scaling up bandwidth by factor of 1")
    # scale_bw(multiplier)
    # each loop is around 40s for 10 Mbps speed, 2 loops easily make 1m
    if iperf:
        cmd = 'sudo docker exec -i mn.client /bin/bash -c "iperf3 --verbose --zerocopy \
        -b %dm -c 10.0.10.10 -p 5202-t %d > iperf-log2.txt" &' % ((multiplier / 10**7), test_time)
    else:
        cmd = 'sudo timeout %d  docker exec -i mn.client /bin/bash -c "tcpreplay --quiet --enable-file-cache \
        --loop=0 --mbps=%d -d 1 --intf1=intf1 /output.pcap" &' % (test_time, (multiplier / 10**7))
    execStatus = subprocess.call(cmd, shell=True)

    time.sleep(test_time / 2 + 10)
    # clean and save the results in csv file named after the test
    # cmds = clean_and_save(cmds, "scaleout")
    cmds.append('sudo killall dstat')
    cmds.append('sudo killall tcpreplay')
    cmds.append('sudo killall iperf3')
    # cmds.append('sudo docker cp mn.vpn:/tmp/dstat.csv ./results/scaleout/' +
    #             str(multiplier / 10**6) + '-from-vpn.csv')
    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))
    print('done')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    parser = OptionParser()
    parser.add_option("-i", "--iperf", action="store_true", dest="iperf", default=False, help="Use Iperf instead")

    (options, args) = parser.parse_args()
    print(options.iperf)
    test_time = 300
    net = scaleOut()
    print("Done with scaleout!")
    print('Running 10 Mbps')
    benchmark(10**7, test_time, options.iperf)
    print('Running 100 Mbps')
    benchmark(10**8, test_time, options.iperf)
    print('Running 1000 Mbps')
    benchmark(10**9, test_time, options.iperf)
    print('Running 10000 Mbps')
    benchmark(10**10, test_time, options.iperf)
    # net.CLI()
    net.stop()
    cleanup()
    os.system("sudo ../clean-stale.sh")
