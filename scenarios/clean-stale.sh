#!/bin/bash 

sudo docker stop $(docker ps -a -q)
sudo docker rm $(docker ps -a -q)
sudo mn -c
sudo killall python
sudo killall containerd-shim
sudo killall docker
sudo killall /usr/bin/dockerd
ps -ef | grep python
ps -ef | grep docker
