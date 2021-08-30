import paramiko
import time


class Remote_ssh():
    def __init__(self, ip, port, username, password=None, private_key_path=None, cur_pc_pwd=None):
        if password is None and private_key_path is None:
            raise TypeError("you must give either password or [private_key_path (cur_pc_pwd if private key file is encrypted)]")

        self.transport = paramiko.Transport((ip, port))
        if password is not None:
            self.transport.connect(username=username, password=password)
        if private_key_path is not None:
            self.private_key = paramiko.RSAKey.from_private_key_file(private_key_path, cur_pc_pwd)
            self.transport.connect(username=username, pkey=self.private_key)
        # self.channel = self.transport.open_session()
        self.ssh = paramiko.SSHClient()
        self.ssh._transport = self.transport
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.sftp = paramiko.SFTPClient.from_transport(self.transport)

    def run_cmd(self, cmd, close_ssh_flag=False):
        # execute one command
        # print("===============================")
        # print(cmd)
        std_in, std_out, std_err = self.ssh.exec_command(cmd)
        # print("err=== ", std_err.read().decode('utf-8').rstrip())
        result = std_out.read().decode('utf-8').rstrip()
        if close_ssh_flag:
            self.transport.close()
        return result

    def run_invoke_cmd(self, cmd, close_ssh_flag=False):
        # execute a list of commands, with state
        # print("===============================")
        # print(cmd)
        invoke = self.ssh.invoke_shell()
        invoke.send(cmd)
        time.sleep(3)
        result = invoke.recv(9999).decode("utf-8")
        # print(result)
        if close_ssh_flag:
            self.transport.close()
        return result

    def upload(self, local_file, server_file, close_ssh_flag=False):
        # upload local file to server
        self.sftp.put(local_file, server_file)
        if close_ssh_flag:
            self.transport.close()

    def download(self, server_file, local_file, close_ssh_flag=False):
        # download server file to local
        self.sftp.get(server_file, local_file)
        if close_ssh_flag:
            self.transport.close()

    def get_cpu_rate(self):
        # cpu = "top -b -n1 | sed -n '3p' | awk '{print $2}'"
        cpu = "vmstat 1 5|sed  '1d'|sed  '1d'|awk '{print $15}'" # the mean of 3 times
        std_in, std_out, std_err = self.ssh.exec_command(cpu)
        cpu_usage = std_out.readlines()
        cpu_usage = round(100 - (int(cpu_usage[2]) + int(cpu_usage[3]) + int(cpu_usage[4])) / 3, 2)
        return cpu_usage

if __name__ == '__main__':
    import os, json
    url = "~/url_test.json"
    with open(os.path.expanduser(url)) as f:
        url = json.load(f)
    ssh = Remote_ssh(url["url"], 22, username=url["name"], password=url["passwd"])
    cpu = ssh.get_cpu_rate()
    print(cpu, type(cpu))
    if cpu>10:
        print("aaa")


