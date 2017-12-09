import time
import sys
import random
import subprocess
import logging
import json
import os
import glog
import inspect

import nfv
from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM

from mininet.cli import CLI
from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.node import DefaultController
from optparse import OptionParser


def executeCmds(cmds):
    if isinstance(cmds, basestring):
        execStatus = subprocess.call(cmds, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmds))
    else:
        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))
    return execStatus


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

    net = DCNetwork(controller=DefaultController, monitor=False,
                    dc_emulation_max_cpu=max_cu_net,
                    dc_emulation_max_mem=max_mu_net,
                    enable_learning=False)
    ram_factor = 512
    cpu_factor = 1
    # Read physical topology from file.
    with open(pn_fname) as data_file:
        data = json.load(data_file)

    glog.info('read data center description from JSON file %s' %
              data['Servers'])

    dcs = {}
    for name, props in data['Servers'].iteritems():
        if name == "gsw":
            continue
        dcs[name] = net.addDatacenter(name)

    rms = {}
    for name, props in data['Servers'].iteritems():
        json_cpu = props[0]
        json_ram = props[1]
        rms[name] = UpbSimpleCloudDcRM(json_cpu * cpu_factor, json_ram * ram_factor)

    for dc_name, dc_obj in dcs.iteritems():
        dc_obj.assignResourceModel(rms[dc_name])
        glog.info('assigned resource model %s to %s',
                  id(rms[dc_name]), dc_name)

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
        os.system('sudo ovs-vsctl set Bridge' + dcs[pn_item[0]].name + ' rstp_enable=true')
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
    # "allocs" has the following format
    # {'allocation_0':
    #   {'assignment': [['fw', 'chain-server0'],
    #                   ['ids', 'chain-server1']],
    #   {'bandwidth': []},
    # 'allocation_1': ...}
    # }
    if algo == 'daisy':
        glog.info('using Daisy for chain allocation')

        out_fname = '/tmp/ns_out.json'
        # cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s --no-repeat" % (
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s %s" % (
            "../../../monosat_datacenter/src/netsolver_nfv.py", pn_fname,
            vn_fname, out_fname, '--max-resource 4')
    elif algo == 'packing':
        glog.info('using packing for chain allocation')

        out_fname = '/tmp/ns_out.json'
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s %s %s %s" % (
            "../../../monosat_datacenter/src/simple_nfv.py", pn_fname,
            vn_fname, "--output", out_fname, "--locality")
    elif algo == 'random':
        glog.info('using random for chain allocation')

        out_fname = '/tmp/ns_out.json'
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s %s %s %s" % (
            "../../../monosat_datacenter/src/simple_nfv.py", pn_fname,
            vn_fname, "--output", out_fname, "--random")
    else:
        glog.error('ERROR: unsupported allocation algorithm: %s' % algo)
        sys.exit(1)

    execStatus = executeCmds(cmd)
    if execStatus == 1:
        glog.info("allocation failed")
        return execStatus
    glog.info("allocation succeeded")

    # Read physical topology from file.
    with open(out_fname) as data_file:
        allocs = json.load(data_file)
    return allocs


def get_chain_mappings(allocs):
    # iterate over each allocation and create each chain
    chain_mappings = []
    for alloc_name, chain_mapping in allocs.iteritems():
        if not alloc_name.startswith('allocation'):
            glog.info('not an allocation, but metadata: %s', alloc_name)
            continue
        # glog.info('Chain Mapping: %s', chain_mapping)
        chain_mappings.append(chain_mapping)

    return chain_mappings


def allocate_chains(dcs, mappings, chain_index=None):
    """ Create chains by assigning VNF to their respective server. """

    # vnfs holds array of each VNF type
    vnfs = {'source': [], 'nat': [], 'fw': [], 'ids': [], 'vpn': [], 'sink': []}

    if chain_index is None:
        chain_index = 0
    print(mappings)
    for chain_mapping in mappings:
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
                                                        image='knodir/sonata-fw-iptables2', flavor_name="fw",
                                                        network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                                                                 {'id': 'output-ids',
                                                                     'ip': '10.0.1.61/24'},
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
                                                                 {'id': 'input-fw',
                                                                     'ip': '10.0.2.5/24'},
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


