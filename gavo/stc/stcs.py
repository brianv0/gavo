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
		dblQuotedString, White, ParseException, ParseResults)

from gavo.stc import stcsdefaults
from gavo.stc.common import *
from gavo.stc.dm import STC
from gavo.utils import stanxml

class AComputedDefault(object):
	"""A sentinel for computed default values.
	"""
	pass


# STC-S spatial flavors, with dimensions and stc flavors
stcsFlavors = {
	"SPHER2": (2, "SPHERICAL"),
	"SPHER3": (3, "SPHERICAL"),
	"UNITSPHERE": (3, "UNITSPHERE"),
	"CART1": (1, "CARTESIAN"),
	"CART2": (2, "CARTESIAN"),
	"CART3": (3, "CARTESIAN"),
}

# STC-S reference frames, with STC counterparts
stcsFrames = {
	"ICRS": None,
	"FK5": None,
	"FK4": None,
	"J2000": None,
	"B1950": None,
	"ECLIPTIC": None,
	"GALACTIC": None,
	"GALACTIC_II": None,
	"SUPER_GALACTIC": None,
	"GEO_C": None,
	"GEO_D": None,
	"UNKNOWNFrame": None,
}

spatialUnits = set(["deg", "arcmin", "arcsec", "m", "mm", "km", "AU", 
	"pc", "kpc", "Mpc"])
temporalUnits = set(["yr", "cy", "s", "d", "a"])
spectralUnits = set(["MHz", "GHz", "Hz", "Angstrom", "keV", "MeV", 
	"eV", "mm", "um", "nm", "m"])
redshiftUnits = set(["km/s", "nil"])
# XXX I don't even know what VelocityInterval is supposed to do...
velocityUnits = set(["km/s", "m/s", "furlongs/fortnight"]) 

def _assertGrammar(cond, msg, pos):
	if not cond:
		raise STCSParseError(msg, pos)


# XXX TODO: Remove this
def _makeIntervals(seq, rootPrototype, startPrototype, stopPrototype):
	"""returns a sequence intervals based on prototype.

	We need this to parse the interval-type sub-phrases in STC/S (which suck).
	Here are the rules:

	(1) intervals may contain of 0, 1, or 2 seq item(s)
	(2) The return value will always contain at least one interval
	(3) Only the last interval is allowed to be incomplete
	"""
	res = [copy.deepcopy(rootPrototype)]
	nextIsStart = first = True
	for item in seq:
		if nextIsStart:
			if first:
				first = False
			else:
				res.append(copy.deepcopy(rootPrototype))
			res[-1][copy.deepcopy(startPrototype)[item]]
		else:
			res[-1][copy.deepcopy(stopPrototype)[item]]
		nextIsStart = not nextIsStart
	return res


def addDefaults(tree):
	"""adds defaults for missing values for a concrete syntax tree.

	The tree is changed in place.  For details, see stcsdefaults.
	"""
	for path, node in iterNodes(tree):
		if path in stcsdefaults.pathFunctions:
			stcsdefaults.pathFunctions[path](node)
		elif path and path[-1] in stcsdefaults.nodeNameFunctions:
			stcsdefaults.nodeNameFunctions[path[-1]](node)
	return tree


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


def getSymbols():
	"""returns a dictionary of symbols for a grammar parsing STC-S into
	a concrete syntax tree.
	"""

	_exactNumericRE = r"\d+(\.(\d+)?)?|\.\d+"
	exactNumericLiteral = Regex(_exactNumericRE)
	number = Regex(r"(?i)(%s)(E[+-]?\d+)?"%_exactNumericRE)

# units
	_unitOpener = Suppress( Keyword("unit") )
	spaceUnit = _unitOpener + Regex(_reFromKeys(spatialUnits))
	timeUnit = _unitOpener + Regex(_reFromKeys(temporalUnits))
	spectralUnit = _unitOpener + Regex(_reFromKeys(spectralUnits))
	redshiftUnit = _unitOpener + Regex(_reFromKeys(redshiftUnits))
	velocityUnit = _unitOpener + Regex(_reFromKeys(velocityUnits))

