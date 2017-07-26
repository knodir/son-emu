#!/bin/bash 

echo "start pushing latest docker images"

sudo docker push knodir/client
sudo docker push knodir/nat
sudo docker push knodir/sonata-fw-vnf
sudo docker push knodir/snort-trusty
sudo docker push knodir/snort-xenial
sudo docker push knodir/vpn-client
sudo docker push knodir/vpn-server
sudo docker push knodir/sonata-fw-iptables1
sudo docker push knodir/sonata-fw-iptables2
sudo docker push knodir/sonata-fw-fixed
sudo docker push knodir/sonata-fw-fixed2
sudo docker push knodir/sonata-fw-ryu
echo "done"
