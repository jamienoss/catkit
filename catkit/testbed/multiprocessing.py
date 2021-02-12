from collections import namedtuple
from contextlib import contextmanager
import multiprocessing
from multiprocessing.connection import Client, Listener


Request = namedtuple("Request", ["member", "func", "args", "kwargs"])


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


class RLockContainer:
    def __init__(self, lock, *args, timeout=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = lock
        self.timeout = timeout
        self.log = multiprocessing.get_logger(__name__)

    @contextmanager
    def acquire_lock(self, timeout=None, raise_on_fail=True):
        """
            https://docs.python.org/3/library/multiprocessing.html#multiprocessing.RLock
            The parent semantics for `timeout=None` := timeout=infinity. We have zero use case for this and, instead,
            will use `self.timeout` if `timeout is None`.
        """
        if timeout is None:
            timeout = self.timeout
        locked = self.lock.acquire(timeout=timeout)
        if raise_on_fail and not locked:
            raise RuntimeError(f"Failed to acquire lock after {timeout}s")
        try:
            yield locked
        finally:
            if locked:
                self.lock.release()


class DeviceServer(RLockContainer, Listener):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_process_list = []  # Set in self.listen.

        # self.accept() doesn't accept a timeout (tut tut) so we have to set it lower down.
        # Without this, if no client tries connects, self.accept() will block indefinitely waiting for a connection.
        # This could happen if a client raises/exits before connecting.
        self._listener._socket.settimeout(self.timeout)

    def are_clients_alive(self):
        is_alive = False
        for client in self.client_process_list:
            is_alive = client.is_alive()
            if not is_alive:
                # Check exitcode and raise on error.
                if client.exitcode != 0:
                    raise RuntimeError(f"The client process '{client.name}' exited with exitcode '{client.exitcode}'")
            is_alive |= is_alive
        return is_alive

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
            try:
                if not self.lock.acquire(self.timeout):
                    raise RuntimeError(f"Failed to acquire lock after {self.timeout}s")
                while self.are_clients_alive():  # Spin until there's something to read.
                    if connection.poll():
                        # Read.
                        try:
                            resp = connection.recv()
                        except EOFError:
                            break

                        # Type check.
                        if not isinstance(resp, Request):
                            raise RuntimeError(f"Expected response type of '{Request}' but got '{type(resp)}'")

                        # Execute.
                        if resp.member is None:
                            # Call self.func()
                            result = self.__getattribute__(resp.func)(*resp.args, **resp.kwargs)
                        else:
                            # Call cache[member].func()
                            result = self.get_cache()[resp.member].__getattribute__(resp.func)(*resp.args, **resp.kwargs)

                        # Send the result back to the client (no post send hand shake).
                        connection.send(result)
            finally:
                self.lock.release()
        self.log.info("No more clients to listen to.")


class DeviceClient(RLockContainer):
    def __init__(self, address, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.address = address

    def __enter__(self):
        self.connection = Client(address=self.address, authkey=None)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.connection.close()

    def get(self, member, func, *args, **kwargs):
        with self.acquire_lock(timeout=self.timeout):
            self.connection.send(Request(member=member, func=func, args=args, kwargs=kwargs))
            self.connection.poll(self.timeout)
            return self.connection.recv()

    def is_callable(self, member, item):
        return self.get(None, "callable", member, item)
