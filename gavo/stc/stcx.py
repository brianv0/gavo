"""
Building STC-X documents, xmlstan-style.
"""

from gavo.stc.common import *
from gavo.utils import ElementTree
from gavo.utils.stanxml import Element, XSINamespace, Error


_schemaLocations = {
	STCNamespace: "http://vo.ari.uni-heidelberg.de/docs/schemata/stc-v1.30.xsd",
	XlinkNamespace: "http://vo.ari.uni-heidelberg.de/docs/schemata/xlink.xsd",
}


class NamespaceWithSubsGroup(type):
	"""is a metaclass for xmlstan namespaces that contain substitution
	groups.

	You get a _addSubsGroup class method on these.
	"""
	def _addSubsGroup(cls, baseClass, validNames):
		"""adds baseClass under all of validNames into namespace.
		"""
		for n in validNames:
			class dynamicallyDefined(baseClass):
				name = n
			setattr(cls, n, dynamicallyDefined)


class STC(object):
	"""is a container for classes modelling STC elements.
	"""
	__metaclass__ = NamespaceWithSubsGroup

	class STCElement(Element):
		mayBeEmpty = True
		namespace = STCNamespace
		local = True
		# We may not want all of these an all elements, but it's not
		# worth the effort discriminating here.
		a_href = None
		href_name = "xlink:href"
		a_type = None
		type_name = "xlink:type"
		a_ucd = None
		a_ID_type = None
		a_IDREF_type = None

	class _Toplevel(STCElement):
		a_xmlns = STCNamespace
		a_xmlns_xlink = XlinkNamespace
		xmlns_xlink_name = "xmlns:xlink"
		a_xsi_schemaLocation = " ".join(["%s %s"%(ns, xs)
			for ns, xs in _schemaLocations.iteritems()])
		xsi_schemaLocation_name = "xsi:schemaLocation"
		a_xmlns_xsi = XSINamespace
		xmlns_xsi_name = "xmlns:xsi"


	class STCResourceProfile(_Toplevel): pass
	class ObsDataLocation(_Toplevel): pass

	class Name(STCElement):
		mayBeEmpty = False
	class Name1(Name): pass
	class Name2(Name): pass
	class Name3(Name): pass

	class T_double1(STCElement):
		stringifyContent = True
		mayBeEmpty = False
		a_gen_unit = None
		a_pos_angle_unit = None
		a_pos_unit = None
		a_spectral_unit = None
		a_time_unit = None
		a_vel_unit = None

	class T_double2(STCElement):
		mayBeEmpty = False
		a_unit = None
		a_gen_unit = None
		a_vel_unit = None
	
	class T_double3(T_double2): 
		mayBeEmpty = False
		a_vel_time_unit = None

	class T_size2(STCElement):
		mayBeEmpty = False
		a_gen_unit = None
		a_unit = None
		a_vel_time_unit = None

	class T_size3(STCElement):
		mayBeEmpty = False
		a_gen_unit = None
		a_unit = None
		a_vel_time_unit = None

	class Error(T_double1): pass
	class Error2Radius(T_double1): pass
	class Resolution(T_double1): pass
	class Size(T_double1): pass

	class T_coordinate(T_double2):
		a_frame_id = None

	class Position(T_coordinate): pass
	class Position1D(T_coordinate): pass
	class Position2D(T_coordinate): pass
	class Position3D(T_coordinate): pass

	class T_Interval(STCElement):
		a_epoch = None
		a_fill_factor = None
		a_hi_include = None
		a_lo_include = None
		a_unit = None
		a_frame_id = None
	
	class Position2VecInterval(T_Interval): pass
	class Coord2VecInterval(T_Interval): pass
	class CoordScalarInterval(T_Interval): pass

	class Polygon(STCElement):
		a_coord_system_id = None
		a_epoch = None
		a_fill_factor = None
		a_frame_id = None
		a_hi_include = None
		a_lo_include = None
		a_note = None
		a_unit = None

	class Circle(STCElement):
		a_coord_system_id = None
		a_epoch = None
		a_fill_factor = None
		a_frame_id = None
		a_hi_include = None
		a_lo_include = None
		a_note = None
		a_unit = None
	
	class Pole(STCElement): 
		a_unit = None
		a_vel_time_unit = None

	class Area(STCElement):
		a_linearUnit = None
		a_validArea = None

	class Vertex(STCElement): pass
	class SmallCircle(STCElement): pass

	class _CoordSys(STCElement): pass
	
	class AstroCoordSystem(_CoordSys): 
		restrictChildren = set(["CoordFrame", "TimeFrame", "SpaceFrame",
			"SpectralFrame", "RedshiftFrame"])

	class Equinox(STCElement):
		mayBeEmpty = False

	class PixelCoordSystem(_CoordSys): 
		restrictChildren = set(["CoordFrame", "PixelCoordFrame"])

	class TimeFrame(STCElement):
		pass
	
	class SpaceFrame(STCElement): pass
	
	class SpectralFrame(STCElement): pass
	
	class RedshiftFrame(STCElement):
		a_value_type = "VELOCITY"

	class Redshift(STCElement):
		a_coord_system_id = None
		a_frame_id = None
		a_unit = None
		a_vel_time_unit = None

	class RedshiftInterval(T_Interval):
		a_vel_time_unit = None

	class DopplerDefinition(STCElement): pass

	class GenericCoordFrame(STCElement): pass

	class PixelCoordFrame(STCElement):
		a_axis1_order = None
		a_axis2_order = None
		a_axis3_order = None
		a_ref_frame_id = None
	
	class PixelSpace(STCElement): pass
	class ReferencePixel(STCElement): pass

	class T_Pixel(STCElement):
		a_frame_id = None
	class Pixel1D(T_Pixel): pass
	class Pixel2D(T_Pixel): pass
	class Pixel3D(T_Pixel): pass

	class T_SpaceRefFrame(STCElement): 
		a_ref_frame_id = None

	class T_ReferencePosition(STCElement): pass

	class T_CoordFlavor(STCElement):
		a_coord_naxes = "2"
		a_handedness = None

	class T_Coords(STCElement):
		a_coord_system_id = None
	
	class AstroCoords(T_Coords): pass
	
	class PixelCoords(T_Coords): pass
	
	class Coordinate(STCElement):
		a_frame_id = None
	
	class Pixel(Coordinate): pass

	class ScalarRefFrame(STCElement):
		a_projection = None
		a_ref_frame_id = None

	class ScalarCoordinate(Coordinate):
		a_unit = None

	class StringCoordinate(Coordinate): 
		a_unit = None

	class Time(STCElement):
		a_unit = None
		a_coord_system_id = None
		a_frame_id = None

	class T_astronTime(Time):
		childSequence = ["Timescale", "TimeOffset", "MJDTime", "JDTime", "ISOTime"]
	
	class StartTime(T_astronTime): pass
	class StopTime(T_astronTime): pass
	class TimeInstant(T_astronTime): pass
	class T(T_astronTime): pass

	class CoordArea(STCElement):
		a_coord_system_id = None
	
	class PixelCoordArea(CoordArea): pass

	class AllSky(T_Interval):
		a_coord_system_id = None
		a_note = None

	class SpatialInterval(T_Interval):
		a_fill_factor = "1.0"
	
	class TimeFrame(STCElement): pass

	class TimeRefDirection(STCElement):
		a_coord_system_id = None


	class TimeInterval(T_Interval):
		childSequence = ["StartTime", "StopTime"]

	class TimeScale(STCElement): pass
	class Timescale(STCElement): pass  # Bizarre, No?

	class ISOTime(STCElement): pass
	class JDTime(STCElement): pass
	class MJDTime(STCElement): pass
	class TimeOrigin(STCElement): pass

	class Spectral(STCElement):
		a_coord_system_id = None
		a_frame_id = None
		a_unit = None

	class SpectralInterval(T_Interval): pass

	class AstroCoordArea(STCElement):
		a_coord_system_id = None
	
	class ObservatoryLocation(STCElement): pass
	class ObservationLocation(STCElement): pass

	class Cart2DRefFrame(STCElement):
		a_projection = None
		a_ref_frame_id = None

	class Vector2DCoordinate(STCElement):
		a_frame_id = None
		a_unit = None

