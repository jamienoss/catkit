from multiprocessing import Manager, get_context
import time
import warnings

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.hardware.npoint.nPointTipTiltController import Parameters
from catkit.testbed import devices, DeviceCacheEnum
from catkit.testbed.multiprocessing import DeviceClient, DeviceServer


server_address = ("127.0.0.1", 6000)


class Device(DeviceCacheEnum):
    NPOINT_C = ("npoint a for test", "dummy_config_id", server_address)
    NPOINT_D = ("npoint a for test", "dummy_config_id", server_address)


@devices.link(key=Device.NPOINT_C)
def npoint_c():
    return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")


def run_from_client(address, lock, timeout):
    print("Client running...")



    with DeviceClient(address=address, lock=lock, timeout=timeout) as client:
        time.sleep(2)  # Give time for parent start listening.
        Device.set_cache(client)
        assert Device.NPOINT_C.instrument
        for channel in Device.NPOINT_C.channels:
            print(Device.NPOINT_C.get_status(channel))

        Device.NPOINT_C.set(Parameters.P_GAIN, 1, 3.14)
        assert Device.NPOINT_C.get(Parameters.P_GAIN, 1) == 3.14

        for channel in Device.NPOINT_C.channels:
            print(Device.NPOINT_C.get_status(channel))
        print("Client closing")


def test():

    timeout = 30

    with Manager() as manager:
        with devices:

            # Create client processes.
            client_process_list = []
            client_lock = manager.RLock()
            ctx = get_context("spawn")
            client_process_list.append(ctx.Process(target=run_from_client,
                                                   name="test_client",
                                                   kwargs=dict(address=server_address,
                                                               lock=client_lock,
                                                               timeout=timeout)))
            client_process_list.append(ctx.Process(target=run_from_client,
                                                   name="test_client",
                                                   kwargs=dict(address=server_address,
                                                               lock=client_lock,
                                                               timeout=timeout)))

            with DeviceServer(address=server_address,
                              lock=manager.RLock(),
                              client_list=client_process_list,
                              timeout=timeout) as device_server:
                device_server.set_cache(devices)

                try:
                    # Start client. This sleeps to give listener time to begin.
                    for client in client_process_list:
                        client.start()
                        print(f"Client '{client.name}' started with PID '{client.pid}'")

                    # Start listening. This parent process is the device server.
                    device_server.listen()
                except Exception:
                    #for client in client_process_list:
                        #if client.exitcode != 0:
                        #    warnings.warn(f"The client process '{client.name}' exited with exitcode '{client.exitcode}'")
                    raise
                finally:
                    print("Finally...")
                    for client in client_process_list:
                        if client.is_alive():
                            # Race exists between is_alive() and here.
                            client.terminate()
                            client.join(30)
                            print("All process joined")
                            if client.exitcode is None:
                                warnings.warn(f"The client process '{client.name}' with PID '{client.pid}' failed to exit.")


if __name__ == "__main__":
    test()
