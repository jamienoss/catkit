from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import psutil
from abc import ABCMeta, abstractmethod
from ..hardware import testbed
from .. config import CONFIG_INI
from ..hardware.thorlabs import ThorlabsTSP01


class SafetyTest(object):
    __metaclass__ = ABCMeta

    name = None
    warning = False

    @abstractmethod
    def check(self):
        """Implement to return two values: boolean for pass/fail, and a string for status message."""


class UpsSafetyTest(SafetyTest):

    name = "White UPS Safety Test"

    # Create a SnmpUPS object to monitor the White UPS.
    ups = testbed.backup_power()

    def check(self):
        return self.ups.is_power_ok(return_status_msg=True)


class HumidityTemperatureTest(SafetyTest):

    name = "Thorlabs Humidity and Temperature Sensor Safety Test"

    min_humidity = CONFIG_INI.getint("safety", "min_humidity")
    max_humidity = CONFIG_INI.getint("safety", "max_humidity")
    min_temp = CONFIG_INI.getint("safety", "min_temp")
    max_temp = CONFIG_INI.getint("safety", "max_temp")

    def check(self):
        if "TSP01GUI.exe" in (p.name() for p in psutil.process_iter()):
            status_msg = "Humidity and Temperature test failed: Close the Thorlabs GUI and run again. " \
                         "It interferes with our code."
            return False, status_msg

        temp, humidity = ThorlabsTSP01.get_temp_humidity("thorlabs_tsp01_1")
        temp_ok = self.min_temp <= temp <= self.max_temp

        if temp_ok:
            status_msg = "Temperature test passed: {} falls between {} and {}.".format(
                temp, self.min_temp, self.max_temp)
        else:
            status_msg = "Temperature test failed: {} is outside of {} and {}.".format(
                temp, self.min_temp, self.max_temp)

        humidity_ok = self.min_humidity <= humidity <= self.max_humidity

        if humidity_ok:
            status_msg += "\nHumidity test passed: {} falls between {} and {}.".format(
                humidity, self.min_humidity, self.max_humidity)
        else:
            status_msg += "\nHumidity test failed: {} is outside of {} and {}.".format(
                humidity, self.min_humidity, self.max_humidity)

        return temp_ok and humidity_ok, status_msg


class SafetyException(Exception):
    def __init__(self, *args):
        Exception.__init__(self, *args)
