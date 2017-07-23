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
from mininet.clean import cleanup


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
    MAX_CU = 10  # max compute units
    MAX_MU = 8704  # max memory units

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

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=False)

    # reg = ResourceModelRegistrar(MAX_CU, MAX_MU)
    # rm = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
    # reg.register("homogeneous_rm", rm)

    # add 3 servers
    off_cloud = net.addDatacenter('off-cloud')  # place client/server VNFs
    chain_server1 = net.addDatacenter('chain-server1')
    chain_server2 = net.addDatacenter('chain-server2')

    # off_cloud.assignResourceModel(rm)
    # chain_server1.assignResourceModel(rm)
    # chain_server2.assignResourceModel(rm)

    # connect data centers with switches
    tor1 = net.addSwitch('tor1')

    # link data centers and switches
    net.addLink(off_cloud, tor1)
    net.addLink(chain_server1, tor1)
    net.addLink(chain_server2, tor1)

    # create REST API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)

    # connect API endpoint to containernet
    api.connectDCNetwork(net)

    # connect data centers to the endpoint
    api.connectDatacenter(off_cloud)
    api.connectDatacenter(chain_server1)
    api.connectDatacenter(chain_server2)

    # start API and containernet
    api.start()
    net.start()

    return (net, api, [off_cloud, chain_server1, chain_server2])
    # return (net, dc, api)


def scaleOut():
    """ Implements node-upgrade scenario. TBD. """

    cmds = []
    net, api, dcs = prepareDC()
    off_cloud_c, cs1, off_cloud_s = dcs[0], dcs[1], dcs[2]
    fl = "large"

    # create client with one interface
    client = off_cloud_c.startCompute("client", image='knodir/client',
                                      network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
    client.sendCmd('sudo ifconfig intf1 hw ether 00:00:00:00:00:1')
    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = cs1.startCompute("nat", image='knodir/nat',
                           network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                    {'id': 'output', 'ip': '10.0.1.4/24'}])
    nat.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:2')
    nat.sendCmd('sudo ifconfig output hw ether 00:00:00:00:00:3')

    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
    # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
    fw = cs1.startCompute("fw", image='knodir/sonata-fw-fixed',
                          network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                                   {'id': 'output-ids', 'ip': '10.0.1.60/24'},
                                   # {'id': 'output-ids2', 'ip': '10.0.1.61/24'},
                                   {'id': 'output-vpn', 'ip': '10.0.1.62/24'}])
    fw.sendCmd('sudo ifconfig input hw ether 00:00:00:00:00:4')
    fw.sendCmd('sudo ifconfig output-ids hw ether 00:00:00:00:00:5')
    fw.sendCmd('sudo ifconfig output-vpn hw ether 00:00:00:00:00:6')

    # create ids VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    ids1 = cs1.startCompute("ids1", image='knodir/snort-trusty',
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
    return net


def set_bw(multiplier):
    low_bw = 1 * multiplier / 10
    high_bw = 2 * multiplier / 10
    print("Scaling up bandwidth by %d and %d" % (low_bw, high_bw))
    sys.stdout.flush()
    os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc1.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth4 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth5 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth7 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth8 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth9 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth10 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth11 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc3.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))


