import logging
import os
import pickle
import time
from collections import deque
from pprint import pformat

import redis

logger = logging.getLogger(__name__)

EXP_KEY = 'es:exp'
TASK_ID_KEY = 'es:task_id'
TASK_DATA_KEY = 'es:task_data'
TASK_CHANNEL = 'es:task_channel'
RESULTS_KEY = 'es:results'
SUFFIX_THETA = 'es:theta'


def serialize(x):
    return pickle.dumps(x, protocol=-1)


def deserialize(x):
    return pickle.loads(x)


def retry_connect(redis_cfg, tries=300, base_delay=4.):
    for i in range(tries):
        try:
            r = redis.StrictRedis(**redis_cfg)
            r.ping()
            return r
        except redis.ConnectionError as e:
            if i == tries - 1:
                raise
            else:
                delay = base_delay * (1 + (os.getpid() % 10) / 9)
                logger.warning('Could not connect to {}. Retrying after {:.2f} sec ({}/{}). Error: {}'.format(
                    redis_cfg, delay, i + 2, tries, e))
                time.sleep(delay)


def retry_get(pipe, key, tries=300, base_delay=4.):
    for i in range(tries):
        # Try to (m)get
        if isinstance(key, (list, tuple)):
            vals = pipe.mget(key)
            if all(v is not None for v in vals):
                return vals
        else:
            val = pipe.get(key)
            if val is not None:
                return val
        # Sleep and retry if any key wasn't available
        if i != tries - 1:
            delay = base_delay * (1 + (os.getpid() % 10) / 9)
            logger.warning('{} not set. Retrying after {:.2f} sec ({}/{})'.format(key, delay, i + 2, tries))
            time.sleep(delay)
    raise RuntimeError('{} not set'.format(key))


# for BSO master
class MasterClient:
    def __init__(self, master_redis_cfg):
        self.task_counter = 0 # record the number of es theta replacement
        self.master_redis = retry_connect(master_redis_cfg)
        logger.info('[master] Connected to Redis: {}'.format(self.master_redis))

    def declare_experiment(self, exp):
        self.master_redis.set(EXP_KEY, serialize(exp))
        logger.info('[master] Declared experiment {}'.format(pformat(exp)))

    def declare_task(self, node_id, task_data):
        # set the new theta from BSO master and replace flag
        task_id = self.task_counter
        self.task_counter += 1

        serialized_task_data = serialize(task_data)
        (self.master_redis.pipeline()
         .mset({TASK_ID_KEY: task_id, node_id+":"+TASK_DATA_KEY: serialized_task_data})
         # .publish(TASK_CHANNEL, serialize((node_id, True, serialized_task_data))) # publish for all workers channel
         .publish(node_id+":"+TASK_CHANNEL, serialize((serialize(True), serialized_task_data))) # publish for node_id worker channel
         .execute())  # TODO: can we avoid transferring task data twice and serializing so much?
        logger.debug('[master] Declared task {} for node_id {}'.format(task_id, node_id))
        return task_id

    def get_result(self, node_id):
        # get the mean rewards of current theta,
        # return (x, y)
        state = deserialize(self.master_redis.get(node_id+":"+RESULTS_KEY))
        logger.debug('[master] Get a result with node_id {}'.format(node_id))
        return state

    def pop_result(self, node_id, timeout=0):
        r = self.master_redis.blpop(node_id+":"+RESULTS_KEY, timeout)
        if r is None:
            state = None
        else:
            state = deserialize(r[1])
        logger.debug('[master] Popped a result with node_id {}'.format(node_id))
        return state

    def get_beststate(self, node_id):
        state = deserialize(self.master_redis.get(node_id + ":beststate"))
        logger.debug('[master] Get a beststate with node_id {}'.format(node_id))
        return state

class RelayClient:
    """
    Receives and stores task broadcasts from the master
    Batches and pushes results from workers to the master
    """

    def __init__(self, master_redis_cfg, relay_redis_cfg, node_id=None):
        self.master_redis = retry_connect(master_redis_cfg)
        logger.info('[relay] Connected to bso master: {}'.format(self.master_redis))
        self.local_redis = retry_connect(relay_redis_cfg)
        logger.info('[relay] Connected to relay: {}'.format(self.local_redis))
        self.node_id = node_id

    def run(self):
        # Initialization: read exp and latest task from master
        self.local_redis.set(EXP_KEY, retry_get(self.master_redis, EXP_KEY))
        flag = serialize(True)
        self._declare_task_local(flag, retry_get(self.master_redis, self.node_id+":"+TASK_DATA_KEY))

        # Start subscribing to tasks
        p = self.master_redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(**{self.node_id+":"+TASK_CHANNEL: lambda msg: self._declare_task_local(*deserialize(msg['data']))})
        # p.subscribe(**{TASK_CHANNEL: lambda msg: self._declare_task_local(*deserialize(msg['data']))})
        p.run_in_thread(sleep_time=0.001)

        # Loop on RESULTS_KEY and push to master
        # batch_sizes, last_print_time = deque(maxlen=20), time.time()  # for logging
        while True:
            time.sleep(0.1)
            # flag0 = deserialize(self.local_redis.get(self.node_id + ":currentflag"))
            flag0 = deserialize(retry_get(self.local_redis, self.node_id + ":currentflag"))
            bestflag = deserialize(retry_get(self.local_redis, self.node_id + ":bestflag"))
            # curr_time = time.time()
            if flag0:
                self.local_redis.set(self.node_id + ":currentflag", serialize(False))
                # set for bso master
                # self.master_redis.set(self.node_id + ":" + RESULTS_KEY, retry_get(self.local_redis, self.node_id + ":" + RESULTS_KEY))
                # push for bso master, (each state should be set after 0.1s)
                self.master_redis.rpush(self.node_id + ":" + RESULTS_KEY, retry_get(self.local_redis, self.node_id + ":" + RESULTS_KEY))
            if bestflag:
                self.local_redis.set(self.node_id + ":bestflag", serialize(False))
                self.master_redis.set(self.node_id + ":beststate", retry_get(self.local_redis, self.node_id + ":beststate"))
            # # results = []
            # start_time = curr_time = time.time()
            # while curr_time - start_time < 0.001:
            #     # results.append(self.local_redis.blpop(RESULTS_KEY)[1])
            #     flag0 = deserialize(self.local_redis.get(self.node_id+":currentflag"))
            #     curr_time = time.time()
            #     if flag0:
            #         self.local_redis.set(self.node_id + ":currentflag", serialize(False))
            #         self.master_redis.set(self.node_id+":"+RESULTS_KEY, self.local_redis.get(self.node_id+":"+RESULTS_KEY))
            # Log
            # batch_sizes.append(len(results))
            # if curr_time - last_print_time > 5.0:
            #     logger.info('[relay] Average batch size {:.3f}'.format(sum(batch_sizes) / len(batch_sizes)))
            #     last_print_time = curr_time

    def _declare_task_local(self, flag, task_data):
        logger.info('[relay] Received task replacement in node_id {}'.format(self.node_id))
        self.local_redis.mset({self.node_id+":flag":flag, self.node_id+":"+TASK_DATA_KEY: task_data})


