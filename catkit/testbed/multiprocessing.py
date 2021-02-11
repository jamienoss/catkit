from collections import namedtuple
from contextlib import contextmanager
from enum import Enum
from multiprocessing import Pipe, Manager


Request = namedtuple("Request", ["member", "func", "args", "kwargs"])


class CommsGroup(Enum):
    CLIENT = 1
    SERVER = 2


class DeviceComms:
    def __init__(self, connection, lock, *args, timeout=5*60, **kwargs):
        self.connection = connection
        self.lock = lock
        self.timeout = timeout

    @contextmanager
    def acquire_lock(self, timeout=None, raise_on_fail=True):
        locked = self.lock.acquire(timeout)
        if raise_on_fail and not locked:
            raise RuntimeError(f"Failed to acquire lock after {timeout}s")
        try:
            yield locked
        finally:
            if locked:
                self.lock.release()


class DeviceServer(DeviceComms):
    def __init__(self, *args, client_list=[], **kwargs):
        super().__init__(*args, **kwargs)
        self.client_list = client_list

    def are_clients_alive(self):
        is_alive = False
        for client in self.client_list:
            is_alive |= client.is_alive()
        return is_alive

    def get_cache(self):
        pass

    def is_callable(self, member, item):
        return callable(self.get_cache()[member].__getattribute__(item))

    def listen(self):
        if not self.lock.acquire(self.timeout):
            raise RuntimeError(f"Failed to acquire lock after {timeout}s")
        try:
            while self.are_clients_alive():
                # spin until there's something to read.
                while not self.connection.poll():
                    pass
                # Read.
                resp = self.connection.recv()
                # Type check.
                if not isinstance(resp, Request):
                    raise RuntimeError(f"Expected response type of '{Request}' but got '{type(resp)}'")

                if resp.member is None:
                    # Call self.func()
                    result = self.__getattribute__(resp.func)(*resp.args, **resp.kwargs)
                else:
                    # Call cache[member].func()
                    result = self.get_cache()[resp.member].__getattribute__(resp.func)(*resp.args, **resp.kwargs)

                # Send the result back to the client (no post send hand shake).
                self.connection.send(result)
        finally:
            self.lock.release()
        print("No more clients to listen to, terminating.")


class DeviceClient(DeviceComms):
    def get(self, member, func, *args, **kwargs):
        with self.acquire_lock(timeout=self.timeout):
            print("sending...")
            self.connection.send(Request(member=member, func=func, args=args, kwargs=kwargs))
            self.connection.poll(self.timeout)
            return self.connection.recv()

    def is_callable(self, member, item):
        return self.get(None, "callable", member, item)


class DeviceCommsManager:

    def __init__(self, *args, **kwargs):
        self.manager = None
        self.comms = {group: None for group in CommsGroup}

    def __enter__(self, client_list=[]):
        self.manager = Manager().__enter__()
        client, server = Pipe(duplex=True)
        self.comms[CommsGroup.CLIENT] = DeviceClient(connection=client, lock=self.manager.RLock())
        self.comms[CommsGroup.SERVER] = DeviceServer(connection=server, lock=self.manager.RLock(), client_list=client_list)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for comm in self.comms.values():
            if comm:
                comm.connection.close()
        self.manager.__exit__(None, None, None)


class DeferredFunc:
    def __init__(self, member, func_name, comms):
        self.member = member
        self.func_name = func_name
        self.comms = comms
        # Lock here such that it remains locked during the interim of wrapper being returned and it being called.
        if not self.comms.lock.acquire(self.comms.timeout):  # Released in self.wrapper()
            raise RuntimeError(f"Failed to acquire lock after {timeout}s")

    def wrapper(self, *args, **kwargs):
        try:
            resp = self.comms.get(self.member, self.func, args, kwargs)
        finally:
            self.comms.lock.release() # Acquired in self.__init__()
        return resp
