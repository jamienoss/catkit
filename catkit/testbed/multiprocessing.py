from collections import namedtuple
from contextlib import contextmanager
from multiprocessing import Pipe, Manager
from multiprocessing.connection import Connection, Listener
import os
import socket

Request = namedtuple("Request", ["member", "func", "args", "kwargs"])


class DeferredFunc:
    def __init__(self, member, func_name, comms):
        self.member = member
        self.func_name = func_name
        self.comms = comms
        # Lock here such that it remains locked during the interim of wrapper being returned and it being called.
        if not self.comms.lock.acquire(self.comms.timeout):  # Released in self.wrapper()
            raise RuntimeError(f"Failed to acquire lock after {self.comms.timeout}s")

    def wrapper(self, *args, **kwargs):
        try:
            resp = self.comms.get(self.member, self.func_name, *args, **kwargs)
        finally:
            self.comms.lock.release()  # Acquired in self.__init__()
        return resp


class DeviceServer(Listener):
    def __init__(self, lock, client_list, *args, timeout=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = lock
        self.timeout = timeout
        self.client_list = client_list

        # self.accept() doesn't accept a timeout (tut tut) so we have to set it lower down.
        # Without this, if no client tries connects, self.accept() will block indefinitely waiting for a connection.
        # This could happen if a client raises/exits before connecting.
        self._listener._socket.settimeout(self.timeout)

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

    def are_clients_alive(self):
        is_alive = False
        for client in self.client_list:
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

    def listen(self):
        print("listening...")

        with self.accept() as connection:
            print("connection accepted")
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
        print("No more clients to listen to, terminating.")


class DeviceClient:
    def __init__(self, address, lock, *args, timeout=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.address = address
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

    def __enter__(self):
        self.connection = Client(address=self.address, authkey=None)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def get(self, member, func, *args, **kwargs):
        with self.acquire_lock(timeout=self.timeout):
            self.connection.send(Request(member=member, func=func, args=args, kwargs=kwargs))
            self.connection.poll(self.timeout)
            return self.connection.recv()

    def is_callable(self, member, item):
        return self.get(None, "callable", member, item)


#
# Stuff swiped from multiprocessing.connection
#

MESSAGE_LENGTH = 20

CHALLENGE = b'#CHALLENGE#'
WELCOME = b'#WELCOME#'
FAILURE = b'#FAILURE#'


def deliver_challenge(connection, authkey):
    import hmac
    if not isinstance(authkey, bytes):
        raise ValueError(
            "Authkey must be bytes, not {0!s}".format(type(authkey)))
    message = os.urandom(MESSAGE_LENGTH)
    connection.send_bytes(CHALLENGE + message)
    digest = hmac.new(authkey, message, 'md5').digest()
    response = connection.recv_bytes(256)        # reject large message
    if response == digest:
        connection.send_bytes(WELCOME)
    else:
        connection.send_bytes(FAILURE)
        raise RuntimeError('Auth error: digest received was wrong')


def answer_challenge(connection, authkey):
    import hmac
    if not isinstance(authkey, bytes):
        raise ValueError(
            "Authkey must be bytes, not {0!s}".format(type(authkey)))
    message = connection.recv_bytes(256)         # reject large message
    assert message[:len(CHALLENGE)] == CHALLENGE, 'message = %r' % message
    message = message[len(CHALLENGE):]
    digest = hmac.new(authkey, message, 'md5').digest()
    connection.send_bytes(digest)
    response = connection.recv_bytes(256)        # reject large message
    if response != WELCOME:
        raise RuntimeError('Auth error: digest sent was rejected')


def SocketClient(address, family=socket.AF_INET):
    if family != socket.AF_INET:
        raise NotImplementedError
    with socket.socket(family) as s:
        s.setblocking(False)  # <------ original code blocked, this is the reason for copying this code.
        s.connect(address)
        c = Connection(s.detach())


def Client(address, family=socket.AF_INET, authkey=None):
    if family != socket.AF_INET:
        raise NotImplementedError
    c = SocketClient(address, family)

    if authkey is not None and not isinstance(authkey, bytes):
        raise TypeError('authkey should be a byte string')

    if authkey is not None:
        answer_challenge(c, authkey)
        deliver_challenge(c, authkey)

    return c