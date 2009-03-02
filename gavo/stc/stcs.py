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


def _assertGrammar(cond, msg, pos):
	if not cond:
		raise STCSParseError(msg, pos)


class NamedNode(object):
	"""a sentinel to wrap literals for later processing by ParseActions.
	"""
	def __init__(self, name, content):
		self.name = name
		self.content = content


class _Attr(object):
	"""wraps a future attribute for STCSGrammar.

	Basically, children destined to become their parent's attributes
	construct an attribute.
	"""
	def __init__(self, name, value):
		self.name, self.value = name, value

	@classmethod
	def getAction(cls, name, argNum=1):
		def make(s, pos, toks):
			return cls(name, toks[argNum])
		return make


def _demuxChildren(toks):
	"""returns a pair of real children and a dict of attributes from the
	embedded _Attr children.
	"""
	realChildren, attrs = [], {}
	for c in toks:
		if isinstance(c, _Attr):
			attrs[c.name] = c.value
		else:
			realChildren.append(c)
	return realChildren, attrs


def _demuxChildrenDict(toksDict):
	"""returns real children and attributes in the dict toksDict.
	"""
	realChildren, attrs = {}, {}
	for key, c in toksDict.iteritems():
		if isinstance(c, _Attr):
			attrs[key] = c.value
		else: # lists of attributes can't work, so it must be a real child.
			realChildren[key] = c
	return realChildren, attrs


def _sxToPA(stanElement):
	"""returns a parse action constructing an xmlstan Element (cf. _Attr).
	"""
	def parseAction(s, pos, toks):
		ch, at = _demuxChildren(toks)
		return stanElement(**at)[ch]
	return parseAction


def _constructFromZeroethChild(s, pos, toks):
	"""is a parse action for constructing an xmlstan Element named
	in the zeroeth token.
	"""
	elName, children = toks[0], toks[1:]
	ch, at = _demuxChildren(children)
	return getattr(STC, elName)(**at)[ch]


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


class ActionT(type):
	"""A metaclass for defaulting parse actions.

	Their primary purpose is to allow defaults to be set.  Of course,
	parsing the baroque constructs takes some special action as well.
	"""
	def __init__(cls, name, bases, dict):
		type.__init__(cls, name, bases, dict)
		cls._collectDefaults()
	
	def _collectDefaults(cls):
		cls.defaults = {}
		for name in dir(cls):
			if name.startswith("default_"):
				cls.defaults[name[8:]] = getattr(cls, name)


class Action(object):
	"""A basic defaulting parse action for pyparsing.

	In simple cases, it should be sufficient to just define rootElement
	(the later parent), and, if necessary, manipulate children and attrs
	in _mogrify.
	"""
	__metaclass__ = ActionT
	
	def getChildAtts(self, toks):
		children = self.defaults.copy()
		children.update(toks)
		return _demuxChildrenDict(children)

	def _mogrify(self, children, attrs):
		pass

	def __call__(self, s, p, toks):
		children, attrs = self.getChildAtts(toks)
		return self.rootElement(**attrs)[children]


class _TimeAction(Action):
	default_Timescale = STC.Timescale["nil"]
	default_unit = _Attr("unit", "s")

class StartTimeAction(_TimeAction):
	rootElement = STC.StartTime

class StopTimeAction(_TimeAction):
	rootElement = STC.StopTime
	
class TimeIntervalsAction(_TimeAction):
	default_fill_factor = _Attr("fill_factor", "1.0")
	rootElement = STC.TimeInterval
	def __call__(self, s, p, toks):
		# Most child nodes must end up in the children
		children, atts = self.getChildAtts(toks)
		myAtts = dict([("fill_factor", atts.pop("fill_factor"))])
		times = children.pop("intervalTimes", [])
		prototype = self.rootElement(**myAtts)
		protoStart = STC.StartTime(**atts)[children.values()]
		protoStop = STC.StopTime(**atts)[children.values()]
		return _makeIntervals(times, prototype, protoStart, protoStop)
	

