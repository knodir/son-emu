#!/bin/bash 

echo "start pushing latest docker images"

sudo docker push knodir/client
sudo docker push knodir/nat
sudo docker push knodir/sonate-fw-vnf
sudo docker push knodir/snort-trusty
sudo docker push knodir/snort-xenial
sudo docker push knodir/vpn-client
sudo docker push knodir/vpn-server

echo "done"
