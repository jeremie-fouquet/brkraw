from __future__ import annotations
from brkraw.api import helper
from .base import BaseAnalyzer
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..pvobj import PvScan


class ScanInfoAnalyzer(BaseAnalyzer):
    """Helps parse metadata from multiple parameter files to make it more human-readable.

    Args:
        pvscan (PvScan): The PvScan object containing acquisition and method parameters.
        reco_id (int, optional): The reconstruction ID. Defaults to None.

    Raises:
        NotImplementedError: If an operation is not implemented.
    """
    def __init__(self, pvscan: 'PvScan', reco_id:int|None = None):
        self._set_pars(pvscan, reco_id)
        self.info_protocol = helper.Protocol(self).get_info()
        if self.visu_pars:
            self.info_dataarray = helper.DataArray(self).get_info()
            self.info_frame_group = helper.FrameGroup(self).get_info()
            self.info_image = helper.Image(self).get_info()
            self.info_slicepack = helper.SlicePack(self).get_info()
            self.info_cycle = helper.Cycle(self).get_info()
            if self.info_image['dim'] > 1:
                self.info_orientation = helper.Orientation(self).get_info()
    
    def _set_pars(self, pvscan: 'PvScan', reco_id: int|None):
        for p in ['acqp', 'method']:
            vals = getattr(pvscan, p)
            setattr(self, p, vals)
        try:
            visu_pars = pvscan.get_visu_pars(reco_id)
        except FileNotFoundError:
            visu_pars = None
        setattr(self, 'visu_pars', visu_pars)
    
    def __dir__(self):
        return [attr for attr in self.__dict__.keys() if 'info_' in attr]
    
    def get(self, key):
        return getattr(self, key) if key in self.__dir__() else None