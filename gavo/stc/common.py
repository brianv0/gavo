"""
Definitions and shared code for STC processing.
"""

from gavo.utils import ElementTree

class STCError(Exception):
	pass

class STCSParseError(Exception):
	"""is raised if an STC-S expression could not be parsed.

	Low-level routines raise a pyparsing ParseException.  Only higher
	level functions raise this error.  The offending expression is in
	the expr attribute, the start position of the offending phrase in pos.
	"""
	def __init__(self, msg, expr=None, pos=None):
		Exception.__init__(self, msg)
		self.pos, self.expr = pos, expr

class STCLiteralError(STCError):
	"""is raised when a literal is not well-formed.

	There is an attribute literal giving the malformed literal.
	"""
	def __init__(self, msg, literal=None):
		Exception.__init__(self, msg)
		self.literal = literal

class STCInternalError(STCError):
	"""is raised when assumptions about the library behaviour are violated.
	"""

STCNamespace = "http://www.ivoa.net/xml/STC/stc-v1.30.xsd"
XlinkNamespace = "http://www.w3.org/1999/xlink/"

ElementTree._namespace_map[STCNamespace] = "stc"
ElementTree._namespace_map[XlinkNamespace] = "xlink"


# The following lists have to be updated when the STC standard is
# updated.  They are used for building the STC namespace, for parsing
# STS/S, and so on.

# known space reference frames
stcSpaceRefFrames = set(["ICRS", "FK4", "FK5", "ECLIPTIC", "GALACTIC_I",
		"GALACTIC_II", "SUPER_GALACTIC", "AZ_EL", "BODY", "GEO_C", "GEO_D", "MAG",
		"GSE", "GSM", "SM", "HGC", "HGS", "HPC", "HPR", "HEE", "HEEQ", "HGI",
		"HRTN", "MERCURY_C", "VENUS_C", "LUNA_C", "MARS_C", "JUPITER_C_III",
		"SATURN_C_III", "UNKNOWNFrame"])

# known space reference positions
stcRefPositions = set(["TOPOCENTER", "BARYCENTER", "HELIOCENTER", "GEOCENTER",
		"LSR", "LSRK", "LSRD", "GALACTIC_CENTER", "LOCAL_GROUP_CENTER", "MOON",
		"EMBARYCENTER", "MERCURY", "VENUS", "MARS", "JUPITER", "SATURN", "URANUS",
		"NEPTUNE", "PLUTO", "RELOCATABLE", "UNKNOWNRefPos", "CoordRefPos"])

# known flavors for coordinates
stcCoordFlavors = set(["SPHERICAL", "CARTESIAN", "UNITSPHERE", "POLAR", 
	"CYLINDRICAL", "STRING", "HEALPIX"])

# known time scales
stcTimeScales = set(["TT", "TDT", "ET", "TAI", "IAT", "UTC", "TEB", "TDB",
	"TCG", "TCB", "LST", "nil"])
