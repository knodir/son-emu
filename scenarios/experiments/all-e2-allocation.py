import time
import sys
import random
import subprocess
import logging
import json
import os
import glog

from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM

from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.node import DefaultController
from optparse import OptionParser


def prepareDC(pn_fname, max_cu, max_mu, max_cu_net, max_mu_net):
    """ Prepares physical topology to place chains. """

    # TODO(nodir): explain compute and memory resource consumption models
    # according to https://github.com/sonata-nfv/son-emu/issues/238

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
    # behaves badly. In most cases all physical cores gets pinned (probably
    # because of the contention between OVS and cgroup mem limitation) and
    # Sonata VM OOM killer starts killing random processes.

    net = DCNetwork(controller=RemoteController, monitor=False,
                    dc_emulation_max_cpu=max_cu_net,
                    dc_emulation_max_mem=max_mu_net,
                    enable_learning=True)

    # Read physical topology from file.
    with open(pn_fname) as data_file:
        data = json.load(data_file)

    glog.info('read data center description from JSON file %s' % data['Servers'])

    dcs = {}
    for name, props in data['Servers'].iteritems():
        if name == "gsw":
            continue
        dcs[name] = net.addDatacenter(name)

    rms = {}
    for name, props in data['Servers'].iteritems():
        rms[name] = UpbSimpleCloudDcRM(max_cu, max_mu)

    for dc_name, dc_obj in dcs.iteritems():
        dc_obj.assignResourceModel(rms[dc_name])
        glog.info('assigned resource model %s to %s', id(rms[dc_name]), dc_name)

    glog.info('PN read from JSON file %s' % data['PN'])

    tors = {}

    # Extract ToR switch names. ToR are the ones not listed as 'Servers'. Note
    # that this code is generic for multi-rack topology, which can have fields
    # like
    # ['server-name', 'tor-name', bw], ['tor-name', 'aggr-sw-name', bw],
    # ['aggr-sw-name', 'gw-sw-name', bw] ...
    # From this example, we need to include 'tor-name', 'aggr-sw-name', and
    # 'gw-sw-name' to tors list.
    # iterate through each PN item and assign None object to the tor. Later,
    # None will be replaced with the ToR object (see net.addSwitch() below).
    for pn_item in data['PN']:
        glog.info('Accessing %s for switch %s', pn_item[0], pn_item[1])
        # check if this item is not 'Server' and also is not already included to
        # tors list.
        if (pn_item[0] not in data['Servers'].keys()) and (
                pn_item[0] not in tors.keys()):
            # glog.info(pn_item[0])
            tors[pn_item[0]] = None

        # same comment as above, but for the second item
        if ((pn_item[1] not in data['Servers'].keys()) or pn_item[1] == "gsw") and (
                pn_item[1] not in tors.keys()):
            # glog.info(pn_item[1])
            tors[pn_item[1]] = None

    # connect ToR switches and DC per PN topology
    index = 0
    for tor_name in tors.keys():
        tors[tor_name] = net.addSwitch(tor_name + str(index))
        index += 1

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

    return (net, api, dcs, tors)


def get_placement(pn_fname, vn_fname, algo):
    """ Does chain placement with Daisy and returns the output. """

    if algo == 'daisy':
        glog.info('using Daisy for chain allocation')

        out_fname = '/tmp/ns_out.json'
        # cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s --no-repeat" % (
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s %s" % (
            "../../../monosat_datacenter/src/netsolver_nfv.py", pn_fname,
            vn_fname, out_fname, '--max-resource 4')
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
    elif algo == 'packing':
        glog.info('using packing for chain allocation')

        out_fname = '/tmp/ns_out.json'
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s %s %s %s" % (
            "../../../monosat_datacenter/src/simple_nfv.py", pn_fname,
            vn_fname, "--output", out_fname, "--locality")
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

    elif algo == 'random':
        glog.info('using random for chain allocation')

        out_fname = '/tmp/ns_out.json'
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s %s %s %s" % (
            "../../../monosat_datacenter/src/simple_nfv.py", pn_fname,
            vn_fname, "--output", out_fname, "--random")
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

    else:
        glog.error('ERROR: unsupported allocation algorithm: %s' % algo)
        sys.exit(1)

    # "allocs" has the following format
    # {'allocation_0':
    #   {'assignment': [['fw', 'chain-server0'],
    #                   ['ids', 'chain-server1']],
    #   {'bandwidth': []},
    # 'allocation_1': ...}
    # }

    # glog.info('allocations: %s' % allocations)
    return allocs


