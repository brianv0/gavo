"""
AST definition for STC.

For now, we want to be able to capture what STC-S can do.  This
means that we do not support generic coordinates (yet), ephemeris,
xlink and all the other stuff.
"""

import re

from gavo.stc import times
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
	_a_equinox = None  # if non-null, it has to match [BJ][0-9]+[.][0-9]+
	
	def getEquinox(self):
		"""returns a datetime.datetime instance for the frame's equinox.

		It will return None if no equinox is given, and it may raise an
		STCValueError if an invalid equinox string has been set.
		"""
		if self.equinox is None:
			return None
		mat = re.match("([B|J])([0-9.]+)", self.equinox)
		if not mat:
			raise STCValueError("Equinoxes must be [BJ]<float>, but %s isn't"%(
				self.equinox))
		if mat.group(1)=='B':
			return times.bYearToDateTime(float(mat.group(2)))
		else:
			return times.jYearToDateTime(float(mat.group(2)))


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


class WiggleSpec(ASTNode):
	"""A base for "wiggle" specifications.

	These are Errors, Resolutions, Sizes, and PixSizes.  They may come
	as simple coordinates (i.e., scalars or vectors) or, in 2 and 3D,
	as radii or matrices (see below).  In all cases, two values may
	be given to indicate ranges.
	"""

class CooWiggle(WiggleSpec):
	"""A wiggle given in coordinates.

	The values attributes stores them just like coordinates are stored.
	"""
	_a_values = ()

class RadiusWiggle(WiggleSpec):
	"""An wiggle given as a radius.
	"""
	_a_radii = ()

class MatrixWiggle(WiggleSpec):
	"""A matrix for specifying wiggle.

	The matrix/matrices are stored as sequences of sequences; see 
	stcxgen._wrapMatrix for details.
	"""
	_a_matrices = ()


class CoordinateLike(ASTNode):
	"""A base for everything that has a frame.
	"""
	_a_frame = None
	_a_name = None
	_a_unit = None
	_a_velTimeUnit = None


class Coordinate(CoordinateLike):
	_a_error = None
	_a_resolution = None
	_a_pixSize = None
	_a_value = None
	_a_size = None


class SpaceCoo(Coordinate): pass
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
	_a_fillFactor = None


class AllSky(Geometry):
	pass


class Circle(Geometry):
	_a_center = None
	_a_radius = None
	_a_radiusUnit = None


class Ellipse(Geometry):
	_a_center = None
	_a_smajAxis = _a_sminAxis = None
	_a_smajAxisUnit = _a_sminAxisUnit = None
	_a_posAngle = None
	_a_posAngleUnit = None


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
	_a_astroSystem = None
	_a_systems = ()
	_a_times = ()
	_a_places = ()
	_a_freqs = ()
	_a_redshifts = ()
	_a_timeAs = ()
	_a_areas = ()
	_a_freqAs = ()
	_a_redshiftAs = ()

	def buildIdMap(self):
		if hasattr(self, "idMap"):
			return
		self.idMap = {}
		for node in self.iterNodes():
			if node.id:
				self.idMap[node.id] = node
