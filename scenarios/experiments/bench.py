import time
import os
import glog

from daisy import executeCmds


def start_benchmark(algo, num_of_chains, mbps, chain_index=None, isIperf=False):
    """ Allocate E2 style chains. """
    # list of commands to execute one-by-one
    cmds = []
    if isIperf:
        glog.info('Launching iperf instead of tcpreplay...')
        dirname = "%s%s-iperf" % (algo, str(mbps))
    else:
        dirname = "%s%s" % (algo, str(mbps))

    cmds.append('sudo rm -f ./results/allocation/%s/*.csv' %
                (dirname))
    executeCmds(cmds)
    cmds[:] = []

    # # copy the traces into the containers for tcpreplay, this might take a while
    if not isIperf:
        glog.info('Copying traces into the containers...')
        if chain_index is None:
            for chain_index in range(num_of_chains):
                cmds.append('sudo docker cp ../traces/output.pcap mn.chain%d-source:/' % chain_index)
        else:
            cmds.append('sudo docker cp ../traces/output.pcap mn.chain%d-source:/' % chain_index)
        executeCmds(cmds)
        cmds[:] = []

    # # copy the traces into the containers for tcpreplay, this might take a while
    glog.info('Running dstat...')
    if chain_index is None:
        for chain_index in range(num_of_chains):
            cmds.append('sudo docker exec -d mn.chain%d-sink dstat --net --time -N intf2 --bits --output /tmp/dstat.csv' % chain_index)
            if isIperf:
                cmds.append('sudo docker exec mn.chain%d-sink iperf3 -s' % chain_index)
    else:
        cmds.append('sudo docker exec -d mn.chain%d-sink dstat --net --time -N intf2 --bits --output /tmp/dstat.csv' % chain_index)
        if isIperf:
            cmds.append('sudo docker exec -d mn.chain%d-sink iperf3 -s' % chain_index)
    executeCmds(cmds)
    cmds[:] = []

    print('>>> wait 2s for dstats to initialize')
    time.sleep(2)
    print('<<< wait complete.')

    if chain_index is None:
        for chain_index in range(num_of_chains):
            # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
            if isIperf:
                cmds.append('sudo docker exec -d mn.chain%d-source iperf3 --zerocopy  -b %dm -c 10.0.10.10' %
                            (chain_index, mbps))
            else:
                cmds.append('sudo docker exec -d mn.chain%d-source tcpreplay --loop=0 --mbps=%d -d 1 --intf1=intf1 output.pcap' %
                            (chain_index, mbps))
    else:
        # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
        if isIperf:
            cmds.append('sudo docker exec -d mn.chain%d-source iperf3 --zerocopy -t 86400 -b %dm -c 10.0.10.10' %
                        (chain_index, mbps))
        else:
            cmds.append('sudo docker exec -d mn.chain%d-source tcpreplay --loop=0 --mbps=%d -d 1 --intf1=intf1 output.pcap' %
                        (chain_index, mbps))
    executeCmds(cmds)
    cmds[:] = []


def finish_benchmark(algo, num_of_chains, mbps, isIperf=False):

    # list of commands to execute one-by-one
    cmds = []

    if isIperf:
        dirname = "%s%s-iperf" % (algo, str(mbps))
    else:
        dirname = "%s%s" % (algo, str(mbps))
    # kill existing tcpreplay and dstat
    # for chain_index in range(num_of_chains):
    #     cmds.append(
    #         'sudo docker exec mn.chain%d-source pkill tcpreplay' % chain_index)
    #     cmds.append(
    #         'sudo docker exec mn.chain%d-sink pkill python2' % chain_index)
    cmds.append("sudo killall tcpreplay")
    cmds.append("sudo killall python2")
    cmds.append("sudo killall iperf3")
    executeCmds(cmds)
    cmds[:] = []

    print('>>> wait 10s for dstats to terminate')
    time.sleep(10)
    print('<<< wait complete.')

    # create the target folder if it does not exist
    dir = 'results/iter-allocation/%s' % (dirname)
    if not os.path.exists(dir):
        os.makedirs(dir)

    # copy .csv results from VNF to the host
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker cp mn.chain%s-sink:/tmp/dstat.csv ./results/iter-allocation/%s/e2-allocate-from-chain%s-sink.csv' %
                    (str(chain_index), dirname, str(chain_index)))
    executeCmds(cmds)
    cmds[:] = []

    # remove dstat output files
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker exec mn.chain%d-sink rm /tmp/dstat.csv' % chain_index)
    executeCmds(cmds)
    cmds[:] = []

    print('done')
