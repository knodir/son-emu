import time
import logging
import os
import glog

import daisy
import bench

from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.dcemulator.resourcemodel.upb.simple import UpbSimpleCloudDcRM


from mininet.cli import CLI
from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.node import DefaultController
from optparse import OptionParser





def iterative_benchmark(allocs, dcs, mbps):
    chain_index = 0
    for alloc_name, chain_mapping in allocs.iteritems():
        if not alloc_name.startswith('allocation'):
            glog.info('not an allocation, but metadata: %s', alloc_name)
            continue
        glog.info('started allocating chain: %d', chain_index)
        vnfs = daisy.allocate_chains(dcs, [chain_mapping], chain_index)
        daisy.plumb_chains(net, vnfs, 1, chain_index)
        # os.system('sudo pkill -f "bash --norc -is mininet"')
        bench.start_benchmark(algo, 1, mbps, chain_index)
        chain_index += 1


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
    bandwidths = [10]
    # algos = ['daisy']
    # print(inspect.getmodule(DCNetwork).__file__)
    os.system("ulimit -n 100000")

    for mbps in bandwidths:
        for algo in algos:
            # start API and containernet
            if topology == "1":
                # e2-nss-1rack-8servers
                net, api, dcs, tors = daisy.prepareDC(pn_fname, 8, 3584, 64, 28672)
            elif topology == "2":
                # e2-azure-1rack-50servers with 10 compute
                net, api, dcs, tors = daisy.prepareDC(
                    pn_fname, 10, 8704, 600, 417792)
            else:
                # e2-azure-1rack-50servers with 20 compute
                net, api, dcs, tors = daisy.prepareDC(
                    pn_fname, 20, 8704, 1200, 417792)
            api.start()
            net.start()
            # allocate servers (Sonata DC construct) to place chains
            # we use 'random' and 'packing' terminology as E2 uses (see fig. 9)
            allocs = daisy.get_placement(pn_fname, vn_fname, algo)
            num_of_chains = 0
            for alloc in allocs:
                if alloc.startswith('allocation'):
                    num_of_chains += 1
            # glog.info('allocs: %s' % allocs)
            iterative_benchmark(allocs, dcs, mbps)

            glog.info('Chain setup done. You should see the terminal now.')

            print('>>> wait 600s to complete the experiment')
            time.sleep(600)
            print('<<< wait complete.')
            print('Cleaning up benchmarking information')
            bench.finish_benchmark(algo, num_of_chains, mbps)
            net.stop()

            cleanup()
            os.system("sudo ../clean-stale.sh")
