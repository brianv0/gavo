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


class _CoordFrame(ASTNode):
	"""is an astronomical coordinate frame.
	"""
	_a_name = None
	_a_refPos = None


class TimeFrame(_CoordFrame):
	nDim = 1
	_a_timeScale = None


class SpaceFrame(_CoordFrame):
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


class SpectralFrame(_CoordFrame):
	nDim = 1


class RedshiftFrame(_CoordFrame):
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


class _CooTypeSentinel(object):
	"""is a base for type indicators.

	Never instantiate any of these.
	"""

class SpectralType(_CooTypeSentinel): pass
class TimeType(_CooTypeSentinel): pass
class SpaceType(_CooTypeSentinel): pass
class RedshiftType(_CooTypeSentinel): pass
class VelocityType(_CooTypeSentinel): pass

############### Coordinates and their intervals


class _WiggleSpec(ASTNode):
	"""A base for "wiggle" specifications.

	These are Errors, Resolutions, Sizes, and PixSizes.  They may come
	as simple coordinates (i.e., scalars or vectors) or, in 2 and 3D,
	as radii or matrices (see below).  In all cases, two values may
	be given to indicate ranges.
	"""

class CooWiggle(_WiggleSpec):
	"""A wiggle given in coordinates.

	The values attributes stores them just like coordinates are stored.
	"""
	_a_values = ()

class RadiusWiggle(_WiggleSpec):
	"""An wiggle given as a radius.
	"""
	_a_radii = ()

class MatrixWiggle(_WiggleSpec):
	"""A matrix for specifying wiggle.

	The matrix/matrices are stored as sequences of sequences; see 
	stcxgen._wrapMatrix for details.
	"""
	_a_matrices = ()


class _CoordinateLike(ASTNode):
	"""An abstract base for everything that has a frame.

	They can return a position object of the proper type and with the
	same unit as self.

	When deriving from _CoordinateLike, you have at some point to define
	a cType class attribute that has values in the _CooTypeSentinels above.
	"""
	_a_frame = None
	_a_name = None


	def getPosition(self):
		"""returns a position appropriate for this class.

		This is a shallow copy of the xCoo object itself for xCoos, 
		xCoo for xInterval, and SpaceCoo for Geometries.  Common attributes
		are copied to the new object.
		"""
		posClass = _positionClassMap[self.cType]
		initArgs = {}
		for name, default in posClass._nodeAttrs:
			if name!="id":
				initArgs[name] = getattr(self, name, default)
		return posClass(**initArgs)


class _Coordinate(_CoordinateLike):
	_a_error = None
	_a_resolution = None
	_a_pixSize = None
	_a_value = None
	_a_size = None


class _OneDMixin(object):
	"""provides attributes for 1D-Coordinates (Time, Spectral, Redshift)
	"""
	_a_unit = None

	def getUnit(self):
		return self.unit


class _SpatialMixin(object):
	"""provides attributes for positional coordinates.
	"""
	_a_units = ()

	cType = SpaceType

	def getUnit(self):
		if self.units:
			if len(set(self.units))==1:
				return self.units[0]
			else:
				return " ".join(self.units)
		return ()


class _VelocityMixin(object):
	"""provides attributes for velocities.
	"""
	_a_units = ()
	_a_velTimeUnits = ()

	cType = VelocityType

	def getUnit(self):
		if self.units:
			if len(set(self.units))==1:
				return "%s/%s"%(self.units[0], self.velTimeUnits[0])
			else:
				return " ".join("%s/%s"%(u, tu) 
					for u, tu in itertools.izip(self.units, self.velTimeUnits))
		return ()


class _RedshiftMixin(object):
	"""provides attributes for redshifts.
	"""
	_a_velTimeUnit = None
	_a_unit = None

	cType = RedshiftType

	def getUnit(self):
		if self.unit:
			return "%s/%s"%(self.unit, self.velTimeUnit)


class SpaceCoo(_Coordinate, _SpatialMixin): pass
class VelocityCoo(_Coordinate, _VelocityMixin): pass
class RedshiftCoo(_Coordinate, _RedshiftMixin): pass

class TimeCoo(_Coordinate, _OneDMixin):
	cType = TimeType

class SpectralCoo(_Coordinate, _OneDMixin):
	cType = SpectralType


_positionClassMap = {
	SpectralType: SpectralCoo,
	TimeType: TimeCoo,
	SpaceType: SpaceCoo,
	RedshiftType: RedshiftCoo,
	VelocityType: VelocityCoo,
}


class _CoordinateInterval(_CoordinateLike):
	_a_lowerLimit = None
	_a_upperLimit = None
	_a_fillFactor = None


class SpaceInterval(_CoordinateInterval, _SpatialMixin): pass
class VelocityInterval(_CoordinateInterval, _VelocityMixin): pass
class RedshiftInterval(_CoordinateInterval, _RedshiftMixin): pass

class TimeInterval(_CoordinateInterval, _OneDMixin):
	cType = TimeType

class SpectralInterval(_CoordinateInterval, _OneDMixin):
	cType = SpectralType



################ Geometries

class _Geometry(_CoordinateLike, _SpatialMixin):
	"""A base class for all kinds of geometries.
	"""
	_a_size = None
	_a_fillFactor = None


class AllSky(_Geometry):
	pass


class Circle(_Geometry):
	_a_center = None
	_a_radius = None
	_a_radiusUnit = None


class Ellipse(_Geometry):
	_a_center = None
	_a_smajAxis = _a_sminAxis = None
	_a_smajAxisUnit = _a_sminAxisUnit = None
	_a_posAngle = None
	_a_posAngleUnit = None


class Box(_Geometry):
	_a_center = None
	_a_boxsize = None


class Polygon(_Geometry):
	_a_vertices = ()


class Convex(_Geometry):
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
	_a_velocities = ()
	_a_velocityAs = ()

	def buildIdMap(self):
		if hasattr(self, "idMap"):
			return
		self.idMap = {}
		for node in self.iterNodes():
			if node.id:
				self.idMap[node.id] = node
