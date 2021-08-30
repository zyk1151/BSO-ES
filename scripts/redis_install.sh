#!/bin/bash

# redis install
# in xxx.sh,  command source ~/.bashrc not useful

set -x

mkdir -p ~/software/redis
cd ~/software/redis/
wget https://download.redis.io/releases/redis-6.2.1.tar.gz
tar -zxvf redis-6.2.1.tar.gz
cd redis-6.2.1
make
cur_path=$(pwd)
echo "export PATH=${cur_path}/src:\$PATH" >> ~/.bashrc
source ~/.bashrc


