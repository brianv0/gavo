"""
The STC data model, XML and text serialized.

Since STC is so insanely huge, we don't implement the whole mess.  I guess
we should expect to get in STC-S as a rule.
"""

from gavo.utils import ElementTree
from gavo.utils.stanxml import Element, XSINamespace, Error


class InvalidSubstitution(Error):
	pass


STCNamespace = "http://www.ivoa.net/xml/STC/stc-v1.30.xsd"
XlinkNamespace = "http://www.w3.org/1999/xlink/"

ElementTree._namespace_map[STCNamespace] = "stc"
ElementTree._namespace_map[XlinkNamespace] = "xlink"

_schemaLocations = {
	STCNamespace: "http://vo.ari.uni-heidelberg.de/docs/schemata/stc-v1.30.xsd",
	XlinkNamespace: "http://vo.ari.uni-heidelberg.de/docs/schemata/xlink.xsd",
}


def _makeElementFactory(baseClass, validNames=None):
	"""returns a element class factories for crazy substitution groups.

	SpaceRefFrame and various other STC types do a kind of name-based
	dispatch -- there are a gazillion elements derived from them.

	Rather than spelling out all those specific elements, the STC namespace
	below provides factory functions that receive the name of the desired
	element and return an Element class.  These factories are generated
	here; just give the base class (e.g., SpaceRefFrame).  The factories
	will automatically cache the generated classes.

	The factories are class methods.
	"""
	cache = {}
	def factory(name):
		if validNames and not name in validNames:
			raise Error("%s is not an allowed name for a %s element"%(
				name, baseClass.__name__))
		if not name in cache:
			vars = {"baseClass": baseClass}
			cDef = "class %s(baseClass): pass"%(name)
			exec cDef in vars
			cache[name] = vars[name]
		return cache[name]
	return staticmethod(factory)


def _addElementsOfType(container, elementList, baseClass):
	"""adds classes derived from baseClass with names from elementList to
	container.

	This is for bulk definition of elements.  Basically, it's the static
	version of the element factories returned by _makeElementFactory.

	I'm not sure yet what the better approach is and use both in the
	definition of STC elements.
	"""
	for name in elementList:
		vars = {"baseClass": baseClass}
		cDef = "class %s(baseClass): pass"%(name)
		exec cDef in vars
		setattr(container, name, vars[name])


stcSpaceRefFrames = ["ICRS", "FK4", "FK5", "ECLIPTIC", "GALACTIC_I",
		"GALACTIC_II", "SUPER_GALACTIC", "AZ_EL", "BODY", "GEO_C", "GEO_D", "MAG",
		"GSE", "GSM", "SM", "HGC", "HGS", "HPC", "HPR", "HEE", "HEEQ", "HGI",
		"HRTN", "MERCURY_C", "VENUS_C", "LUNA_C", "MARS_C", "JUPITER_C_III",
		"SATURN_C_III"]

stcRefPositions = ["TOPOCENTER", "BARYCENTER", "HELIOCENTER", "GEOCENTER",
		"LSR", "LSRK", "LSRD", "GALACTIC_CENTER", "LOCAL_GROUP_CENTER", "MOON",
		"EMBARYCENTER", "MERCURY", "VENUS", "MARS", "JUPITER", "SATURN", "URANUS",
		"NEPTUNE", "PLUTO", "RELOCATABLE", "UNKNOWNRefPos", "CoordRefPos"]

stcCoordFlavors = ["SPHERICAL", "CARTESIAN", "UNITSPHERE", "POLAR", 
	"CYLINDRICAL", "STRING", "HEALPIX"]


class STC(object):
	"""is a container for classes modelling STC elements.
	"""
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

	class Name(STCElement): pass
	class Name1(STCElement): pass
	class Name2(STCElement): pass
	class Name3(STCElement): pass

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

	class PixelCoordSystem(_CoordSys): 
		restrictChildren = set(["CoordFrame", "PixelCoordFrame"])
	
	class TimeFrame(STCElement):
		restrictChildren = set(["Name", "TimeScale", "ReferencePosition",
			"TimeRefDirection"])
	
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

	makeSpaceRefFrame = _makeElementFactory(T_SpaceRefFrame,
		validNames=set(stcSpaceRefFrames))

	class T_ReferencePosition(STCElement): pass

	makeReferencePosition = _makeElementFactory(T_ReferencePosition,
		validNames=set(stcRefPositions))
	
	class T_CoordFlavor(STCElement):
		a_coord_naxes = "2"
		a_handedness = None

	makeCoordFlavor = _makeElementFactory(T_CoordFlavor, validNames=
		set(stcCoordFlavors))

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

	class T_astronTime(STCElement): pass
	
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

	class TimeScale(STCElement): pass

	class TimeInterval(T_Interval): pass

	class Timescale(STCElement): pass

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

