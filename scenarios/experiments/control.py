#! /usr/bin/env python

from time import sleep
import subprocess
import cmd
import threading
import thread
import os


def switch_ids():
    """ Switch IDS1 with IDS2. """

    print('switch_ids() activated, waiting 10s before trigger')
    sleep(20)
    print('switch_ids() wait complete. Trigger the IDS switch.')

    cmds = []

    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=1,out_port=2"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=2,out_port=1"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl add-flow ovs1 priority=2,in_port=1,action=output:3"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl add-flow ovs1 priority=2,in_port=3,action=output:1"')
    # little hack to enforce immediate impact of the new OVS rule
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ip link set output-ids1 down && ip link set output-ids1 up"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "route del -net 10.0.1.0/24 dev input-ids1"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.1.0/24 dev input-ids2"')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    #print('> sleeping 60s to VPN client initialize...')
    # time.sleep(60)
    #print('< wait complete')


def switch_ids_back():
    """ Undoes everything switch_ids() did, i.e., switches IDS2 with IDS1. """

    cmds = []

    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=1,out_port=3"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=3,out_port=1"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl add-flow ovs1 priority=2,in_port=1,action=output:2"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl add-flow ovs1 priority=2,in_port=2,action=output:1"')
    # little hack to enforce immediate impact of the new OVS rule
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ip link set output-ids2 down && ip link set output-ids2 up"')

    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "route del -net 10.0.1.0/24 dev input-ids2"')
    cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.1.0/24 dev input-ids1"')

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []


def clean_stale(cmds):

    # kill existing iperf server
    #cmds.append('sudo docker exec -i mn.server /bin/bash -c "pkill iperf3"')
    # remove stale iperf output file (if any)
    #cmds.append('sudo docker exec -i mn.client /bin/bash -c "rm /tmp/iperf3.json"')
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
    sleep(3)

    return cmds


def clean_stale_alloc(num_of_chains):
    cmds = []
    # kill existing tcpreplay and dstat, and copy traces to the source VNF
    for chain_index in range(num_of_chains):
        cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "pkill tcpreplay"' % chain_index)
        cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "pkill python2"' % chain_index)
        # remove stale dstat output file (if any)
        cmds.append('sudo docker cp ../topologies/output.pcap mn.chain%d-source:/' % chain_index)

    for cmd in cmds:
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmds[:] = []

    print('cleanup done; wait 3s for stale processes cleanup')
    sleep(3)


def clean_and_save(cmds, testName):

    cmds.append('sudo docker exec -i mn.client /bin/bash -c "pkill tcpreplay"')

    print('wait 3s for iperf client and other processes terminate')
    sleep(3)
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


def set_bw():
    os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc1.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth4 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth5 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=1000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=1000000 other-config:max-rate=10000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=1000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=1000000 other-config:max-rate=10000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=1000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=1000000 other-config:max-rate=10000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth7 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=1000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=1000000 other-config:max-rate=10000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth8 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth9 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth10 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=1000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=1000000 other-config:max-rate=10000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth11 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc3.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')


