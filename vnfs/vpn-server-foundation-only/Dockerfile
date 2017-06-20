FROM ubuntu:trusty
MAINTAINER nodir.qodirov@gmail.com

RUN export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y -q \
	vim \
  tcpdump \
  openvpn \
  easy-rsa \
  ufw \
  rsyslog \
  wget \
  software-properties-common

# move tcpdump from sbin to slience apparmor
RUN mv /usr/sbin/tcpdump /usr/local/bin/

# install iperf3
RUN add-apt-repository -y "ppa:patrickdk/general-lucid" 
RUN apt-get update
RUN apt-get install -y iperf3

ADD start.sh start.sh
RUN chmod +x start.sh

# normal entry point
CMD /bin/bash