_addElementsOfType(STC, ["C1", "C2", "C3", "e", "Error", "Error2Radius",
		"Error3Radius", "HiLimit", "LoLimit", "PixSize", "Radius", "Resolution",
		"Resolution2Radius", "Resolution3Radius", "Scale", "SemiMajorAxis",
		"SemiMinorAxis", "Size2Radius", "Size3Radius", "Value"],
	STC.T_double1)

_addElementsOfType(STC, ["HiLimit2Vec", "LoLimit2Vec", 
	"Pole", "Position", "Value2"], STC.T_double2)

_addElementsOfType(STC, ["HiLimit3Vec", "LoLimit3Vec", "Point", "Value3",
	"Vector"], STC.T_double3)

_addElementsOfType(STC, ["Error2", "PixSize2", "Resolution2", "Size2",
	"Transform2"], STC.T_size2)



class _Attr(object):
	"""is a helper for STCSGrammar.

	Basically, children destined to become their parent's attributes
	construct an attribute.
	"""
	def __init__(self, name, value):
		self.name, self.value = name, value

	@classmethod
	def getAction(cls, name, argNum=1):
		def make(s, pos, toks):
			return cls(name, toks[argNum])


def _demuxChildren(toks):
	"""returns a pair of real children and a dict of attributes from the
	embedded _Attr children.
	"""
	realChildren, attrs = [], {}
	for c in tok:
		if isinstance(c, _Attr):
			attrs[c.name] = c.value
		else:
			realChildren.append(c)
	return realChildren, attrs


def _sxToPA(stanElement):
	"""returns a parse action constructing an xmlstan Element (cf. _Attr).
	"""
	def parseAction(s, pos, toks):
		ch, at = _demuxChildren(toks)
		return stanElement(**at)[ch]


def _factorycallToPA(factory):
	"""returns a parse action constructing an xmlstan Element using
	factory.

	This is for makeSpaceRefFrame and friends.
	"""
	def _frameAction(s, pos, toks):
		ch, at = _demuxChildren(toks)
		return factory(ch[0])(**at)[ch[1:]]



def getSTCSGrammar():
	"""returns the root symbol for a grammar parsing STC-S into STC in xmlstan.
	"""
	from pyparsing import Word, Literal, Optional, alphas, CaselessKeyword,\
		ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,\
		Suppress, Keyword, Forward, QuotedString, Group, printables, nums,\
		CaselessLiteral, ParseException, Regex, sglQuotedString, alphanums,\
		dblQuotedString, White

	_exactNumericRE = r"\d+(\.(\d+)?)?|\.\d+"
	exactNumericLiteral = Regex(_exactNumericRE)
	number = Regex(r"(?i)(%s)E[+-]?\d+"%_exactNumericRE)

# meta items common to most spatial specs
	fillfactor = Keyword("fillfactor") + number
	fillfactor.setParseAction(_Attr.getAction("fill_factor"))
	frame = Regex("|".join(stcSpaceRefFrames))
	frame.setParseAction(_factorycallToPA(STC.makeSpaceRefFrame))
	refpos = Regex("|".join(stcRefPositions))
	refpos.setParseAction(_factorycallToPA(STC.makePreferencePosition))
	flavor = Regex("|".join(stcCoordFlavor))
	flavor.setParseAction(_factorycallToPA(STC.makeCoordFlavor))
	commonSpaceItems = (Optional( fillfactor ) + frame + Optional( refpos ) + 
		Optional( flavor ))

# properties of most spatial specs
	position = Keyword("Position") + OneOrMore( number )
	# XXX parse action????
	unit = Keyword("unit") + Word()
	unit.setParseAction(_Attr.getAction("unit"))
	error = Keyword("Error") + OneOrMore( number )
	resolution = Keyword("Resolution") + OneOrMore( number )
	size = Keyword("Size") + OneOrMore(number)
	pixSize = Keyword("PixSize") + OneOrMore(number)
	spatialProps = (Optional( unit ) +
		Optional( error ) + Optional( resolution ) + Optional( size ) +
		Optional( pixSize ))

# the velocity sub-phrase
	velocityInterval = (Keyword("VelocityInterval") + number +
		OneOrMore( number ))
	velocity = Keyword("Velocity") + number
	velocityPhrase = (Optional( velocityInterval ) +
		Optional( velocity ) + spatialProps)

# stuff common to regions
	spatialTail = spatialProps + Optional( velocityPhrase )
	regionTail = position + spatialTail

	limits = ZeroOrMore( number )
	positionInterval = (Keyword("PositionInterval") +
		commonSpaceItems + limits + spatialTail)


