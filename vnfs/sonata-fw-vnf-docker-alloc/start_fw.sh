#! /bin/bash
echo "Fixed FW container started"

#echo "start ryu learning switch"
# ryu-manager --verbose ryu.app.simple_switch_13 ryu.app.ofctl_rest 2>&1 | tee ryu.log &


echo "Start ovs"
service openvswitch-switch start

# Configuration parameters of the switch can for example be configured by a docker environment variable
# but configuration is not yet implemented in the (dummy) gatekeeper, so we hard code it for now
# also controller ip address should be configured by a service controller after vnfs are deployed and assigned an ip address
NODEID="$1"
NODEID=$(($NODEID+1))
NAME="ovs-$NODEID"
OVS_DPID=$(printf "%016d" $NODEID)

# declare an array variable holding the ovs port names
# the interfaces are expected to be configured from the vnfd or nsd
declare -a PORTS=("input" "output-ids" "output-vpn")

echo "setup ovs bridge"
ovs-vsctl add-br $NAME
#ovs-dpctl add-dp $NAME

echo "skipping datapath setup"
ovs-vsctl set bridge $NAME datapath_type=netdev
#ovs-vsctl set bridge $NAME protocols=OpenFlow10,OpenFlow12,OpenFlow13
#ovs-vsctl set-fail-mode $NAME secure
#ovs-vsctl set bridge $NAME other_config:disable-in-band=true
ovs-vsctl set bridge $NAME other-config:datapath-id=$OVS_DPID

## now loop through the PORTS array
for i in "${PORTS[@]}"
do
   echo "added port $i to switch $NAME"
   ovs-vsctl add-port $NAME $i
   #ovs-dpctl add-if $NAME $i

   # or do whatever with individual element of the array
done


# configuration after startup (needs CONTROLLER_IP):
# use localhost as interface for ryu <-> ovs 
# since both are running in the same VNF
#CONTROLLER_IP="127.0.0.1"
#CONTROLLER="tcp:$CONTROLLER_IP:6633"
#ovs-vsctl set-controller $NAME $CONTROLLER
echo "Wait 2 seconds for openvswitch to initialize"
sleep 2
echo "setup generic forwarding for PCAP traffic"
ovs-ofctl add-flow $NAME 'priority=2,in_port=1,action=output:2'
ovs-ofctl add-flow $NAME 'priority=2,in_port=2,action=output:1'
# send ftp traffic (port 20, 21) over port #3 (output-vpn, directly to VPN)
ovs-ofctl add-flow $NAME 'priority=3,in_port=1,tcp,tp_src=20,actions=output:3'
ovs-ofctl add-flow $NAME 'priority=3,in_port=3,tcp,tp_src=20,actions=output:1'
ovs-ofctl add-flow $NAME 'priority=3,in_port=1,tcp,tp_src=21,actions=output:3'
ovs-ofctl add-flow $NAME 'priority=3,in_port=3,tcp,tp_src=21,actions=output:1'