#!/bin/bash 

echo "start pulling latest docker images"

sudo docker pull knodir/client
sudo docker pull knodir/nat
sudo docker pull knodir/sonata-fw-vnf
sudo docker pull knodir/snort-trusty
sudo docker pull knodir/snort-xenial
sudo docker pull knodir/vpn-client
sudo docker pull knodir/vpn-server
sudo docker pull knodir/sonata-fw-iptables
sudo docker pull knodir/sonata-fw-iptables2
sudo docker pull knodir/sonata-fw-fixed
sudo docker pull knodir/sonata-fw-fixed2
sudo docker pull knodir/sonata-fw-ryu

echo "done"
