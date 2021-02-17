from collections import namedtuple
from contextlib import contextmanager
from multiprocess import get_logger
from multiprocess.connection import Client, Listener
from multiprocess.managers import SyncManager, BarrierProxy, DictProxy
import os
import threading

Request = namedtuple("Request", ["member", "func", "args", "kwargs"])

default_timeout = 60
default_shared_memory_address = ("127.0.0.1", 6002)


@contextmanager
def acquire(lock, timeout=None, raise_on_fail=True):
    locked = lock.acquire(timeout=timeout)
    if raise_on_fail and not locked:
        raise RuntimeError(f"Failed to acquire lock after {timeout}s")
    try:
        yield locked
    finally:
        if locked:
            lock.release()


class DeferredFunc:
    def __init__(self, member, func_name, comms):
        self.member = member
        self.func_name = func_name
        self.comms = comms
        # Lock here such that it remains locked during the interim between wrapper being returned and it being called.
        if not self.comms.lock.acquire(self.comms.timeout):  # Released in self.wrapper()
            raise RuntimeError(f"Failed to acquire lock after {self.comms.timeout}s")

    def wrapper(self, *args, **kwargs):
        try:
            resp = self.comms.get(self.member, self.func_name, *args, **kwargs)
        finally:
            self.comms.lock.release()  # Acquired in self.__init__()
        return resp


