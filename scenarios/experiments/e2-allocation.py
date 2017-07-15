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


def prepareDC(pn_fname, max_cu, max_mu):
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
                    dc_emulation_max_cpu=max_cu, dc_emulation_max_mem=max_mu,
                    enable_learning=True)

    # Read physical topology from file.
    with open(pn_fname) as data_file:
        data = json.load(data_file)

    glog.info('read data center description from JSON file %s' % data['Servers'])

    dcs = {}
    for name, props in data['Servers'].iteritems():
        dcs[name] = net.addDatacenter(name)

    rms = {}
    for name, props in data['Servers'].iteritems():
        rms[name] = UpbSimpleCloudDcRM(max_cu, max_mu)

    for dc_name, dc_obj in dcs.iteritems():
        dc_obj.assignResourceModel(rms[dc_name])
        glog.info('assigned resource model %s to %s', id(rms[dc_name]), dc_name)

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

# def prepareDC():
#     """ Prepares physical topology to place chains. """

#     # We use Sonata data center construct to simulate physical servers (just
#     # servers hereafter). The reason is that Sonata DC has CPU/RAM resource
#     # constraints just like the servers. We also model the links between servers
#     # with bandwidth constraints of Sonata switch-to-DC link.

#     # The topology we create below is one rack with two servers. The rack has
#     # ToR switches (Sonata switch called "tor1"), to place chain VNFs.

#     # Similar to the paper story of middlebox-as-a-server, we will put client
#     # and server (traffic source and sink) outside the DC.

#     # Here is the reason why we do not use Sonata "host" to model the servers.
#     # Sonata uses Mininet host construct as-is. Mininet "host" supports only CPU
#     # resource constraint. Therefore, we do not use Sonata "host" construct.

#     # Unless otherwise specified, we always use "server" for variables and
#     # description instead of "DC". This should avoid confusion with terminology.

#     # add resource model (rm) to limit cpu/ram available in each server. We
#     # create one resource mode and use it for all servers, meaning all of our
#     # servers are homogeneous. Create multiple RMs for heterogeneous servers
#     # (with different amount of cpu,ram).
#     MAX_CU = 8  # max compute units
#     MAX_MU = 3500  # max compute units

#     # the cpu, ram resource above are consumed by VNFs with one of these
#     # flavors. For some reason memory allocated for tiny flavor is 42 MB,
#     # instead of 32 MB in this systems. Other flavors are multipliers of this
#     # 42 MB (as expected).
#     # "tiny",  {"compute": 0.5, "memory": 32, "disk": 1}
#     # "small",  {"compute": 1.0, "memory": 128, "disk": 20}
#     # "medium",  {"compute": 4.0, "memory": 256, "disk": 40}
#     # "large",  {"compute": 8.0, "memory": 512, "disk": 80}
#     # "xlarge",  {"compute": 16.0, "memory": 1024, "disk": 160}
#     #
#     # Note that all these container VNFs need at least 500 MB of memory to be
#     # able to work. Firewall in particular, runs OVS, needs more than 1 GB to be
#     # able to process packets. If you do not allocate sufficient CPU, system
#     # behaves bad. In most cases all physical cores gets pinned (probably
#     # because of the contention between OVS and cgroup mem limitation) and
#     # Sonata VM OOM killer starts killing random processes.

#     net = DCNetwork(controller=RemoteController, monitor=True,
#                     dc_emulation_max_cpu=64, dc_emulation_max_mem=28000,
#                     enable_learning=True)

#     # create registrars
#     # reg_E52680 = ResourceModelRegistrar(MAX_CU_E52680, MAX_MU_E52680)
#     # reg_E52680_2 = ResourceModelRegistrar(MAX_CU_E52680, MAX_MU_E52680)
#     # reg_E52650 = ResourceModelRegistrar(MAX_CU_E52650, MAX_MU_E52650)
#     # reg_E52650_2 = ResourceModelRegistrar(MAX_CU_E52650, MAX_MU_E52650)
#     # reg_E52650_3 = ResourceModelRegistrar(MAX_CU_E52650, MAX_MU_E52650)

