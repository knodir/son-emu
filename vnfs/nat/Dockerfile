FROM      ubuntu:trusty
MAINTAINER nodir.qodirov@gmail.com

# slightly modified version of sonatanfv/sonata-fw-vnf

RUN	apt-get update && apt-get install -y \
	net-tools \
	iproute \
  iptables \
	inetutils-ping \
  vim \
  tcpdump \
  software-properties-common

# move tcpdump from sbin to slience apparmor
RUN mv /usr/sbin/tcpdump /usr/local/bin/

# install iperf3
RUN add-apt-repository -y "ppa:patrickdk/general-lucid" 
RUN apt-get update
RUN apt-get install -y iperf3

ADD start.sh start.sh
RUN chmod +x start.sh

# set entry point for emulator gatekeeper
ENV SON_EMU_CMD "./start.sh"

CMD /bin/bash