def scale_bw():

    # clientPorts = subprocess.check_output(["sudo ovs-vsctl list-ports dc1.s1"], shell=True)
    # serverPorts = subprocess.check_output(["sudo ovs-vsctl list-ports dc3.s1"], shell=True)

    # for p in clientPorts.split():
    #     print(p)
    #     os.system('ovs-vsctl -- set Port ' + p + ' qos=@newqos -- \
    #  --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    #  --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    # for p in serverPorts.split():
    #     print(p)
    #     os.system('ovs-vsctl -- set Port ' + p + ' qos=@newqos -- \
    #  --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    #  --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')

    # # Client 1 continuously consumes 700 Mbps and is constrained to 800Mpbs throughput.
    # # Client 2 is limited to 200 Mbps at 100 Mbps packet rate.
    # # After 30 seconds, client 2 increases its bandwidth to 500 Mbps while client 1 drops to 300.
    # # NetSolver increases the link capacity of the second client while limiting client 1 to 450.
    # # Get switch ports
    # # print("Setting bandwidth of all links to 250 MB")
    # # for p in portList.split():
    # #     print(p)
    # #     os.system('ovs-vsctl -- set Port ' + p + ' qos=@newqos -- \
    # #  --id=@newqos create QoS type=linux-htb other-config:max-rate=10000000 queues=0=@q0 -- \
    # #  --id=@q0   create   Queue   other-config:min-rate=10000000 other-config:max-rate=100000000')

    # os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    # --id=@newqos create QoS type=linux-htb other-config:max-rate=20000000 queues=0=@q0 -- \
    # --id=@q0   create   Queue   other-config:min-rate=20000000 other-config:max-rate=200000000')
    # os.system('ovs-vsctl -- set Port dc1.s1-eth3 qos=@newqos -- \
    #     --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    #     --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')

    # # Test iPerf
    # print("Performing iPerf Test")
    # # server.cmdPrint("iperf3 -s &")
    # # client.cmdPrint("iperf3 -c 10.0.10.10 -t 10 > test.log &")
    # print("Running Server")
    # os.system('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s -V" > test_s.log &')
    # time.sleep(5)
    # # os.system('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s -p 5202 -V" > test_s2.log &')
    # # time.sleep(5)
    # # os.system('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s -p 5203 -V" > test_s3.log &')
    # # time.sleep(5)
    # # os.system('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s -p 5204 -V" > test_s4.log &')
    # # time.sleep(5)
    # print("Running Client for 30 seconds.")
    # os.system('sudo timeout 75s ../netbps dc1.s1-eth2 > client_throughput.log &')
    # # os.system('sudo timeout 75s ../netbps dc1.s1-eth3 > client2_throughput.log &')
    # os.system('sudo timeout 75s ../netbps dc3.s1-eth2 > server_throughput.log &')
    # os.system('sudo docker exec -i mn.client /bin/bash -c "iperf3 -V -u -b 1G -c 10.0.10.10 -t 60" > test_c.log &')
    # # os.system('sudo docker exec -i mn.client2 /bin/bash -c "iperf3 -V -b 1G -c 10.0.10.10 -p 5202 -t 32" > test_c2.log &')
    # # os.system('sudo tcpdump -i dc1.s1-eth3 -l -e -n | ./netbps &')
    os.system('ovs-vsctl -- set Port dc1.s1-eth1 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc1.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth3 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth4 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth5 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth6 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth7 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth8 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth9 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth10 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=2000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=2000000 other-config:max-rate=20000000')
    os.system('ovs-vsctl -- set Port dc2.s1-eth11 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')
    os.system('ovs-vsctl -- set Port dc3.s1-eth2 qos=@newqos -- \
    --id=@newqos create QoS type=linux-htb other-config:max-rate=3000000 queues=0=@q0 -- \
    --id=@q0   create   Queue   other-config:min-rate=3000000 other-config:max-rate=30000000')


