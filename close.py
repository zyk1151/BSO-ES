from bso_es_distributed.utils import close_server_redis, get_ssh_dict, check_server_stop

if __name__ == '__main__':
    url = "./urls.json"
    ssh_dict = get_ssh_dict(url)
    close_server_redis(ssh_dict)
    x = check_server_stop(ssh_dict)
    print(x)
    pass


