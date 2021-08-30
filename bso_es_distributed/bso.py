'''
    bso-v1
    threshold condition

'''

import numpy as np
import os

from .dist_bso import MasterClient, WorkerClient, RelayClient
from .es_bso import run_master, run_worker, SharedNoiseTable, setup, RunningStat
from .utils import get_ssh_dict, close_server_redis

import logging
logger = logging.getLogger(__name__)
import time
import click
import errno, sys, json

# import multiprocessing as mp

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

@click.group()
def cli():
    logging.basicConfig(
        format='[%(asctime)s pid=%(process)d] %(message)s',
        level=logging.INFO,
        stream=sys.stderr)


def logsig(x):
    return 1 / (1 + np.exp(-x))


# def save_results(state, file_path):
#     # save the final results
#     with open(file_path, "w") as f:
#         json.dump(state, f)


def stop_all_servers(url_json):
    ssh_dict = get_ssh_dict(url_json)
    close_server_redis(ssh_dict)


# def compute_test(env, policy, ntest):
#     rews = np.empty((ntest,))
#     for i in range(ntest):
#         rew, t = policy.rollout(env)
#         rews[i] = np.sum(rew)
#     return np.mean(rews)

# def compute_test_thread(env, policy, ntest):
#     start = time.time()
#     num_cores = int(mp.cpu_count()) - 2
#     pool = mp.Pool(num_cores)
#     ret = [pool.apply_async(policy.rollout, args=(env,)) for _ in range(ntest)]
#     ret = [p.get() for p in ret]
#     print(ret)
#     # print("test time:{}, mean:{}".format(time.time()-start, np.mean(np.array(ret))))
#     pass

def print_state(state, tlogger):
    tlogger.log("EpRewMean:{}".format(state.EpRewMean))
    tlogger.log("EpRewStd:{}".format(state.EpRewStd))
    tlogger.log("EpLenMean:{}".format(state.EpLenMean))
    tlogger.log("EvalEpRewMean:{}".format(state.EvalEpRewMean))
    tlogger.log("EvalEpRewStd:{}".format(state.EvalEpRewStd))
    tlogger.log("EvalEpLenMean:{}".format(state.EvalEpLenMean))
    tlogger.log("EvalEpCount:{}".format(state.EvalEpCount))
    tlogger.log("EpisodesThisIter:{}".format(state.EpisodesThisIter))
    tlogger.log("EpisodesSoFar:{}".format(state.EpisodesSoFar))
    tlogger.log("TimestepsThisIter:{}".format(state.TimestepsThisIter))
    tlogger.log("TimestepsSoFar:{}".format(state.TimestepsSoFar))
    tlogger.log("TimeElapsedThisIter:{}".format(state.TimeElapsedThisIter))
    tlogger.log("num_generation:{}".format(state.num_generation))
    tlogger.log("TimeElapsed:{}".format(state.TimeElapsed))
    pass


