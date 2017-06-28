#! /usr/bin/env python

import time
import subprocess

def switch_ids():
    """ Switch IDS1 with IDS2. """

    cmd = 'sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 priority=2,in_port=1"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmd = 'sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl del-flows ovs1 priority=2,in_port=2"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmd = 'sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl add-flow ovs1 priority=2,in_port=1,action=output:3"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmd = 'sudo docker exec -i mn.fw /bin/bash -c "ovs-ofctl add-flow ovs1 priority=2,in_port=3,action=output:1"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmd = 'sudo docker exec -i mn.vpn /bin/bash -c "route del -net 10.0.1.0/24 dev input-ids1"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from %s (0 is success)' % (execStatus, cmd))

    cmd = 'sudo docker exec -i mn.vpn /bin/bash -c "route add -net 10.0.1.0/24 dev input-ids2"'
    execStatus = subprocess.call(cmd, shell=True)
    print('returned %d from %s (0 is success)' % (execStatus, cmd))

    #print('> sleeping 60s to VPN client initialize...')
    #time.sleep(60)
    #print('< wait complete')


if __name__ == '__main__':
    switch_ids()
