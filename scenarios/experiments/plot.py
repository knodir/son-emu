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
        mbps = bps / 1048576  # = (1024 * 1024)
        bw.append(mbps)

    return bw


def extract_dstat(fname, pos):
    """ Extracts and returns bandwidth value from CSV file. """
    bw = []
    # open the csv file with Python CSV parser, walk through each line (row) and
    # add to the bandwidth array only if the row value is numeric (digit), which
    # corresponds to the interface rx bandwidth reported on bps.
    with open(fname) as data_file:
        reader = csv.DictReader(data_file)
        for row in reader:
            # print(row)
            if pos == 1:
                try:
                    val = row['Dstat 0.7.3 CSV output']
                except KeyError:
                    val = row['Dstat 0.7.2 CSV output']
            else:
                val = row[None][0]
            sep = '.'
            rest = val.split(sep, 1)[0]
            if rest.isdigit():
                # multiply to 8 to convert byte to bit (dstat reports on bytes)
                mbps = 8 * int(rest) / 1048576  # = (1024 * 1024)
                bw.append(mbps)

    # we need to trim first 3 seconds as dstat monitoring starts 3 seconds
    # before iperf3 client
    bw = bw[3:]
    # we also care about only 60s execution since iperf3 terminates after 60s
    bw = bw[:60]
    return bw



def plot_upgrade():
    # for client we monitor TX traffic, which is the value on the 2nd position
    # of the CSV file.
    client_bw = extract_dstat('./results/upgrade-from-client.csv', 2)
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    # for all other VNFs we monitor RX traffic, which is the value on the 1st
    # position of the CSV file.
    ids1_bw = extract_dstat('./results/upgrade-from-ids1.csv', 1)
    print('ids1_bw = %s, len = %d' % (ids1_bw, len(ids1_bw)))

    ids2_bw = extract_dstat('./results/upgrade-from-ids2.csv', 1)
    print('ids2_bw = %s, len = %d' % (ids2_bw, len(ids2_bw)))

    vpn_bw = extract_dstat('./results/upgrade-from-vpn.csv', 1)
    print('vpn_bw = %s, len = %d' % (vpn_bw, len(vpn_bw)))

    figure_name = 'results/upgrade.png'
    t = np.arange(0.0, 60, 1)

    # Plots the figure
    fig, ax = plt.subplots(figsize=(8, 4))
    axes = plt.gca()
    plt.xlabel('Time (s)')
    plt.ylabel('Bandwidth (Mbps)')
    client = plt.plot(t, client_bw, 'r--', label='Client')
    ids1 = plt.plot(t, ids1_bw, 'g--', label='IDS1')
    ids2 = plt.plot(t, ids2_bw, 'b--', label='IDS2')
    vpn = plt.plot(t, vpn_bw, 'k--', label='VPN')
    ax.legend(loc='upper left', bbox_to_anchor=(0, 1.2), numpoints=1, ncol=4,
              frameon=False)
    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(figure_name, bbox_inches='tight', dpi=200)
    print('plotting done, see %s' % figure_name)
    plt.close(fig)


def plot_scaleout():
    # for client we monitor TX traffic, which is the value on the 2nd position
    # of the CSV file.
    client_bw = extract_dstat('./results/scaleout-from-client.csv', 2)
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    # for all other VNFs we monitor RX traffic, which is the value on the 1st
    # position of the CSV file.
    ids1_bw = extract_dstat('./results/scaleout-from-ids1.csv', 2)
    print('ids1_bw = %s, len = %d' % (ids1_bw, len(ids1_bw)))

    vpn_bw = extract_dstat('./results/scaleout-from-vpn.csv', 2)
    print('vpn_bw = %s, len = %d' % (vpn_bw, len(vpn_bw)))

    figure_name = 'results/scaleout.png'
    t = np.arange(0.0, 60, 1)

    # Plots the figure
    fig, ax = plt.subplots(figsize=(8, 4))
    axes = plt.gca()
    plt.xlabel('Time (s)')
    plt.ylabel('Bandwidth (Mbps)')
    plt.ylim([0,10])
    client = plt.plot(t, client_bw, 'r--', label='Client')
    ids1 = plt.plot(t, ids1_bw, 'g--', label='IDS1')
    vpn = plt.plot(t, vpn_bw, 'k--', label='VPN')
    ax.legend(loc='upper left', bbox_to_anchor=(0, 1.2), numpoints=1, ncol=3,
              frameon=False)
    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(figure_name, bbox_inches='tight', dpi=200)
    print('plotting done, see %s' % figure_name)
    plt.close(fig)


if __name__ == '__main__':
    plot_upgrade()
    plot_scaleout()
