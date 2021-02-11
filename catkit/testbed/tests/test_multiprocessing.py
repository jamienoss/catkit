import multiprocessing
import time
import warnings

from catkit.emulators.npoint_tiptilt import SimNPointLC400
from catkit.hardware.npoint.nPointTipTiltController import Parameters
from catkit.testbed import devices, DeviceCacheEnum, Experiment
from catkit.testbed.multiprocessing import DeviceCommsManager, CommsGroup


class Device(DeviceCacheEnum):
    NPOINT_C = ("npoint a for test", "dummy_config_id", CommsGroup.CLIENT)
    NPOINT_D = ("npoint a for test", "dummy_config_id", CommsGroup.CLIENT)


@devices.link(key=Device.NPOINT_C)
def npoint_c():
    return SimNPointLC400(config_id="npoint_tiptilt_lc_400", com_id="dummy")


def run_from_client(comms=None):
    print("Client running...")
    time.sleep(2)  # Give time for parent start listening.
    Device.set_cache(comms)
    assert Device.NPOINT_C.instrument
    for channel in Device.NPOINT_C.channels:
        print(Device.NPOINT_C.get_status(channel))

    Device.NPOINT_C.set(Parameters.P_GAIN, 1, 3.14)
    assert Device.NPOINT_C.get(Parameters.P_GAIN, 1) == 3.14

    for channel in Device.NPOINT_C.channels:
        print(Device.NPOINT_C.get_status(channel))


def test():
    with DeviceCommsManager(timeout=30) as manager:
        with devices:
            manager.comms[CommsGroup.SERVER].set_cache(devices)

            # Create client processes.
            client_process_list = []
            ctx = multiprocessing.get_context("spawn")
            client_process_list.append(ctx.Process(target=run_from_client, name="test_client", args=(manager.comms,)))

            try:
                # Start client. This sleeps to give listener time to begin.
                for client in client_process_list:
                    client.start()
                    print(f"Client '{client.name}' started with PID '{client.pid}'")

                # Start listening. This parent process is the device server.
                manager.comms[CommsGroup.SERVER].listen(client_process_list)
            except Exception:
                #for client in client_process_list:
                    #if client.exitcode != 0:
                    #    warnings.warn(f"The client process '{client.name}' exited with exitcode '{client.exitcode}'")
                raise
            finally:
                for client in client_process_list:
                    if client.is_alive():
                        # Race exists between is_alive() and here.
                        client.terminate()
                        client.join(30)
                        if client.exitcode is None:
                            warnings.warn(f"The client process '{client.name}' with PID '{client.pid}' failed to exit.")


if __name__ == "__main__":
    test()
