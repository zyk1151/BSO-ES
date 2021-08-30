from bso_es_distributed.utils import get_ssh_dict, start_server_redis, start_running, download_node_files, close_server_redis, check_server_stop
import os, time


if __name__ == '__main__':
    url_json = "./urls.json"
    ssh_dict = get_ssh_dict(url_json)

    # the path of the codes
    compress_codes_path = os.path.abspath("./")

    # experiment configuration file name
    names = ["humanoid_test"]


    for name in names:
            root_path = "test_dea"
            print("root_path:", root_path)

            start_server_redis(ssh_dict, compress_codes_path, root_path=root_path)

            exp_file = "./configurations/{}.json".format(name)
            log_dir = "~/{}/log1".format(root_path)

            start_running(ssh_dict, exp_file=exp_file, log_dir=log_dir, root_path=root_path)

            check_idx = 0
            while True:
                # the interval time for check_server_stop
                time.sleep(300)
                # time.sleep(30)
                print("check the {}th time".format(check_idx))
                check_idx += 1
                if check_server_stop(ssh_dict):
                    print("servers have stopped!")
                    break
            # copy
            download_node_files(ssh_dict, os.path.join(os.path.expanduser("~"), root_path), download_path=os.path.join(os.path.expanduser("~"), root_path+"/log1"), rm_root_path_flag=False)
            print("finish {} experiment.".format(name))
            print("="*20)
    print("finish all experiments.")





