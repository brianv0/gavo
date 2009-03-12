"""
AST definition for STC.

For now, we want to be able to capture what STC-S can do.  This
means that we do not support generic coordinates (yet), ephemeris,
xlink and all the other stuff.
"""

from gavo.stc.common import *


################ Coordinate Systems


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
	_a_type = None


class CoordSys(ASTNode):
	"""is an astronomical coordinate system.
	"""
	_a_timeFrame = None
	_a_spaceFrame = None
	_a_spectralFrame = None
	_a_redshiftFrame = None
	_a_name = None



############### Coordinates and their intervals


class CoordinateLike(ASTNode):
	"""A base for everything that has frames, errors, and the like.
	"""
	_a_frame = None
	_a_name = None
	_a_error = ()
	_a_resolution = ()
	_a_pixSize = ()
	_a_unit = None
	_a_velTimeUnit = None


class Coordinate(CoordinateLike):
	_a_value = None


class SpaceCoo(Coordinate):
	_a_size = ()

class TimeCoo(Coordinate): pass
class SpectralCoo(Coordinate): pass 
class RedshiftCoo(Coordinate): pass


class CoordinateInterval(CoordinateLike):
	_a_lowerLimit = None
	_a_upperLimit = None
	_a_fillFactor = None
	_a_size = ()


class TimeInterval(CoordinateInterval): pass
class SpaceInterval(CoordinateInterval): pass 
class SpectralInterval(CoordinateInterval): pass
class RedshiftInterval(CoordinateInterval): pass


################ Geometries


class Geometry(CoordinateLike):
	"""A base class for all kinds of geometries.
	"""
	_a_size = ()

class AllSky(Geometry):
	pass


class Circle(Geometry):
	_a_center = None
	_a_radius = None


class Ellipse(Geometry):
	_a_center = None
	_a_majAxis = _a_minAxis = None
	_a_posAngle = None


class Box(Geometry):
	_a_center = None
	_a_boxsize = None


class Polygon(Geometry):
	_a_vertices = ()


class Convex(Geometry):
	_a_vectors = ()


################ Toplevel

class STCSpec(ASTNode):
	"""is an STC specification, i.e., the root of an STC tree.
	"""
	_a_systems = ()
	_a_times = ()
	_a_places = ()
	_a_freqs = ()
	_a_redshifts = ()
	_a_timeAs = ()
	_a_areas = ()
	_a_freqAs = ()
	_a_redshiftAs = ()
