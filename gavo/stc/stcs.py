"""
Parsing and generating STC-S

The general plan is to parse STC-S into some sort of tree (dictionaries
with list values, possibly containing more such dictionaries).  These
trees can then be processed into something roughly resembling the data
model, furnished with defaults, and processed by what essentially is
user code.
"""

import copy

from pyparsing import (Word, Literal, Optional, alphas, CaselessKeyword,
		ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,
		Suppress, Keyword, Forward, QuotedString, Group, printables, nums,
		CaselessLiteral, ParseException, Regex, sglQuotedString, alphanums,
		dblQuotedString, White, ParseException, ParseResults, Empty)

from gavo.stc import stcsdefaults
from gavo.stc import times
from gavo.stc.common import *
from gavo.utils import stanxml

class AComputedDefault(object):
	"""A sentinel for computed default values.
	"""
	pass


# STC-S spatial flavors, with dimensions and stc flavors
stcsFlavors = {
	"SPHER2": (2, "SPHERICAL"),
	"SPHER3": (3, "SPHERICAL"),
	"UNITSPHER": (3, "UNITSPHERE"),
	"CART1": (1, "CARTESIAN"),
	"CART2": (2, "CARTESIAN"),
	"CART3": (3, "CARTESIAN"),
}


spatialUnits = set(["deg", "arcmin", "arcsec", "m", "mm", "km", "AU", 
	"pc", "kpc", "Mpc", "rad"])
temporalUnits = set(["yr", "cy", "s", "d", "a"])
spectralUnits = set(["MHz", "GHz", "Hz", "Angstrom", "keV", "MeV", 
	"eV", "mm", "um", "nm", "m"])

def _assertGrammar(cond, msg, pos):
	if not cond:
		raise STCSParseError(msg, pos)


def _iterDictNode(node, path):
	"""does iterNode's work for dict nodes.
	"""
	for k, v in node.iteritems():
		if isinstance(v, list):
			subIter = _iterListNode(v, path+(k,))
		elif isinstance(v, dict):
			subIter = _iterDictNode(v, path+(k,))
		else:
			continue  # content does not contain a subtree
		for res in subIter:
			yield res
	yield path, node

def _iterListNode(node, path):
	"""does iterNode's work for list nodes.
	"""
	for subNode in node:
		if isinstance(subNode, dict):
			for res in _iterDictNode(subNode, path):
				yield res

def iterNodes(tree):
	"""traverses the concrete syntax tree in postorder, returning pairs of 
	paths and nodes.

	A node returned here is always a dictionary.  The path consists of the
	keys leading to the node in a tuple.
	"""
	if isinstance(tree, list):
		return _iterListNode(tree, ())
	elif isinstance(tree, dict):
		return _iterDictNode(tree, ())
	else:
		raise STCInternalError("Bad node in tree %s"%tree)


def addDefaults(tree):
	"""adds defaults for missing values for a concrete syntax tree.

	The tree is changed in place.  For details, see stcsdefaults.
	"""
	for path, node in iterNodes(tree):
		if path and path[-1] in stcsdefaults.defaultingFunctions:
			stcsdefaults.defaultingFunctions[path[-1]](node)
	return tree


def removeDefaults(tree):
	"""removes defaults from a concrete syntax tree.

	The tree is changed in place.  For details, see stcsdefaults.
	"""
	for path, node in iterNodes(tree):
		if path and path[-1] in stcsdefaults.undefaultingFunctions:
			stcsdefaults.undefaultingFunctions[path[-1]](node)
	return tree


