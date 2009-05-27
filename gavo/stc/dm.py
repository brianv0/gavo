"""
AST definition for STC.

For now, we want to be able to capture what STC-S can do.  This
means that we do not support generic coordinates (yet), ephemeris,
xlink and all the other stuff.
"""

from itertools import *
import re

from gavo.stc import sphermath
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

	def isSpherical(self):
		"""returns True if this is a frame deemed suitable for space
		frame transformations.

		This is really a property of stc.sphermath rather than of the
		data model, but it's more convenient to have this as a frame
		method.
		"""
		return (isinstance(self, SpaceFrame)
			and self.nDim>1
			and self.flavor=="SPHERICAL")


class TimeFrame(_CoordFrame):
	nDim = 1
	_a_timeScale = None


class SpaceFrame(_CoordFrame):
	_a_flavor = None
	_a_nDim = None
	_a_refFrame = "UNKNOWNRefFrame"
	_a_equinox = None  # if non-null, it has to match [BJ][0-9]+[.][0-9]+

	def _setupNode(self):
		if self.refFrame=="J2000":
			self.refFrame = "FK5"
			self.equinox = "J2000.0"
		elif self.refFrame=="B1950":
			self.refFrame = "FK4"
			self.equinox = "B1950.0"

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

	def asTriple(self):
		"""returns a triple defining the space frame for spherc's purposes.

		This is for the computation of coordinate transforms.  Since we only
		do coordinate transforms for spherical coordinate systems, this
		will, for now, raise STCValueErrors if everything but 2 or 3D SPHERICAL 
		flavours.
		"""
		if self.flavor!="SPHERICAL" or (self.nDim!=2 and self.nDim!=3):
			raise STCValueError("Can only conform 2/3-spherical coordinates")
		return (self.refFrame, self.getEquinox(), self.refPos.standardOrigin)


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

class SpectralType(_CooTypeSentinel):
	posAttr = "freq"

class TimeType(_CooTypeSentinel):
	posAttr = "time"

class SpaceType(_CooTypeSentinel):
	posAttr = "place"

class RedshiftType(_CooTypeSentinel):
	posAttr = "redshift"

class VelocityType(_CooTypeSentinel):
	posAttr = "velocity"


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

	inexactAttrs = set(["values"])

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

	inexactAttrs = set(["radii"])

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

	def getPosition(self, initArgs=None):
		"""returns a position appropriate for this class.

		This is a shallow copy of the xCoo object itself for xCoos, 
		xCoo for xInterval, and SpaceCoo for Geometries.  Common attributes
		are copied to the new object.
		"""
		posClass = _positionClassMap[self.cType]
		if initArgs is None:
			initArgs = {}
		for name, default in posClass._nodeAttrs:
			if name!="id" and name not in initArgs:
				initArgs[name] = getattr(self, name, default)
		return posClass(**initArgs)


class _Coordinate(_CoordinateLike):
	"""An abstract base for coordinates.

	They have an iterTransformed(convFunc) method iterating over constructor
	keys that have to be changed when some convFunc is applied to the
	coordinate.  These may be multiple values when, e.g., errors are given
	or for geometries.

	Since these only make sense together with units, some elementary
	unit handling is required.  Since we keep the basic unit model
	of STC, this is a bit over-complicated.
	
	First, for the benefit of STC-S, a method
	getUnitString() -> string or None is required.  It should return
	an STC-S-legal unit string.

	Second, a method getUnitArgs() -> dict or None is required.  It has to
	return a dictionary with all unit-related constructor arguments
	(that's unit and velTimeUnit for the standard
	coordinate types).  No None values are allowed; if self's units are
	not defined, return None.

	Third, a method 
	getUnitConverter(otherUnits) -> function or None is required.  It
	must return a function accepting the self's coordinates if self's
	units and otherUnits are defined, None otherwise.  OtherUnits can 
	be a tuple or a result of getUnitArgs.  The tuple is interpreted as 
	(baseUnit, timeUnit).
	"""
	_a_error = None
	_a_resolution = None
	_a_pixSize = None
	_a_value = None
	_a_size = None

	_dimensionedAttrs = ["error", "resolution", "pixSize", "size"]

	inexactAttrs = set(["value"])

	def _setupNode(self):
		for name in self._dimensionedAttrs:
			wiggle = getattr(self, name)
			if wiggle and wiggle.origUnit is not None:
				setattr(self, name, wiggle.adaptValuesWith(
					self.getUnitConverter(wiggle.origUnit)))
		self._setupNodeNext(_Coordinate)
	
	def iterTransformed(self, converter):
		if self.value is not None:
			yield "value", converter(self.value)
		for attName in self._dimensionedAttrs:
			wiggle = getattr(self, attName)
			if wiggle:
				yield attName, wiggle.adaptValuesWith(converter)

		
class _OneDMixin(object):
	"""provides attributes for 1D-Coordinates (Time, Spectral, Redshift)
	"""
	_a_unit = None

	def getUnitString(self):
		return self.unit

	def getUnitConverter(self, otherUnits):
		if self.unit is None or not otherUnits:
			return None
		if isinstance(otherUnits, dict):
			otherUnits = (otherUnits["unit"],)
		return units.getBasicConverter(self.unit, otherUnits[0], True)

	def getUnitArgs(self):
		if self.unit:
			return {"unit": self.unit}


