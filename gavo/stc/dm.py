"""
AST definition for STC.

For now, we want to be able to capture what STC-S can do.  This
means that we do not support generic coordinates (yet), ephemeris,
xlink and all the other stuff.
"""

from itertools import *
import re

from gavo.stc import times
from gavo.stc import units
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

	These need an adaptValuesWith(converter) method that will return a wiggle of
	the same type but with every value replaced with the result of the
	application of converter to that value.
	"""

class CooWiggle(_WiggleSpec):
	"""A wiggle given in coordinates.

	The values attributes stores them just like coordinates are stored.
	"""
	_a_values = ()
	_a_origUnit = None

	def adaptValuesWith(self, unitConverter):
		if unitConverter is None:
			return self
		return self.change(values=tuple(unitConverter(v) for v in self.values))

class RadiusWiggle(_WiggleSpec):
	"""An wiggle given as a radius.

	If unit adaption is necessary and the base value is a vector, the radii
	are assumed to be of the dimension of the first vector component.
	"""
	_a_radii = ()
	_a_origUnit = None

	def adaptValuesWith(self, unitConverter):
		if unitConverter is None:
			return self
		return self.change(radii=tuple(unitConverter(repeat(r))[0] 
			for r in self.radii))


class MatrixWiggle(_WiggleSpec):
	"""A matrix for specifying wiggle.

	The matrix/matrices are stored as sequences of sequences; see 
	stcxgen._wrapMatrix for details.
	"""
	_a_matrices = ()
	_a_origUnit = None

	def adaptValuesWith(self, unitConverter):
		raise STCValueError("Matrix wiggles cannot be transformed.")


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

	_dimensionedAttrs = ["error", "resolution", "pixSize", "size"]
	def _setupNode(self):
		for name in self._dimensionedAttrs:
			wiggle = getattr(self, name)
			if wiggle and wiggle.origUnit is not None:
				setattr(self, name, wiggle.adaptValuesWith(
					self.getUnitConverter(wiggle.origUnit)))
		self._setupNodeNext(_Coordinate)


class _OneDMixin(object):
	"""provides attributes for 1D-Coordinates (Time, Spectral, Redshift)
	"""
	_a_unit = None

	def getUnit(self):
		return self.unit

	def getUnitConverter(self, otherUnit):
		"""returns a function converting from otherUnits to self.units.
		"""
		if self.unit is None:
			return None
		return units.getBasicConverter(self.unit, otherUnit[0], True)


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

	def getUnitConverter(self, otherUnits):
		if self.units is None:
			return None
		f = units.getVectorConverter(self.units, otherUnits[0], True)
		return f


class _VelocityMixin(object):
	"""provides attributes for velocities.
	"""
	_a_units = ()
	_a_velTimeUnits = ()

	cType = VelocityType

	def getUnit(self):
		if self.units:
			try:
				if len(set(self.units))==1:
					return "%s/%s"%(self.units[0], self.velTimeUnits[0])
				else:
					return " ".join("%s/%s"%(u, tu) 
						for u, tu in itertools.izip(self.units, self.velTimeUnits))
				return ()
			except IndexError:
				raise STCValueError("Invalid units for Velocity: %s/%s."%(
					repr(self.units), repr(self.velTimeUnits)))

	def getUnitConverter(self, otherUnits):
		if self.units is None:
			return None
		return units.getVelocityConverter(self.units, self.velTimeUnits,
			otherUnits[0], otherUnits[1], True)


class _RedshiftMixin(object):
	"""provides attributes for redshifts.
	"""
	_a_velTimeUnit = None
	_a_unit = None

	cType = RedshiftType

	def getUnit(self):
		if self.unit:
			return "%s/%s"%(self.unit, self.velTimeUnit)

	def getUnitConverter(self, otherUnits):
		if self.unit is None:
			return None
		return units.getRedshiftConverter(self.unit, self.velTimeUnit, 
			otherUnits[0], otherUnits[1], True)


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


class _GeometryWithDeps(_Geometry):
	"""is a geometry that has "dependent quantities" like radii.

	All radii etc. have to be in the unit of the primary quantity (the center).

	In order to sensibly be able to do this, we enforce units to be 
	homogeneous for all geometries that have dependent quantities.
	"""
	def _setupNode(self):
		if self.units:
			try:
				if self.units[0]!=self.units[1]:
					raise Exception
			except:
				raise STCValueError("Geometries must have the same units in both"
					" dimensions, so %s is invalid"%str(self.units[0]))


class AllSky(_Geometry):
	pass


class Circle(_GeometryWithDeps):
	_a_center = None
	_a_radius = None


class Ellipse(_GeometryWithDeps):
	_a_center = None
	_a_smajAxis = _a_sminAxis = None
	_a_smajAxisUnit = _a_sminAxisUnit = None
	_a_posAngle = None


class Box(_GeometryWithDeps):
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