def chain_vnfs(net, vnfs, chain_index):
    pair_src_name = vnfs['source'][chain_index].keys()[0]
    pair_dst_name = vnfs['nat'][chain_index].keys()[0]
    res = net.setChain(pair_src_name, pair_dst_name, 'intf1', 'input',
                       bidirectional=True, cmd='add-flow')
    glog.info('chain(%s, %s) output: %s',
              pair_src_name, pair_dst_name, res)

    pair_src_name = vnfs['nat'][chain_index].keys()[0]
    pair_dst_name = vnfs['fw'][chain_index].keys()[0]
    res = net.setChain(pair_src_name, pair_dst_name, 'output', 'input',
                       bidirectional=True, cmd='add-flow')
    glog.info('chain(%s, %s) output: %s',
              pair_src_name, pair_dst_name, res)

    pair_src_name = vnfs['fw'][chain_index].keys()[0]
    pair_dst_name = vnfs['ids'][chain_index].keys()[0]
    res = net.setChain(pair_src_name, pair_dst_name, 'output-ids', 'input',
                       bidirectional=True, cmd='add-flow')
    glog.info('chain(%s, %s) output: %s',
              pair_src_name, pair_dst_name, res)

    pair_src_name = vnfs['fw'][chain_index].keys()[0]
    pair_dst_name = vnfs['vpn'][chain_index].keys()[0]
    res = net.setChain(pair_src_name, pair_dst_name, 'output-vpn', 'input-fw',
                       bidirectional=True, cmd='add-flow')
    glog.info('chain(%s, %s) output: %s',
              pair_src_name, pair_dst_name, res)

    pair_src_name = vnfs['ids'][chain_index].keys()[0]
    pair_dst_name = vnfs['vpn'][chain_index].keys()[0]
    res = net.setChain(pair_src_name, pair_dst_name, 'output', 'input-ids',
                       bidirectional=True, cmd='add-flow')
    glog.info('chain(%s, %s) output: %s',
              pair_src_name, pair_dst_name, res)

    pair_src_name = vnfs['vpn'][chain_index].keys()[0]
    pair_dst_name = vnfs['sink'][chain_index].keys()[0]
    res = net.setChain(pair_src_name, pair_dst_name, 'output', 'intf2',
                       bidirectional=True, cmd='add-flow')
    glog.info('chain(%s, %s) output: %s',
              pair_src_name, pair_dst_name, res)


def ping_test(net, vnfs, chain_index):
    src_vnf_name = vnfs['source'][chain_index].keys()[0]
    dst_vnf_name = vnfs['sink'][chain_index].keys()[0]
    src_vnf_obj = vnfs['source'][chain_index][src_vnf_name]
    dst_vnf_obj = vnfs['sink'][chain_index][dst_vnf_name]

    ping_res = net.ping([src_vnf_obj, dst_vnf_obj], timeout=10)

    glog.info('ping %s -> %s. Packet drop %s%%',
              src_vnf_name, dst_vnf_name, ping_res)


def plumb_chains(net, vnfs, num_of_chains, chain_index=None):
    # vnfs have the following format:
    # {fw: [{chain0_fw: obj}, {chain1_fw: obj}, ...],
    #  nat: [{chain0_nat: obj}, {chain1_nat: obj}, ...],
    #  ...}
    cmds = []

    for vnf_name_and_obj in vnfs['source']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds = nfv.init_source(vnf_name)
    executeCmds(cmds)
    cmds[:] = []

    # execute /start.sh script inside nat image. It attaches both input
    # and output interfaces to OVS bridge to enable packet forwarding.
    for vnf_name_and_obj in vnfs['nat']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds = nfv.init_nat(vnf_name)
    executeCmds(cmds)
    cmds[:] = []

    # execute /start.sh script inside all firewalls. It starts Ryu
    # controller and OVS with proper configuration.
    for vnf_name_and_obj in vnfs['fw']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds = nfv.init_fw(vnf_name)
    executeCmds(cmds)
    cmds[:] = []

    glog.info('source, nat, and fw start done')
    glog.info('My commands' % cmds)

    # try:
    #     input('Pause1 ')
    # except SyntaxError:
    #     print('Proceeding')

    # execute /start.sh script inside ids image. It bridges input and output
    # interfaces with br0, and starts ids process listering on br0.
    for vnf_name_and_obj in vnfs['ids']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds = nfv.init_ids(vnf_name)
    executeCmds(cmds)
    cmds[:] = []

    glog.info('> sleeping 2s to let ids initialize properly...')
    time.sleep(2)
    glog.info('< 2s wait complete')
    glog.info('start VNF chaining')

    # chain 'client <-> nat <-> fw <-> ids <-> vpn <-> server'
    if chain_index is None:
        for chain_index in range(num_of_chains):
            chain_vnfs(net, vnfs, chain_index)
    else:
        chain_vnfs(net, vnfs, 0)

    for vnf_name_and_obj in vnfs['sink']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds = nfv.init_sink(vnf_name)
    executeCmds(cmds)
    cmds[:] = []

    for vnf_name_and_obj in vnfs['vpn']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds = nfv.init_vpn(vnf_name)
    executeCmds(cmds)
    cmds[:] = []

    glog.info('> sleeping 5s to let VPN client initialize...')
    time.sleep(5)
    glog.info('< 5s wait complete')
    glog.info('VPN client VNF started')

    if chain_index is None:
        for chain_index in range(num_of_chains):
            ping_test(net, vnfs, chain_index)
    else:
        ping_test(net, vnfs, 0)
