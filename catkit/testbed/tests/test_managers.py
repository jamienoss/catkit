import logging
from multiprocessing import get_context, get_logger
from multiprocessing.managers import SyncManager, DictProxy
import os
import time
import sys

shared_memory_manager_address = ("127.0.0.1", 6002)


def client1():
    print(f"Client1 running... ({os.getpid()})")

    SyncManager.register("get_lock_cache")
    manager = SyncManager(address=shared_memory_manager_address)

    manager.connect()
    cache = manager.get_lock_cache()
    for i in range(50):
        with cache["client"]:
            print("c1", os.getpid())

    print("client1 done")


def client2():
    print(f"Client2 running... ({os.getpid()})")

    SyncManager.register("get_lock_cache")
    manager = SyncManager(address=shared_memory_manager_address)
    manager.connect()
    cache = manager.get_lock_cache()
    for i in range(50):
        with cache["client"]:
            print("c2", os.getpid())

    print("client2 done")


def test():
    print(f"Parent pid: {os.getpid()}")

    timeout = 30

    lock_cache = {}
    SyncManager.register("get_lock_cache", callable=lambda: lock_cache, proxytype=DictProxy)

    with SyncManager(address=shared_memory_manager_address) as manager:
        manager.get_lock_cache().update({"client": manager.RLock()})


        ctx = get_context("spawn")
        client_process_list = []
        client_process_list.append(ctx.Process(target=client1,
                                               name="test_client"))
        client_process_list.append(ctx.Process(target=client2,
                                               name="test_client2"))

        try:
            for client in client_process_list:
                client.start()
                print(f"Client '{client.name}' started with PID '{client.pid}'")
        finally:
            # Terminate and join all client/child processes.
            print("Parent b4", os.getpid(), lock_cache, manager.get_lock_cache())
            for client in client_process_list:
                client.join()
            print("Parent after", os.getpid(), lock_cache, manager.get_lock_cache())

        print("All process joined.")


if __name__ == "__main__":
    test()
