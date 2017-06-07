"""
Copyright (c) 2015 SONATA-NFV
ALL RIGHTS RESERVED.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Neither the name of the SONATA-NFV [, ANY ADDITIONAL AFFILIATION]
nor the names of its contributors may be used to endorse or promote
products derived from this software without specific prior written
permission.

This work has been performed in the framework of the SONATA project,
funded by the European Commission under Grant number 671517 through
the Horizon 2020 and 5G-PPP programmes. The authors would like to
acknowledge the contributions of their colleagues of the SONATA
partner consortium (www.sonata-nfv.eu).
"""
"""
Test suite to automatically test emulator functionalities.
Directly interacts with the emulator through the Mininet-like
Python API.

Does not test API endpoints. This is done in separated test suites.
"""

#import time
#import unittest
#from emuvim.dcemulator.node import EmulatorCompute
#from emuvim.test.base import SimpleTestTopology
#from mininet.node import RemoteController

import logging
from mininet.log import setLogLevel
from emuvim.dcemulator.net import DCNetwork
from emuvim.api.rest.rest_api_endpoint import RestApiEndpoint
from emuvim.api.sonata import SonataDummyGatekeeperEndpoint
from mininet.node import RemoteController

import time
from mininet.clean import cleanup


def runSDNChainingMultiService():
    """
    This function is copied from src/emuvim/test/unittests/test_emulator.py
    Create a two data centers and interconnect them with additional
    switches between them.
    Uses Ryu SDN controller.
    Setup 2 services and setup isolated paths between them
    Delete only the first service, and check that other one still works
    """
    # create network
    testTop = SimpleTestTopology()
    #SimpleTestTopology.createNet(
    testTop.createNet(
        nswitches=3, ndatacenter=2, nhosts=0, ndockers=0,
        autolinkswitches=True,
        controller=RemoteController,
        enable_learning=False)

    # setup links
    self.net.addLink(self.dc[0], self.s[0])
    self.net.addLink(self.s[2], self.dc[1])
    # start Mininet network
    self.startNet()

    ## First Service
    # add compute resources
    vnf1 = self.dc[0].startCompute("vnf1", network=[{'id': 'intf1', 'ip': '10.0.10.1/24'}])
    vnf2 = self.dc[1].startCompute("vnf2", network=[{'id': 'intf2', 'ip': '10.0.10.2/24'}])
    # setup links
    self.net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=1)
    # check connectivity by using ping
    self.assertTrue(self.net.ping([vnf1, vnf2]) <= 0.0)

    ## Second Service
    # add compute resources
    vnf11 = self.dc[0].startCompute("vnf11", network=[{'id': 'intf1', 'ip': '10.0.20.1/24'}])
    vnf22 = self.dc[1].startCompute("vnf22", network=[{'id': 'intf2', 'ip': '10.0.20.2/24'}])

    # check number of running nodes
    self.assertTrue(len(self.getContainernetContainers()) == 4)
    self.assertTrue(len(self.net.hosts) == 4)
    self.assertTrue(len(self.net.switches) == 5)

    # setup links
    self.net.setChain('vnf11', 'vnf22', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=2)
    # check connectivity by using ping
    self.assertTrue(self.net.ping([vnf11, vnf22]) <= 0.0)
    # check first service cannot ping second service
    self.assertTrue(self.net.ping([vnf1, vnf22]) > 0.0)
    self.assertTrue(self.net.ping([vnf2, vnf11]) > 0.0)

    # delete the first service chain
    self.net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='del-flows', cookie=1)
    # check connectivity of first service is down
    self.assertTrue(self.net.ping([vnf1, vnf2]) > 0.0)
    #time.sleep(100)
    # check connectivity of second service is still up
    self.assertTrue(self.net.ping([vnf11, vnf22]) <= 0.0)

    # stop Mininet network
    self.stopNet()


def basicTest():
    """ This basic test creates one data center and two VNFs with default
    ubuntu:xenial image, and checks if VNFs can ping each other. """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add one data center
    dc = net.addDatacenter('dc1', metadata={'node-upgrade'})
    # connect data center to API endpoint
    api = RestApiEndpoint("0.0.0.0", 5001)
    # connect DC to the network
    api.connectDCNetwork(net)
    # connect DC to the endpoint
    api.connectDatacenter(dc)

    print(net)
    print(api)

    # start API endpoint and network
    api.start()
    net.start()

    # create two VNFs
    vnf1 = dc.startCompute("vnf1", network=[{'id': 'intf1', 'ip': '10.0.10.1/24'}])
    vnf2 = dc.startCompute("vnf2", network=[{'id': 'intf2', 'ip': '10.0.10.2/24'}])
    print('ping vnfs before explicit chaining: %s' % net.ping([vnf1, vnf2]))

    # explcitly chain two VNFs
    net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=1)
    print('ping vnfs after explicit chaining: %s' % net.ping([vnf1, vnf2]))

    # prompt containernet CLI for further debugging
    net.CLI()
    # exit containernet when user types 'exit'
    net.stop()



def nodeUpgrade():
    """ TBD """

    net = DCNetwork(controller=RemoteController, monitor=True, enable_learning=True)
    # add one data center
    dc = net.addDatacenter('dc1', metadata={'node-upgrade'})

    api = RestApiEndpoint("0.0.0.0", 5001)

    api.connectDCNetwork(net)
    # connect data centers to the endpoint
    api.connectDatacenter(dc)

    # sw = net.addSwitch('sw1')
    # add one host
    # host1 = net.addHost('h1')
    # add one docker
    # docker1 = net.addDocker('docker1', dimage='ubuntu:trusty')
    print(net)
    print(api)
    #print(host1)
    #print(docker1)
    api.start()
    net.start()

    vnf1 = dc.startCompute("vnf1", network=[{'id': 'intf1', 'ip': '10.0.10.1/24'}])
    vnf2 = dc.startCompute("vnf2", network=[{'id': 'intf2', 'ip': '10.0.10.2/24'}])
    print('(1) ping vnfs: %s' % net.ping([vnf1, vnf2]))

    # delete the first service chain
    net.setChain('vnf1', 'vnf2', 'intf1', 'intf2', bidirectional=True, cmd='add-flow', cookie=1)
    print('(2) ping vnfs: %s' % net.ping([vnf1, vnf2]))

    net.CLI()

    # time.sleep(30)
    net.stop()


if __name__ == '__main__':
    # runSDNChainingMultiService()
    logging.basicConfig(level=logging.DEBUG)

    basicTest()

    # nodeUpgrade()
    
    cleanup()
