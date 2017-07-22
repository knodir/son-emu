#! /usr/bin/env python

import matplotlib.pyplot as plt
import numpy as np
import json
import csv
import os


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


def extract_dstat(fname, pos, omit_sec, duration):
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
    bw = bw[omit_sec:]
    # we also care about only 60s execution since iperf3 terminates after 60s
    bw = bw[:duration]
    return bw


def plot_upgrade():
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 3, 60
    # for client we monitor TX traffic, which is the value on the 2nd position
    # of the CSV file.
    client_bw = extract_dstat('./results/upgrade-from-client.csv', 2, omit_sec,
                              duration)
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    # for all other VNFs we monitor RX traffic, which is the value on the 1st
    # position of the CSV file.
    ids1_bw = extract_dstat('./results/upgrade-from-ids1.csv', 1, omit_sec,
                            duration)
    print('ids1_bw = %s, len = %d' % (ids1_bw, len(ids1_bw)))

    ids2_bw = extract_dstat('./results/upgrade-from-ids2.csv', 1, omit_sec,
                            duration)
    print('ids2_bw = %s, len = %d' % (ids2_bw, len(ids2_bw)))

    vpn_bw = extract_dstat('./results/upgrade-from-vpn.csv', 1, omit_sec,
                           duration)
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
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 3, 60
    # for client we monitor TX traffic, which is the value on the 2nd position
    # of the CSV file.
    client_bw = extract_dstat('./results/scaleout-from-client.csv', 2, omit_sec,
                              duration)
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    # for all other VNFs we monitor RX traffic, which is the value on the 1st
    # position of the CSV file.
    ids1_bw = extract_dstat('./results/scaleout-from-ids1.csv', 2, omit_sec,
                            duration)
    print('ids1_bw = %s, len = %d' % (ids1_bw, len(ids1_bw)))

    vpn_bw = extract_dstat('./results/scaleout-from-vpn.csv', 2, omit_sec,
                           duration)
    print('vpn_bw = %s, len = %d' % (vpn_bw, len(vpn_bw)))

    figure_name = 'results/scaleout.png'
    t = np.arange(0.0, 60, 1)

    # Plots the figure
    fig, ax = plt.subplots(figsize=(8, 4))
    axes = plt.gca()
    plt.xlabel('Time (s)')
    plt.ylabel('Bandwidth (Mbps)')
    plt.ylim([0, 10])
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


def plot3bars(plot_file_name,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              vdc_names, bw_range, allocs_range):

    print('started plotting')
    n_groups = 1  # len(random_bw)
    fig, ax = plt.subplots(figsize=(6, 3))

    bar_width = 0.05
    index = np.arange(n_groups)

    opacity = 0.3

    random_rects = plt.bar(index, random_bw,
                           bar_width,
                           alpha=opacity,
                           color='g',
                           hatch='//',
                           label='random')

    packing_rects = plt.bar(index + 2 * bar_width, packing_bw, bar_width,
                            alpha=opacity,
                            color='b',
                            hatch='\\\\',
                            label='packing')

    daisy_rects = plt.bar(index + 4 * bar_width, daisy_bw,
                          bar_width,
                          alpha=opacity,
                          color='r',
                          hatch='--',
                          label='daisy')

    # # put numbers of top of the bars
    # for rect, label in zip(random_rects, random_bw):
    #         height = rect.get_height()
    #         ax.text(rect.get_x() + rect.get_width()/2, height + 5, label,
    #                 ha='center', va='bottom')

    # for rect, label in zip(packing_rects, daisy_bw):
    #         height = rect.get_height()
    #         ax.text(rect.get_x() + rect.get_width()/2, height + 5, label,
    #                 ha='center', va='bottom')

    # for rect, label in zip(daisy_rects, packing_bw):
    #         height = rect.get_height()
    #         ax.text(rect.get_x() + rect.get_width()/2, height + 5, label,
    #                 ha='center', va='bottom')

    # put final metadata and plot
    axes = plt.gca()
    plt.ylabel('Aggregate chain throughput (Mbps)')

    plt.yticks(allocs_range)

    plt.xlabel('Chain allocation algorithm')
    plt.xticks(index, [])  # vdc_names)
    #plt.xticks(index + 0.5*bar_width, vdc_names)

    # plot right-vertical axis for execution time
    ax2 = ax.twinx()
    ax2.set_ylim(bw_range)

    ax2.plot(index + bar_width / 2, random_allocs, 'g^', markersize=10,
             label='random')
    ax2.plot(index + 5 * bar_width / 2, packing_allocs, 'bs', markersize=10,
             label='packing')
    ax2.plot(index + 9 * bar_width / 2, daisy_allocs, 'r*', markersize=10,
             label='daisy')

    ax2.set_ylabel('Number of allocated chains')

    # put legends
    ax.legend(loc='upper left', bbox_to_anchor=(-0.05, 1.6), numpoints=1, ncol=1,
              title='Left Scale, Throughput', frameon=False)
    ax2.legend(loc='upper right', bbox_to_anchor=(1.1, 1.6),
               numpoints=1, ncol=1, frameon=False,
               title='Right Scale, Number Of Chains')

    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(plot_file_name, bbox_inches='tight', dpi=200)
    print('plotting done, see %s' % plot_file_name)
    plt.close(fig)