@cli.command()
@click.option('--exp_str')
@click.option('--exp_file')
@click.option('--master_socket_path', required=True)
@click.option('--log_dir')
@click.option('--url_json')
def runbsomaster(exp_str, exp_file, master_socket_path, log_dir, url_json):
    master_redis_cfg = {'unix_socket_path': master_socket_path}
    log_dir = os.path.expanduser(log_dir) if log_dir else '/tmp/es_master_{}'.format(os.getpid())
    mkdir_p(log_dir)

    logger.info('run_bso_master: {}'.format(locals()))
    from . import tabular_logger as tlogger
    logger.info('Tabular logging to {}'.format(log_dir))
    tlogger.start(log_dir)

    assert (exp_str is None) != (exp_file is None), 'Must provide exp_str xor exp_file to the master'
    if exp_str:
        exp = json.loads(exp_str)
    elif exp_file:
        with open(exp_file, 'r') as f:
            exp = json.loads(f.read())
            # exp = json.load(f)
    else:
        assert False

    master = MasterClient(master_redis_cfg)
    master.declare_experiment(exp)

    # exp
    config, env, sess, policy = setup(exp, single_threaded=False)
    ndim = policy.num_params

    # hyper-parameters
    # # interaction
    # check_time = 300
    # # check_time = 100
    # # policy ndim
    # # ndim = 10
    # n_population = 6
    # elite_percent = 0.3
    # replace_percent = 0.3
    # # replace_percent = 0
    # p_norm = 0.95
    # p_one = 0.5
    # # max_generation = 30
    # max_generation = 15
    # k = 25
    # threshold_value = 6000

    bso_params = exp["bso"]
    check_time = bso_params["check_time"]
    n_population = bso_params["n_population"]
    elite_percent = bso_params["elite_percent"]
    replace_percent = bso_params["replace_percent"]
    p_norm = bso_params["p_norm"]
    p_one = bso_params["p_one"]
    max_generation = bso_params["max_generation"]
    k = bso_params["k"]

    threshold_value = exp["stop"]["threshold_value"]
    max_runtime = exp["stop"]["max_runtime"]
    # termination_falg = False
    if threshold_value <=0:
        threshold_value = np.inf
        threshold_value_flag = True
    else:
        threshold_value_flag = False
    if max_runtime <=0:
        max_runtime = np.inf
        max_runtime_flag = True
    else:
        max_runtime_flag = False

    replace_num = int(np.ceil(n_population * replace_percent))

    elite_num = int(np.ceil(n_population*elite_percent))
    normal_num = n_population - elite_num
    node_ids = ["node" + str(i) for i in range(n_population)]
    # bso initialize population
    XX = np.random.randn(n_population, ndim)
    X = np.empty((n_population, ndim), dtype=np.float32)
    X[:, :] = XX[:, :]

    # save init policy
    ob_stat = RunningStat(
        env.observation_space.shape,
        eps=1e-2  # eps to prevent dividing by zero at the beginning when computing mean/stdev
    )
    for i_init in range(n_population):
        policy.set_trainable_flat(X[i_init, :])
        if policy.needs_ob_stat:
            policy.set_ob_stat(ob_stat.mean, ob_stat.std)
        policy.save(log_dir+"/init_x_{}.h5".format(i_init))

    fittness = np.empty((n_population,))
    update_dict = {}
    for i in range(n_population):
        update_dict["node"+str(i)] = True

    num_generation = 0

    states_now = {}

    best_y = -np.inf

    while True:
        tlogger.log('********** Generation {} **********'.format(num_generation))
        # update the theta of nodes if needed
        for i in range(n_population):
            node_id = node_ids[i]
            if update_dict[node_id]:
                master.declare_task(node_id, X[i, :])
                update_dict[node_id] = False

        # get the current results of all nodes for certain time/generations
        # certain time
        # time.sleep(check_time)
        start_generation = time.time()

        states = {}
        num_to_threshold = 0 # record the num times for threshold reaching
        cur_time = 0

        while time.time()-start_generation<check_time:
            for i in range(n_population):
                state = master.pop_result(node_ids[i], timeout=0.5)
                if state is not None:
                    states[node_ids[i]] = state
                    # just for record info
                    states_now[node_ids[i]] = state

                    cur_time = state.TimeElapsed
                    #print("cur_time:", cur_time)

                    if not threshold_value_flag and state.EvalEpRewMean >= threshold_value:
                        # termination_falg = True
                        threshold_value_flag = True
                        print("threshold enought")

                        # reconstruct policy
                        policy.set_trainable_flat(state.x)
                        if policy.needs_ob_stat:
                            policy.set_ob_stat(state.ob_stat_mean, state.ob_stat_std)

                        policy.save(log_dir+"/first_threshold_x_iter{:05d}_rew{}.h5".format(state.num_generation, int(state.EvalEpRewMean))) # state.EvalEpRewMean is not np.nan
                        tlogger.log("the first time to reach threshold by TimeElapsed:{} with node_id:{}".format(state.TimeElapsed, node_ids[i]))


                    # if state.EvalEpRewMean >= threshold_value:
                    #     num_to_threshold += 1
                    #     tlogger.log('the {}th reach threshold with EvalEpRewMean {}'.format(num_to_threshold, state.EvalEpRewMean))
                    #     # compute 100test
                    #     policy.set_trainable_flat(state.x)
                    #     if policy.needs_ob_stat:
                    #         policy.set_ob_stat(state.ob_stat_mean, state.ob_stat_std)
                    #
                    #     policy.save(log_dir + "/test_{}.h5".format(num_to_threshold))
                    #
                    #     start_compute_test = time.time()
                    #     rew_mean = compute_test(env, policy, ntest=100)
                    #     tlogger.log('100 reward mean:{} with test runtime:{} by node_id:{}'.format(rew_mean, time.time()-start_compute_test, node_ids[i]))
                    #     if rew_mean >= threshold_value:
                    #         termination_falg = True
                    #         policy.save(log_dir+"/first_threshold_x_rew{}.h5".format(int(rew_mean)))
                    #         tlogger.log("TimeElapsed:{}".format(state.TimeElapsed))


                        pass

                    if not max_runtime_flag and cur_time >= max_runtime:
                        max_runtime_flag = True
                        print("max runtime enought")
                        # saving the last state policy
                        for i_max_runtime in range(n_population):
                            state = states_now.get(node_ids[i_max_runtime])
                            if state is not None:
                                # reconstruct policy
                                policy.set_trainable_flat(state.x)
                                if policy.needs_ob_stat:
                                    policy.set_ob_stat(state.ob_stat_mean, state.ob_stat_std)

                                policy.save(log_dir + "/{}_max_runtime_x_iter{:05d}_rew{}.h5".format(node_ids[i_max_runtime], state.num_generation, int(state.EvalEpRewMean)))  # state.EvalEpRewMean is not np.nan
                                tlogger.log("the policy for {} to reach max_runtime with EvalEpRewMean:{}".format(node_ids[i_max_runtime], state.EvalEpRewMean))

                            pass
                    pass
                pass
            if threshold_value_flag and max_runtime_flag:
                break

            if cur_time >= max_runtime:
                break

        if threshold_value_flag and max_runtime_flag:
            for i_best in range(n_population):
                best_state = master.get_beststate(node_ids[i_best])
                policy.set_trainable_flat(best_state.x)
                if policy.needs_ob_stat:
                    policy.set_ob_stat(best_state.mean, best_state.std)
                policy.save(log_dir + "/{}_best_rew{}.h5".format(node_ids[i_best], int(best_state.y)))
                tlogger.log("the best policy until now for {} with EvalEpRewMean:{}".format(node_ids[i_best], best_state.y))
            break

        if cur_time >= max_runtime:
            for i_best in range(n_population):
                best_state = master.get_beststate(node_ids[i_best])
                policy.set_trainable_flat(best_state.x)
                if policy.needs_ob_stat:
                    policy.set_ob_stat(best_state.mean, best_state.std)
                policy.save(log_dir + "/{}_best_rew{}.h5".format(node_ids[i_best], int(best_state.y)))
                tlogger.log("the best policy until now for {} with EvalEpRewMean:{}".format(node_ids[i_best], best_state.y))
            tlogger.log("the policy to reach max_runtime without reaching threshold")
            break



        # for i in range(n_population):
        #     node_id = node_ids[i]
        #     # pop_result:(x, y)
        #     results = master.get_result(node_id)
        #     X[i, :] = results.x
        #     fittness[i] = results.y
        #     tlogger.log("node{} fitness:{} cur_generation:{}".format(str(i), fittness[i], results.num_generation))
        #print("keys:", states.keys())
        for i in range(n_population):
            node_id = node_ids[i]
            state = states[node_id]
            if state is None:
                break
            else:
                X[i, :] = state.x
                # fittness[i] = state.EpRewMean
                fittness[i] = state.EvalEpRewMean
                tlogger.log("node{} fitness:{} cur_generation:{}".format(str(i), fittness[i], state.num_generation))

        
        # bso update the new population(not all new individuals)
        index = np.argsort(-fittness) # descend

        # create new individuals
        for i in range(replace_num):
            if np.random.uniform() < p_norm:
                if np.random.uniform() < p_one:
                    n1 = np.random.randint(0, normal_num) + elite_num
                    sel_x = X[n1, :]
                    idx_rep = n1
                    pass
                else:
                    n1 = np.random.randint(0, normal_num) + elite_num
                    n2 = np.random.randint(0, normal_num) + elite_num
                    sel_x = 0.5 * (X[n1, :] + X[n2, :])
                    idx_rep = np.random.choice([n1, n2])
            else:
                if np.random.uniform() < p_one:
                    n1 = np.random.randint(0, elite_num)
                    sel_x = X[n1, :]
                    idx_rep = n1
                    pass
                else:
                    n1 = np.random.randint(0, elite_num)
                    n2 = np.random.randint(0, elite_num)
                    sel_x = 0.5 * (X[n1, :] + X[n2, :])
                    idx_rep = np.random.choice([n1, n2])
            replace_node_idx = index[idx_rep]
            update_dict[node_ids[replace_node_idx]] = True
            if num_generation < max_generation:
                coef = logsig((0.5 * max_generation - num_generation) / k) * np.random.uniform(0, 1)
            else:
                coef = 0
            X[replace_node_idx, :] = sel_x + coef * np.random.standard_normal((ndim,))
            tlogger.log('********** replace node{} **********'.format(replace_node_idx))

        num_generation += 1

    for k, v in states_now.items():
        tlogger.log("*"*15)
        tlogger.log("node_id:{}".format(k))
        print_state(v, tlogger)

    url_json = url_json if url_json else "./urls.json"
    stop_all_servers(url_json)
    pass

