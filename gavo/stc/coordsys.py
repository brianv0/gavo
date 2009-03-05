"""
AST Coordinate systems definition by the STC data model.

For now, we want to be able to capture what STC-S can do here.  This
means that we do not support generic coordinates (yet).
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
	_a_timeScale = None


class SpaceFrame(CoordFrame):
	_a_flavor = None
	_a_nDim = None
	_a_refFrame = "UNKNOWNRefFrame"
	_a_equinox = None


class SpectralFrame(CoordFrame):
	pass


class RedshiftFrame(CoordFrame):
	_a_dopplerDef = None


class CoordSys(ASTNode):
	"""is an astronomical coordinate system.
	"""
	_a_timeFrame = None
	_a_spaceFrame = None
	_a_spectralFrame = None
	_a_redshiftFrame = None
	_a_name = None


class STCSpec(ASTNode):
	"""is an STC specification.
	"""
	_a_systems = None
	_a_coords = None
	_a_areas = None
