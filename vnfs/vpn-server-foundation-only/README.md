# VPN server

WARNING: do not generate and push docker vpn-server image directly built from
this Dockerfile. vpn-server image contains additional (critical) changes on top
of this basic image (hence the folder is called 'foundation-only').

How to prepare knodir/vpn-server docker image:
- create docker instance from "cd son-emu/vnfs/vpn-server"
- follow this tutorial to create server (and client.ovpn files)
  https://www.digitalocean.com/community/tutorials/how-to-set-up-an-openvpn-server-on-ubuntu-14-04

In the tutorial make sure to use correct interface name, e.g.,
in /etc/ufw/before.rules
-A POSTROUTING -s 10.8.0.0/8 -o eth0 -j MASQUERADE 
+A POSTROUTING -s 10.0.10.10/8 -o input -j MASQUERADE 