class _SpatialMixin(object):
	"""provides attributes for positional coordinates.
	"""
	_a_unit = ()

	cType = SpaceType

	def getUnitString(self):
		if self.unit:
			if len(set(self.unit))==1:
				return self.unit[0]
			else:
				return " ".join(self.unit)

	def getUnitConverter(self, otherUnits):
		if self.unit is None or not otherUnits:
			return None
		if isinstance(otherUnits, dict):
			otherUnits = (otherUnits["unit"],)
		f = units.getVectorConverter(self.unit, otherUnits[0], True)
		return f

	def getUnitArgs(self):
		return {"unit": self.unit}


class _VelocityMixin(object):
	"""provides attributes for velocities.
	"""
	_a_unit = ()
	_a_velTimeUnit = ()

	cType = VelocityType

	def _setupNode(self):
		if self.unit:
			if not self.velTimeUnit or len(self.unit)!=len(self.velTimeUnit):
				raise STCValueError("Invalid units for Velocity: %s/%s."%(
					repr(self.unit), repr(self.velTimeUnit)))
		self._setupNodeNext(_VelocityMixin)

	def getUnitString(self):
		if self.unit:
			strs = ["%s/%s"%(u, tu) 
				for u, tu in itertools.izip(self.unit, self.velTimeUnit)]
			if len(set(strs))==1:
				return strs[0]
			else:
				return " ".join(strs)

	def getUnitConverter(self, otherUnits):
		if self.unit is None or not otherUnits:
			return None
		if isinstance(otherUnits, dict):
			otherUnits = (otherUnits["unit"], otherUnits["velTimeUnit"])
		return units.getVelocityConverter(self.unit, self.velTimeUnit,
			otherUnits[0], otherUnits[1], True)

	def getUnitArgs(self):
		return {"unit": self.unit, "velTimeUnit": self.velTimeUnit}


class _RedshiftMixin(object):
	"""provides attributes for redshifts.
	"""
	_a_velTimeUnit = None
	_a_unit = None

	cType = RedshiftType

	def _setupNode(self):
		if self.unit and not self.velTimeUnit:
			raise STCValueError("Invalid units for Redshift: %s/%s."%(
				repr(self.unit), repr(self.velTimeUnit)))
		self._setupNodeNext(_RedshiftMixin)

	def getUnitString(self):
		if self.unit:
			return "%s/%s"%(self.unit, self.velTimeUnit)

	def getUnitConverter(self, otherUnits):
		if self.unit is None or not otherUnits:
			return None
		if isinstance(otherUnits, dict):
			otherUnits = (otherUnits["unit"], otherUnits["velTimeUnit"])
		return units.getRedshiftConverter(self.unit, self.velTimeUnit, 
			otherUnits[0], otherUnits[1], True)

	def getUnitArgs(self):
		return {"unit": self.unit, "velTimeUnit": self.velTimeUnit}


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
	_a_origUnit = None
	
	inexactAttrs = set(["lowerLimit", "upperLimit"])

	def adaptValuesWith(self, converter):
		changes = {"origUnit": None}
		if self.lowerLimit is not None:
			changes["lowerLimit"] = converter(self.lowerLimit)
		if self.upperLimit is not None:
			changes["upperLimit"] = converter(self.upperLimit)
		return self.change(**changes)


class SpaceInterval(_CoordinateInterval):
	cType = SpaceType

	def getFullTransformed(self, trafo, posUnit, destFrame):
# XXX TODO: Think about if this really is the right way -- and make it
# work at all; this should somehow reuse what's done for positions...
		raise STCNotImplementedError("Cannot transform SpaceIntervals yet.")
		sTrafo = sphermath.makePlainSphericalTransformer(trafo, posUnit)
		ll, ul = self.lowerLimit, self.upperLimit
		if ll is None:
			return self.change(upperLimit=sTrafo(ul))
		if ul is None:
			return self.change(lowerLimit=sTrafo(ll))
		vertices = [sTrafo(coo) for coo in (
			(ll[0], ll[1]), (ul[0], ll[1]), (ll[0], ul[1]), (ul[0], ul[1]))]
		xVals = [coo[0] for coo in vertices]
		yVals = [coo[1] for coo in vertices]
		return self.change(upperLimit=(max(xVals), max(yVals)),
			lowerLimit=(min(xVals), min(yVals)), frame=destFrame)
		

class VelocityInterval(_CoordinateInterval):
	cType = VelocityType

class RedshiftInterval(_CoordinateInterval):
	cType = RedshiftType

class TimeInterval(_CoordinateInterval):
	cType = TimeType

	def adaptValuesWith(self, converter):
		# timeIntervals are unitless; units only refer to errors, etc,
		# which we don't have here.
		return self

class SpectralInterval(_CoordinateInterval):
	cType = SpectralType



################ Geometries

