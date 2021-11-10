import time

import pytest

from catkit.multiprocessing import DEFAULT_SHARED_MEMORY_SERVER_ADDRESS, EXCEPTION_SERVER_ADDRESS
from catkit.testbed.experiment import Experiment, SafetyException, SafetyTest, Testbed


def interruptible_sleep(seconds):
    counter = 0
    while counter < seconds:
        time.sleep(1)
        counter += 1


class ExperimentTest(Experiment):
    name = "Test Experiment"

    def __init__(self, *args, sleep=2, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_sleep = sleep

    def experiment(self, *args, **kwargs):
        interruptible_sleep(self.test_sleep)


class NonFailingSafetyTest(SafetyTest):
    def check(self):
        pass


@pytest.mark.dont_own_exception_handler
def test_monitor(tmpdir):
    with Testbed(safety_tests=[NonFailingSafetyTest], output_path=tmpdir):
        experiment = ExperimentTest(output_path=tmpdir)
        experiment.start()
        experiment.join()


class FailingSafetyTest(SafetyTest):
    def check(self):
        raise SafetyException("FAIL")


@pytest.mark.dont_own_exception_handler
def test_initial_safety_fail_during_setup(tmpdir):
    with pytest.raises(SafetyException, match="FAIL"):
        with Testbed(safety_tests=[FailingSafetyTest], output_path=tmpdir):
            pass


class DelayedFailingSafetyTest(SafetyTest):
    def __init__(self):
        super().__init__()
        self.call_counter = 0

    def check(self):
        self.call_counter += 1
        if self.call_counter > 1:
            raise SafetyException(f"FAILING (on {self.call_counter} fail)")


@pytest.mark.dont_own_exception_handler
def test_safety_fail_during_run(tmpdir):
    experiment = ExperimentTest(sleep=10, output_path=tmpdir)
    t0 = time.time()
    with pytest.raises(SafetyException, match="FAILING \\(on [0-9]+ fail\\)"):
        with Testbed(safety_tests=[DelayedFailingSafetyTest], output_path=tmpdir, safety_check_interval=3):
            experiment.start()
            experiment.join()

    assert time.time() - t0 < 10*1.1  # 10%


@pytest.mark.dont_own_exception_handler
def test_auto_ports(tmpdir):
    address = ("127.0.0.1", 0)

    with Testbed(safety_tests=[NonFailingSafetyTest], output_path=tmpdir, exception_server_address=address) as testbed:
        assert testbed.exception_manager.address[1] != 0
        # NOTE: It's possible for this assertion to coincidentally fail.
        assert testbed.exception_manager.address[1] not in (DEFAULT_SHARED_MEMORY_SERVER_ADDRESS[1], EXCEPTION_SERVER_ADDRESS[1])

        experiment = ExperimentTest(sleep=10, output_path=tmpdir, exception_server_address=testbed.exception_manager.address)
        assert experiment.exception_manager.address == testbed.exception_manager.address
        experiment.start()
        assert experiment.exception_manager.address == testbed.exception_manager.address
        experiment.join()
