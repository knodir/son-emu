#! /usr/bin/env python

import matplotlib.pyplot as plt
import numpy as np
import json
import csv
import os
import collections
import sys

import glog


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
                mbps = round(8.0 * float(rest) / 1048576.0, 4) # = (1024 * 1024)
                bw.append(mbps)

    # we need to trim first 3 seconds as dstat monitoring starts 3 seconds
    # before iperf3 client
    bw = bw[omit_sec:]
    # we also care about only 60s execution since iperf3 terminates after 60s
    bw = bw[:duration]
    return bw


def extract_dstat_with_time(fname, pos):
    """ Extracts bandwidth and timestamp as a dict from CSV file. """
    bw_dict = collections.OrderedDict()
    # open the csv file with Python CSV parser, walk through each line (row) and
    # add to the bandwidth array only if the row value is numeric (digit), which
    # corresponds to the interface bandwidth reported on bps.
    with open(fname) as data_file:
        reader = csv.DictReader(data_file)
        for row in reader:
            val = row['Dstat 0.7.3 CSV output']
            if val.isdigit():
                bw_val, timestamp = val, row[None][-1]
                # glog.info('%s, %s', bw_val, timestamp)

                # multiply to 8 to convert byte to bit (dstat reports on bytes)
                mbps = round(8.0 * float(bw_val) / 1048576.0, 4) # = (1024 * 1024)
                bw_dict[timestamp] = mbps

    # glog.info(bw_dict)
    return bw_dict



def plot_upgrade(mbps):
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 0, 300
    # for client we monitor TX traffic, which is the value on the 2nd position
    # of the CSV file.
    client_bw = extract_dstat('./results/upgrade/' +
                              str(mbps) + '-from-client.csv', 1, omit_sec,
                              duration)
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    # for all other VNFs we monitor RX traffic, which is the value on the 1st
    # position of the CSV file.
    ids1_bw = extract_dstat('./results/upgrade/' +
                            str(mbps) + '-from-ids1.csv', 2, omit_sec,
                            duration)
    print('ids_bw = %s, len = %d' % (ids1_bw, len(ids1_bw)))

    ids2_bw = extract_dstat('./results/upgrade/' +
                            str(mbps) + '-from-ids2.csv', 2, omit_sec,
                            duration)
    print('ids_bw = %s, len = %d' % (ids2_bw, len(ids2_bw)))

    vpn_ids1_bw = extract_dstat('./results/upgrade/' +
                                str(mbps) + '-from-vpn-ids1.csv', 2, omit_sec,
                                duration)
    print('vpn_bw = %s, len = %d' % (vpn_ids1_bw, len(vpn_ids1_bw)))

    vpn_ids2_bw = extract_dstat('./results/upgrade/' +
                                str(mbps) + '-from-vpn-ids2.csv', 2, omit_sec,
                                duration)
    print('vpn_bw = %s, len = %d' % (vpn_ids2_bw, len(vpn_ids2_bw)))

    vpn_fw_bw = extract_dstat('./results/upgrade/' +
                              str(mbps) + '-from-vpn-fw.csv', 2, omit_sec,
                              duration)
    print('server_bw = %s, len = %d' % (vpn_fw_bw, len(vpn_fw_bw)))

    figure_name = 'results/upgrade' + str(mbps) + '.png'
    figure_name_pdf = 'results/upgrade' + str(mbps) + '.pdf'

    t = np.arange(0.0, duration, 1)
    merged_server_bw = [x + y for x, y in zip(vpn_ids1_bw, vpn_fw_bw)]
    merged_server_bw = [x + y for x, y in zip(vpn_ids2_bw, merged_server_bw)]

    # Plots the figure
    fig, ax = plt.subplots(figsize=(3, 1))
    axes = plt.gca()

    plt.xlabel('Time (s)')
    plt.ylabel('Throughput (Mbps)')
    plt.ylim([0, 32])
    plt.yticks(np.arange(0, 32, 10))

    plt.xlim([0, 300])
    plt.xticks(np.arange(0, 301, 150))
    
    # client = plt.plot(t, client_bw, 'r-', marker='o', markevery=max( int(duration / 2), 1), label='Source')
    ax.plot(t, client_bw, linestyle='--', color='k', label='Source',
            marker='>', markersize=5, markevery=[40, 75])
    ax.plot(t, ids1_bw, linestyle='-.', color='g', label='IDS1',
            marker='x', markersize=5, markevery=[20, 75])
    ax.plot(t, ids2_bw, linestyle=':', color='m', label='IDS2',
            marker='d', markersize=5, markevery=[20, 75])
    # ax.plot(t, vpn_fw_bw, linestyle='--', color='c',  label='VPN-FW')
    ax.plot(t, merged_server_bw, linestyle='-', color='r', label='Sink',
            marker='<', markersize=5, markevery=[60, 75])

    plt.legend(loc='upper left', bbox_to_anchor=(0, 2.25), numpoints=1, ncol=4,
               frameon=False)
    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(figure_name, bbox_inches='tight', dpi=200)
    final_figure.savefig(figure_name_pdf, bbox_inches='tight', dpi=200)

    print('plotting done, see %s' % figure_name)
    plt.close(fig)


