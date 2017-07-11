#!/usr/bin/env python

"""
Generates FTP data packets (port 20) with given data length (in each packet) and
number of packets. Writes the result to ftp.pcap file.
"""

from scapy.all import Ether,IP,TCP,send,wrpcap

data_length = 1400
num_of_packets = 9999
pcap_fname = 'ftp.pcap'

# generate raw content to put as a packet payload
raw_data = ""
for ii in range(data_length):
    raw_data += "A"

# generate single packet
pkt = Ether(src="00:00:00:00:00:01", dst="00:00:00:00:00:02")/IP(
        src="10.0.0.2", dst="10.8.0.1")/TCP(sport=20, dport=20)/raw_data

# print packet summary for debugging purposes
print(pkt.summary())

# write a single packet to the file. This is needed to erase entire content of
# the file (if any) so that we can append more packets later.
wrpcap(pcap_fname, pkt)

# repeatedly append the same packet to the pcap file to get a file with
# requested number of packets.
for ii in range(num_of_packets):
    wrpcap(pcap_fname, pkt, append=True)

# send packer over the wire, instead of writing to the file
# send(pkt) 