def makeTree(parseResult):
	"""returns the pyparsing parseResult as a data structure consisting
	of simple python dicts and lists.

	The "tree" has two kinds of nodes: Dictionaries having lists as
	values, and lists containing (as a rule) literals or (for more deeply
	nested constructs, which are rare in STC-S) other dictionaries of
	this kind.

	A parse node becomes a dict node if it has named children.  The root
	always is a dict.

	Note that unnamed children of nodes becoming dicts will be lost in
	the result.
	"""
	if not len(parseResult):  # empty parse results become empty lists
		res = []
	elif parseResult.keys():  # named children, generate a dict
		res = {}
		for k in parseResult.keys():
			v = parseResult[k]
			if isinstance(v, ParseResults):
				res[k] = makeTree(v)
			else:
				res[k] = v
	else:                     # no named children, generate a list
		if isinstance(parseResult[0], ParseResults):
			res = [makeTree(child) for child in parseResult]
		else:
			res = list(parseResult)
	return res


def _reFromKeys(iterable):
	"""returns a regular expression matching any of the strings in iterable.

	The trick is that the longest keys must come first.
	"""
	return "|".join(sorted(iterable, key=lambda x:-len(x)))


def getSymbols(_exportAll=False):
	"""returns a dictionary of symbols for a grammar parsing STC-S into
	a concrete syntax tree.
	"""

	_exactNumericRE = r"[+-]?\d+(\.(\d+)?)?|[+-]?\.\d+"
	exactNumericLiteral = Regex(_exactNumericRE)
	number = Regex(r"(?i)(%s)(E[+-]?\d+)?"%_exactNumericRE).addParseAction(
		lambda s,p,toks: float(toks[0]))

# units
	_unitOpener = Suppress( Keyword("unit") )
	_spaceUnitWord = Regex(_reFromKeys(spatialUnits))
	_timeUnitWord = Regex(_reFromKeys(temporalUnits))
	spaceUnit = _unitOpener + OneOrMore( _spaceUnitWord ).addParseAction(
		lambda s,p,t: " ".join(t))("unit")
	timeUnit = _unitOpener + _timeUnitWord("unit")
	spectralUnit = _unitOpener + Regex(_reFromKeys(spectralUnits))("unit")
	redshiftUnit = _unitOpener + ( (_spaceUnitWord + "/" + _timeUnitWord
		).addParseAction(lambda s,p,t: "".join(t)) | Keyword("nil") )("unit")
	velocityUnit = _unitOpener + OneOrMore( (_spaceUnitWord + "/" + _timeUnitWord
		).addParseAction(lambda s,p,t: "".join(t)) ).addParseAction(
			lambda s,p,t: " ".join(t))("unit")

# basic productions common to most STC-S subphrases
	fillfactor = (Suppress( Keyword("fillfactor") ) + number("fillfactor"))
	noEqFrame = (Keyword("J2000") | Keyword("B1950") | Keyword("ICRS") | 
		Keyword("GALACTIC") | Keyword("GALACTIC_I") | Keyword("GALACTIC_II") | 
		Keyword("SUPER_GALACTIC") | Keyword("GEO_C") | Keyword("GEO_D") | 
		Keyword("UNKNOWNFrame"))("frame")
	eqFrameName = (Keyword("FK5") | Keyword("FK4") | Keyword("ECLIPTIC")
		)("frame")
	eqSpec = Regex("[BJ][0-9]+([.][0-9]*)?")("equinox")
	eqFrame = eqFrameName + Optional( eqSpec )
	frame = eqFrame | noEqFrame
	refpos = (Regex(_reFromKeys(stcRefPositions)))("refpos")
	flavor = (Regex(_reFromKeys(stcsFlavors)))("flavor")

# basic productions for times and such.
	timescale = (Regex("|".join(stcTimeScales)))("timescale")
	jdLiteral = (Suppress( Literal("JD") ) + exactNumericLiteral
		).addParseAction(lambda s,p,toks: times.jdnToDateTime(float(toks[0])))
	mjdLiteral = (Suppress( Literal("MJD") ) + exactNumericLiteral
		).addParseAction(lambda s,p,toks: times.mjdToDateTime(float(toks[0])))
	isoTimeLiteral = Regex(r"\d\d\d\d-?\d\d-?\d\d(T\d\d:?\d\d:?\d\d(\.\d*)?Z?)?"
		).addParseAction(lambda s,p,toks: times.parseISODT(toks[0]))
	nakedTime = (isoTimeLiteral | jdLiteral | mjdLiteral)