def plot_scaleout(mbps, iperf):

    if iperf:
        testname = "scaleout-iperf"
    else:
        testname = "scaleout"

    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 0, 300
    # for client we monitor TX traffic, which is the value on the 2nd position
    # of the CSV file.
    client_bw = extract_dstat('./results/' + testname + '/' +
                              str(mbps) + '-from-client.csv', 2, omit_sec,
                              duration)
    print('client_bw = %s, len = %d' % (client_bw, len(client_bw)))

    # for all other VNFs we monitor RX traffic, which is the value on the 1st
    # position of the CSV file.
    ids_bw = extract_dstat('./results/' + testname + '/' +
                           str(mbps) + '-from-ids.csv', 2, omit_sec,
                           duration)
    print('ids_bw = %s, len = %d' % (ids_bw, len(ids_bw)))

    vpn_ids_bw = extract_dstat('./results/' + testname + '/' +
                               str(mbps) + '-from-vpn-ids.csv', 2, omit_sec,
                               duration)
    print('vpn_bw = %s, len = %d' % (vpn_ids_bw, len(vpn_ids_bw)))

    vpn_fw_bw = extract_dstat('./results/' + testname + '/' +
                              str(mbps) + '-from-vpn-fw.csv', 2, omit_sec,
                              duration)
    print('server_bw = %s, len = %d' % (vpn_fw_bw, len(vpn_fw_bw)))

    figure_name = 'results/' + testname + '' + str(mbps) + '.png'
    figure_name_pdf = 'results/' + testname + '' + str(mbps) + '.pdf'

    t = np.arange(0.0, duration, 1)
    merged_server_bw = [x + y for x, y in zip(vpn_ids_bw, vpn_fw_bw)]
    # Plots the figure
    fig, ax = plt.subplots(figsize=(3, 1))
    axes = plt.gca()
    plt.xlabel('Time (s)')
    plt.ylabel('Throughput (Mbps)')
    plt.ylim([0, 32])
    plt.yticks(np.arange(0, 32, 10))

    plt.xlim([0, 300])
    plt.xticks(np.arange(0, 301, 150))
    # client = plt.plot(t, client_bw, 'r-', marker='o', markevery=max( int(duration / 2), 1), label='Source')
    ax.plot(t, client_bw, linestyle='--', color='k', label='Source',
            marker='>', markersize=5, markevery=[40, 75])
    ax.plot(t, ids_bw, linestyle='-.', color='g', label='IDS',
            marker='o', markersize=5, markevery=[20, 75])
    ax.plot(t, vpn_fw_bw, linestyle=':', color='m', label='VPN-FW',
            marker='*', markersize=5, markevery=[60, 75])
    ax.plot(t, merged_server_bw, linestyle='-', color='r', label='Sink',
            marker='<', markersize=5, markevery=[60, 75])
    # server = plt.plot(t, server_bw, 'b--', label='Server')


    # ax.plot(t, client_bw, linestyle='--', color='k', label='Source',
    #         marker='>', markersize=5, markevery=[40, 75])
    # ax.plot(t, ids1_bw, linestyle='-.', color='g', label='IDS1',
    #         marker='x', markersize=5, markevery=[20, 75])
    # ax.plot(t, ids2_bw, linestyle=':', color='m', label='IDS2',
    #         marker='d', markersize=5, markevery=[20, 75])
    # # ax.plot(t, vpn_fw_bw, linestyle='--', color='c',  label='VPN-FW')
    # ax.plot(t, merged_server_bw, linestyle='-', color='r', label='Sink',
    #         marker='<', markersize=5, markevery=[60, 75])






    ax.legend(loc='upper left', bbox_to_anchor=(0, 2.25), numpoints=1, ncol=4,
              frameon=False)
    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(figure_name, bbox_inches='tight', dpi=300)
    final_figure.savefig(figure_name_pdf, bbox_inches='tight', dpi=300)

    print('plotting done, see %s' % figure_name)
    plt.close(fig)


