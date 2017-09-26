from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from abc import ABCMeta, abstractmethod

"""Abstract base class for all cameras. Implementations of this class also become context managers."""


class Camera(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        """Opens connection with camera sets class attributes for 'config_id' and 'camera'."""
        self.config_id = config_id
        self.camera = self.initialize(self, *args, **kwargs)
        print("Opened connection to camera: " + self.config_id)

    # Implementing context manager.
    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.close()
        self.camera = None
        print("Safely closed camera: " + self.config_id)

    # Abstract Methods.
    @abstractmethod
    def initialize(self, *args, **kwargs):
        """Opens connection with camera and returns the camera manufacturer specific object."""

    @abstractmethod
    def close(self):
        """Close camera connection."""

    @abstractmethod
    def take_exposures(self, exposure_length, num_exposures, path=None, filename=None, *args, **kwargs):
        """Takes exposures and should be able to save fits and simply return the image data."""
