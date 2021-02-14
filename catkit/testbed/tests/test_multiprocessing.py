from multiprocessing import get_context
import time
import warnings

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.hardware.npoint.nPointTipTiltController import Parameters
from catkit.testbed import devices, DeviceCacheEnum
from catkit.testbed.multiprocessing import DeviceClient, DeviceServer, MutexManager


server_address = ("127.0.0.1", 6001)
manager_address = ("127.0.0.1", 6002)


class Device(DeviceCacheEnum):
    NPOINT_C = ("npoint a for test", "dummy_config_id", server_address)
    NPOINT_D = ("npoint a for test", "dummy_config_id", server_address)


@devices.link(key=Device.NPOINT_C)
def npoint_c():
    return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")


def run_from_client(comms):
    print("Client running...")
    time.sleep(2)  # Give time for parent start listening.
    Device.set_cache(comms)
    assert Device.NPOINT_C.instrument
    print(Device.NPOINT_C.get_status(1))

    for i in range(50):
        with comms.acquire(10):
            Device.NPOINT_C.set(Parameters.P_GAIN, 1, 3.14)
            result = Device.NPOINT_C.get(Parameters.P_GAIN, 1)
            print(result)
            assert result == 3.14

    print("client1 done")


def run_from_client2(comms):
    print("Client running...")
    time.sleep(2)  # Give time for parent start listening.
    Device.set_cache(comms)
    assert Device.NPOINT_C.instrument
    print(Device.NPOINT_C.get_status(1))

    manager = MutexManager(address=manager_address)
    manager.connect()
    with manager.RLock("client").acquire():
        for i in range(50):
            with comms.acquire(10):
                Device.NPOINT_C.set(Parameters.P_GAIN, 1, 1.42)
                result = Device.NPOINT_C.get(Parameters.P_GAIN, 1)
                print(result)
                assert result == 1.42

    print("client2 done")


def test_device_server():

    timeout = 30

    with MutexManager(address=("127.0.0.1", 6002)) as manager:
        with devices:
            with DeviceServer(address=server_address,
                              lock=manager.RLock("server", timeout=timeout)) as device_server:
                device_server.set_cache(devices)
                with DeviceClient(address=server_address, lock=manager.RLock("client", timeout=timeout)) as client_comms:

                    ctx = get_context("spawn")
                    client_process_list = []
                    client_process_list.append(ctx.Process(target=run_from_client,
                                                           name="test_client",
                                                           kwargs=dict(comms=client_comms)))
                    client_process_list.append(ctx.Process(target=run_from_client2,
                                                           name="test_client",
                                                           kwargs=dict(comms=client_comms)))

                    try:
                        # Start client. This sleeps to give listener time to begin.
                        for client in client_process_list:
                            client.start()
                            print(f"Client '{client.name}' started with PID '{client.pid}'")

                        # Start listening. This parent process is the device server.
                        device_server.listen(client_process_list)
                    finally:
                        # Terminate and join all client/child processes.
                        for client in client_process_list:
                            if client.is_alive():
                                # Race exists between is_alive() and here.
                                client.terminate()  # Has no return value (None).
                                client.join(timeout)  # Has no return value (None).
                                if client.exitcode != 0:
                                    warnings.warn(f"The client process '{client.name}' with PID '{client.pid}' failed to exit.")
                        print("All process terminated and joined.")


if __name__ == "__main__":
    test_device_server()
