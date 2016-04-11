__author__ = 'Administrator'

import urllib2
import logging
from mininet.node import  OVSSwitch
import ast
import time
logging.basicConfig(level=logging.INFO)

"""
class to read openflow stats from the Ryu controller of the DCNEtwork
"""

class DCNetworkMonitor():
    def __init__(self, net):
        self.net = net
        # link to REST_API
        self.ip = '0.0.0.0'
        self.port = '8080'
        self.REST_api = 'http://{0}:{1}'.format(self.ip,self.port)

        self.previous_measurement = 0
        self.previous_monitor_time = 0
        self.switch_dpid = 0
        self.metric_key = None
        self.mon_port = None

    # first set some parameters, before measurement can start
    def setup_rate_measurement(self, vnf_name, vnf_interface=None, direction='tx', metric='packets'):
        # check if port is specified (vnf:port)
        if vnf_interface is None:
            # take first interface by default
            connected_sw = self.net.DCNetwork_graph.neighbors(vnf_name)[0]
            link_dict = self.net.DCNetwork_graph[vnf_name][connected_sw]
            vnf_interface = link_dict[0]['src_port_id']

        for connected_sw in self.net.DCNetwork_graph.neighbors(vnf_name):
            link_dict = self.net.DCNetwork_graph[vnf_name][connected_sw]
            for link in link_dict:
                # logging.info("{0},{1}".format(link_dict[link],vnf_interface))
                if link_dict[link]['src_port_id'] == vnf_interface:
                    # found the right link and connected switch
                    # logging.info("{0},{1}".format(link_dict[link]['src_port_id'], vnf_source_interface))
                    self.mon_port = link_dict[link]['dst_port']
                    break

        try:
            # default port direction to monitor
            if direction is None:
                direction = 'tx'
            if metric is None:
                metric = 'packets'

            vnf_switch = self.net.DCNetwork_graph.neighbors(str(vnf_name))

            if len(vnf_switch) > 1:
                logging.info("vnf: {0} has multiple ports".format(vnf_name))
                return
            elif len(vnf_switch) == 0:
                logging.info("vnf: {0} is not connected".format(vnf_name))
                return
            else:
                vnf_switch = vnf_switch[0]
            next_node = self.net.getNodeByName(vnf_switch)

            if not isinstance(next_node, OVSSwitch):
                logging.info("vnf: {0} is not connected to switch".format(vnf_name))
                return

            self.previous_measurement = 0
            self.previous_monitor_time = 0

            #self.switch_dpid = x = int(str(next_node.dpid), 16)
            self.switch_dpid = int(str(next_node.dpid), 16)
            self.metric_key = '{0}_{1}'.format(direction, metric)

        except Exception as ex:
            logging.exception("get_txrate error.")
            return ex.message


    # call this function repeatedly for streaming measurements
    def get_rate(self, vnf_name, vnf_interface=None, direction='tx', metric='packets'):

            key = self.metric_key

            ret = self.REST_cmd('stats/port', self.switch_dpid)
            port_stat_dict = ast.literal_eval(ret)
            for port_stat in port_stat_dict[str(self.switch_dpid)]:
                if port_stat['port_no'] == self.mon_port:
                    port_uptime = port_stat['duration_sec'] + port_stat['duration_nsec'] * 10 ** (-9)
                    this_measurement = port_stat[key]

                    if self.previous_monitor_time <= 0 or self.previous_monitor_time >= port_uptime:
                        self.previous_measurement = port_stat[key]
                        self.previous_monitor_time = port_uptime
                        # do first measurement
                        time.sleep(1)
                        byte_rate = self.get_rate(vnf_name, vnf_interface, direction, metric)
                        return byte_rate
                    else:
                        time_delta = (port_uptime - self.previous_monitor_time)
                        byte_rate = (this_measurement - self.previous_measurement) / float(time_delta)
                        #logging.info('uptime:{2} delta:{0} rate:{1}'.format(time_delta,byte_rate,port_uptime))

                    self.previous_measurement = this_measurement
                    self.previous_monitor_time = port_uptime
                    return byte_rate

            return ret

    def REST_cmd(self, prefix, dpid):
        url = self.REST_api + '/' + str(prefix) + '/' + str(dpid)
        req = urllib2.Request(url)
        ret = urllib2.urlopen(req).read()
        return ret