#     # create data center resource models per data center
#     rm_1 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_2 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_3 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_4 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_5 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_6 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_7 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     rm_8 = UpbSimpleCloudDcRM(MAX_CU, MAX_MU)
#     # # attach individual resource models
#     # reg_E52680.register("homogeneous_rm_E52680_1", rm_E52680_1)
#     # reg_E52680.register("homogeneous_rm_E52680_2", rm_E52680_1)
#     # reg_E52650.register("homogeneous_rm_E52650_1", rm_E52650_1)
#     # reg_E52650.register("homogeneous_rm_E52650_2", rm_E52650_1)
#     # reg_E52650.register("homogeneous_rm_E52650_3", rm_E52650_1)

#     # add 8 servers
#     off_cloud_1 = net.addDatacenter('off-cloud1')  # place client/server VNFs
#     off_cloud_2 = net.addDatacenter('off-cloud2')  # place client/server VNFs
#     off_cloud_3 = net.addDatacenter('off-cloud3')  # place client/server VNFs
#     off_cloud_4 = net.addDatacenter('off-cloud4')  # place client/server VNFs
#     chain_server_1 = net.addDatacenter('chain-server1')
#     chain_server_2 = net.addDatacenter('chain-server2')
#     chain_server_3 = net.addDatacenter('chain-server3')
#     chain_server_4 = net.addDatacenter('chain-server4')

#     off_cloud_1.assignResourceModel(rm_1)
#     off_cloud_2.assignResourceModel(rm_2)
#     off_cloud_3.assignResourceModel(rm_3)
#     off_cloud_4.assignResourceModel(rm_4)
#     chain_server_1.assignResourceModel(rm_5)
#     chain_server_2.assignResourceModel(rm_6)
#     chain_server_3.assignResourceModel(rm_7)
#     chain_server_4.assignResourceModel(rm_8)
#     # connect data centers with switches
#     tor1 = net.addSwitch('tor1')

#     # link data centers and switches
#     net.addLink(off_cloud_1, tor1)
#     net.addLink(off_cloud_2, tor1)
#     net.addLink(off_cloud_3, tor1)
#     net.addLink(off_cloud_4, tor1)
#     net.addLink(chain_server_1, tor1)
#     net.addLink(chain_server_2, tor1)
#     net.addLink(chain_server_3, tor1)
#     net.addLink(chain_server_4, tor1)

#     # create REST API endpoint
#     api = RestApiEndpoint("0.0.0.0", 5001)

#     # connect API endpoint to containernet
#     api.connectDCNetwork(net)

#     # connect data centers to the endpoint
#     api.connectDatacenter(off_cloud_1)
#     api.connectDatacenter(off_cloud_2)
#     api.connectDatacenter(off_cloud_3)
#     api.connectDatacenter(off_cloud_4)
#     api.connectDatacenter(chain_server_1)
#     api.connectDatacenter(chain_server_2)
#     api.connectDatacenter(chain_server_3)
#     api.connectDatacenter(chain_server_4)

#     # start API and containernet
#     api.start()
#     net.start()

#     return (net, api, [off_cloud_1, off_cloud_2, off_cloud_3, off_cloud_4, chain_server_1, chain_server_2, chain_server_3, chain_server_4])
#     # return (net, dc, api)