class WorkerClient:
    def __init__(self, relay_redis_cfg, node_id):
        self.node_id = node_id
        self.local_redis = retry_connect(relay_redis_cfg)
        logger.info('[es master and worker] Connected to relay: {}'.format(self.local_redis))

        self.cached_task_id, self.cached_task_data = None, None
        self.task_counter = 0 # record the task id (generation number)

    def get_experiment(self, flag="es worker"):
        # Grab experiment info
        exp = deserialize(retry_get(self.local_redis, EXP_KEY))
        logger.info('[node_id {} {}] Experiment: {}'.format(self.node_id, flag, exp))
        return exp

    def get_new_task(self):
        # task is just theta
        # return deserialize(self.local_redis.get(self.node_id+":"+TASK_DATA_KEY))
        return deserialize(retry_get(self.local_redis, self.node_id+":"+TASK_DATA_KEY))

    # attention to task_id(may waste a generation results)
    def set_current_task(self, task_data):
        # ToDo: set new theta by es master
        # task_data is a task obj
        task_id = self.task_counter
        self.task_counter += 1
        serialized_task_data = serialize(task_data)
        self.local_redis.mset({TASK_ID_KEY: task_id, TASK_DATA_KEY: serialized_task_data})
        logger.debug('[es master] Declared task {}'.format(task_id))
        return task_id

    def get_current_task(self):
        with self.local_redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(TASK_ID_KEY)
                    task_id = int(retry_get(pipe, TASK_ID_KEY))
                    if task_id == self.cached_task_id:
                        logger.debug('[worker] Returning cached task {}'.format(task_id))
                        break
                    pipe.multi()
                    pipe.get(TASK_DATA_KEY)
                    logger.info('[worker] Getting new task {}. Cached task was {}'.format(task_id, self.cached_task_id))
                    self.cached_task_id, self.cached_task_data = task_id, deserialize(pipe.execute()[0])
                    break
                except redis.WatchError:
                    continue
        return self.cached_task_id, self.cached_task_data

    def set_current_flag(self, flag=False):
        # current stat flag
        self.local_redis.set(self.node_id+":currentflag", serialize(flag))

    # def get_current_flag(self): # current stat flag
    #     return deserialize(self.local_redis.get(self.node_id+":currentflag"))

    def set_current_stat(self, state):
        # ToDo: set the current state to bso master
        self.local_redis.set(self.node_id + ":" +RESULTS_KEY, serialize(state))
        logger.debug('[es master] Pushed current stat for node_id {}'.format(self.node_id))
        pass

    # def push_current_stat(self, state):
    #     # ToDo: push the current state to bso master
    #     self.local_redis.rpush(self.node_id + ":" +RESULTS_KEY, serialize(state))
    #     logger.debug('[es master] Pushed current stat for node_id {}'.format(self.node_id))
    #     pass

    def set_best_stat(self, state):
        self.local_redis.set(self.node_id + ":beststate", serialize(state))
        logger.debug('[es master] Pushed best state for node_id {}'.format(self.node_id))
        pass

    def set_best_flag(self, flag=False):
        self.local_redis.set(self.node_id + ":bestflag", serialize(flag))
        pass

    def push_result(self, task_id, result):
        # ToDo: not need push the results to master
        self.local_redis.rpush(RESULTS_KEY, serialize((task_id, result)))
        logger.debug('[es worker] Pushed result for task {}'.format(task_id))

    def pop_result(self):
        task_id, result = deserialize(self.local_redis.blpop(RESULTS_KEY)[1])
        logger.debug('[es master] Popped a result for task {}'.format(task_id))
        return task_id, result

    def get_flag(self):
        # ToDo: get the flag of replace theta or not
        return deserialize(self.local_redis.get(self.node_id+":flag"))

    def set_flag(self, flag=False):
        self.local_redis.set(self.node_id+":flag", serialize(flag))