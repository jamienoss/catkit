import copy
import logging

import hicat.util
import numpy as np

import poppy.dms

import catkit.hardware.boston.DmCommand
from catkit.hardware.boston.BostonDmController import BostonDmController
from catkit.interfaces.Instrument import SimInstrument


class PoppyDM(poppy.dms.ContinuousDeformableMirror):
    def __init__(self, max_volts, meter_per_volt_map, bias_voltage=None, flat_map=None, **super_kwargs):
        self.max_volts = max_volts
        self.meter_per_volt_map = meter_per_volt_map
        self.flat_map = flat_map
        self.bias_voltage = bias_voltage
        super().__init__(**super_kwargs)


class PoppyBmcEmulator:
    """ This class (partially) emulates the Boston Micromachines Company's (BMC)
    SDK that communicates with their kilo 952 deformable mirror (DM) controller.
    It is not yet functionally complete."""

    NO_ERR = 0
    dac_bit_width = 14  # Should this belong to PoppyDM?

    def __init__(self, num_actuators, command_length, dm1, dm2=None):
        self.log = logging.getLogger(f"{self.__module__}.{self.__class__.__qualname__}")
        self._num_actuators = num_actuators
        self._command_length = command_length
        self.dm1 = dm1
        self.dm2 = dm2

        # As the class name suggests, the design only works with ``poppy.dms.ContinuousDeformableMirror``.
        assert isinstance(dm1, PoppyDM)
        assert isinstance(dm2, PoppyDM)

    def BmcDm(self):
        return self

    def open_dm(self, _serial_number):
        return self.NO_ERR

    def close_dm(self):
        return self.NO_ERR

    def send_data(self, full_dm_command):

        assert np.min(full_dm_command) >= 0 and np.max(full_dm_command) <= 1, \
            "DM command must be unitless (normalized Volts), i.e. 0.0-1.0."

        full_dm_command = copy.deepcopy(full_dm_command)

        if self.dac_bit_width:
            self.log.info(f"Simulating DM quantization with {self.dac_bit_width}b DAC")

            quantization_step_size = 1.0/(2**self.dac_bit_width - 1)
            full_dm_command.data = quantization_step_size * np.round(full_dm_command / quantization_step_size)

        def convert_command_to_poppy_surface(dm_command, dm):
            # Convert to volts
            dm_command *= dm.max_volts
            # Convert to 2D image
            dm_image = hicat.util.convert_dm_command_to_image(dm_command)

            # Remove flatmap
            if dm.flat_map is not None:
                dm_image -= dm.flat_map
                # The flatmap includes the voltage bias/offset so if one exists add it back
                if dm.bias_voltage:
                    dm_image += dm.bias_voltage

            # Convert to meters
            dm_surface = catkit.hardware.boston.DmCommand.convert_volts_to_m(dm_image, dm.meter_per_volt_map)
            return dm_surface

        if self.dm1:
            dm1_command = full_dm_command[:self._num_actuators]
            self.dm1.set_surface(convert_command_to_poppy_surface(dm1_command, self.dm1))
        if self.dm2:
            dm2_command = full_dm_command[self._command_length // 2:self._command_length // 2 + self._num_actuators]
            self.dm2.set_surface(convert_command_to_poppy_surface(dm2_command, self.dm2))

        return self.NO_ERR

    def num_actuators(self):
        # Oddly, the hardware actually returns the command length, not the number of actuators per dm etc.
        return self._command_length

    def error_string(self, _status):
        return "Woops!"


class PoppyBostonDMController(SimInstrument, BostonDmController):
    """ Emulated version of the real hardware `BostonDmController` class.
    This directly follows the hardware control except that the communication layer to the
    hardware uses our emulated version of Boston's DM SDK - `PoppyBmcEmulator`"""

    instrument_lib = PoppyBmcEmulator