# basic productions common to most STC-S subphrases
	fillfactor = (Suppress( Keyword("fillfactor") ) + number)("fillfactor")
	frame = (Regex(_reFromKeys(stcsFrames)))("frame")
	refpos = (Regex(_reFromKeys(stcRefPositions)))("refpos")
	flavor = (Regex(_reFromKeys(stcsFlavors)))("flavor")

# basic productions for times and such.
	timescale = (Regex("|".join(stcTimeScales)))("timescale")
	jdLiteral = (Suppress( Literal("JD") ) + exactNumericLiteral)
	mjdLiteral = (Suppress( Literal("MJD") ) + exactNumericLiteral)
	isoTimeLiteral = Regex(r"\d\d\d\d-?\d\d-?\d\d(T\d\d:?\d\d:?\d\dZ?)?")
	nakedTime = (isoTimeLiteral | jdLiteral | mjdLiteral)


# properties of most spatial specs
	positionSpec = Suppress( Keyword("Position") ) + OneOrMore( number )
	error = Suppress( Keyword("Error") ) + OneOrMore( number )
	resolution = Suppress( Keyword("Resolution") ) + OneOrMore( number )
	size = Suppress( Keyword("Size") ) + OneOrMore(number)
	pixSize = Suppress( Keyword("PixSize") ) + OneOrMore(number)
	_spatialProps = (Optional( spaceUnit("unit") ) +
		Optional( error("error") ) + Optional( resolution("resolution") ) + 
		Optional( size("size") ) + Optional( pixSize("pixSize") ))
	velocitySpec = Suppress( Keyword("Velocity") ) + OneOrMore( number )
	velocityInterval = (Keyword("VelocityInterval") + Optional( fillfactor ) +
		ZeroOrMore( number )("coos") + Optional( velocitySpec("velocity") ) + 
		Optional( velocityUnit("unit") ) +
		Optional( error("error") ) + Optional( resolution("resolution") ) + 
		Optional( pixSize("pixSize") )).addParseAction(makeTree)
	_spatialTail = (_spatialProps + 
		Optional( velocityInterval )("velocityInterval"))
	_regionTail = Optional( positionSpec ) + _spatialTail
	_commonSpaceItems = ( frame + Optional( refpos ) + 
		Optional( flavor ))
	_commonRegionItems = Optional( fillfactor ) + _commonSpaceItems
	coos = ZeroOrMore( number )("coos")


# times and time intervals
	timephrase = Suppress( Keyword("Time") ) + nakedTime
	_commonTimeItems = (	Optional( timeUnit("unit") ) + Optional( 
		error("error") ) + Optional( resolution("resolution") ) + 
		Optional( pixSize("pixSize") ) )
	_intervalOpener = ( Optional( fillfactor("fill_factor") ) + 
		Optional( timescale("timescale") ) +
		Optional( refpos("refpos") ) )
	_intervalCloser = Optional( timephrase("timephrase") ) + _commonTimeItems

	timeInterval =  (Keyword("TimeInterval")("type") + 
		_intervalOpener + ZeroOrMore(nakedTime)("coos") + 
		_intervalCloser)
	startTime = (Keyword("StartTime")("type") + _intervalOpener + 
		nakedTime("startTime") + _intervalCloser)
	stopTime = (Keyword("StopTime")("type") + _intervalOpener + 
		nakedTime("stopTime") + _intervalCloser)
	time = (Keyword("Time")("type")  + Optional( timescale("timescale") ) + 
		Optional( refpos("refpos") ) + Optional ( nakedTime("givenTime") ) + 
		_commonTimeItems)
	timeSubPhrase = (timeInterval | startTime | stopTime | time).addParseAction(
		makeTree)

