import time
import sys
import random
import subprocess
from subprocess import check_call
from subprocess import CalledProcessError
import logging
import json

from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM
from emuvim.dcemulator.resourcemodel import ResourceModelRegistrar

from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.net import Containernet
from mininet.node import Controller, Docker, OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink, Link

import glog


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

    glog.info('read data center description from JSON file %s' % data['Servers'])

    dcs = {}
    for name, props in data['Servers'].iteritems():
        dcs[name] = net.addDatacenter(name)

    reg = ResourceModelRegistrar(MAX_CU, MAX_MU)
    rm = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
    reg.register("homogeneous_rm", rm)

    for dc_name, dc_obj in dcs.iteritems():
        dc_obj.assignResourceModel(rm)
        glog.info('assigned resource model to %s' % dc_name)


    # Extract ToR switch names. Thyse are the ones not listed as 'Servers'
    glog.info('PN read from JSON file %s' % data['PN'])

    tors = {}

    for pn_item in data['PN']:
        if (pn_item[0] not in data['Servers'].keys()) and (
                pn_item[0] not in tors.keys()):
            # glog.info(pn_item[0])
            tors[pn_item[0]] = None

        if (pn_item[1] not in data['Servers'].keys()) and (
                pn_item[1] not in tors.keys()):
            # glog.info(pn_item[1])
            tors[pn_item[1]] = None

    # connect ToR switches and DC per PN topology
    for tor_name in tors.keys():
        tors[tor_name] = net.addSwitch(tor_name)

    glog.info('ToR switch name and objects: %s' % tors)

    for pn_item in data['PN']:
        net.addLink(dcs[pn_item[0]], tors[pn_item[1]])

    glog.info('added link from DCs to ToR')

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


def get_placement(pn_fname, vn_fname, algo):
    """ Does chain placement with NetSolver and returns the output. """

    if algo == 'netsolver':
        glog.info('using NetSolver for chain allocation')

        out_fname = '/tmp/ns_out.json'
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s --no-repeat" % (
                "../../../monosat_datacenter/src/vdcmapper.py", pn_fname, vn_fname,
                out_fname)
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)', execStatus, cmd)

        if execStatus == 1:
            glog.info("allocation failed")
            return execStatus

        glog.info("allocation succeeded")
        # Read physical topology from file.
        with open(out_fname) as data_file:
            allocs = json.load(data_file)
        return allocs

    # Read physical network from file.
    with open(pn_fname) as data_file:
        pn = json.load(data_file)

    # Read virtual network from file.
    with open(vn_fname) as data_file:
        vn = json.load(data_file)

    # get 'off-cloud' and 'chain-server' server names on a separate list. We
    # place 'source' and 'sink' VNFs on 'off-cloud', and all other VNFs on the
    # 'chain-server's. This is done to replicate E2 experiment, where traffic
    # generator VNF (source) and traffic sink is placed on different servers
    # (from VNFs).
    off_cloud = []
    chain_server = []
    for server_name in pn['Servers']:
        if server_name.startswith('off-cloud'):
            off_cloud.append(server_name)
        elif server_name.startswith('chain-server'):
            chain_server.append(server_name)
        else:
            glog.info('ERROR: unknown server type %s', server_name)
            sys.exit(1)

    glog.info('off_cloud: %s', off_cloud)
    glog.info('chain_server: %s', chain_server)

    # candidate_servers contains list of server names which have enough capacity
    # [cpu, ram, bandwidth] to host this VNF.
    candidate_servers = []
    allocations = {}
    assignments, bandwidth = [], []
    chain_index = 0
    enough_resources = True

    # loop until servers have resources to host VNFs. Note that partial chain
    # allocations are invalid and we ignore them (at the end of the loop).
    while enough_resources:
        for vnf_name in vn['VMs']:
            
            # iterate through each server and add it to the candidate_servers
            # list if it has enough resources to host this VNF. Then we select
            # one of these servers based on the algorithm. RoundRobin randomly
            # chooses a server from candidates while DepthFirst always chooses
            # the first server on the list.
            # Note that pn['Servers'][sname] represents [cpu, ram, bandwidth]
            # capacity of the server and vn['VMs'][vnf_name] represents VNF
            # capacity in the same order.
            if vnf_name == 'source' or vnf_name == 'sink':
                # sname means 'server name'
                for sname in off_cloud:
                    if (pn['Servers'][sname][0]-vn['VMs'][vnf_name][0] >= 0) and (
                            pn['Servers'][sname][1]-vn['VMs'][vnf_name][1] >= 0) and (
                            pn['Servers'][sname][2]-vn['VMs'][vnf_name][2] >= 0):
                        glog.info('%s has enough resources [%.4f, %.4f, %.4f]' +
                                ' to host %s [%.4f, %.4f, %.4f]', 
                            sname, pn['Servers'][sname][0],
                            pn['Servers'][sname][1], pn['Servers'][sname][2],
                            vnf_name, vn['VMs'][vnf_name][0],
                            vn['VMs'][vnf_name][1], vn['VMs'][vnf_name][2])
                        candidate_servers.append(sname)
            else: # this is a chain VNF
                for sname in chain_server:
                    if (pn['Servers'][sname][0]-vn['VMs'][vnf_name][0] >= 0) and (
                            pn['Servers'][sname][1]-vn['VMs'][vnf_name][1] >= 0) and (
                            pn['Servers'][sname][2]-vn['VMs'][vnf_name][2] >= 0):
                        glog.info('%s has enough resources [%.4f, %.4f, %.4f]' +
                                ' to host %s [%.4f, %.4f, %.4f]',
                            sname, pn['Servers'][sname][0],
                            pn['Servers'][sname][1], pn['Servers'][sname][2],
                            vnf_name, vn['VMs'][vnf_name][0],
                            vn['VMs'][vnf_name][1], vn['VMs'][vnf_name][2])
                        candidate_servers.append(sname)

            if len(candidate_servers) == 0:
                # no more VNF allocation possible. We can ignore the last
                # partial chain allocation since chains have to be fully
                # allocated to be a valid allocation.
                glog.info('candidate_servers is empty. No more allocation is' +
                    ' possible. Completed %d allocations.', (chain_index+1))
                enough_resources = False
                break

            if algo == 'round-robin':
                # randomly choose a server from the candidate list
                sname = random.choice(candidate_servers)
            elif algo == 'depth-first':
                # always choose the first server on the list. Note that Python
                # retains an order items appended to the list. Because
                # 'off_cloud' and 'chain_server' lists are constant, and we
                # iterate through these lists and append them into
                # 'candidate_servers' in the same order, choosing the first
                # server on the list always going to be the same server (as long
                # as it has enough resources to host the VNF). This is exactly
                # how depth-first algorithm operates.
                sname = candidate_servers[0]

            # empty candidate_servers for the next iteration
            candidate_servers = []
            # decrease available resources from the chosen server
            pn['Servers'][sname][0] -= vn['VMs'][vnf_name][0]
            pn['Servers'][sname][1] -= vn['VMs'][vnf_name][1]
            pn['Servers'][sname][2] -= vn['VMs'][vnf_name][2]

            assignments.append([vnf_name, sname])
            # glog.info('assignments = %s', assignments)
        
        if enough_resources:
            allocations['allocation_%d' % chain_index] = {
                    'assignment': assignments, 'bandwidth': bandwidth}

            # increment chain index and renew assignment after completing each
            # chain allocation
            chain_index += 1
            assignments = []

        # watchdog to prevent infinite loop
        if chain_index > 30: # some impossible number of allocations
            glog.info('ERROR: chain_index = %d' % chain_index)
            break

    # "allocs" has the following format
    # {'allocation_0':
    #   {'assignment': [['fw', 'chain-server0'],
    #                   ['ids', 'chain-server1']],
    #   {'bandwidth': []},
    # 'allocation_1': ...}
    # }

    # glog.info('allocations: %s' % allocations)
    return allocations


