#!/bin/bash 
sudo docker stop $(docker ps -a -q)
sudo docker rm $(docker ps -a -q)
sudo mn -c
sudo service openvswitch-switch restart
# sudo killall python
sudo killall containerd-shim
sudo killall docker
sudo killall /usr/bin/dockerd
sudo killall /usr/lib/snapd/snapd
sudo killall ryu-manager
sudo killall iperf3
ps -ef | grep python
ps -ef | grep docker