def allocate_chains(dcs, allocs):
    """ Create chains by assigning VNF to their respective server. """

    fl = "large"
    chain_index = 0
    # vnfs holds array of each VNF type
    vnfs = {'source': [], 'nat': [], 'fw': [], 'ids': [], 'vpn': [], 'sink': []}

    # iterate over each allocation and create each chain
    for alloc_name, chain_mapping in allocs.iteritems():
        if not alloc_name.startswith('allocation'):
            glog.info('not an allocation, but metadata: %s', alloc_name)
            continue
        glog.info('started allocating chain: %d', chain_index)
        try:
            glog.info('Chain Mapping: %s', chain_mapping['assignment'])
        except TypeError:
            glog.info('Chain Mapping: %f', chain_mapping)

        # iterate over each chain and create chain VNFs by placing it on an
        # appropriate server (such as chosen by Daisy)..
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
                                                        image='knodir/client', flavor_name="source",
                                                        network=[{'id': 'intf1', 'ip': '10.0.0.2/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'nat':
                # create NAT VNF with two interfaces. Its 'input'
                # interface faces the client and output interface the server VNF.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                                                        image='knodir/nat', flavor_name="nat",
                                                        network=[{'id': 'input', 'ip': '10.0.0.3/24'},
                                                                 {'id': 'output', 'ip': '10.0.1.4/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'fw':
                # create fw VNF with three interfaces. 'input' interface for
                # 'nat', 'output-ids' interface for 'ids' VNF, and 'output-vpn'
                # for VPN VNF. All three interfaces are bridged to ovs1 bridge.
                # knodir/sonata-fw-vnf:alloc image  has OVS and Ryu controller,
                # and is specifically designed for e2-allocations experiment.
                # node-upgrade experiment requires knodir/sonata-fw-vnf:upgrade
                # image as it has an additional interface for ids2.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                                                        image='knodir/sonata-fw-iptables', flavor_name="fw",
                                                        network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                                                                 {'id': 'output-ids', 'ip': '10.0.1.61/24'},
                                                                 {'id': 'output-vpn', 'ip': '10.0.2.4/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})
                # os.system("sudo docker update --cpu-shares 200000 " + vnf_id)

            elif vnf_name == 'ids':
                # create ids VNF with two interfaces. 'input' interface for 'fw' and
                # 'output' interface for the 'server' VNF.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                                                        image='knodir/snort-trusty', flavor_name="ids",
                                                        network=[{'id': 'input', 'ip': '10.0.1.70/24'},
                                                                 {'id': 'output', 'ip': '10.0.1.80/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            elif vnf_name == 'vpn':
                # create VPN VNF with two interfaces. Its 'input'
                # interface faces the client and output interface the server VNF.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                                                        image='knodir/vpn-client', flavor_name="vpn",
                                                        network=[{'id': 'input-ids', 'ip': '10.0.1.91/24'},
                                                                 {'id': 'input-fw', 'ip': '10.0.2.5/24'},
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
                                                        image='knodir/vpn-server', flavor_name="sink",
                                                        network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})
                # os.system("sudo docker update --cpus 64 --cpuset-cpus 0-63 " + vnf_id)

            else:
                glog.error('ERROR: unknown VNF type: %s', vnf_name)
                sys.exit(1)

            glog.info('successfully created VNF: %s', vnf_id)

        glog.info('successfully created chain: %d', chain_index)
        chain_index += 1
    return vnfs


def plumb_chains(net, vnfs, num_of_chains):
    # vnfs have the following format:
    # {fw: [{chain0_fw: obj}, {chain1_fw: obj}, ...],
    #  nat: [{chain0_nat: obj}, {chain1_nat: obj}, ...],
    #  ...}
    cmds = []

    # execute /start.sh script inside all firewalls. It starts Ryu
    # controller and OVS with proper configuration.
    vnf_index = 0
    for vnf_name_and_obj in vnfs['fw']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds.append('sudo docker exec mn.%s /root/start.sh %s &' % (vnf_name, vnf_index))
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.10.0/24 dev output-ids"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route del -net 10.0.1.0/24 dev output-ids"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route del -net 10.0.1.0/24 dev input"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.8.0.0/24 dev output-ids"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.0.0/24 dev input"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.1.0/26 dev input"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.1.0/24 dev output-ids"' % vnf_name)
        vnf_index = vnf_index + 1
    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    glog.info('> sleeping 2s to let ryu controller initialize properly')
    time.sleep(2)
    glog.info('< wait complete')
    glog.info('fw start done')

    # execute /start.sh script inside ids image. It bridges input and output
    # interfaces with br0, and starts ids process listering on br0.
    for vnf_name_and_obj in vnfs['ids']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmd = 'sudo docker exec -i mn.%s /bin/bash -c "sh /start.sh"' % vnf_name
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)', execStatus, cmd)

    # execute /start.sh script inside nat image. It attaches both input
    # and output interfaces to OVS bridge to enable packet forwarding.
    for vnf_name_and_obj in vnfs['nat']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmd = 'sudo docker exec -i mn.%s /bin/bash /start.sh' % vnf_name
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)', execStatus, cmd)

    glog.info('> sleeping 2s to let fw, ids, nat initialize properly...')
    time.sleep(2)
    glog.info('< 5s wait complete')
    glog.info('start VNF chaining')

    # chain 'client <-> nat <-> fw <-> ids <-> vpn <-> server'
    for chain_index in range(num_of_chains):
        pair_src_name = vnfs['source'][chain_index].keys()[0]
        pair_dst_name = vnfs['nat'][chain_index].keys()[0]
        res = net.setChain(pair_src_name, pair_dst_name, 'intf1', 'input',
                           bidirectional=True, cmd='add-flow')
        glog.info('chain(%s, %s) output: %s', pair_src_name, pair_dst_name, res)

        pair_src_name = vnfs['nat'][chain_index].keys()[0]
        pair_dst_name = vnfs['fw'][chain_index].keys()[0]
        res = net.setChain(pair_src_name, pair_dst_name, 'output', 'input',
                           bidirectional=True, cmd='add-flow')
        glog.info('chain(%s, %s) output: %s', pair_src_name, pair_dst_name, res)

        pair_src_name = vnfs['fw'][chain_index].keys()[0]
        pair_dst_name = vnfs['ids'][chain_index].keys()[0]
        res = net.setChain(pair_src_name, pair_dst_name, 'output-ids', 'input',
                           bidirectional=True, cmd='add-flow')
        glog.info('chain(%s, %s) output: %s', pair_src_name, pair_dst_name, res)

        pair_src_name = vnfs['fw'][chain_index].keys()[0]
        pair_dst_name = vnfs['vpn'][chain_index].keys()[0]
        res = net.setChain(pair_src_name, pair_dst_name, 'output-vpn', 'input-fw',
                           bidirectional=True, cmd='add-flow')
        glog.info('chain(%s, %s) output: %s', pair_src_name, pair_dst_name, res)

        pair_src_name = vnfs['ids'][chain_index].keys()[0]
        pair_dst_name = vnfs['vpn'][chain_index].keys()[0]
        res = net.setChain(pair_src_name, pair_dst_name, 'output', 'input-ids',
                           bidirectional=True, cmd='add-flow')
        glog.info('chain(%s, %s) output: %s', pair_src_name, pair_dst_name, res)

        pair_src_name = vnfs['vpn'][chain_index].keys()[0]
        pair_dst_name = vnfs['sink'][chain_index].keys()[0]
        res = net.setChain(pair_src_name, pair_dst_name, 'output', 'intf2',
                           bidirectional=True, cmd='add-flow')
        glog.info('chain(%s, %s) output: %s', pair_src_name, pair_dst_name, res)

    for vnf_name_and_obj in vnfs['sink']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"' % vnf_name)
        # start openvpn server and related services inside openvpn server
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ufw enable"' % vnf_name)
        # open iperf3 port (5201) on firewall (ufw)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ufw allow 5201"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ufw status"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "service openvpn start"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "service openvpn status"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "service rsyslog start"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "service rsyslog status"' % vnf_name)

    for vnf_name_and_obj in vnfs['vpn']:
        vnf_name = vnf_name_and_obj.keys()[0]
        # execute /start.sh script inside VPN client to connect to VPN server.
        cmds.append('sudo docker exec -i mn.%s /bin/bash /start.sh &' % vnf_name)

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    glog.info('> sleeping 10s to let VPN client initialize...')
    time.sleep(10)
    glog.info('< 10s wait complete')
    glog.info('VPN client VNF started')

    for vnf_name_and_obj in vnfs['nat']:
        vnf_name = vnf_name_and_obj.keys()[0]
        # rewrite NAT VNF MAC addresses for tcpreplay
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ifconfig input hw ether 00:00:00:00:00:02"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.10.0/24 dev output"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ip route add 10.8.0.0/24 dev output"' % vnf_name)

    for vnf_name_and_obj in vnfs['vpn']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.0.0/24 dev input-ids"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ip route del 10.0.10.10/32"' % vnf_name)

    for vnf_name_and_obj in vnfs['source']:
        vnf_name = vnf_name_and_obj.keys()[0]
        # rewrite client VNF MAC addresses for tcpreplay
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ifconfig intf1 hw ether 00:00:00:00:00:01"' % vnf_name)
        # manually chain routing table entries on VNFs
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.0.0/16 dev intf1"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.8.0.0/24 dev intf1"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ping -i 0.1 -c 10 10.0.10.10"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ping -i 0.1 -c 10 10.8.0.1"' % vnf_name)

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)' % (execStatus, cmd))
    cmds[:] = []

    for chain_index in range(num_of_chains):
        src_vnf_name = vnfs['source'][chain_index].keys()[0]
        dst_vnf_name = vnfs['sink'][chain_index].keys()[0]
        src_vnf_obj = vnfs['source'][chain_index][src_vnf_name]
        dst_vnf_obj = vnfs['sink'][chain_index][dst_vnf_name]

        ping_res = net.ping([src_vnf_obj, dst_vnf_obj], timeout=10)

        glog.info('ping %s -> %s. Packet drop %s%%',
                  src_vnf_name, dst_vnf_name, ping_res)


def benchmark(algo, line, mbps):
    """ Allocate E2 style chains. """

    # list of commands to execute one-by-one
    cmds = []
    num_of_chains = int(line)

    # kill existing tcpreplay and dstat, and copy traces to the source VNF
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "pkill tcpreplay"' % chain_index)
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "pkill python2"' % chain_index)
        # remove stale dstat output file (if any)
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "rm /tmp/dstat.csv"' % chain_index)
        cmds.append('sudo docker cp ../traces/output.pcap mn.chain%d-source:/' % chain_index)

    cmds.append('sudo rm -f ./results/allocation/%s%s/*.csv' %
                (algo, str(mbps)))
    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    for chain_index in range(num_of_chains):
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "dstat --net --time -N intf2 --bits --output /tmp/dstat.csv" &' % chain_index)
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "iperf3 -s" &' % chain_index)

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []
    print('>>> wait 10s for dstats to initialize')
    time.sleep(10)
    print('<<< wait complete.')

    for chain_index in range(num_of_chains):
        # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
        # cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "tcpreplay --loop=0 --mbps=%d -d 1 --intf1=intf1 /output.pcap" &' % (chain_index, mbps))
        cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "iperf3 --verbose --zerocopy  -b %dm -c 10.0.10.10 -t 86400" &' % (chain_index, mbps))

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    print('>>> wait 60s to complete the experiment')
    time.sleep(60)
    print('<<< wait complete.')

    # kill existing tcpreplay and dstat
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "pkill tcpreplay"' % chain_index)
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "pkill python2"' % chain_index)
        cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "killall iperf3"' % chain_index)
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "killall iperf3"' % chain_index)

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    print('>>> wait 10s for dstats to terminate')
    time.sleep(10)
    print('<<< wait complete.')
    cmds.append('mkdir ./results/allocation/%s%s' %
                (algo, str(mbps)))
    # copy .csv results from VNF to the host
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker cp mn.chain%s-sink:/tmp/dstat.csv ./results/allocation/%s%s/e2-allocate-from-chain%s-sink.csv' %
                    (str(chain_index), algo, str(mbps), str(chain_index)))

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    # remove dstat output files
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "rm /tmp/dstat.csv"' % chain_index)

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    print('done')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    parser = OptionParser()
    parser.add_option("-t", "--topo", dest="topology",
                      help="Specifiy the NSS topology")

    (options, args) = parser.parse_args()
    topology = options.topology

    # net, api, dcs, tors = prepareDC(pn_fname, 8, 3584, 64, 28672)

    # vn_fname = "../topologies/e2-chain-4vnfs-8wa.vn.json"
    # e2-azure-1rack-24servers
    # pn_fname = "../topologies/e2-azure-1rack-24servers.pn.json"
    # net, api, dcs, tors = prepareDC(pn_fname, 20, 17408, 1200, 417792)

    # vn_fname = "../topologies/e2-chain-4vnfs-8wa.vn.json"
    # e2-azure-1rack-48servers (or 50 servers)
    # pn_fname = "../topologies/e2-azure-1rack-48servers.pn.json"
    # net, api, dcs, tors = prepareDC(pn_fname, 10, 8704, 600, 417792)
    # max_cu_net = 600 => 10 dc_cu x 60 physical cores
    if topology == "1":
        # e2-nss-1rack-8servers
        pn_fname = "../topologies/e2-nss-1rack-8servers.pn.json"
        vn_fname = "../topologies/e2-chain-4vnfs-8wa.vn.json"
        compute = 8
    elif topology == "2":
        # e2-azure-1rack-50servers with 10 compute
        vn_fname = "../topologies/e2-chain-4vnfs-50wa.vn.json"
        pn_fname = "../topologies/e2-azure-1rack-50servers.pn.json"
        compute = 10
    else:
        # e2-azure-1rack-50servers with 20 compute
        vn_fname = "../topologies/e2-chain-4vnfs-50wa.vn.json"
        pn_fname = "../topologies/e2-azure-1rack-50-20servers.pn.json"
        compute = 20
    algos = ['daisy', 'random', 'packing']
    bandwidths = [10, 100]
    # algos = ['daisy']

    for mbps in bandwidths:
        for algo in algos:
            # start API and containernet
            if topology == "1":
                # e2-nss-1rack-8servers
                net, api, dcs, tors = prepareDC(pn_fname, 8, 3584, 64, 28672)
            elif topology == "2":
                # e2-azure-1rack-50servers with 10 compute
                net, api, dcs, tors = prepareDC(pn_fname, 10, 8704, 600, 417792)
            else:
                # e2-azure-1rack-50servers with 20 compute
                net, api, dcs, tors = prepareDC(pn_fname, 20, 8704, 1200, 417792)
            api.start()
            net.start()

            # allocate servers (Sonata DC construct) to place chains
            # we use 'random' and 'packing' terminology as E2 uses (see fig. 9)
            allocs = get_placement(pn_fname, vn_fname, algo)  # daisy
            # allocs = get_placement(pn_fname, vn_fname, algos[1])  # random
            # allocs = get_placement(pn_fname, vn_fname, algos[2])  # packing
            num_of_chains = 0
            for alloc in allocs:
                if alloc.startswith('allocation'):
                    num_of_chains += 1

            glog.info('allocs: %s; num_of_chains = %d', allocs, num_of_chains)
            # sys.exit(0)
            # allocate chains by placing them on appropriate servers
            vnfs = allocate_chains(dcs, allocs)
            # configure the datapath on chains to push packets through them
            plumb_chains(net, vnfs, num_of_chains)
            glog.info('successfully plumbed %d chains', num_of_chains)
            glog.info('Chain setup done. You should see the terminal now.')
            algo = algo + str(compute) + "_"
            benchmark(algo=algo, line=num_of_chains, mbps=mbps)
            net.stop()
            cleanup()
            os.system("sudo ../clean-stale.sh")
