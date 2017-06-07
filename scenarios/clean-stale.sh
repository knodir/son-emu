#!/bin/bash 

sudo killall -9 python
sudo killall -9 containerd-shim
sudo killall -9 docker

ps -ef | grep python
ps -ef | grep docker
