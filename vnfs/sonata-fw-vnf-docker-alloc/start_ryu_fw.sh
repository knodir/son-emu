#! /bin/bash
echo "FW container started"

echo "start ryu learning switch"

echo "Start ovs"
service openvswitch-switch start

# Configuration parameters of the switch can for example be configured by a docker environment variable
# but configuration is not yet implemented in the (dummy) gatekeeper, so we hard code it for now
# also controller ip address should be configured by a service controller after vnfs are deployed and assigned an ip address
NODEID="$1"
NODEID=$(($NODEID+1))
NAME="ovs-$NODEID"
OVS_DPID=$(printf "%016d" $NODEID)
API_PORT=$(($NODEID+8080))
OF_PORT=$((NODEID+6633))
ryu-manager ryu.app.rest_firewall --wsapi-port $API_PORT --ofp-tcp-listen-port $OF_PORT &

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
CONTROLLER_IP="127.0.0.1"
CONTROLLER="tcp:$CONTROLLER_IP:$OF_PORT"
ovs-vsctl set-controller $NAME $CONTROLLER

sleep 20
curl -X PUT http://localhost:$API_PORT/firewall/module/enable/$OVS_DPID
echo "setup generic forwarding for PCAP traffic"
curl -X POST -d '{"nw_src": "10.0.0.0/8", "nw_dst": "10.0.0.0/8"}' http://localhost:$API_PORT/firewall/rules/$OVS_DPID
