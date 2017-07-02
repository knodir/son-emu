#! /usr/bin/env python

from time import sleep
import subprocess
import cmd
import threading
import thread


def switch_ids():
    """ Switch IDS1 with IDS2. """

    print('switch_ids() activated, waiting 10s before trigger')
    sleep(20)
    print('switch_ids() wait complete. Trigger the IDS switch.')

    cmds = []

    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=1"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=2"')
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
    #time.sleep(60)
    #print('< wait complete')

def switch_ids_back():
    """ Undoes everything switch_ids() did, i.e., switches IDS2 with IDS1. """

    cmds = []

    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=1"')
    cmds.append('sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 in_port=3"')
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


class RunBench(cmd.Cmd):
    """Simple command processor example."""

    def do_q(self, line):
        # alias for quit
        return self.do_quit(line)

    def do_quit(self, line):
        #this command will make you exit from the shell
	print("quiting...")
        return True

    def do_help(self, line):
        commands = ['help', 'start', 'switch', 'restore', 'q | quit']
        print("list of supported commands: %s" % commands)

    def default(self, line):
        # triggered when command requested does not exists
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


    def do_start(self, line):
	""" Start traffic generation. """

        # list of commands to execute one-by-one
        cmds = []

        # kill existing iperf server 
        cmds.append('sudo docker exec -i mn.server /bin/bash -c "pkill iperf3"')
        # remove stale iperf output file (if any)
        cmds.append('sudo docker exec -i mn.client /bin/bash -c "rm /tmp/iperf3.json"')
        # kill existing dstat 
        cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "pkill python2"')
        cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "pkill python2"')
        cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "pkill python2"')
        # remove stale dstat output file (if any)
        cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "rm /tmp/dstat.csv"')
        cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "rm /tmp/dstat.csv"')
        cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "rm /tmp/dstat.csv"')

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        print('wait 3s for iperf server and other stale processes cleanup')
        sleep(3)
 
        cmds.append('sudo docker exec -i mn.server /bin/bash -c "iperf3 -s --bind 10.8.0.1" &')
        cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "dstat --net --time -N input --bits --output /tmp/dstat.csv" &')
        cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "dstat --net --time -N input --bits --output /tmp/dstat.csv" &')
        cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "dstat --net --time -N input-fw --bits --output /tmp/dstat.csv" &')

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        print('wait 3s for iperf server and other processes initialize')
        sleep(3)
 
        # start ids switch functionality which triggers after 10s
        thread.start_new_thread(switch_ids, ())
        # t1 = threading.Thread(target=switch_ids)

        # start iperf client
        cmd = 'sudo docker exec -i mn.client /bin/bash -c "iperf3 -c 10.8.0.1 -t 60 -b 10M --no-delay --omit 0 --json --logfile /tmp/iperf3.json"'
        execStatus = subprocess.call(cmd, shell=True)
        print('returned %d from %s (0 is success)' % (execStatus, cmd))

        print('wait 3s for iperf client and other processes terminate')
        sleep(3)
 
        # kill dstat inside ids. dstat runs as python2 process.
        cmds.append('sudo docker exec -i mn.ids1 /bin/bash -c "pkill python2"')
        cmds.append('sudo docker exec -i mn.ids2 /bin/bash -c "pkill python2"')
        cmds.append('sudo docker exec -i mn.vpn /bin/bash -c "pkill python2"')
        # copy the iperf client output file to the local machine
        cmds.append('sudo docker cp mn.client:/tmp/iperf3.json ./output/from-client.json')
        cmds.append('sudo docker cp mn.ids1:/tmp/dstat.csv ./output/from-ids1.csv')
        cmds.append('sudo docker cp mn.ids2:/tmp/dstat.csv ./output/from-ids2.csv')
        cmds.append('sudo docker cp mn.vpn:/tmp/dstat.csv ./output/from-vpn.csv')
        # do remaining cleanup inside containers
        cmds.append('sudo docker exec -i mn.server /bin/bash -c "pkill iperf3"')

        for cmd in cmds:
            execStatus = subprocess.call(cmd, shell=True)
            print('returned %d from %s (0 is success)' % (execStatus, cmd))

        cmds[:] = []

        print('done')


if __name__ == '__main__':
    RunBench().cmdloop()
    # switch_ids()
