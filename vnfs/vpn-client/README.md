# OpenVPN client VNF

This is modified version of snort-ids-vnf example, but stripped down the snort
https://github.com/sonata-nfv/son-examples/blob/master/vnfs/sonata-snort-ids-vnf-docker
and installed OpenVPN with client.ovpn files. The client connects to OpenVPN
server running on the 'sink server'.

Thhis client bridges two network interfaces of a container (L2) and forwards
part of the input traffic to the output interface and VPN tunnel interface.

### Configuration

```
    +--------------------------------------------+
    |                   VNF                      |
    |                                            |
    |                             +----------+   |
    |                        +--->eth:output +------->
    |                        |    +----------+   |
    | +----------+    +-+-+  |                   |
+----->eth:input +---->br0+--|                   |
    | +----------+    +---+  |                   |
    |                        |     +---------+   |
    |                        +----> eth:tun0 +------->
    |                             +----------+   |
    |                                            |
    +--------------------------------------------+

```

### Entry point:

```
./start.sh
```

