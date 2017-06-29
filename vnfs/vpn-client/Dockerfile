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
  openvpn \
  dstat

# move tcpdump from sbin to slience apparmor
RUN mv /usr/sbin/tcpdump /usr/local/bin/

# install iperf3
ADD libiperf0_3.1.3-1_amd64.deb libiperf0_3.1.3-1_amd64.deb
ADD iperf3_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb

RUN dpkg -i libiperf0_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb
RUN rm libiperf0_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb

ADD start.sh start.sh
RUN chmod +x start.sh
ADD client.ovpn client.ovpn

# replace old dstat with the latest
ADD dstat /usr/bin/dstat

# set entry point for emulator gatekeeper
ENV SON_EMU_CMD "./start.sh"

CMD /bin/bash