# properties of most spatial specs
	_coos = ZeroOrMore( number )("coos")
	_twoDCoo = number + number
	_pos = Optional( ZeroOrMore( number )("pos") )
	positionSpec = Suppress( Keyword("Position") ) + _pos
	error = Suppress( Keyword("Error") ) + OneOrMore( number )
	resolution = Suppress( Keyword("Resolution") ) + OneOrMore( number )
	size = Suppress( Keyword("Size") ) + OneOrMore(number)
	pixSize = Suppress( Keyword("PixSize") ) + OneOrMore(number)
	_spatialProps = (Optional( spaceUnit ) +
		Optional( error("error") ) + Optional( resolution("resolution") ) + 
		Optional( size("size") ) + Optional( pixSize("pixSize") ))
	velocitySpec = Suppress( Keyword("Velocity") ) + OneOrMore( number )("pos")
	velocityInterval = ( Keyword("VelocityInterval")("type") + 
		Optional( fillfactor ) + _coos + Optional( velocitySpec ) + 
		Optional( velocityUnit ) +
		Optional( error("error") ) + Optional( resolution("resolution") ) + 
		Optional( pixSize("pixSize") )).addParseAction(makeTree)
	_spatialTail = (_spatialProps + 
		Optional( velocityInterval )("velocity"))
	_regionTail = Optional( positionSpec ) + _spatialTail
	_commonSpaceItems = ( frame + Optional( refpos ) + 
		Optional( flavor ))
	_commonRegionItems = Optional( fillfactor ) + _commonSpaceItems

# times and time intervals
	timephrase = Suppress( Keyword("Time") ) + nakedTime
	_commonTimeItems = (	Optional( timeUnit ) + Optional( 
		error("error") ) + Optional( resolution("resolution") ) + 
		Optional( pixSize("pixSize") ) )
	_intervalOpener = ( Optional( fillfactor ) + 
		Optional( timescale("timescale") ) +
		Optional( refpos("refpos") ) )
	_intervalCloser = Optional( timephrase("pos") ) + _commonTimeItems

	timeInterval =  (Keyword("TimeInterval")("type") + 
		_intervalOpener + ZeroOrMore( nakedTime )("coos") + 
		_intervalCloser)
	startTime = (Keyword("StartTime")("type") + _intervalOpener + 
		nakedTime.setResultsName("coos", True) + _intervalCloser)
	stopTime = (Keyword("StopTime")("type") + _intervalOpener + 
		nakedTime.setResultsName("coos", True) + _intervalCloser)
	time = (Keyword("Time")("type")  + Optional( timescale("timescale") ) + 
		Optional( refpos("refpos") ) + nakedTime.setResultsName("pos", True) + 
		_commonTimeItems)
	timeSubPhrase = (timeInterval | startTime | stopTime | time).addParseAction(
		makeTree)

# atomic "geometries"; I do not bother to specify their actual
# arguments since, without knowing the frame, they may be basically
# anthing.  Sure, most of those only make sense with 2D spherical, but
# I'm not so sure of this as to enshrine it in the grammar.
	_atomicGeometryKey = ( Keyword("AllSky") | Keyword("Circle") |
		Keyword("Ellipse") | Keyword("Box") | Keyword("Polygon") |
		Keyword("Convex") )
	atomicGeometry = ( _atomicGeometryKey("type") + _commonRegionItems + 
		_coos + _regionTail )

# compound "geometries"
	_compoundGeoOperator = ( Keyword("Union") | Keyword("Intersection") |
		Keyword("Difference") )
	_compoundNot = Keyword("Not")
	_compoundGeoExpression = Forward()
	_compoundGeoOperand  = ( Optional( _compoundNot )("complement") + ( 
		( _atomicGeometryKey("subtype") + _coos )
		| _compoundGeoExpression )).addParseAction(lambda s,p,t: dict(t))
	_compoundGeoArguments = OneOrMore( _compoundGeoOperand )
	_compoundGeoExpression << ( _compoundGeoOperator("subtype") + 	
		_compoundGeoArguments("children") )
	compoundGeoPhrase = ( _compoundGeoOperator("type") + _commonRegionItems +
		_compoundGeoArguments("children") + _regionTail )

