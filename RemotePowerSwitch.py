from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from abc import ABCMeta, abstractmethod

"""Interface for remote controlled power switch."""


class RemotePowerSwitch(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        self.config_id = config_id

    # Abstract Methods.
    @abstractmethod
    def turn_on(self, outlet_id):
        """
        Turn on an individual outlet.
        """

    @abstractmethod
    def turn_off(self, outlet_id):
        """
        Turn off an individual outlet.
        """

    @abstractmethod
    def all_on(self):
        """
        Turn on all outlets.
        """

    @abstractmethod
    def all_off(self):
        """
        Turn off all outlets.
        """
