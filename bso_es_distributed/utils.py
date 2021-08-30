import json
import os
import time

from .ssh_utils import Remote_ssh
from .script_util import compress_codes_script, make_file_download_script, make_master_redis_script, make_worker_redis_script, make_master_script, make_worker_script

def get_ssh_dict(url_json):
    with open(url_json, "r") as f:
        nodes = json.load(f)
    ssh_dict = {}
    master_node = nodes["master"]
    ssh = Remote_ssh(master_node["url"], 22, master_node["name"], master_node["passwd"])
    ssh_dict["master"] = {"url":master_node["url"], "ssh":ssh}
    worker_nodes = nodes["worker"]
    for node_id, v in worker_nodes.items():
        if not node_id.startswith("node"):
            raise TypeError("worker keys must be start with node")
        ssh = Remote_ssh(v["url"], 22, v["name"], v["passwd"])
        ssh_dict[node_id] = {"url":v["url"], "ssh":ssh}
    return ssh_dict

def start_server_redis(ssh_dict, compress_codes_path=None, file_download_flag=True, root_path="dea/bso/run_test"):
    # master part
    master_ssh = ssh_dict["master"]["ssh"]
    if compress_codes_path is not None:
        master_ssh.run_invoke_cmd(compress_codes_script(compress_codes_path))
    if file_download_flag:
        # download files
        master_ssh.run_cmd("mkdir -p ~/{}".format(root_path))
        master_ssh.run_cmd("rm -r ~/{}/*".format(root_path))
        master_ssh.upload(os.path.expanduser("~/dea/raw/bso_code.tar.gz"), os.path.expanduser("~/{}/bso_code.tar.gz".format(root_path)))
        # decompress
        master_ssh.run_invoke_cmd(make_file_download_script().replace("dea/run", root_path))
        print("master {} file download".format(ssh_dict["master"]["url"]))
        pass
    master_ssh.run_invoke_cmd(make_master_redis_script().replace("dea/run", root_path))

    # worker part
    for node_id, v in ssh_dict.items():
        if not node_id.startswith("node"):
            continue
        ssh = v["ssh"]
        if file_download_flag:
            # download files
            ssh.run_cmd("mkdir -p ~/{}".format(root_path))
            ssh.run_cmd("rm -r ~/{}/*".format(root_path))
            # ~ is the server home, if not the same to master server, need to modify
            ssh.upload(os.path.expanduser("~/dea/raw/bso_code.tar.gz"), os.path.expanduser("~/{}/bso_code.tar.gz".format(root_path)))
            # decompress
            ssh.run_invoke_cmd(make_file_download_script().replace("dea/run", root_path))
            print("worker {} file download".format(v["url"]))
        # redis start
        ssh.run_invoke_cmd(make_worker_redis_script().replace("dea/run", root_path))

def start_running(ssh_dict, exp_file="./humanoid.json", log_dir="~/dea/run/log1", root_path="dea/bso/run_test"):
    with open(exp_file, 'r') as f:
        exp = json.load(f)
    exp_str = json.dumps(exp)
    ssh_dict["master"]["ssh"].run_invoke_cmd(make_master_script(exp_str, log_dir=log_dir).replace("dea/run", root_path))
    for node_id, v in ssh_dict.items():
        if not node_id.startswith("node"):
            continue
        ssh = v["ssh"]
        ssh.run_invoke_cmd(make_worker_script(node_id, ssh_dict["master"]["url"], log_dir).replace("dea/run", root_path))
        print("{} worker {} start".format(node_id, v["url"]))

def close_redis(ssh_dict):
    for k, v in ssh_dict.items():
        v["ssh"].run_cmd("ps aux|grep redis-server|awk '{print $2}'|xargs kill -9")
        # v["ssh"].run_cmd("ps aux|grep python|awk '{print $2}'|xargs kill -9")

def check_server_stop(ssh_dict):
    node_ids = list(ssh_dict.keys())
    for node_id in node_ids:
        if not node_id.startswith("node"):
            node_ids.remove(node_id)
    ssh = ssh_dict[node_ids[0]]["ssh"]
    cpu_rate = ssh.get_cpu_rate()
    if cpu_rate > 10:
        return False
    else:
        for i in range(3):
            time.sleep(10)
            print("*" * 10)
            for node_id in node_ids:
                ssh = ssh_dict[node_id]["ssh"]
                cpu_rate = ssh.get_cpu_rate()
                print(node_id, cpu_rate)
                if cpu_rate > 30:
                    print("the {}th node {} not stop with cpu rate {}".format(i, node_id, cpu_rate))
                    return False
    return True

def close_server_redis(ssh_dict):
    close_redis(ssh_dict)
    for i in range(3):
        if check_server_stop(ssh_dict):
            break
        else:
            close_redis(ssh_dict)

def download_node_files(ssh_dict, root_path, copy_path=None, download_path=None, rm_root_path_flag=False):
    if download_path is not None:
        if not os.path.exists(os.path.expanduser(download_path)):
            os.makedirs(os.path.expanduser(download_path))
    for node_id, node in ssh_dict.items():
        ssh = node["ssh"]
        if copy_path is not None:
            ssh.run_cmd("cp -r {} {}".format(root_path, copy_path))
        if node_id.startswith("node"):
            if download_path is not None:
                print("start download")
                ssh.run_invoke_cmd("cd {}/log1/\ntar -zcvf ~/tmp_compress_results.tar.gz *\n".format(root_path))
                ssh.download(os.path.expanduser("~/tmp_compress_results.tar.gz"), os.path.expanduser("{}/{}_results.tar.gz".format(download_path, node_id)))
                ssh.run_cmd("rm ~/tmp_compress_results.tar.gz")
        if rm_root_path_flag:
            ssh.run_cmd("rm -r {}".format(root_path))
    pass