def allocate_chains(dcs, allocs):
    """ Create chains. """

    cmds = []
    fl = "large"
    chain_index = 0
    # vnfs holds array of each VNF type
    vnfs = {'source': [], 'nat': [], 'fw': [], 'ids': [], 'vpn': [], 'sink': []}

    # iterate over each allocation and create each chain
    for alloc_name, chain_mapping in allocs.iteritems():
        glog.info('started allocating chain: %d', chain_index)

        # iterate over each chain and create chain VNFs by placing it on an
        # appropriate server (such as chosen by NetSolver)..
        for vnf_mapping in chain_mapping['assignment']:
            glog.info('vnf_mapping = %s', vnf_mapping)
            vnf_name = vnf_mapping[0]
            server_name = vnf_mapping[1]
            vnf_prefix = 'chain%d' % chain_index
            vnf_id = '%s-%s' % (vnf_prefix, vnf_name)
            vnf_obj = None
            glog.info('creating %s on %s', vnf_id, server_name)

            if vnf_name == 'source':
                # create client with one interface
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                        image='knodir/client', flavor_name=fl,
                        network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})
            
            elif vnf_name == 'nat':
                # create NAT VNF with two interfaces. Its 'input'
                # interface faces the client and output interface the server VNF.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                        image='knodir/nat', flavor_name=fl,
                        network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                            {'id': 'output', 'ip': '10.0.1.4/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'fw':
                # create fw VNF with two interfaces. 'input' interface for 'client' and
                # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
                # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                        image='knodir/sonata-fw-vnf', flavor_name="xlarge",
                        network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                            {'id': 'output-ids1', 'ip': '10.0.1.60/24'},
                            {'id': 'output-ids2', 'ip': '10.0.1.61/24'},
                            {'id': 'output-vpn', 'ip': '10.0.1.62/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'ids':
                # create ids VNF with two interfaces. 'input' interface for 'fw' and
                # 'output' interface for the 'server' VNF.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                        image='knodir/snort-trusty', flavor_name=fl,
                        network=[{'id': 'input', 'ip': '10.0.1.70/24'},
                            {'id': 'output', 'ip': '10.0.1.80/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'vpn':
                # create VPN VNF with two interfaces. Its 'input'
                # interface faces the client and output interface the server VNF.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                        image='knodir/vpn-client', flavor_name=fl,
                        network=[{'id': 'input-ids1', 'ip': '10.0.1.90/24'},
                            {'id': 'input-ids2', 'ip': '10.0.1.91/24'},
                            {'id': 'input-fw', 'ip': '10.0.1.92/24'},
                            {'id': 'output', 'ip': '10.0.10.2/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'sink':
                # create server VNF with one interface. Do not change assigned 10.0.10.10/24
                # address of the server. It is the address VPN clients use to connect to the
                # server and this address is hardcoded inside client.ovpn of the vpn-client
                # Docker image. We also remove the injected routing table entry for this
                # address. So, if you change this address make sure it is changed inside
                # client.ovpn file as well as subprocess mn.vpn route injection call below.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                        image='knodir/vpn-server', flavor_name=fl,
                        network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            else:
                glog.error('ERROR: unknown VNF type: %s', vnf_name)
                sys.exit(1)

            glog.info('successfully created VNF: %s', vnf_id)

        glog.info('successfully created chain: %d', chain_index)
        chain_index += 1

    return vnfs


def plumb_chains(vnfs):
    # vnfs have the following format:
    # {fw: [{chain0_fw: obj}, {chain1_fw: obj}, ...],
    #  nat: [{chain0_nat: obj}, {chain1_nat: obj}, ...],
    #  ...}

    # execute /start.sh script inside all firewalls. It starts Ryu
    # controller and OVS with proper configuration.
    for fw_name_and_obj in vnfs['fw']:
        fw_name = fw_name_and_obj.keys()[0]
        cmd = 'sudo docker exec -i mn.%s /bin/bash /root/start.sh &' % fw_name
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)' % (execStatus, cmd))

    return

    glog.info('> sleeping 10s to wait ryu controller initialize')
    time.sleep(10)
    glog.info('< wait complete')
    glog.info('fw start done')

    # execute /start.sh script inside ids image. It bridges input and output
    # interfaces with br0, and starts ids process listering on br0.
    cmd = 'sudo docker exec -i mn.ids1 /bin/bash -c "sh /start.sh"'
    execStatus = subprocess.call(cmd, shell=True)
    glog.info('returned %d from ids1 start.sh start (0 is success)' % execStatus)

    cmd = 'sudo docker exec -i mn.ids2 /bin/bash -c "sh /start.sh"'
    execStatus = subprocess.call(cmd, shell=True)
    glog.info('returned %d from ids2 start.sh start (0 is success)' % execStatus)

    # execute /start.sh script inside nat image. It attaches both input
    # and output interfaces to OVS bridge to enable packet forwarding.
    cmd = 'sudo docker exec -i mn.nat /bin/bash /start.sh'
    execStatus = subprocess.call(cmd, shell=True)
    glog.info('returned %d from nat start.sh start (0 is success)' % execStatus)

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
        glog.info('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    glog.info('> sleeping 60s to VPN client initialize...')
    time.sleep(60)
    glog.info('< wait complete')
    glog.info('VPN client VNF started')

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
        glog.info('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    glog.info('ping client -> server after explicit chaining. Packet drop %s%%' %
          net.ping([client, server], timeout=5))

    net.CLI()
    net.stop()


if __name__ == '__main__':
    logger = logging.getLogger()
    print('logger handlers = %s' % logger.handlers)
    if len(logger.handlers) > 1:
        # when glog is included, system will just adds it as an additional log
        # handler resulting into each message being printed twice (which is bad).
        # We drop all handlers except the last one, assuming the last one is
        # glog (which seems always to be true). Comment out these lines if you
        # see different behaviour
        logger.handlers = logger.handlers[len(logger.handlers)-1:]
    print('logger handlers = %s' % logger.handlers)

    pn_fname = "../topologies/e2-1rack-8servers.pn.json"
    vn_fname = "../topologies/e2-chain-4vnfs.vn.json"

    net, api, dcs, tors = prepareDC(pn_fname)
    algos = ['netsolver', 'round-robin', 'depth-first']
    # allocs = get_placement(pn_fname, vn_fname, algos[0]) # netsolver
    # allocs = get_placement(pn_fname, vn_fname, algos[1]) # round-robin
    allocs = get_placement(pn_fname, vn_fname, algos[2]) # depth-first

    glog.info('allocs: %s' % allocs)
    # sys.exit(0)

    # allocate chains by placing them on appropriate servers
    vnfs = allocate_chains(dcs, allocs)

    # configure the datapath on chains to push packets through them
    plumb_chains(vnfs)

    net.CLI()
    net.stop()

    cleanup()