# space subphrase
	positionInterval = ( Keyword("PositionInterval")("type") +
		_commonRegionItems + _coos + _regionTail )
	position = ( Keyword("Position")("type") + 
		_commonSpaceItems + _pos + _spatialTail )
	spaceSubPhrase = ( positionInterval | position | atomicGeometry |
		compoundGeoPhrase ).addParseAction(makeTree)

# spectral subphrase
	spectralSpec = (Suppress( Keyword("Spectral") ) + number)("pos")
	_spectralTail = (Optional( spectralUnit ) + 
		Optional( error("error") ) + 
		Optional( resolution("resolution") ) + Optional( pixSize("pixSize") ))
	spectralInterval = (Keyword("SpectralInterval")("type") +
		Optional( fillfactor ) + Optional( refpos ) + _coos + 
		Optional( spectralSpec ) + _spectralTail)
	spectral = (Keyword("Spectral")("type") + Optional( refpos ) +
		_pos + _spectralTail)
	spectralSubPhrase = (spectralInterval | spectral ).addParseAction(
		makeTree)

# redshift subphrase
	redshiftType = Regex("VELOCITY|REDSHIFT")("redshiftType")
	redshiftSpec = (Suppress( Keyword("Redshift") ) + number)("pos")
	dopplerdef = Regex("OPTICAL|RADIO|RELATIVISTIC")("dopplerdef")
	_redshiftTail = ( Optional( redshiftUnit ) +
		Optional( error("error") ) + Optional( resolution("resolution") ) + 
		Optional( pixSize("pixSize") ))
	redshiftInterval = (Keyword("RedshiftInterval")("type") + 
		Optional( fillfactor ) + Optional( refpos ) + 
		Optional( redshiftType ) + Optional( dopplerdef ) +
		_coos + Optional( redshiftSpec ) + _redshiftTail)
	redshift = (Keyword("Redshift")("type") + Optional( refpos ) +
		Optional( redshiftType ) + Optional( dopplerdef ) +
		_pos + 
		_redshiftTail)
	redshiftSubPhrase = (redshiftInterval | redshift ).addParseAction(
		makeTree)

# top level
	stcsPhrase = (Optional( timeSubPhrase )("time") +
		Optional( spaceSubPhrase )("space") +
		Optional( spectralSubPhrase )("spectral") +
		Optional( redshiftSubPhrase )("redshift") ) + StringEnd()

	if _exportAll:
		return dict((n, v) for n, v in locals().iteritems()
			if hasattr(v, "setName"))
	else:
		return dict((n, v) for n, v in locals().iteritems() 
			if not n.startswith("_"))


def enableDebug(syms, debugNames=None):
	if not debugNames:
		debugNames = syms
	for name in debugNames:
		ob = syms[name]
		ob.setDebug(True)
		ob.setName(name)


getGrammar = CachedGetter(getSymbols)


def getCST(literal):
	try:
		tree = makeTree(getGrammar()["stcsPhrase"].parseString(literal))
	except ParseException, ex:
		raise STCSParseError("Invalid STCS expression (%s at %s)"%(ex.msg, ex.loc),
			expr=literal, pos=ex.loc)
	addDefaults(tree)
	return tree


if __name__=="__main__":
	syms = getSymbols(_exportAll=True)
#	print getCST("PositionInterval ICRS 1 2 3 4")
	enableDebug(syms)
	print makeTree(syms["stcsPhrase"].parseString(
		"Difference ICRS Union Circle 10 10 2 Not Difference AllSky Box 11 11 2 3 Intersection Polygon 10 2 2 10 10 10 Ellipse 11 11 2 3 30", parseAll=True))
