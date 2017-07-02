#! /usr/bin/env python

import json

def extract_iperf(fname):
    # extracts and returns bandwidth info as one-dimentional array
    bw = []
    with open(fname) as data_file:    
        data = json.load(data_file)

    for interval in data['intervals']:
        bps = interval['sum']['bits_per_second']
        mbps = bps / 1048576 # = (1024 * 1024)
        bw.append(mbps)

    return bw


def extract_dstat(fname):
    # TBD


if __name__ == '__main__':
    bw = extract_iperf('./results/from-client.json')
    print(bw)
