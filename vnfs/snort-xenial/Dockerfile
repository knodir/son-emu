FROM ubuntu:xenial
MAINTAINER nodir.qodirov@gmail.com

# define interface names (should be the same as in VNFD)
ENV IFIN input
ENV IFOUT output

RUN export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y -q \
	net-tools \
	iproute \
	inetutils-ping \
	iptables \
	arptables \
	ebtables \
	bridge-utils \
	ethtool \
	vim \
	snort \
  tcpdump \
  dstat

ADD snort.conf /etc/snort/snort.conf
ADD start.sh start.sh
RUN chmod +x start.sh
ADD restart_snort.sh restart_snort.sh
RUN chmod +x restart_snort.sh
RUN mkdir /snort-logs

# move tcpdump from sbin to slience apparmor
RUN mv /usr/sbin/tcpdump /usr/local/bin/

# install iperf3
ADD libiperf0_3.1.3-1_amd64.deb libiperf0_3.1.3-1_amd64.deb
ADD iperf3_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb

RUN dpkg -i libiperf0_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb
RUN rm libiperf0_3.1.3-1_amd64.deb iperf3_3.1.3-1_amd64.deb

# replace old dstat with the latest
ADD dstat /usr/bin/dstat

# set entry point for emulator gatekeeper
ENV SON_EMU_CMD ./start.sh

# normal entry point
CMD /bin/bash
