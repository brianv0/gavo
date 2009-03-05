"""
AST definition for STC.

For now, we want to be able to capture what STC-S can do.  This
means that we do not support generic coordinates (yet), ephemeris,
xlink and all the other stuff.
"""

from gavo.stc.common import *


class RefPos(ASTNode):
	"""is a reference position.

	Right now, this is just a wrapper for a RefPos id, as defined by STC-S.
	"""
	_a_standardOrigin = "UNKNOWNRefPos"


class CoordFrame(ASTNode):
	"""is an astronomical coordinate frame.
	"""
	_a_name = None
	_a_refPos = None


class TimeFrame(CoordFrame):
	nDim = 1
	_a_timeScale = None


class SpaceFrame(CoordFrame):
	_a_flavor = None
	_a_nDim = None
	_a_refFrame = "UNKNOWNRefFrame"
	_a_equinox = None


class SpectralFrame(CoordFrame):
	nDim = 1


class RedshiftFrame(CoordFrame):
	nDim = 1
	_a_dopplerDef = None


class CoordSys(ASTNode):
	"""is an astronomical coordinate system.
	"""
	_a_timeFrame = None
	_a_spaceFrame = None
	_a_spectralFrame = None
	_a_redshiftFrame = None
	_a_name = None


class Coordinate(ASTNode):
	_a_frame = None
	_a_name = None
	_a_value = None
	_a_error = ()
	_a_resolution = ()
	_a_size = ()
	_a_pixSize = ()
	_a_units = None

	def _setupNode(self):
		if self.units and self.frame.nDim:  # expand units to match nDim
			if len(self.units)==1:
				self.units = self.units*self.frame.nDim
			if len(self.units)!=self.frame.nDim:
				raise STCValueError("Wrong dimensionality of units %s, expected"
					" %d unit(s)"%(self.units, self.frame.nDim))

# Maybe we want to derive those later
TimeCoo = SpaceCoo = SpectralCoo = RedshiftCoo = Coordinate


class STCSpec(ASTNode):
	"""is an STC specification, i.e., the root of an STC tree.
	"""
	_a_systems = ()
	_a_times = ()
	_a_places = ()
	_a_freqs = ()
	_a_redshifts = ()
	_a_areas = ()


