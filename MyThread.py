from executor.safe_queue import Executor, Job
import numpy as np


class MyThread:
    # 配置
    param = []
    engine: Executor
    # 下载订阅链接将其合并
    sub_link = []
    thread_num = 1

    def __init__(self, func, param, callback, thread_num=1) -> None:
        self.func = func
        self.param = param
        self.callback = callback
        self.thread_num = thread_num

    def execute(self,):
        split_array = np.array_split(self.param, self.thread_num)
        self.engine = Executor(number_threads=len(
            split_array), max_queue_size=0)
        for sa in split_array:
            print(sa)
            self.engine.send(
                Job(func=self.func, args=(sa,), kwargs={}, callback=self.callback))
        self.engine.wait()
