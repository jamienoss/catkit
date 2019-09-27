from glob import glob
import logging

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston import commands, DmCommand
from hicat.hicat_types import units, quantity, ImageCentering
from hicat import util
from hicat.experiments.modules.general import take_exposures_both_dm_commands


class TestPrDmCommands(Experiment):
    name = "PR Test DM Command Data Collection"
    log = logging.getLogger(__name__)

    def __init__(self, commands_path,
                 num_exposures=10,
                 coron_exp_time=quantity(100, units.millisecond),
                 direct_exp_time=quantity(250, units.microsecond),
                 centering=ImageCentering.custom_apodizer_spots,
                 output_path=None, suffix="test_pr_dm_data"):

        super().__init__(output_path=output_path, suffix=suffix)

        self.commands_path = commands_path
        self.num_exposures = num_exposures
        self.coron_exp_time = coron_exp_time
        self.direct_exp_time = direct_exp_time
        self.centering = centering

    def experiment(self):
        dm2_command = commands.flat_command(bias=False, flat_map=True, dm_num=2,
                                            return_shortname=False)
        # DM2 Flat, DM1 PR WF correction command.
        for command in self.commands_path:
            take_exposures_both_dm_commands([dm2_command],
                                            self.commands_path,
                                            self.output_path,
                                            "pr_flats",
                                            self.coron_exp_time,
                                            self.direct_exp_time,
                                            dm2_flat_map=False,
                                            dm1_flat_map=True,
                                            dm2_list_of_paths=False,
                                            dm1_list_of_paths=True,
                                            num_exposures=self.num_exposures,
                                            camera_type="imaging_camera",
                                            centering=self.centering)

        # # DM1 Flat, DM2 Flat.
        # take_exposures_dm_commands([dm2_command],
        #                            self.path, "pr_flats", self.coron_exp_time,
        #                            self.direct_exp_time, list_of_paths=False,
        #                            num_exposures=self.num_exposures,
        #                            centering=self.centering)