class Mutex:
    def __init__(self, lock, *args, timeout=default_timeout, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = lock.lock if isinstance(lock, Mutex) else lock
        self.timeout = timeout

    def acquire(self, timeout=None, raise_on_fail=True):
        """
            https://docs.python.org/3/library/multiprocessing.html#multiprocessing.RLock
            The parent semantics for `timeout=None` := timeout=infinity. We have zero use case for this and, instead,
            will use `self.timeout` if `timeout is None`.
        """
        if timeout is None:
            timeout = self.timeout
        return acquire(lock=self.lock, timeout=timeout, raise_on_fail=raise_on_fail)

    def release(self):
        return self.lock.release()


class MutexedAccess(Mutex):
    def __getattribute__(self, item):
        with object.__getattribute__(self, "acquire")():
            return object.__getattribute__(self, item)

    def __setattr__(self, key, value):
        with self.acquire():
            setattr(self, key, value)


class SharedMemoryManager(SyncManager):
    """ Managers can be connected to from any process using SharedMemoryManager(address=<address>).connect().
        They therefore don't have to be passed to child processes, when created, from the parent.
        However, SyncManager.RLock() is a factory and has no functionality to return the same locks thus requiring
        the locks to still be passed to the child processes, when created, from the parent.
        This class solves this issue.
    """

    def __init__(self, *args, parties=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = get_logger()

        self.register("getpid", callable=self.getpid)

        self.lock_cache = {}  # Cache for all locks.
        self.client_cache = {}  # Cache for all client connections.

        # Nothing is stored in the above instances and must be accessed with the following registered funcs.
        self.register("get_lock_cache", callable=lambda: self.lock_cache, proxytype=DictProxy)
        self.register("get_client_cache", callable=lambda: self.client_cache, proxytype=DictProxy)

        self.barrier = threading.Barrier(parties=parties)
        self.register("get_barrier", callable=lambda: self.barrier, proxytype=BarrierProxy)

    def getpid(self):
        return os.getpid()

    @classmethod
    def get_lock(cls, address, name, timeout=default_timeout):
        cls.register("get_lock_cache")
        manager = cls(address=address)
        manager.connect()
        cache = manager.get_lock_cache()
        with cache["cache_lock"]:
            cache = manager.get_lock_cache()
            if name not in cache:
                cache.update({name: Mutex(lock=manager.RLock(), timeout=timeout)})
            return manager.get_lock_cache().get(name)

    @classmethod
    def get_client(cls, server_address, shared_memory_address):
        cls.register("get_client_cache")
        manager = cls(address=shared_memory_address)
        manager.connect()  # Get's closed by gc.
        with manager.get_lock_cache()["cache_lock"]:
            cache = manager.get_client_cache()
            if server_address not in cache:
                cache.update({server_address: Client(address=server_address, authkey=None)})
            return manager.get_client_cache().get(server_address)


class DeviceServer(Mutex, Listener):
    def __init__(self, shared_memory_address=default_shared_memory_address, *args, lock="device_server", **kwargs):
        if isinstance(lock, str):
            lock = SharedMemoryManager.get_lock(shared_memory_address, lock)

        super().__init__(*args, lock=lock, **kwargs)
        self.shared_memory_address = shared_memory_address
        self.log = get_logger()
        self.client_process_list = []  # Set in self.listen.

        # self.accept() doesn't accept a timeout (tut tut) so we have to set it lower down.
        # Without this, if no client tries to connect, self.accept() will block indefinitely waiting for a connection.
        # This could happen if a client raises/exits before connecting.
        self._listener._socket.settimeout(self.timeout)

    def are_clients_alive(self):
        is_one_alive = False
        for client in self.client_process_list:
            is_alive = client.is_alive()
            if not is_alive:
                # Check exitcode and raise on error.
                if client.exitcode != 0:
                    raise RuntimeError(f"The client process '{client.name}' exited with exitcode '{client.exitcode}'")
            is_one_alive |= is_alive
        return is_one_alive

    @classmethod
    def set_cache(cls, cache):
        """ Call this to set the cache by dynamically overriding get_cache(). """
        def get_cache(self):
            nonlocal cache
            return cache
        # Override get_cache() with the one above.
        setattr(cls, "get_cache", get_cache)

    def get_cache(self):
        raise NotImplementedError("set_cache() must be called to first register the cache to be used. ")

    def callable(self, member, item):
        return callable(self.get_cache()[member].__getattribute__(item))

    def listen(self, client_process_list):
        self.log.info(f"Server listening on '{self.address}'...")
        self.client_process_list = client_process_list

        with self.accept() as connection:  # The timeout for this is set in `self.__init__()`.
            self.log.info(f"Connection accepted from '{self.last_accepted}'")

            with self.acquire():  # Why not...

                # Spin until there's something to read,
                # whilst at least a single client is alive AND none have exited in error.
                while self.are_clients_alive():
                    if connection.poll():
                        # Read.
                        try:
                            resp = connection.recv()
                        except EOFError:
                            # The connection could have been closed during the race between poll() & recv().
                            break

                        # Type check response.
                        if not isinstance(resp, Request):
                            raise RuntimeError(f"Expected response type of '{Request}' but got '{type(resp)}'")

                        # Execute response.
                        if resp.member is None:
                            # Call self.func()
                            result = self.__getattribute__(resp.func)(*resp.args, **resp.kwargs)
                        else:
                            # Call cache[member].func()
                            result = self.get_cache()[resp.member].__getattribute__(resp.func)(*resp.args, **resp.kwargs)

                        # Send the result back to the client (no post send hand shake).
                        connection.send(result)
        self.log.info("No more clients to listen to.")


class DeviceClient(Mutex):
    def __init__(self, server_address, shared_memory_address=default_shared_memory_address, *args, lock="client", **kwargs):
        if isinstance(lock, str):
            lock = SharedMemoryManager.get_lock(shared_memory_address, lock)

        super().__init__(*args, lock=lock, **kwargs)
        self.connection = None
        self.server_address = server_address
        self.shared_memory_address = shared_memory_address
        self.log = get_logger()

    def __enter__(self):
        self.connection = SharedMemoryManager.get_client(self.server_address, self.shared_memory_address)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # self.connection is shared so we can't close it.
        pass

    def get(self, member, func, *args, **kwargs):
        with self.acquire():
            self.connection.send(Request(member=member, func=func, args=args, kwargs=kwargs))
            if not self.connection.poll(self.timeout):
                raise RuntimeError(f"No response available during the given timeout '{self.timeout}'s")
            return self.connection.recv()

    def is_callable(self, member, item):
        return self.get(None, "callable", member, item)