class RunBench(cmd.Cmd):
    """Simple command processor example."""

    def do_q(self, line):
        # alias for quit
        return self.do_quit(line)

    def do_quit(self, line):
        # this command will make you exit from the shell
        print("quiting...")
        return True

    def do_help(self, line):
        commands = ['help', 'allocate', 'upgrade', 'switch', 'restore',
                'scaleout', 'q | quit']
        print("list of supported commands: %s" % commands)

    def default(self, line):
        # triggered when command requested does not exist
        print('error: unsupported command *%s*' % line)
        self.do_help(line)

    def emptyline(self):
        pass
        # print('-- emptyline --')

    def do_switch(self, line):
        """ Switch from IDS1 to IDS2. """
        switch_ids()

    def do_restore(self, line):
        """ Restore IDS1 connectivity. """
        switch_ids_back()

    def do_scaleout(self, line):
        """ Start traffic generation. """

        # list of commands to execute one-by-one
        cmds = []
        # clean stale programs and remove old files
        cmds.append('sudo rm ./results/scaleout-from-client.csv')
        cmds.append('sudo rm ./results/scaleout-from-ids1.csv')
        cmds.append('sudo rm ./results/scaleout-from-vpn.csv')

        cmds = clean_stale(cmds)

        # Set the initial bandwidth constraints of the system
        set_bw()
        sleep(3)
        # cmds.append('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s --bind 10.8.0.1" &')
        # cmds.append('sudo docker exec -i mn.client /bin/bash -c "dstat --net --time -N intf1 --bits --output /tmp/dstat.csv" &')
        # cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "dstat --net --time -N input --bits --output /tmp/dstat.csv" &')
        # cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "dstat --net --time -N input-fw --bits --output /tmp/dstat.csv" &')
        cmds.append('sudo timeout 70 dstat --net --time -N dc1.s1-eth1 --nocolor --output ./results/scaleout-from-client.csv &')
        cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth7 --nocolor --output ./results/scaleout-from-ids1.csv &')
        cmds.append('sudo timeout 70 dstat --net --time -N dc2.s1-eth4 --nocolor --output ./results/scaleout-from-vpn.csv &')

        # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
        cmds.append('sudo docker exec -i mn.client /bin/bash -c "tcpreplay --loop=100 --mbps=10 -d 1 --intf1=intf1 /ftp.ready.pcap" &')
        # each loop is around 40s for 10 Mbps speed, 2 loops easily make 1m
        cmds.append('sudo docker exec -i mn.client /bin/bash -c "tcpreplay --loop=2 --mbps=10 -d 1 --intf1=intf1 /output.pcap" &')

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))
        cmds[:] = []
        print("Generating traffic for 30 seconds")

        # start scaling up the bandwidth after 30 seconds
        sleep(30)
        print("Scaling up bandwidth by factor of 1")
        scale_bw()
        sleep(40)
        # clean and save the results in csv file named after the test
        # cmds = clean_and_save(cmds, "scaleout")
        cmds.append('sudo killall dstat')
        print('done')

    def do_upgrade(self, line):
        """ Start traffic generation. """

        # list of commands to execute one-by-one
        cmds = []

        # clean stale programs and remove old files
        cmds = clean_stale(cmds)

        # cmds.append('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s --bind 10.8.0.1" &')
        cmds.append('sudo docker exec -i mn.client /bin/bash -c "dstat --net --time -N intf1 --bits --output /tmp/dstat.csv" &')
        cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "dstat --net --time -N input --bits --output /tmp/dstat.csv" &')
        cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "dstat --net --time -N input --bits --output /tmp/dstat.csv" &')
        cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "dstat --net --time -N input-fw --bits --output /tmp/dstat.csv" &')
        # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
        cmds.append('sudo docker exec -i mn.client /bin/bash -c "tcpreplay --loop=100 --mbps=10 -d 1 --intf1=intf1 /ftp.ready.pcap" &')

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        print('wait 3s for iperf server and other processes initialize')
        sleep(3)

        # start ids switch functionality which triggers after 10s
        thread.start_new_thread(switch_ids, ())

        # start iperf client or replay enterprise traces
        # cmd = 'sudo docker exec -i mn.client /bin/bash -c "iperf3 -c 10.8.0.1 -t 60 -b 10M --no-delay --omit 0 --json --logfile /tmp/iperf3.json"'
        # each loop is around 40s for 10 Mbps speed, 2 loops easily make 1m
        cmd = 'sudo docker exec -i mn.client /bin/bash -c "tcpreplay --loop=2 --mbps=10 -d 1 --intf1=intf1 /output.pcap"'
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

        # clean and save the results in csv file named after the test
        cmds = clean_and_save(cmds, "upgrade")

        print('done')


    def do_allocate(self, line):
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

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        for chain_index in range(num_of_chains):
            cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "dstat --net --time -N tun0 --bits --output /tmp/dstat.csv" &' % chain_index)

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []
        print('>>> wait 10s for dstats to initialize')
        sleep(10)
        print('<<< wait complete.')

        for chain_index in range(num_of_chains):
            # each loop is around 1s for 10 Mbps speed, 100 loops easily make 1m
            cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "tcpreplay --loop=0 --mbps=100 -d 1 --intf1=intf1 /output.pcap" &' % chain_index)

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        print('>>> wait 60s to complete the experiment')
        sleep(120)
        print('<<< wait complete.')

        # kill existing tcpreplay and dstat
        for chain_index in range(num_of_chains):
            cmds.append('sudo docker exec -i mn.chain%d-source /bin/bash -c "pkill tcpreplay"' % chain_index)
            cmds.append('sudo docker exec -i mn.chain%d-sink /bin/bash -c "pkill python2"' % chain_index)

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        print('>>> wait 10s for dstats to terminate')
        sleep(10)
        print('<<< wait complete.')

        # copy .csv results from VNF to the host
        for chain_index in range(num_of_chains):
            cmds.append('sudo docker cp mn.chain%d-sink:/tmp/dstat.csv ./results/e2-allocate-from-chain%d-sink.csv' % (chain_index, chain_index))

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
    RunBench().cmdloop()
    # switch_ids()