def plot3bars(plot_file_name,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              vdc_names, bw_range, allocs_range):

    print('started plotting')
    n_groups = 1  # len(random_bw)
    fig, ax = plt.subplots(figsize=(5, 0.8))

    bar_width = 0.03
    index = np.arange(n_groups)

    opacity = 0.2

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
    #ax.set_ylim([0,550])
    #plt.yticks([0,100,200,300,400,500])
    plt.yticks(np.arange(0, 401, 200))

    plt.xlabel('Chain allocation algorithm')
    plt.xticks(index, [])  # vdc_names)
    # plt.xticks(index + 0.5*bar_width, vdc_names)
    # plot right-vertical axis for execution time
    #ax2 = ax.twinx()
    #ax2.set_ylim(bw_range)
    #plt.yticks([0,10,20,30,40,50])
    #ax2.plot(index + bar_width / 2, random_allocs, 'g^', markersize=5,
    #         label='random')
    #ax2.plot(index + 5 * bar_width / 2, packing_allocs, 'bs', markersize=5,
    #         label='packing')
    #ax2.plot(index + 9 * bar_width / 2, daisy_allocs, 'r*', markersize=5,
    #         label='daisy')

    #ax2.set_ylabel('Number of allocated chains')

    # put legends
    vert_anchor = 3.3
    ax.legend(loc='upper left', bbox_to_anchor=(-0.05, vert_anchor),
            numpoints=1, ncol=1, title='Left Scale, Throughput', frameon=False)
    #ax2.legend(loc='upper right', bbox_to_anchor=(1.1, vert_anchor),
    #           numpoints=1, ncol=1, frameon=False,
    #           title='Right Scale, Number Of Chains')

    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(plot_file_name, bbox_inches='tight', dpi=300)

    print('plotting done, see %s' % plot_file_name)
    plt.close(fig)


def plot_allocate(compute, mbps, duration):
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 15, duration
    extension = str(compute) + "_" + str(mbps)
    # list of average bandwidth amount each chain gets
    chain_bw_aggr_list = []
    total_bw = {}
    total_allocs = {}
    algos = ['random' + extension, 'packing' + extension, 'daisy' + extension]
    # algo_bw_files = {'random': [], 'packing': [], 'daisy': []}
    algo_bw_files = {algos[0]: [], algos[1]: [], algos[2]: []}

    base_path = './results/allocation'

    # algos = ['random', 'packing', 'daisy']
    # algos = ['random', 'packing']
    # algos = ['random']

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

    plot_file_name = 'results/allocate' + extension + '.png'
    plot_file_name_pdf = 'results/allocate' + extension + '.pdf'

    random_bw = total_bw[algos[0]]
    packing_bw = total_bw[algos[1]]
    daisy_bw = total_bw[algos[2]]  # daisy']

    random_allocs = total_allocs[algos[0]]
    packing_allocs = total_allocs[algos[1]]
    daisy_allocs = total_allocs[algos[2]]  # daisy']

    vdc_names = algos
    chain_range = [0, 55]
    allocs_range = np.arange(0, mbps * 55, mbps * 10)
    allocs_range = np.append(allocs_range, [550])

    print (allocs_range)
    plot3bars(plot_file_name,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              ['random', 'packing', 'daisy'], chain_range, allocs_range)
    plot3bars(plot_file_name_pdf,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              ['random', 'packing', 'daisy'], chain_range, allocs_range)
    # vdc_names, bw_range, allocs_range)

def plot_allocate_iperf(compute, mbps, duration):
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 15, duration
    extension = str(compute) + "_" + str(mbps) + "_iperf"
    # list of average bandwidth amount each chain gets
    chain_bw_aggr_list = []
    total_bw = {}
    total_allocs = {}
    algos = ['random' + extension, 'packing' + extension, 'daisy' + extension]
    # algo_bw_files = {'random': [], 'packing': [], 'daisy': []}
    algo_bw_files = {algos[0]: [], algos[1]: [], algos[2]: []}

    base_path = './results/allocation/iperf'

    # algos = ['random', 'packing', 'daisy']
    # algos = ['random', 'packing']
    # algos = ['random']

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

    plot_file_name = 'results/allocate' + extension + '_iperf.png'
    plot_file_name_pdf = 'results/allocate' + extension + '_iperf.pdf'

    random_bw = total_bw[algos[0]]
    packing_bw = total_bw[algos[1]]
    daisy_bw = total_bw[algos[2]]  # daisy']

    random_allocs = total_allocs[algos[0]]
    packing_allocs = total_allocs[algos[1]]
    daisy_allocs = total_allocs[algos[2]]  # daisy']

    vdc_names = algos
    bw_range = [0, 100]
    allocs_range = np.arange(0, mbps * 60, mbps * 10)

    plot3bars(plot_file_name,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              ['random', 'packing', 'daisy'], bw_range, allocs_range)
    plot3bars(plot_file_name_pdf,
              random_bw, packing_bw, daisy_bw,
              random_allocs, packing_allocs, daisy_allocs,
              ['random', 'packing', 'daisy'], bw_range, allocs_range)
    # vdc_names, bw_range, allocs_range


