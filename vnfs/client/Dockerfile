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
  tcpreplay \
  dstat

# move tcpdump from sbin to slience apparmor
RUN mv /usr/sbin/tcpdump /usr/local/bin/

ADD libiperf0_3.1.3-1_amd64.deb libiperf0_3.1.3-1_amd64.deb
ADD iperf3_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb

RUN dpkg -i libiperf0_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb
RUN rm libiperf0_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb

# replace old dstat with the latest
ADD dstat /usr/bin/dstat

CMD /bin/bash
