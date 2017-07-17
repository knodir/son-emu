Physical topology description

Physical topology (network) has two fields. "Servers" field describes
spec of each server in following format:
{server-name: number-of-cores, amount-of-ram-in-gb, bandwidth-in-gbps}
There is a separate entry for each server.

"PN" field (Physical Network) describes connectivity between servers
and ToR switches in following format:
[server-name, tor-name, bandwidth-in-gbps].

See example below for a single rack (tor0) with two servers (s0, s1).


{
  "Servers": [{
    "s0": [32, 128, 100]
  }, {
    "s1": [32, 128, 100]
  }],
  "PN": [
    ["s0", "tor0", 100],
    ["s1", "tor0", 100]
  ]
}

Virtual topology description

Chain has "VMs" and "VN" fields. Both of these names are from
NetSolver VDC. We do not modify them for compatibility (no need to
change NetSolver VDC for NFV).

VMs describe individual VNFs with their resource requirements per Gbps
traffic. It has following format:
{vnf-name, [core-fraction-per-gbps, mem-in-gb-per-gbps, traffic-in-gbps]}
The example below shows "nat" consumes 1/8 core and 1/2 GB ram per 1
Gbps traffic.

VN (virtual network) field describes the chain (connectivity between NFs)
in the following format:
[vnf1-name, vnf2-name, inter-vnf-bandwidth-in-gbps]
The example below shows "source" VNF connected to "nat" with 1 Gbps
bandwidth link.

The field name is 

{
	"VMs": [{
		"source": [0.125, 0.5, 1]
	}, {
		"nat": [0.125, 0.5, 1]
	}, {
		"sink": [0.125, 0.5, 1]
	}],
	"VN": [
		["source", "nat", 1],
		["nat", "sink", 1]
	]
}

Netsolver Sonata Topologies:

In Sonata, the minimum amount of space a network function can consume
is 512 MB. CPU time is relative and can be adjusted freely.
Our allocation model assumes that 0.125 CPU time is the lowest possible unit.
We denote these values as our NetSolver compute basis of 1 (for 512 MB
ram) and 1 (for 0.125 core).
All subsequent values are multiples of the 512 MB RAM and 0.125 CPU time.
According to these properties we model the base consumption for NetSolver as follows:

IDS  0.500 CPU time, 2.0 Memory, 1 Gbps: 4 4 1
NAT  0.250 CPU time, 1.0 Memory, 1 Gbps: 2 2 1
FW   0.375 CPU time, 1.0 Memory, 1 Gbps: 3 2 1
VPN  0.250 CPU time, 1.0 Memory, 1 Gbps: 2 2 1
WC   0.250 CPU time, 1.0 Memory, 1 Gbps: 2 3 1
LB   0.375 CPU time, 1.0 Memory, 1 Gbps: 3 2 1
GW   0.250 CPU time, 1.0 Memory, 1 Gbps: 2 2 1
RE   0.250 CPU time, 1.5 Memory, 1 Gbps: 2 3 1

We currently have two machines available for testing:
NSS: 8 cores, 32 GB memory
Azure: 64 cores, 436 GB memory

We emulate the following topologies:

1-rack-8-servers on NSS:
32 - 3.2 (10% memory buffer) = ~ 28 GB = 3.5*8
One CPU core per machine
1 machine:
8 compute units
3.5 GB Ram: 7 ram units

1-rack-24-servers on Azure:
436 - 21 (5% memory buffer) = ~ 414 GB = ~17*8
64 cores / 24 = ~2.66 cores per machine = ~2.5*8 compute units
1 machine:
20 compute units
17 GB Ram: 34 ram units

1-rack-48-servers: Azure
436 - 21 (5% memory buffer) = ~ 414 GB = ~8.5*48
64 cores / 48 = ~1.33 cores per machine = ~1.25*8 compute units
1 machine:
10 compute units
8.5 GB Ram: 17 ram units