class PositionsAction(Action):
	"""An abstract action setting positionsal defaults.
	"""
	default_frame = STC.UNKNOWNFrame
	default_refpos = STC.UNKNOWNRefPos
	default_flavor = AComputedDefault
	default_unit = AComputedDefault
	default_fill_factor = "1.0"

	flavorTranslations = {
		"SPHER2": (STC.SPHERICAL, 2),
		"SPHER3": (STC.SPHERICAL, 3),
		"CART1": (STC.CARTESIAN, 1),
		"CART2": (STC.CARTESIAN, 2),
		"CART3": (STC.CARTESIAN, 3),
		"UNITSPHER": (STC.UNITSPHERE, 3),
	}

	def _computeDefaults(self, children, atts):
		if children["flavor"] is AComputedDefault:
			if isinstance(self, Convex):
				children["flavor"] = "UNITSPHER"
			else:
				children["flavor"] = "SPHER2"
		if atts["unit"] is AComputedDefault:
			if children["flavor"].startswith("SPHER"):
				atts["unit"] = "deg"
			elif children["flavor"].startswith("CART"):
				atts["unit"] = "m"
			elif children["flavor"].startswith("GEO"):
				atts["unit"] = "deg deg m"
			else:
				atts["unit"] = None
		flavor, self.nDim = self.flavorTranslations[children.pop("flavor")]
		children["coordFrame"] = STC.SpaceFrame[children.pop("frame"),
			flavor(coord_naxes=self.nDim),
			children.pop("refpos")]
			

	def __call__(self, s, p, toks):
		children, atts = self.getChildAtts(toks)
		self._computeDefaults(children, atts)


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

# the velocity sub-phrase
	velocityInterval = (Keyword("VelocityInterval") + number +
		OneOrMore( number ))
	velocity = Keyword("Velocity") + number
	_velocityPhrase = (Optional( velocityInterval ) +
		Optional( velocity ) ) # XXX incomplete

# properties of most spatial specs
	positionSpec = Suppress( Keyword("Position") ) + OneOrMore( number )
	error = Suppress( Keyword("Error") ) + OneOrMore( number )
	resolution = Suppress( Keyword("Resolution") ) + OneOrMore( number )
	size = Suppress( Keyword("Size") ) + OneOrMore(number)
	pixSize = Suppress( Keyword("PixSize") ) + OneOrMore(number)
	_spatialProps = (Optional( spaceUnit("unit") ) +
		Optional( error("error") ) + Optional( resolution("resolution") ) + 
		Optional( size("size") ) + Optional( pixSize("pixSize") ))
	_spatialTail = _spatialProps + Optional( _velocityPhrase )
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
		Optional( redshiftSubPhrase )("redshift") )

	return dict((n, v) for n, v in locals().iteritems() if not n.startswith("_"))


def addActions(syms):
	for sym, action in [
		("fillfactor",   _Attr.getAction("fill_factor")),
		("flavor",       _constructFromZeroethChild),
		("frame",        _constructFromZeroethChild),
		("refpos",       _constructFromZeroethChild),
		("timeUnit",     _Attr.getAction("unit")),
		("spaceUnit",    _Attr.getAction("unit")),
		("timeInterval", TimeIntervalsAction()),
		("startTime",    StartTimeAction()),
		("stopTime",     StopTimeAction()),
		("jdLiteral",    _sxToPA(STC.JDTime)),
		("mjdLiteral",   _sxToPA(STC.MJDTime)),
		("isoTimeLiteral", _sxToPA(STC.ISOTime)),
		("timescale",    _sxToPA(STC.Timescale)),
		("timephrase",   lambda s,p,t: []), # XXX TODO: What shall I do with this?
		("limits",       lambda s,p,t: NamedNode("limits", t)),
		]:
		syms[sym].addParseAction(action)
	return None, syms


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


if __name__=="__main__":
	syms = getSymbols()
	#enableDebug(syms)
	print makeTree(syms["stcsPhrase"].parseString(
		"Circle ICRS 2 23 12 RedshiftInterval RADIO 0.1 0.2", parseAll=True))
