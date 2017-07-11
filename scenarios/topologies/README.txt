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

Chain has "VMs" and "VN" fileds. Both of these names are from
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