def plot_allocate100():
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 10, 60
    # list of average bandwidth amount each chain gets
    chain_bw_aggr_list = []
    total_bw = {}
    total_allocs = {}
    # algo_bw_files = {'random': [], 'packing': [], 'daisy': []}
    algo_bw_files = {'random100': [], 'packing100': [], 'daisy100': []}

    base_path = './results/allocation'

    # algos = ['random', 'packing', 'daisy']
    # algos = ['random', 'packing']
    # algos = ['random']
    algos = ['random100', 'packing100', 'daisy100']

    for algo in algos:
        folder_name = '%s/%s' % (base_path, algo)
        fnames = os.listdir(folder_name)
        for fname in fnames:
            if fname.endswith('.csv'):
                algo_bw_files[algo].append(fname)
            else:
                print('WARNING: non .csv file %s in %s' % (fname, folder_name))
        total_allocs[algo] = len(algo_bw_files[algo])

    # print(algo_bw_files)
    print('total_allocs = %s' % total_allocs)

    # for allocate we monitor Rx traffic, which is the value on the 1st position
    # of the CSV file.
    for algo in algos:
        for fname in algo_bw_files[algo]:
            infile = '%s/%s/%s' % (base_path, algo, fname)
            bandwidth = extract_dstat(infile, 1, omit_sec, duration)
            if len(bandwidth) == 0:
                print('WARNING: len(bandwidth)=0 for %s' % infile)
                continue
            chain_bw_aggr_list.append(sum(bandwidth) / len(bandwidth))
            # break
        total_bw[algo] = sum(chain_bw_aggr_list)
        chain_bw_aggr_list[:] = []
        # break
    print('total_bw = %s' % total_bw)

    plot_file_name = 'results/allocate100.png'

    random_bw = total_bw['random100']
    packing_bw = total_bw['packing100']
    daisy_bw = total_bw['daisy100']  # daisy']

    random_allocs = total_allocs['random100']
    packing_allocs = total_allocs['packing100']
    daisy_allocs = total_allocs['daisy100']  # daisy']

    vdc_names = algos
    bw_range = [0, 100]
    allocs_range = np.arange(0, 1000, 100)

    plot3bars(plot_file_name,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              ['random', 'packing', 'daisy'], bw_range, allocs_range)
    # vdc_names, bw_range, allocs_range)


def plot_allocate10():
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 10, 60
    # list of average bandwidth amount each chain gets
    chain_bw_aggr_list = []
    total_bw = {}
    total_allocs = {}
    # algo_bw_files = {'random': [], 'packing': [], 'daisy': []}
    algo_bw_files = {'random10': [], 'packing10': [], 'daisy10': []}

    base_path = './results/allocation'

    # algos = ['random', 'packing', 'daisy']
    # algos = ['random', 'packing']
    # algos = ['random']
    algos = ['random10', 'packing10', 'daisy10']

    for algo in algos:
        folder_name = '%s/%s' % (base_path, algo)
        fnames = os.listdir(folder_name)
        for fname in fnames:
            if fname.endswith('.csv'):
                algo_bw_files[algo].append(fname)
            else:
                print('WARNING: non .csv file %s in %s' % (fname, folder_name))
        total_allocs[algo] = len(algo_bw_files[algo])

    # print(algo_bw_files)
    print('total_allocs = %s' % total_allocs)

    # for allocate we monitor Rx traffic, which is the value on the 1st position
    # of the CSV file.
    for algo in algos:
        for fname in algo_bw_files[algo]:
            infile = '%s/%s/%s' % (base_path, algo, fname)
            bandwidth = extract_dstat(infile, 1, omit_sec, duration)
            if len(bandwidth) == 0:
                print('WARNING: len(bandwidth)=0 for %s' % infile)
                continue
            chain_bw_aggr_list.append(sum(bandwidth) / len(bandwidth))
            # break
        total_bw[algo] = sum(chain_bw_aggr_list)
        chain_bw_aggr_list[:] = []
        # break
    print('total_bw = %s' % total_bw)

    plot_file_name = 'results/allocate.png'

    random_bw = total_bw['random10']
    packing_bw = total_bw['packing10']
    daisy_bw = total_bw['daisy10']  # daisy']

    random_allocs = total_allocs['random10']
    packing_allocs = total_allocs['packing10']
    daisy_allocs = total_allocs['daisy10']  # daisy']

    vdc_names = algos
    bw_range = [0, 100]
    allocs_range = np.arange(0, 1000, 100)

    plot3bars(plot_file_name,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              ['random', 'packing', 'daisy'], bw_range, allocs_range)
    # vdc_names, bw_range, allocs_range)

if __name__ == '__main__':
    # plot_upgrade()
    # plot_scaleout()
    plot_allocate10()
    plot_allocate100()
