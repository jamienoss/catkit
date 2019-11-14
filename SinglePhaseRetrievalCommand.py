import numpy as np
import logging
import os
import csv
from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston.DmCommand import DmCommand
from hicat.experiments.modules.phase_retrieval import take_phase_retrieval_data
from hicat.config import CONFIG_INI
import hicat.util
from catkit.catkit_types import units, quantity
from hicat import wavefront_correction
from catkit.hardware.boston.commands import flat_command
import catkit.util


class SinglePhaseRetrievalCommand(Experiment):
    name = "Single Phase Retrieval Command"
    log = logging.getLogger(__name__)

    def __init__(self,
                 input_image_path=None,
                 dm_num=1,
                 rotate=90,
                 fliplr=True,
                 damping_ratio=.6,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 step=10,
                 output_path=None,
                 camera_type="phase_retrieval_camera",
                 position_list=None,
                 suffix="single_phase_retrieval",
                 **kwargs):

        super(self, Experiment).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.input_image_path = input_image_path
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.damping_ratio = damping_ratio
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.step = step
        self.camera_type = camera_type
        self.position_list = position_list
        self.kwargs = kwargs

    def experiment(self):

        # Read in the actuator map into a dictionary.
        map_file_name = "actuator_map_dm1.csv" if self.dm_num == 1 else "actuator_map_dm2.csv"
        map_path = os.path.join(hicat.util.find_package_location(), "hardware", "FourDTechnology", map_file_name)
        actuator_index = {}
        with open(map_path) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                actuator_index[int(row['actuator'])] = (int(row['x_coord']), int(row['y_coord']))

        actuator_intensities = {}

        # Load phase retriveal input image, and find intensities.
        image = fits.getdata(self.input_image_path)

        # Apply rotates and flips.
        image = catkit.util.rotate_and_flip_image(image, self.rotate, self.fliplr)

        # Apply a -1 to the pr data.
        # image *= -1

        print("Finding intensities...")
        for key, value in actuator_index.items():
            # Create a small circle mask around index, and take the median.
            actuator_mask = wavefront_correction.circle_mask(image, value[0], value[1], 3)

            # Find the median within the mask. Throw away values of zero, because they probably outside of the image.
            actuator_intensity = np.median(image[actuator_mask])

            # Add to intensity dictionary.
            actuator_intensities[key] = actuator_intensity

        # Generate the correction values.
        print("Generating corrections...")
        corrected_values = []
        for key, value in actuator_intensities.items():
            correction = quantity(value, units.nanometer).to_base_units().m

            # Apply the factor of 2 for the DM reflection.
            opd_scaling_dm = 1
            correction *= opd_scaling_dm

            # Apply damping ratio.
            correction *= self.damping_ratio
            corrected_values.append(correction)

        # Update the DmCommand.
        pr_command = DmCommand(catkit.util.convert_dm_command_to_image(corrected_values), 1, flat_map=True)

        print("Starting phase retrieval data set...")
        take_phase_retrieval_data(self.exposure_time,
                                  self.num_exposures,
                                  self.step,
                                  self.output_path,
                                  self.camera_type,
                                  position_list=self.position_list,
                                  dm1_command=pr_command,
                                  dm2_command=flat_command(False, True, dm_num=2),
                                  suffix=self.suffix,
                                  **self.kwargs)
