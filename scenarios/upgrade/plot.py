#! /usr/bin/env python

import matplotlib.pyplot as plt
import numpy as np
import json
import csv


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
    """ Extracts and returns bandwidth value from CSV file. """
    bw = []
    # open the csv file with Python CSV parser, walk through each line (row) and
    # add to the bandwidth array only if the row value is numeric (digit), which
    # corresponds to the interface rx bandwidth reported on bps.
    with open(fname) as data_file:
        reader = csv.DictReader(data_file)
        for row in reader:
            val = row['Dstat 0.7.3 CSV output']
            if val.isdigit():
                # multiply to 8 to convert byte to bit (dstat reports on bytes)
                mbps = 8 * int(val) / 1048576 # = (1024 * 1024)
                bw.append(mbps)

    # we need to trim first 3 seconds as dstat monitoring starts 3 seconds
    # before iperf3 client
    bw = bw[3:]
    # we also care about only 60s execution since iperf3 terminates after 60s
    bw = bw[:60]
    return bw


def plot(x, client_bw, ids1_bw, ids2_bw, vpn_bw, fname):
    # Plots the figure
    fig, ax = plt.subplots(figsize=(8, 4))
    axes = plt.gca()
    plt.xlabel('Time (s)')
    plt.ylabel('Bandwidth (Mbps)')
    client = plt.plot(x, client_bw, 'r--', label='Client')
    ids1 = plt.plot(x, ids1_bw, 'g.', label='IDS1')
    ids2 = plt.plot(x, ids2_bw, 'bo', label='IDS2')
    vpn = plt.plot(x, vpn_bw, 'k^', label='VPN')
    ax.legend(loc='upper left', bbox_to_anchor=(0, 1.2), numpoints=1, ncol=4,
            frameon=False)
    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(fname, bbox_inches='tight', dpi=200)
    print('plotting done, see %s' % fname)
    plt.close(fig)


if __name__ == '__main__':
    client_bw = extract_iperf('./results/from-client.json')
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    ids1_bw = extract_dstat('./results/from-ids1.csv')
    print('ids1_bw = %s, len = %d' % (ids1_bw, len(ids1_bw)))

    ids2_bw = extract_dstat('./results/from-ids2.csv')
    print('ids2_bw = %s, len = %d' % (ids2_bw, len(ids2_bw)))

    vpn_bw = extract_dstat('./results/from-vpn.csv')
    print('vpn_bw = %s, len = %d' % (vpn_bw, len(vpn_bw)))

    figure_name = 'results/upgrade.png'
    t = np.arange(0.0, 60, 1)
    plot(t, client_bw, ids1_bw, ids2_bw, vpn_bw, figure_name)
