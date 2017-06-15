FROM ubuntu:trusty
MAINTAINER nodir.qodirov@gmail.com

RUN export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y -q \
	vim \
  tcpdump \
  openvpn \
  easy-rsa \
  ufw \
  rsyslog \
  wget

# move tcpdump from sbin to slience apparmor
RUN mv /usr/sbin/tcpdump /usr/local/bin/

CMD service rsyslog restart
CMD service openvpn start

# normal entry point
CMD /bin/bash