class _Geometry(_CoordinateLike, _SpatialMixin):
	"""A base class for all kinds of geometries.
	"""
	_a_size = None
	_a_fillFactor = None
	# The following helps since geometries are areas (like intervals)
	# However, no unit coercion takes place for them, so it's fixed None.
	origUnit = None


class _GeometryWithDeps(_Geometry):
	"""is a geometry that has "dependent quantities" like radii.

	All radii etc. have to be in the unit of the primary quantity (the center).

	In order to sensibly be able to do this, we enforce units to be 
	homogeneous for all geometries that have dependent quantities.
	"""
	def _setupNode(self):
		if self.unit:
			try:
				if self.unit[0]!=self.unit[1]:
					raise Exception
			except:
				raise STCValueError("Geometries must have the same units in both"
					" dimensions, so %s is invalid"%str(self.unit[0]))


class AllSky(_Geometry):
	pass

	def getTransformed(self, sTrafo, destFrame):
		return self.change(frame=destFrame)

	def adaptUnit(self, fromUnit, toUnit):
		return self


class Circle(_GeometryWithDeps):
	_a_center = None
	_a_radius = None

	def getTransformed(self, sTrafo, destFrame):
		return self.change(center=sTrafo(self.center), frame=destFrame)

	def adaptUnit(self, fromUnit, toUnit):
		vTrafo = units.getVectorConverter(fromUnit, toUnit)
		sTrafo = units.getBasicConverter(fromUnit[0], toUnit[0])
		return self.change(center=vTrafo(self.center), 
			radius=sTrafo(self.radius))


class Ellipse(_GeometryWithDeps):
	_a_center = None
	_a_smajAxis = _a_sminAxis = None
	_a_posAngle = None

	def getTransformed(self, sTrafo, destFrame):
# XXX TODO: actually rotate the ellipse.
		return self.change(center=sTrafo(self.center), frame=destFrame)

	def adaptUnit(self, fromUnit, toUnit):
		vTrafo = units.getVectorConverter(fromUnit, toUnit)
		sTrafo = units.getBasicConverter(fromUnit[0], toUnit[0])
		return self.change(center=vTrafo(self.center), 
			smajAxis=sTrafo(self.smajAxis), sminAxis=sTrafo(self.sminAxis))


class Box(_GeometryWithDeps):
	_a_center = None
	_a_boxsize = None
	
	def getTransformed(self, sTrafo, destFrame):
		"""returns a Polygon corresponding to this Box after rotation.
		"""
		center, boxsize = self.center, self.boxsize
		return Polygon(vertices=(sTrafo(coo) for coo in (
			(center[0]-boxsize[0], center[1]-boxsize[1]),
			(center[0]-boxsize[0], center[1]+boxsize[1]),
			(center[0]+boxsize[0], center[1]+boxsize[1]),
			(center[0]+boxsize[0], center[1]-boxsize[1]))), frame=destFrame)

	def adaptUnit(self, fromUnit, toUnit):
		vTrafo = units.getVectorConverter(fromUnit, toUnit)
		return self.change(center=vTrafo(self.center), 
			boxsize=vTrafo(self.boxsize))


class Polygon(_Geometry):
	_a_vertices = ()

	def getTransformed(self, sTrafo, destFrame):
		return self.change(vertices=(sTrafo(v) for v in self.vertices), 
			frame=destFrame)

	def adaptUnit(self, fromUnit, toUnit):
		vTrafo = units.getVectorConverter(fromUnit, toUnit)
		return self.change(vertices=(vTrafo(v) for v in self.vertices))


class Convex(_Geometry):
	_a_vectors = ()

	def getTransformed(self, sTrafo, destFrame):
		raise STCNotImplementedError("Cannot transform convexes yet.")

	def adaptUnit(self, fromUnit, toUnit):
		raise STCNotImplementedError("Cannot adapt units for convexes yet.")


################ Toplevel

class STCSpec(ASTNode):
	"""is an STC specification, i.e., the root of an STC tree.
	"""
	_a_astroSystem = None
	_a_systems = ()
	_a_time = None
	_a_place = None
	_a_freq = None
	_a_redshift = None
	_a_velocity = None
	_a_timeAs = ()
	_a_areas = ()
	_a_freqAs = ()
	_a_redshiftAs = ()
	_a_velocityAs = ()

	def buildIdMap(self):
		if hasattr(self, "idMap"):
			return
		self.idMap = {}
		for node in self.iterNodes():
			if node.id:
				self.idMap[node.id] = node

	def polish(self):
		"""does global fixups when parsing is finished.

		This method has to be called after the element is complete.  The
		standard parsers to this.

		For convenience, it returns the instance itself.
		"""
# Operations here cannot be in a _setupNode since when parsing from
# XML, there may be IdProxies instead of real objects.
		# Equinox for ecliptic defaults to observation time
		if self.place:
			frame = self.place.frame
			if frame and frame.equinox is None and frame.refFrame=="ECLIPTIC":
				if self.time and self.time.value:
					frame.equinox = "J%.8f"%(times.dateTimeToJYear(self.time.value))
		return self
