#!/bin/bash 
sudo mn -c
sudo docker stop $(docker ps -a -q)
sudo docker rm $(docker ps -a -q)
sudo service openvswitch-switch restart
# sudo killall python
sudo killall containerd-shim
sudo killall docker
sudo killall /usr/bin/dockerd
sudo killall /usr/lib/snapd/snapd
ps -ef | grep python
ps -ef | grep docker