# space subphrase
	positionInterval = (Keyword("PositionInterval")("type") +
		_commonRegionItems + coos + _regionTail)
	allSky = ( Keyword("AllSky")("type") +
		_commonRegionItems + _regionTail )
	circle = ( Keyword("Circle")("type") + 
		_commonRegionItems + coos + _regionTail )
	ellipse = ( Keyword("Ellipse")("type") + 
		_commonRegionItems + coos + _regionTail )
	box = ( Keyword("Box")("type") + 
		_commonRegionItems + coos + _regionTail )
	polygon = ( Keyword("Polygon")("type") + 
		_commonRegionItems + coos + _regionTail )
	convex = ( Keyword("Convex")("type") + 
		_commonRegionItems + coos + _regionTail )
	position = ( Keyword("Position")("type") + 
		_commonSpaceItems + coos + _spatialTail )
	spaceSubPhrase = (positionInterval | allSky | circle | ellipse | box
		| polygon | convex | position).addParseAction(makeTree)

# spectral subphrase
	spectralSpec = (Suppress( Keyword("Spectral") ) + number)("spectral")
	_spectralTail = (Optional( spectralUnit("unit") ) + Optional( error ) + 
		Optional( resolution ) + Optional( pixSize ))
	spectralInterval = (Keyword("SpectralInterval")("type") +
		Optional( fillfactor ) + Optional( refpos ) + coos + 
		Optional( spectralSpec ) + _spectralTail)
	spectral = (Keyword("Spectral")("type") + Optional( refpos ) +
		number("coos") + _spectralTail)
	spectralSubPhrase = (spectralInterval | spectral ).addParseAction(
		makeTree)

# redshift subphrase
	redshiftType = Regex("VELOCITY|REDSHIFT")("redshiftType")
	redshiftSpec = (Suppress( Keyword("Redshift") ) + number)("redshift")
	dopplerdef = Regex("OPTICAL|RADIO|RELATIVISTIC")("dopplerdef")
	_redshiftTail = ( Optional( redshiftUnit("unit") ) +
		Optional( error ) + Optional( resolution ) + Optional( pixSize ))
	redshiftInterval = (Keyword("RedshiftInterval")("type") + 
		Optional( fillfactor ) + Optional( refpos ) + 
		Optional( redshiftType ) + Optional( dopplerdef ) +
		coos + Optional( redshiftSpec ) + _redshiftTail)
	redshift = (Keyword("Redshift")("type") + Optional( refpos ) +
		Optional( number )("coos") + Optional( redshiftType ) +
		Optional( dopplerdef ) + _redshiftTail)
	redshiftSubPhrase = (redshiftInterval | redshift ).addParseAction(
		makeTree)

# top level
	stcsPhrase = (Optional( timeSubPhrase )("time") +
		Optional( spaceSubPhrase )("space") +
		Optional( spectralSubPhrase )("spectral") +
		Optional( redshiftSubPhrase )("redshift") ) + StringEnd()

	return dict((n, v) for n, v in locals().iteritems() if not n.startswith("_"))


def enableDebug(syms, debugNames=None):
	if not debugNames:
		debugNames = syms
	for name in debugNames:
		ob = syms[name]
		ob.setDebug(True)
		ob.setName(name)


class CachedGetter(object):
	def __init__(self, getter):
		self.cache, self.getter = None, getter
	
	def __call__(self):
		if self.cache is None:
			self.cache = self.getter()
		return self.cache

getGrammar = CachedGetter(lambda: getSymbols())


def getCST(literal):
	tree = makeTree(getGrammar()["stcsPhrase"].parseString(literal))
	addDefaults(tree)
	return tree


if __name__=="__main__":
	syms = getSymbols()
	enableDebug(syms)
	print makeTree(syms["circle"].parseString(
		"Circle FK4 TOPOCENTER", parseAll=True))
