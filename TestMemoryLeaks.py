import logging
import os
from astropy.io import fits

from hicat.data_pipeline import standard_file_pipeline
from hicat.experiments.Experiment import Experiment
from hicat.hardware import testbed_state
from hicat.hicat_types import ImageCentering
import hicat.util
from hicat.config import CONFIG_INI

from glob import glob


class TestMemoryLeaks(Experiment):
    name = "Test Memory Leak"
    log = logging.getLogger(__name__)

    def __init__(self, speckle_nulling_path, output_path=None, **kwargs):
        super(TestMemoryLeaks, self).__init__(output_path=output_path, **kwargs)

        self.speckle_nulling_path = speckle_nulling_path
        self.path = output_path

    def experiment(self):

        # Make a list of each iteration available in speckle nulling data.
        iteration_folders = glob(os.path.join(self.speckle_nulling_path, "iteration*"))

        # Store the reference image for global alignment.
        reference_path = glob(os.path.join(self.speckle_nulling_path, "reference", "coron", "*.fits"))[0]
        testbed_state.reference_image = fits.getdata(reference_path)
        testbed_state.global_alignment_mask = self.__make_global_alignment_mask()

        # Iterate through and run pipeline on raw images.
        for iteration_folder in iteration_folders:

            iteration_string = os.path.basename(os.path.normpath(iteration_folder))
            output_iteration_folder_path = os.path.join(self.path,
                                                        iteration_string)

            # Run standard file pipeline using global cross correlation.
            standard_file_pipeline(os.path.join(iteration_folder, "coron"),
                                   centering=ImageCentering.global_cross_correlation,
                                   output_path=output_iteration_folder_path)

            # Collect phase folders.
            phase_folders = glob(os.path.join(iteration_folder, "phase*"))

            for phase_folder in phase_folders:
                phase_string = os.path.basename(os.path.normpath(phase_folder))
                output_phase_folder_path = os.path.join(output_iteration_folder_path,
                                                        phase_string)

                # Run standard file pipeline using global cross correlation.
                standard_file_pipeline(os.path.join(phase_folder, "coron"),
                                       centering=ImageCentering.global_cross_correlation,
                                       output_path=os.path.join(output_phase_folder_path))

            # Collect amplitude folders.
            amplitude_folders = glob(os.path.join(iteration_folder, "amplitude*"))

            for amplitude_folder in amplitude_folders:
                amplitude_string = os.path.basename(os.path.normpath(amplitude_folder))
                output_amplitude_folder_path = os.path.join(output_iteration_folder_path,
                                                        amplitude_string)

                # Run standard file pipeline using global cross correlation.
                standard_file_pipeline(os.path.join(amplitude_folder, "coron"),
                                       centering=ImageCentering.global_cross_correlation,
                                       output_path=os.path.join(output_amplitude_folder_path))


    @staticmethod
    def __make_global_alignment_mask():
        radius = CONFIG_INI.getint("speckle_nulling", "global_alignment_mask_radius")
        camera = CONFIG_INI.get("testbed", "imaging_camera")
        width = CONFIG_INI.getint(camera, "width")
        height = CONFIG_INI.getint(camera, "height")
        center_x = int(round(width / 2))
        center_y = int(round(height / 2))

        # Make a mask as big as the CNT apodizer's natural dark zone.
        return hicat.util.circular_mask((center_x, center_y), radius, (width, height))
