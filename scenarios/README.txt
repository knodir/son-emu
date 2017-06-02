git clone https://github.com/knodir/son-emu
cd son-emu
git checkout dev

Install VirtualBox VM with vagrant

vagrant up
vagrant ssh

Run Unit Tests

(do after vagrant ssh, i.e., inside the Vagrant VM)
ubuntu@ubuntu-xenial:~$ cd ~/son-emu
sudo py.test -v src/emuvim/test/unittests

son-cli

(these are also inside Vagrant VM)
git clone https://github.com/sonata-nfv/son-cli.git
cd son-cli/ 
pip install virtualenvwrapper
export WORKON_HOME=~/Envs
mkdir -p $WORKON_HOME
source /home/ubuntu/.local/bin/virtualenvwrapper.sh
mkvirtualenv -p /usr/bin/python3.5 sonata
python bootstrap.py
sudo apt-get install libfreetype6-dev
pip install numpy
pip install scipy 
bin/buildout
export PATH=$PATH:/home/ubuntu/son-cli/bin

son-examples

(these are also inside Vagrant VM)
git clone https://github.com/sonata-nfv/son-examples.git
cd son-examples/service-projects
son-package --project sonata-empty-service-emu -n sonata-empty-service
son-package --project sonata-snort-service-emu -n sonata-snort-service
curl -i -X POST -F package=@sonata-empty-service.son http://127.0.0.1:5000/packages
curl -X POST http://127.0.0.1:5000/instantiations -d "{}"
son-emu-cli compute list
son-emu-cli compute list

Known issues:

1) vagrant up fails with “ubuntu/xenial64” not found.
Solution: remove default vagrant and install vagrant 1.9.5

wget https://releases.hashicorp.com/vagrant/1.9.5/vagrant_1.9.5_x86_64.deb
sudo dpkg -i vagrant_1.9.5_x86_64.deb

Source: https://github.com/fideloper/Vaprobash/issues/322

git tag -l
git checkout tags/v2.1 -b dev
