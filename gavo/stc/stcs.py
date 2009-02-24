"""
Parsing and generating STC/S
"""

import copy

from pyparsing import (Word, Literal, Optional, alphas, CaselessKeyword,
		ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,
		Suppress, Keyword, Forward, QuotedString, Group, printables, nums,
		CaselessLiteral, ParseException, Regex, sglQuotedString, alphanums,
		dblQuotedString, White, ParseException)

from gavo.stc.common import *
from gavo.stc.dm import STC
from gavo.utils import stanxml

class AComputedDefault(object):
	"""A sentinel for computed default values.
	"""
	pass


# STC/S spatial flavors, with dimensions and stc flavors
stcsFlavors = {
	"SPHER2": (2, "SPHERICAL"),
	"SPHER3": (3, "SPHERICAL"),
	"UNITSPHERE": (3, "UNITSPHERE"),
	"CART1": (1, "CARTESIAN"),
	"CART2": (2, "CARTESIAN"),
	"CART3": (3, "CARTESIAN"),
}


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

	def __call__(self, s, p, toks):
		children, atts = self.getChildAtts(toks)
		self._computeDefaults(children, atts)


class PositionIntervalsAction(PositionsAction):
	pass


def getSymbols():
	"""returns the root symbol for a grammar parsing STC-S into STC in xmlstan.
	"""

	_exactNumericRE = r"\d+(\.(\d+)?)?|\.\d+"
	exactNumericLiteral = Regex(_exactNumericRE)
	number = Regex(r"(?i)(%s)(E[+-]?\d+)?"%_exactNumericRE)

# basic productions common to most spatial specs
	fillfactor = (Suppress( Keyword("fillfactor") ) + number)("fillfactor")
	frame = (Regex("|".join(stcSpaceRefFrames)))("frame")
	refpos = (Regex("|".join(stcRefPositions)))("refpos")
	flavor = (Regex("|".join(stcsFlavors)))("flavor")
	spaceUnit = (Suppress(Keyword("unit")) + Regex(
		"deg|arcmin|arcsec|m|mm|km|AU|pc|kpc|Mpc"))("spaceUnit")
	_commonSpaceItems = (Optional( fillfactor ) + frame + Optional( refpos ) + 
		Optional( flavor ))

# basic productions for times and such.
	timescale = (Regex("|".join(stcTimeScales)))("timescale")
	jdLiteral = (Suppress( Keyword("JD") ) + exactNumericLiteral)
	mjdLiteral = (Suppress( Keyword("MJD") ) + exactNumericLiteral)
	isoTimeLiteral = Regex(r"\d\d\d\d-?\d\d-?\d\d(T\d\d:?\d\d:?\d\dZ?)?")
	nakedTime = (isoTimeLiteral | jdLiteral | mjdLiteral)
	timeUnit = (Keyword("unit") + Regex("yr|cy|s|d|a"))("unit")

# properties of most spatial specs
	position = Keyword("Position") + OneOrMore( number )
	error = Keyword("Error") + OneOrMore( number )
	resolution = Keyword("Resolution") + OneOrMore( number )
	size = Keyword("Size") + OneOrMore(number)
	pixSize = Keyword("PixSize") + OneOrMore(number)
	_spatialProps = (Optional( spaceUnit ) +
		Optional( error ) + Optional( resolution ) + Optional( size ) +
		Optional( pixSize ))

# the velocity sub-phrase
	velocityInterval = (Keyword("VelocityInterval") + number +
		OneOrMore( number ))
	velocity = Keyword("Velocity") + number
	_velocityPhrase = (Optional( velocityInterval ) +
		Optional( velocity ) ) # XXX incomplete

# stuff common to regions
	_spatialTail = _spatialProps + Optional( _velocityPhrase )
	_regionTail = position + _spatialTail
	limits = ZeroOrMore( number )

# times and time intervals
	timephrase = Suppress( Keyword("Time") ) + nakedTime
	_commonTimeItems = (	Optional( timeUnit ) + Optional( error ) + 
		Optional( resolution ) + Optional( pixSize ) )
	_intervalOpener = ( Optional( fillfactor ) + Optional( timescale ) +
		Optional( refpos ) )
	_intervalCloser = Optional( timephrase ) + _commonTimeItems

	timeInterval =  (Suppress( Keyword("TimeInterval") ) + _intervalOpener 
		+ ZeroOrMore(nakedTime)("intervalTimes") + _intervalCloser)
	startTime = (Suppress( Keyword("StartTime") ) + _intervalOpener + 
		nakedTime("startTime") + _intervalCloser)
	stopTime = (Suppress( Keyword("StopTime") ) + _intervalOpener + 
		nakedTime("stopTime") + _intervalCloser)
	time = (Suppress( Keyword("Time") ) + Optional( timescale ) + 
		Optional( refpos ) + Optional ( nakedTime("givenTime") ) + 
		_commonTimeItems)

# spatial things
	positionInterval = ( Keyword("PositionInterval") +
		_commonSpaceItems + limits + _spatialTail )
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
		("positionInterval", PositionIntervalsAction()),
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

getGrammar = CachedGetter(lambda: addActions(getSymbols()))


if __name__=="__main__":
	root, syms = getGrammar()
	#enableDebug(syms)
	print syms["timeInterval"].parseString(
		"TimeInterval 2000-01-01 2000-03-03 unit s", parseAll=True)[0].render()
