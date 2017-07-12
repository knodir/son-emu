import time
import subprocess
import logging
import json

from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM
from emuvim.dcemulator.resourcemodel import ResourceModelRegistrar


from mininet.log import setLogLevel, info
from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.net import Containernet
from mininet.node import Controller, Docker, OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink, Link


def prepareDC(pn_fname):
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
    MAX_CU = 128 # max compute units
    MAX_MU = 8192 # max memory units

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

    net = DCNetwork(controller=RemoteController, monitor=True,
            dc_emulation_max_cpu=MAX_CU, dc_emulation_max_mem=MAX_MU,
            enable_learning=True)

    # Read physical topology from file.
    with open(pn_fname) as data_file:
        data = json.load(data_file)

    print('read data center description from JSON file %s' % data['Servers'])

    dcs = {}
    for name, props in data['Servers'].iteritems():
        dcs[name] = net.addDatacenter(name)

    reg = ResourceModelRegistrar(MAX_CU, MAX_MU)
    rm = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
    reg.register("homogeneous_rm", rm)

    for dc_name, dc_obj in dcs.iteritems():
        dc_obj.assignResourceModel(rm)
        print('assigned resource model to %s' % dc_name)


    # Extract ToR switch names. Thyse are the ones not listed as 'Servers'
    print('PN read from JSON file %s' % data['PN'])

    tors = {}

    for pn_item in data['PN']:
        if (pn_item[0] not in data['Servers'].keys()) and (
                pn_item[0] not in tors.keys()):
            # print(pn_item[0])
            tors[pn_item[0]] = None

        if (pn_item[1] not in data['Servers'].keys()) and (
                pn_item[1] not in tors.keys()):
            # print(pn_item[1])
            tors[pn_item[1]] = None

    # connect ToR switches and DC per PN topology
    for tor_name in tors.keys():
        tors[tor_name] = net.addSwitch(tor_name)

    print('ToR switch name and objects: %s' % tors)

    for pn_item in data['PN']:
        net.addLink(dcs[pn_item[0]], tors[pn_item[1]])

    print('added link from DCs to ToR')

    # create REST API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)

    # connect API endpoint to containernet
    api.connectDCNetwork(net)

    # connect data centers to the endpoint
    for dc_name, dc_obj in dcs.iteritems():
        api.connectDatacenter(dc_obj)

    # start API and containernet
    api.start()
    net.start()

    return (net, api, dcs, tors)


def get_placement(pn_fname, vn_fname):
    """ Return chain placement with NetSolver. """




def nodeUpgrade(pn):
    """ Implements node-upgrade scenario. TBD. """

    cmds = []
    net, api, dcs, tors = prepareDC(pn)
    fl = "large"

    net.CLI()
    net.stop()
    return

    # create client with one interface
    client = off_cloud.startCompute("client", image='knodir/client',
            flavor_name=fl,
            network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
    # create NAT VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    nat = cs1.startCompute("nat", image='knodir/nat',
            flavor_name=fl,
            network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                {'id': 'output', 'ip': '10.0.1.4/24'}])
    # create fw VNF with two interfaces. 'input' interface for 'client' and
    # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
    # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
    fw = cs1.startCompute("fw", image='knodir/sonata-fw-vnf',
            flavor_name="xlarge",
            network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                {'id': 'output-ids1', 'ip': '10.0.1.60/24'},
                {'id': 'output-ids2', 'ip': '10.0.1.61/24'},
                {'id': 'output-vpn', 'ip': '10.0.1.62/24'}])
    # create ids VNF with two interfaces. 'input' interface for 'fw' and
    # 'output' interface for the 'server' VNF.
    ids1 = cs1.startCompute("ids1", image='knodir/snort-trusty',
            flavor_name=fl,
            network=[{'id': 'input', 'ip': '10.0.1.70/24'},
                {'id': 'output', 'ip': '10.0.1.80/24'}])
    ids2 = cs1.startCompute("ids2", image='knodir/snort-xenial',
            flavor_name=fl,
            network=[{'id': 'input', 'ip': '10.0.1.71/24'},
                {'id': 'output', 'ip': '10.0.1.81/24'}])
 
    # create VPN VNF with two interfaces. Its 'input'
    # interface faces the client and output interface the server VNF.
    vpn = cs1.startCompute("vpn", image='knodir/vpn-client',
            flavor_name=fl,
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
    server = off_cloud.startCompute("server", image='knodir/vpn-server',
            flavor_name="small",
            network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])

    #net.stop()
    #return

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
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "ufw enable"')
    # open iperf3 port (5201) on firewall (ufw)
    cmds.append('sudo docker exec -i mn.server /bin/bash -c "ufw allow 5201"')
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

    print('> sleeping 60s to VPN client initialize...')
    time.sleep(60)
    print('< wait complete')
    print('VPN client VNF started')

    # rewrite client and NAT VNF MAC addresses for tcpreplay
    cmds.append('sudo docker exec -i mn.client /bin/bash -c "ifconfig intf1 hw ether 00:00:00:00:00:01"')
    cmds.append('sudo docker exec -i mn.nat /bin/bash -c "ifconfig input hw ether 00:00:00:00:00:02"')
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

    net.CLI()
    net.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    # logging.basicConfig(level=logging.INFO)

    pn_fname = "../topologies/e2-1rack-8servers.pn.json"

    nodeUpgrade(pn_fname)
    cleanup()
