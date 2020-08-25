import logging

from catkit.catkit_types import units, quantity, FpmPosition
from catkit.hardware.boston.commands import flat_command
from hicat.config import CONFIG_INI
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules.mtf_sampling import mtf_sampling
from hicat.hardware import testbed
import hicat.calibration_util


class CalculateSampling(Experiment):
    name = "Mtf Sampling Calculation"
    log = logging.getLogger(__name__)

    def __init__(self,
                 bias=False,
                 flat_map=True,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=100,
                 output_path=None,
                 camera_type="imaging_camera",
                 suffix="mtf_calibration",
                 mtf_snr_threshold=None,
                 **kwargs):
        super().__init__(output_path=output_path, suffix=suffix)

        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.camera_type = camera_type

        if mtf_snr_threshold is None:
            mtf_snr_threshold = CONFIG_INI.getint("calibration", "sampling_mtf_snr_thrshold")
        self.mtf_snr_threshold = mtf_snr_threshold
        self.kwargs = kwargs

    def experiment(self):

        # Create a flat dm command.
        flat_command_object1, flat_file_name = flat_command(flat_map=self.flat_map,
                                                           bias=self.bias,
                                                           return_shortname=True,
                                                           dm_num=1)

        flat_command_object2, flat_file_name = flat_command(flat_map=self.flat_map,
                                                           bias=self.bias,
                                                           return_shortname=True,
                                                           dm_num=2)
        direct_exp_time_estimate = self.exposure_time
        num_exposures = self.num_exposures

        with testbed.laser_source() as laser:
            direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
            laser.set_current(direct_laser_current)

            with testbed.dm_controller() as dm:
                # Flat.
                dm.apply_shape_to_both(flat_command_object1, flat_command_object2)
                cal_image, header = testbed.run_hicat_imaging(direct_exp_time_estimate, num_exposures, FpmPosition.direct,
                                                      path=self.output_path, exposure_set_name="direct",
                                                      filename=flat_file_name, camera_type=self.camera_type,
                                                      pipeline=True,
                                                      **self.kwargs)

        bin_file_path = header["PATH"]
        self.log.info("Binned file: "+bin_file_path)
        cal_file_path = bin_file_path.replace('_bin.fits', '_cal.fits')
        self.log.info("Using calibrated file: "+cal_file_path)

        pixel_sampling = mtf_sampling(self.output_path, cal_file_path, self.mtf_snr_threshold)
        self.log.info("pixel sampling in focused image = {}".format(pixel_sampling))

        hicat.calibration_util.record_calibration_measurement(f"Pixel Sampling from MTF",
                                                              pixel_sampling, "pixels",
                                                              comment=f"MTF SNR threshold={self.mtf_snr_threshold}" )