def get_placement(pn_fname, vn_fname, algo):
    """ Does chain placement with NetSolver and returns the output. """

    if algo == 'netsolver':
        glog.info('using NetSolver for chain allocation')

        out_fname = '/tmp/ns_out.json'
        # cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s" % (
        cmd = "export PYTHONHASHSEED=1 && python3 %s %s %s --output %s --no-repeat" % (
            "../../../monosat_datacenter/src/vdcmapper.py", pn_fname,
            vn_fname, out_fname)
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

    # all following code is for round-robin and depth-first allocations

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

    # get bandwidth for each VNF. Note that we assume VN format (of input JSON
    # file) is [vnf_source, vnf_destination, bandwidth_amount] and there is no
    # duplicate for VNF src-dst pair. This is true since we handcraft chain JSON
    # files (but something to be aware if JSON is auto-generated, where the VNF
    # order might get mixed).
    vnf_bws = {}
    for vnf in vn['VN']:
        vnf_name = vnf[0]
        if vnf_name in vnf_bws.keys():
            vnf_bws[vnf_name] += vnf[2]
        else:
            vnf_bws[vnf_name] = vnf[2]
        last_vnf_name = vnf[1]
    # following must be a 'sink' VNF, which does not appear as a 'source' VNF
    # (as the first element) at all, but we need to add it as a VNF too.
    vnf_bws[last_vnf_name] = vnf[2]

    glog.info('vnf_bws: %s', vnf_bws)

    # candidate_servers contains list of server names which have enough capacity
    # [cpu, ram, bandwidth] to host this VNF.
    candidate_servers = []
    allocations = {}
    assignments, bandwidth = [], []
    assignments_dict = {}
    chain_index = 0
    enough_resources = True

    # loop until servers have resources to host VNFs. Note that partial chain
    # allocations are invalid and we ignore them (at the end of the loop).
    while enough_resources:
        for vnf_name in vn['VMs']:
            vnf_cpu = vn['VMs'][vnf_name][0] * vnf_bws[vnf_name]
            vnf_ram = vn['VMs'][vnf_name][1] * vnf_bws[vnf_name]
            vnf_bw = vn['VMs'][vnf_name][2] * vnf_bws[vnf_name]
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
                    if (pn['Servers'][sname][0] - vnf_cpu >= 0) and (
                            pn['Servers'][sname][1] - vnf_ram >= 0) and (
                            pn['Servers'][sname][2] - vnf_bw >= 0):
                        # glog.info('%s has enough resources [%.4f, %.4f, %.4f]'+
                        glog.debug('%s has enough resources [%.4f, %.4f, %.4f]' +
                                   ' to host %s [%.4f, %.4f, %.4f]', sname,
                                   pn['Servers'][sname][0],
                                   pn['Servers'][sname][1],
                                   pn['Servers'][sname][2], vnf_name, vnf_cpu,
                                   vnf_ram, vnf_bw)
                        candidate_servers.append(sname)
            else:  # this is a chain VNF
                for sname in chain_server:
                    if (pn['Servers'][sname][0] - vnf_cpu >= 0) and (
                            pn['Servers'][sname][1] - vnf_ram >= 0) and (
                            pn['Servers'][sname][2] - vnf_bw >= 0):
                        # glog.info('%s has enough resources [%.4f, %.4f, %.4f]'+
                        glog.debug('%s has enough resources [%.4f, %.4f, %.4f]' +
                                   ' to host %s [%.4f, %.4f, %.4f]', sname,
                                   pn['Servers'][sname][0],
                                   pn['Servers'][sname][1],
                                   pn['Servers'][sname][2], vnf_name, vnf_cpu,
                                   vnf_ram, vnf_bw)
                        candidate_servers.append(sname)

            if len(candidate_servers) == 0:
                # no more VNF allocation possible. We can ignore the last
                # partial chain allocation since chains have to be fully
                # allocated to be a valid allocation.
                glog.info('candidate_servers is empty. No more allocation is' +
                          ' possible. Completed %d allocations.', chain_index)
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
            pn['Servers'][sname][0] -= vnf_cpu
            pn['Servers'][sname][1] -= vnf_ram
            pn['Servers'][sname][2] -= vnf_bw
            glog.info('Server %s CPU: %s', sname, pn['Servers'][sname][0])
            glog.info('Server %s RAM: %s', sname, pn['Servers'][sname][1])
            glog.info('Server %s BW: %s', sname, pn['Servers'][sname][2])

            # Note that we do not decrease link bandwidth on ToR switch because
            # we know this is a single rack environment (all servers are
            # connected to the same ToR switch). On a single rack topology,
            # decrementing the server bandwidth suffice because ToR switch
            # provides full bisection bandwidth. This will not be true for
            # multi-rack topologies (watch out Sam) without full bisection
            # bandwidth (ToR-to-OtherSwitch links can get saturated before
            # server-to-ToR links).

            assignments.append([vnf_name, sname])
            assignments_dict[vnf_name] = sname

        glog.debug('assignments = %s', assignments)
        glog.debug('assignments_dict = %s', assignments_dict)

        if enough_resources:
            # do not deduct bandwidth from server-to-ToR link if the VNF pair
            # is assigned to the same server. Since the code above already
            # deducts the bandwidth we just increase the same amount back.
            for pair in vn['VN']:
                glog.debug('pair = %s', pair)
                if ('source' in pair) or ('sink' in pair):
                    # ignore source and sink VNFs since they are always placed
                    # on different server than other VNFs.
                    continue
                if assignments_dict[pair[0]] == assignments_dict[pair[1]]:
                    glog.debug('both %s are assigned to the same server %s',
                               pair, assignments_dict[pair[0]])
                    pn['Servers'][sname][2] += vn['VMs'][pair[0]][2] * vnf_bws[pair[0]]
                    pn['Servers'][sname][2] += vn['VMs'][pair[1]][2] * vnf_bws[pair[1]]

            # add this chain allocation to the list of allocations
            allocations['allocation_%d' % chain_index] = {
                'assignment': assignments, 'bandwidth': bandwidth}

            # increment chain index and renew assignment after completing each
            # chain allocation
            chain_index += 1
            assignments = []
            assignments_dict = {}

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
    """ Create chains by assigning VNF to their respective server. """

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
                                                        image='knodir/client', flavor_name="nat",
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
                # create fw VNF with two interfaces. 'input' interface for 'client' and
                # 'output' interface for the 'ids' VNF. Both interfaces are bridged to
                # ovs1 bridge. knodir/sonata-fw-vnf has OVS and Ryu controller.
                vnf_obj = dcs[server_name].startCompute(vnf_id,
                                                        image='knodir/sonata-fw-vnf', flavor_name="fw",
                                                        network=[{'id': 'input', 'ip': '10.0.1.5/24'},
                                                                 {'id': 'output-ids', 'ip': '10.0.1.61/24'},
                                                                 {'id': 'output-vpn', 'ip': '10.0.1.62/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

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
                                                        image='knodir/vpn-server', flavor_name="nat",
                                                        network=[{'id': 'intf2', 'ip': '10.0.10.10/24'}])
                vnfs[vnf_name].append({vnf_id: vnf_obj})

            else:
                glog.error('ERROR: unknown VNF type: %s', vnf_name)
                sys.exit(1)

            glog.info('successfully created VNF: %s', vnf_id)

        glog.info('successfully created chain: %d', chain_index)
        chain_index += 1

    return vnfs


def plumb_chains(vnfs, num_of_chains):
    # vnfs have the following format:
    # {fw: [{chain0_fw: obj}, {chain1_fw: obj}, ...],
    #  nat: [{chain0_nat: obj}, {chain1_nat: obj}, ...],
    #  ...}

    # execute /start.sh script inside all firewalls. It starts Ryu
    # controller and OVS with proper configuration.
    for vnf_name_and_obj in vnfs['fw']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmd = 'sudo docker exec -i mn.%s /bin/bash /root/start.sh &' % vnf_name
        execStatus = subprocess.call(cmd, shell=True)
        glog.info('returned %d from %s (0 is success)', execStatus, cmd)

    glog.info('> sleeping 10s to let ryu controller initialize properly')
    time.sleep(10)
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

    # chain 'client <-> nat <-> fw <-> ids <-> vpn <-> server'
    for chain_index in range(num_of_chains):
        pair_src_name = vnfs['source'][chain_index].keys()[0]
        pair_dst_name = vnfs['nat'][chain_index].keys()[0]
        net.setChain(pair_src_name, pair_dst_name, 'intf1', 'input',
                     bidirectional=True, cmd='add-flow')
        glog.info('successfully chained %s and %s', pair_src_name, pair_dst_name)

        pair_src_name = vnfs['nat'][chain_index].keys()[0]
        pair_dst_name = vnfs['fw'][chain_index].keys()[0]
        net.setChain(pair_src_name, pair_dst_name, 'output', 'input',
                     bidirectional=True, cmd='add-flow')
        glog.info('successfully chained %s and %s', pair_src_name, pair_dst_name)

        pair_src_name = vnfs['fw'][chain_index].keys()[0]
        pair_dst_name = vnfs['ids'][chain_index].keys()[0]
        net.setChain(pair_src_name, pair_dst_name, 'output-ids', 'input',
                     bidirectional=True, cmd='add-flow')
        glog.info('successfully chained %s and %s', pair_src_name, pair_dst_name)

        pair_src_name = vnfs['fw'][chain_index].keys()[0]
        pair_dst_name = vnfs['vpn'][chain_index].keys()[0]
        net.setChain(pair_src_name, pair_dst_name, 'output-vpn', 'input-fw',
                     bidirectional=True, cmd='add-flow')
        glog.info('successfully chained %s and %s', pair_src_name, pair_dst_name)

        pair_src_name = vnfs['ids'][chain_index].keys()[0]
        pair_dst_name = vnfs['vpn'][chain_index].keys()[0]
        net.setChain(pair_src_name, pair_dst_name, 'output', 'input-ids',
                     bidirectional=True, cmd='add-flow')
        glog.info('successfully chained %s and %s', pair_src_name, pair_dst_name)

        pair_src_name = vnfs['vpn'][chain_index].keys()[0]
        pair_dst_name = vnfs['sink'][chain_index].keys()[0]
        net.setChain(pair_src_name, pair_dst_name, 'output', 'intf2',
                     bidirectional=True, cmd='add-flow')
        glog.info('successfully chained %s and %s', pair_src_name, pair_dst_name)

    cmds = []

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

    glog.info('> sleeping 60s to VPN client initialize...')
    time.sleep(60)
    glog.info('< wait complete')
    glog.info('VPN client VNF started')

    for vnf_name_and_obj in vnfs['sink']:
        vnf_name = vnf_name_and_obj.keys()[0]
        # rewrite NAT VNF MAC addresses for tcpreplay
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ifconfig input hw ether 00:00:00:00:00:02"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.10.0/24 dev output"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ip route add 10.8.0.0/24 dev output"' % vnf_name)

    for vnf_name_and_obj in vnfs['sink']:
        vnf_name = vnf_name_and_obj.keys()[0]
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "route add -net 10.0.0.0/24 dev input-ids"' % vnf_name)
        cmds.append('sudo docker exec -i mn.%s /bin/bash -c "ip route del 10.0.10.10/32"' % vnf_name)
        #cmds.append('sudo docker exec -i mn.server /bin/bash -c "route add -net 10.0.0.0/24 dev intf2"')

    for vnf_name_and_obj in vnfs['sink']:
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

    source_vnfs, sink_vnfs = [], []
    for vnf_name_and_obj in vnfs['source']:
        vnf_name = vnf_name_and_obj.keys()[0]
        source_vnfs.append(vnf_name)

    for vnf_name_and_obj in vnfs['sink']:
        vnf_name = vnf_name_and_obj.keys()[0]
        sink_vnfs.append(vnf_name)

    glog.info('source_vnf = %s, sink_vnfs = %s', source_vnfs, sink_vnfs)

    for chain_index in range(num_of_chains):
        glog.info('ping %s -> %s. Packet drop %s%%', source_vnfs[chain_index],
                  sink_vnfs[chain_index], net.ping([source_vnfs[chain_index],
                                                    sink_vnfs[chain_index]], timeout=5))


if __name__ == '__main__':
    logger = logging.getLogger()
    print('logger handlers = %s' % logger.handlers)
    if len(logger.handlers) > 1:
        # when glog is included, system will just adds it as an additional log
        # handler resulting into each message being printed twice (which is bad).
        # We drop all handlers except the last one, assuming the last one is
        # glog (which seems always to be true). Comment out these lines if you
        # see different behaviour
        logger.handlers = logger.handlers[len(logger.handlers) - 1:]
    print('logger handlers = %s' % logger.handlers)

    vn_fname = "../topologies/e2-chain-4vnfs.vn.json"
    pn_fname = "../topologies/e2-nss-1rack-8servers.pn.json"
    #pn_fname = "../topologies/e2-azure-1rack-24servers.pn.json"
    #pn_fname = "../topologies/e2-azure-1rack-48servers.pn.json"

    # allocate servers (Sonata DC construct) to place chains
    net, api, dcs, tors = prepareDC(pn_fname, 8, 3584)

    algos = ['netsolver', 'round-robin', 'depth-first']
    # allocs = get_placement(pn_fname, vn_fname, algos[0])  # netsolver
    # allocs = get_placement(pn_fname, vn_fname, algos[1])  # round-robin
    allocs = get_placement(pn_fname, vn_fname, algos[2])  # depth-first

    glog.info('allocs: %s; len = %d', allocs, len(allocs))
    # sys.exit(0)

    # allocate chains by placing them on appropriate servers
    vnfs = allocate_chains(dcs, allocs)

    # configure the datapath on chains to push packets through them
    plumb_chains(vnfs, len(allocs))

    net.CLI()
    net.stop()

    cleanup()

    os.system("sudo ../clean-stale.sh")