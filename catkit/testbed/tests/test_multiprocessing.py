from multiprocessing import get_context
import os
import signal
import time
import warnings

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.hardware.npoint.nPointTipTiltController import Parameters
from catkit.testbed import devices, DeviceCacheEnum
from catkit.testbed.multiprocessing import DeviceClient, DeviceServer, SharedMemoryManager
from multiprocessing.managers import DictProxy


device_server_address = ("127.0.0.1", 6001)
shared_memory_manager_address = ("127.0.0.1", 6002)


class Device(DeviceCacheEnum):
    NPOINT_C = ("npoint a for test", "dummy_config_id", device_server_address)
    NPOINT_D = ("npoint a for test", "dummy_config_id", device_server_address)


@devices.link(key=Device.NPOINT_C)
def npoint_c():
    return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")


def run_from_client():
    print(f"Client running... ({os.getpid()})")

    with DeviceClient(server_address=device_server_address) as comms:
        Device.set_cache(comms)

        assert Device.NPOINT_C.instrument
        print(Device.NPOINT_C.get_status(1))

        for i in range(50):
            with comms.acquire():
                Device.NPOINT_C.set(Parameters.P_GAIN, 1, 3.14)
                result = Device.NPOINT_C.get(Parameters.P_GAIN, 1)
                print(os.getpid(), result)
                assert result == 3.14

    print("client1 done")


def run_from_client2():
    print(f"Client2 running... ({os.getpid()})")
    with DeviceClient(server_address=device_server_address) as comms:
        Device.set_cache(comms)

        assert Device.NPOINT_C.instrument
        print(Device.NPOINT_C.get_status(1))

        manager = SharedMemoryManager(address=shared_memory_manager_address)
        manager.connect()
        for i in range(50):
            #with manager.get_lock_cache()["client"].acquire():
            with comms.acquire():
                Device.NPOINT_C.set(Parameters.P_GAIN, 1, 1.42)
                result = Device.NPOINT_C.get(Parameters.P_GAIN, 1)
                print(os.getpid(), result)
                assert result == 1.42

    print("client2 done")


def test_device_server():

    print(f"Parent pid: {os.getpid()}")

    timeout = 30
    with devices:

        lock_cache = {}  # Cache for all locks.
        client_cache = {}  # Cache for all client connections.
        # Nothing is stored in the above instances and must be accessed with the following registered funcs.
        SharedMemoryManager.register("get_lock_cache", callable=lambda: lock_cache, proxytype=DictProxy)
        SharedMemoryManager.register("get_client_cache", callable=lambda: client_cache, proxytype=DictProxy)

        with SharedMemoryManager(address=shared_memory_manager_address) as manager:
            print(f"Manager running on pid: {manager.getpid()}")

            # Create a single lock to mutex CAS access to ``lock_cache`` and ``client_cache``.
            manager.get_lock_cache().update({"cache_lock": manager.RLock()})

            with DeviceServer(address=device_server_address) as device_server:
                device_server.set_cache(devices)
                ctx = get_context("spawn")
                client_process_list = []
                client_process_list.append(ctx.Process(target=run_from_client,
                                                       name="test_client"))
                client_process_list.append(ctx.Process(target=run_from_client2,
                                                       name="test_client2"))
                try:
                    # Start client. This sleeps to give listener time to begin.
                    for client in client_process_list:
                        client.start()

                    # Start listening. This parent process is the device server.
                    device_server.listen(client_process_list)
                finally:
                    # Terminate and join all client/child processes.
                    for client in client_process_list:
                        if client.is_alive():
                            # Race exists between is_alive() and here.
                            client.terminate()  # Has no return value (None).
                            client.join(timeout)  # Has no return value (None).
                            if client.exitcode != 0 and client.exitcode != signal.SIGTERM.value:
                                warnings.warn(f"The client process '{client.name}' with PID '{client.pid}' failed to exit with exitcode '{client.exitcode}'.")
                    print("All process terminated and joined.")

            assert not lock_cache
            assert not client_cache
            print("lock_cache", lock_cache, manager.get_lock_cache())
            print("client_cache", client_cache, manager.get_client_cache())


if __name__ == "__main__":
    test_device_server()