@cli.command()
@click.option('--node_id', required=True)
@click.option('--master_host', required=True)
@click.option('--master_port', default=6379, type=int)
@click.option('--relay_socket_path', required=True)
@click.option('--num_workers', type=int, default=0)
@click.option('--log_dir')
def runbsoworker(node_id, master_host, master_port, relay_socket_path, num_workers, log_dir):
    logger.info('run_000_worker: {}'.format(locals()))
    master_redis_cfg = {'host': master_host, 'port': master_port}
    relay_redis_cfg = {'unix_socket_path': relay_socket_path}
    noise = SharedNoiseTable()  # Workers share the same noise

    # fork for RelayClient
    if os.fork()==0:
        RelayClient(master_redis_cfg, relay_redis_cfg, node_id).run()
        pass

    # fork for es.master
    # Start the master
    # assert (exp_str is None) != (exp_file is None), 'Must provide exp_str xor exp_file to the master'
    # if exp_str:
    #     exp = json.loads(exp_str)
    # elif exp_file:
    #     with open(exp_file, 'r') as f:
    #         exp = json.loads(f.read())
    #         # exp = json.load(f)
    # else:
    #     assert False
    log_dir = os.path.expanduser(log_dir) if log_dir else '/tmp/es_master_{}'.format(os.getpid())
    mkdir_p(log_dir)
    if os.fork()==0:
        run_master(relay_redis_cfg, log_dir, noise, node_id)
        pass

    # fork for es.workers
    # Start the workers
    num_workers = num_workers if num_workers else os.cpu_count() - 4
    logging.info('Spawning {} workers'.format(num_workers))
    for _ in range(num_workers):
        if os.fork()==0:
            run_worker(relay_redis_cfg, noise, node_id)
            pass
    pass


if __name__ == '__main__':
    cli()