STC._addSubsGroup(STC.T_double1, ["C1", "C2", "C3", "e", "Error", 
	"Error2Radius",
	"Error3Radius", "HiLimit", "LoLimit", "PixSize", "Radius", "Resolution",
	"Resolution2Radius", "Resolution3Radius", "Scale", "SemiMajorAxis",
	"SemiMinorAxis", "Size2Radius", "Size3Radius", "Value"])

STC._addSubsGroup(STC.T_double2, ["HiLimit2Vec", "LoLimit2Vec", 
	"Pole", "Position", "Value2"])

STC._addSubsGroup(STC.T_double3, ["HiLimit3Vec", "LoLimit3Vec", 
	"Point", "Value3", "Vector"])

STC._addSubsGroup(STC.T_size2, ["Error2", "PixSize2", "Resolution2", 
	"Size2", "Transform2", "CValue2"])

STC._addSubsGroup(STC.T_size3, ["Error3", "PixSize3", "Resolution3", 
	"Size3", "Transform3", "CValue3"])

STC._addSubsGroup(STC.T_SpaceRefFrame, stcSpaceRefFrames)
STC._addSubsGroup(STC.T_ReferencePosition,stcRefPositions)
STC._addSubsGroup(STC.T_CoordFlavor, stcCoordFlavors)



if __name__=="__main__":
	print ex3().render()