def ex3():
	for name in dir(STC):
		if not name.startswith("_"):
			exec "%s = getattr(STC, %s)"%(name, repr(name))
	return ObsDataLocation[
		ObservatoryLocation(id="Arecibo", type="simple", 
			href="ivo://STClib/Observatories#Arecibo"),
		ObservationLocation[
			AstroCoordSystem(id="TT-GAL-RADIO-LSR-TOPO")[
				TimeFrame[
					TimeScale["TT"],
					makeReferencePosition("TOPOCENTER")],
				SpaceFrame(id="GalFrame")[
					makeSpaceRefFrame("GALACTIC_II"),
					makeReferencePosition("TOPOCENTER"),
					makeCoordFlavor("SPHERICAL")(coord_naxes="2")],
				SpectralFrame[
					makeReferencePosition("TOPOCENTER")],
				RedshiftFrame(id="VELFrame", value_type="VELOCITY")[
					DopplerDefinition["RADIO"],
					makeReferencePosition("LSR")]],
			AstroCoordSystem(id="TT-ICRS-RADIO-LSR-TOPO")[
				TimeFrame[
					TimeScale["TT"],
					makeReferencePosition("TOPOCENTER")],
				SpaceFrame[
					makeSpaceRefFrame("ICRS"),
					makeReferencePosition("TOPOCENTER"),
					makeCoordFlavor("SPHERICAL")(coord_naxes="2")],
				SpectralFrame[
					makeReferencePosition("TOPOCENTER")],
				RedshiftFrame(id="VELFrame", value_type="VELOCITY")[
					DopplerDefinition["RADIO"],
					makeReferencePosition("LSR")]],
			AstroCoords(coord_system_id="TT-GAL-RADIO-LSR-TOPO")[
				Time(unit="s")[
					TimeInstant[
						ISOTime["2005-12-15T08:23:56"]],
					Error[15000000],
					Resolution[100],
					PixSize[100]],
				Position2D(unit="deg")[
					Error2Radius[0.002],
					Resolution2[
						C1[0.05],
						C2[0.05]],
					PixSize2[
						C1[0.01],
						C2[0.01]]],
				Spectral(unit="MHz")[
					Value[1420.405752],
					Size[0],
					PixSize[0]],
				Redshift(unit="km", vel_time_unit="s")[
					Resolution[0.5],
					PixSize[0.25]]],
			AstroCoordArea(coord_system_id="TT-GAL-RADIO-LSR-TOPO")[
				TimeInterval[
					StartTime[
						ISOTime["2005-06-15T06:57:36"]],
					StopTime[
						ISOTime["2006-06-15T10:07:16"]]],
				Position2VecInterval(unit="deg")[
					LoLimit2Vec[
						C1[10],
						C2[-3]],
					HiLimit2Vec[
						C1[20],
						C2[3]]],
				RedshiftInterval(unit="km", vel_time_unit="s")[
					LoLimit[-200],
					HiLimit[2000]]],
			AstroCoordArea(coord_system_id="TT-ICRS-RADIO-LSR-TOPO")[
				TimeInterval[
					StartTime[
						ISOTime["2005-06-15T06:57:36"]],
					StopTime[
						ISOTime["2006-06-15T10:07:16"]]],
				Polygon(unit="deg")[
					Vertex[
						Position[
							C1[274.762],
							C2[-21.726]]],
					Vertex[
						Position[
							C1[274.762],
							C2[-21.726]]],
					Vertex[
						Position[
							C1[274.762],
							C2[-21.726]]],
					Vertex[
						Position[
							C1[274.762],
							C2[-21.726]]]],
					RedshiftInterval(unit="km", vel_time_unit="s")[
						LoLimit[-200],
						HiLimit[200]]]],
		PixelSpace[
			PixelCoordSystem(id="GlPix")[
				PixelCoordFrame(id="PixGALFrame", ref_frame_id="GALFrame",
						axis1_order="1", axis2_order="2")[
					Cart2DRefFrame(projection="CAR")[
						Transform2(unit="deg")[
							C1[-0.01], C2[0.01]]],
					makeReferencePosition("CoordRefPos")[
						Vector2DCoordinate(unit="deg", frame_id="GALFrame")[
							Value2[
								C1[20], C2[-3]]]],
					makeCoordFlavor("CARTESIAN")(coord_naxes="2"),
					ReferencePixel[
						Pixel2D[
							Name1["l"],
							Name2["b"],
							Value2[
								C1[1], C2[1]]]]],
				PixelCoordFrame(id="PixVELFrame", ref_frame_id="VELFrame",
						axis1_order="3")[
					ScalarRefFrame[
						Scale[0.25]],
					makeReferencePosition("CoordRefPos")[
						Redshift(frame_id="VELFrame")[
							Value[-200]]],
					makeCoordFlavor("CARTESIAN")(coord_naxes="1"),
					ReferencePixel[
						Pixel1D[
							Name["Velocity"],
							Value[-200]]]]],
			PixelCoordArea(coord_system_id="GlPix")[
				Coord2VecInterval(frame_id="PixGalFrame")[
					LoLimit2Vec[
						C1[1], C2[1]],
					HiLimit2Vec[
						C1[1001], C2[601]]],
				CoordScalarInterval(frame_id="PixVELFrame")[
					LoLimit[1],
					HiLimit[1001]]]]]


if __name__=="__main__":
	print ex3().render()