def get_chain_bandwidth(base_path, omit_sec, duration):
    num_of_chains = 0
    for file in os.listdir(base_path):
        if file.endswith(".csv"):
            num_of_chains += 1
    # we monitor sink VNF RX traffic, which is the value on the 1st position
    # of the CSV file.
    chains = collections.OrderedDict()

    for index in range(num_of_chains):
        chains['chain%d'%index] = extract_dstat_with_time(base_path +
                '/e2-allocate-from-chain%d-sink.csv'%index, 0)
        # print('sink_bw = %s, len = %d' % (sink_bw, len(sink_bw)))
    # glog.info('length = %s', len(chains))

    for index in range(1, num_of_chains, 1):
        for timestamp, bw_val in chains['chain%d'%index].iteritems():
            if timestamp in chains['chain0']:
                chains['chain0'][timestamp] += chains['chain%d'%index][timestamp]

    bw = chains['chain0'].values()
    total_time = len(bw)
    # glog.info('bw = %s\nlen = %d', bw, len(bw))
    # we need to trim from head and tail for sanity
    bw = bw[omit_sec:]
    bw = bw[:duration]

    return (num_of_chains, total_time, bw)


def plot_iterative():
    # amount of seconds to skip data collection, and duration of the experiment
    omit_sec, duration = 0, 2200
    time_range = [0, 2200]
    bandwidth_range = [0, 550]
    t = np.arange(0.0, duration, 1)

    alg_band_values = {}
    alg_num_of_chains = {}
    alg_total_time = {}

    alg_base_paths = {}
    alg_base_paths['random'] = './results/iter-allocation/random10'
    alg_base_paths['netpack'] = './results/iter-allocation/packing10'
    alg_base_paths['vnfsolver'] = './results/iter-allocation/daisy10'
    for alg_key, alg_base_path in alg_base_paths.iteritems():
        alg_num_of_chains[alg_key], alg_total_time[alg_key], alg_band_values[alg_key] = get_chain_bandwidth(
                alg_base_path, omit_sec, duration)
        glog.info('%s: chains = %d, time range = %d, max_band = %d', alg_key,
                alg_num_of_chains[alg_key], alg_total_time[alg_key],
                max(alg_band_values[alg_key]))

    figure_name = 'results/iterative.png'
    figure_name_pdf = 'results/iterative.pdf'

    # Plots the figure
    fig, ax = plt.subplots(figsize=(8, 2))
    msize = 7
    axes = plt.gca()

    plt.xlabel('Time (s)')
    plt.ylabel('Throughput (Mbps)')
    plt.ylim(bandwidth_range)
    plt.yticks(np.arange(0, 510, 100))

    plt.xlim(time_range)
    plt.xticks(np.arange(0, time_range[1], 300))

    ax.plot(t, alg_band_values['random'], linestyle='-', color='r',
            label='Random', marker='x', markersize=msize, markevery=[100, 300])
    ax.plot(t, alg_band_values['netpack'], linestyle='-', color='g',
            label='NetPack', marker='d', markersize=msize, markevery=[200, 300])
    ax.plot(t, alg_band_values['vnfsolver'], linestyle='-', color='b',
            label='VNFSolver', marker='>', markersize=msize, markevery=[300, 300])
 
    plt.legend(loc='upper left', bbox_to_anchor=(0.05, 1.3), numpoints=1, ncol=4,
               frameon=False)
    plt.draw()
    final_figure = plt.gcf()
    final_figure.savefig(figure_name, bbox_inches='tight', dpi=200)
    final_figure.savefig(figure_name_pdf, bbox_inches='tight', dpi=200)

    print('plotting done, see %s' % figure_name)
    plt.close(fig)


if __name__ == '__main__':
    # plot_upgrade(10)

    # plot_upgrade(100) # this one is used in the paper
    plot_iterative() # this one is used in the paper
    

    # plot_upgrade(1000)
    # plot_upgrade(10000)

    # plot_scaleout(10, True)
    # plot_scaleout(100, True)
    # plot_scaleout(1000, True)
    # plot_scaleout(10000, True)

    # plot_scaleout(10, False)


    # plot_scaleout(100, False) # this one is used in the paper


    # plot_scaleout(1000, False)
    # plot_scaleout(10000, False)

    # plot_allocate(compute=10, mbps=10, duration=60)
    # plot_allocate(compute=10, mbps=100, duration=60)
    # plot_allocate_iperf(compute=10, mbps=10, duration=60)
    # plot_allocate_iperf(compute=10, mbps=100, duration=60)


    #plot_allocate(compute=20, mbps=10, duration=60) # this one is used in the paper


    # plot_allocate(compute=20, mbps=100, duration=60)
    # plot_allocate_iperf(compute=20, mbps=10, duration=60)
    # plot_allocate_iperf(compute=20, mbps=100, duration=60)

