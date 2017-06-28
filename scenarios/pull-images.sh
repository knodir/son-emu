#!/bin/bash 

echo "start pulling latest docker images"

sudo docker pull knodir/client
sudo docker pull knodir/nat
sudo docker pull knodir/sonate-fw-vnf
sudo docker pull knodir/snort-trusty
sudo docker pull knodir/snort-xenial
sudo docker pull knodir/vpn-client
sudo docker pull knodir/vpn-server

echo "done"
