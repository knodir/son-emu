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
+}
