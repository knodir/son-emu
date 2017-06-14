# Dummy forwarder VNF

This is modified version of snort-ids-vnf example, but stripped down the snort
https://github.com/sonata-nfv/son-examples/blob/master/vnfs/sonata-snort-ids-vnf-docker

Dummy forwarder bridges two network interfaces of a container (L2) and forwards
all traffic from the input interface to the output interface.

### Configuration

```
    +----------------------------------------+
    |                  VNF                   |
    |                                        |
    |                                        |
    | +----------+    +-+-+    +-----------+ |
+----->eth:input +---->br0+---->eth:output +------->
    | +----------+    +---+    +-----------+ |
    |                                        |
    +----------------------------------------+

```

### Entry point:

```
./start.sh
```

