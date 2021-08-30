

def compress_codes_script(path):
    return """#!/bin/bash
    {
    set -x
    mkdir -p ${HOME}/dea/raw
    cd %s
    tar -zcvf ${HOME}/dea/raw/bso_code.tar.gz *
    }
    """ % (path)

def make_file_download_script():
    return """
set -x
cd ~
mkdir -p dea/run/
cd dea/run/

tar zxvf bso_code.tar.gz
rm bso_code.tar.gz
"""

def make_master_redis_script():
    return """#!/bin/bash
{
set -x

# make_disable_hyperthreading_script
mkdir -p ~/dea/redis
cp -f ~/dea/run/redis_config/redis.conf ~/dea/redis/

# Disable redis snapshots
echo 'save ""' >> ~/dea/redis/redis.conf

# Make the unix domain socket available for the master client
# (TCP is still enabled for workers/relays)
sed -ie "s/bind 127.0.0.1/bind 0.0.0.0/" ~/dea/redis/redis.conf
sed -ie "s/daemonize no/daemonize yes/" ~/dea/redis/redis.conf
echo "unixsocket $HOME/dea/redis/redis.sock" >> ~/dea/redis/redis.conf
echo "unixsocketperm 777" >> ~/dea/redis/redis.conf

redis-server ~/dea/redis/redis.conf

} >> ~/dea/run/user_data.log 2>&1
"""


def make_worker_redis_script():
    return """#!/bin/bash
{
set -x

# make_disable_hyperthreading_script
mkdir -p ~/dea/redis
cp -f ~/dea/run/redis_config/redis.conf ~/dea/redis/

# Disable redis snapshots
echo 'save ""' >> ~/dea/redis/redis.conf

# Make redis use a unix domain socket and disable TCP sockets
sed -ie "s/port 6379/port 0/" ~/dea/redis/redis.conf
sed -ie "s/daemonize no/daemonize yes/" ~/dea/redis/redis.conf
echo "unixsocket $HOME/dea/redis/redis.sock" >> ~/dea/redis/redis.conf
echo "unixsocketperm 777" >> ~/dea/redis/redis.conf

redis-server ~/dea/redis/redis.conf

} >> ~/dea/run/user_data.log 2>&1
"""


def make_disable_hyperthreading_script():
    return """
# disable hyperthreading
# https://forums.aws.amazon.com/message.jspa?messageID=189757
for cpunum in $(
    cat /sys/devices/system/cpu/cpu*/topology/thread_siblings_list |
    sed 's/-/,/g' | cut -s -d, -f2- | tr ',' '\n' | sort -un); do
        echo 0 > /sys/devices/system/cpu/cpu$cpunum/online
done
"""

def make_master_script(exp_str, virtual_env_name="vtest", log_dir="~/dea/run"):
    cmd = """
cat > ~/dea/run/experiment.json <<< '{exp_str}'
nohup python -m bso_es_distributed.bso runbsomaster \
--master_socket_path ~/dea/redis/redis.sock \
--log_dir {log_dir} \
--exp_file ~/dea/run/experiment.json >output-master.txt 2>error-master.txt &
    """.format(exp_str=exp_str, log_dir=log_dir)
    # print(cmd)
    return """#!/bin/bash
{
cd ~/dea/run/
%s

%s
} >> ~/dea/run/user_data.log 2>&1
""" % (virtual_env_name, cmd)


def make_worker_script(node_id, master_private_ip, log_dir, virtual_env_name="vtest"):
    cmd = ("MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "
           "nohup python -m bso_es_distributed.bso runbsoworker --node_id {} --master_host {} --log_dir {} --relay_socket_path ~/dea/redis/redis.sock >output-workers.txt 2>error-worker.txt &"
    ).format(node_id, master_private_ip, log_dir)
    # print(cmd)
    return """#!/bin/bash
{
set -x
cd ~/dea/run/
%s
echo %s
%s
} >> ~/dea/run/user_data.log 2>&1
""" % (virtual_env_name, node_id, cmd)


# ToDo
def close_master_redis_script(url):
    return """#!/bin/bash
{
set -x

redis-cli -h %s -p 6379
shutdown nosave
# ps aux|grep redis-server|awk '{print $2}'|xargs kill -9

} >> ~/dea/run/user_data.log 2>&1
""" % (url)

def close_worker_redis_script():
    return """#!/bin/bash
{
set -x

redis-cli -p 6379
shutdown nosave

} >> ~/dea/run/user_data.log 2>&1
"""