def scale_bw(multiplier):
    low_bw = 2 * multiplier / 10
    high_bw = 3 * multiplier / 10
    print("Scaling up bandwidth by %d and %d" % (low_bw, high_bw))
    sys.stdout.flush()
    os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc1.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth4 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth5 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth7 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth8 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth9 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth10 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(low_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(low_bw) + ' other-config:max-rate=' + str(low_bw))
    os.system('ovs-vsctl -- set Port dc2.s1-eth11 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=' + str(high_bw) + ' queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=' + str(high_bw) + ' other-config:max-rate=' + str(high_bw))
    os.system('ovs-vsctl -- set Port dc3.s1-eth2 qos=@newqos -- \
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
    cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "pkill python2"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "pkill python2"')
    # remove stale dstat output file (if any)
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "rm /tmp/dstat.csv"')
    cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "rm /tmp/dstat.csv"')
    cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "rm /tmp/dstat.csv"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "rm /tmp/dstat.csv"')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    print('wait 3s for iperf server and other stale processes cleanup')
    time.sleep(3)

    return cmds


def clean_and_save(cmds, testName):

    cmds.append('sudo docker exec -i mn.client /bin/bash -c "pkill tcpreplay"')

    print('wait 3s for iperf client and other processes terminate')
    time.sleep(3)
    # kill dstat daemons, they runs as python2 process.
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "pkill python2"')
    cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "pkill python2"')
    cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "pkill python2"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "pkill python2"')
    # copy the iperf client output file to the local machine
    # cmds.append('sudo docker cp mn.client:/tmp/iperf3.json ./output/from-client.json')
    cmds.append('sudo docker cp mn.client:/tmp/dstat.csv ./results/' + testName + '-from-client.csv')
    cmds.append('sudo docker cp mn.ids1:/tmp/dstat.csv ./results/' + testName + '-from-ids1.csv')
    cmds.append('sudo docker cp mn.ids2:/tmp/dstat.csv ./results/' + testName + '-from-ids2.csv')
    cmds.append('sudo docker cp mn.vpn:/tmp/dstat.csv ./results/' + testName + '-from-vpn.csv')
    # do remaining cleanup inside containers
    # cmds.append('sudo docker exec -i mn.server /bin/bash -c "pkill iperf3"')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    return cmds


def benchmark(multiplier):
    """ Start traffic generation. """
    # list of commands to execute one-by-one
    cmds = []
    # clean stale programs and remove old files
    cmds.append('sudo rm ./results/scaleout' +
                str(multiplier / 10**6) + '-from-client.csv')
    cmds.append('sudo rm ./results/scaleout' +
                str(multiplier / 10**6) + '-from-ids1.csv')
    cmds.append('sudo rm ./results/scaleout' +
                str(multiplier / 10**6) + '-from-vpn.csv')

    cmds = clean_stale(cmds)

    # Set the initial bandwidth constraints of the system
    set_bw(multiplier)
    time.sleep(3)
    # cmds.append('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s --bind 10.8.0.1" &')
    # cmds.append('sudo docker exec -i mn.client /bin/bash -c "dstat --net --time -N intf1 --bits --output /tmp/dstat.csv" &')
    # cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "dstat --net --time -N input --bits --output /tmp/dstat.csv" &')
    # cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "dstat --net --time -N input-fw --bits --output /tmp/dstat.csv" &')
    cmds.append('sudo timeout 70 dstat --net --time -N dc1.s1-eth1 --nocolor --output ./results/scaleout' +
                str(multiplier / 10**6) + '-from-client.csv &')
    cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth7 --nocolor --output ./results/scaleout' +
                str(multiplier / 10**6) + '-from-ids1.csv &')
    cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth4 --nocolor --output ./results/scaleout' +
                str(multiplier / 10**6) + '-from-vpn.csv &')

    # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
    cmds.append('sudo timeout 70  docker exec -i mn.client /bin/bash -c "tcpreplay --loop=0 --mbps=' +
                str(multiplier / 10**6) + ' -d 1 --intf1=intf1 /ftp.ready.pcap" &')
    # each loop is around 40s for 10 Mbps speed, 2 loops easily make 1m
    cmds.append('sudo timeout 70  docker exec -i mn.client /bin/bash -c "tcpreplay --loop=0 --mbps=' +
                str(multiplier / 10**6) + ' -d 1 --intf1=intf1 /output.pcap" &')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    print("Generating traffic for 30 seconds")

    # start scaling up the bandwidth after 30 seconds
    time.sleep(30)
    print("Scaling up bandwidth by factor of 1")
    scale_bw(multiplier)
    time.sleep(40)
    # clean and save the results in csv file named after the test
    # cmds = clean_and_save(cmds, "scaleout")
    # cmds.append('sudo killall dstat')
    # cmds.append('sudo killall tcpreplay')
    # for cmd in cmds:
    #     execStatus = subprocess.call(cmd, shell=True)
    #     print('returned %d from %s (0 is success)' % (execStatus, cmd))
    print('done')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    net = scaleOut()
    print("Done with scaleout!")
    print('Running 10 Mbps')
    benchmark(10**7)
    print('Running 100 Mbps')
    benchmark(10**8)
    print('Running 1000 Mbps')
    benchmark(10**9)
    print('Running 10000 Mbps')
    benchmark(10**10)
    net.CLI()
    net.stop()
    cleanup()
    os.system("sudo ../clean-stale.sh")
