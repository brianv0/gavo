"""
This module contains macros and their infrastructure used while
importing data into GAVO.

A macro is some python code that modifies *one* row dictionary (as opposed
to row processors that are free to do whatever they like, including
discarding rows and creating new ones.  Therefore, they are less
intrusive and, given a choice, preferable.

Of course, ideally nothing of the sort should be necessary...

A macro basically is a thing that takes a dictionary with preterminals
and their values and changes it in whatever way it likes.  It is
configured through constructor arguments that are usually given in
a resource descriptor.
"""


import time
import os
import re
import math
import urlparse

from mx import DateTime
from mx.DateTime import ISO as DateTimeISO

import gavo
from gavo import logger
from gavo import utils
from gavo import coords
from gavo import config
from gavo import interfaces
from gavo import resourcecache
from gavo.parsing import parsehelpers
from gavo.parsing import resource
from gavo.web import siap

supportHtm = False

if supportHtm:
	import pyhtm

class Error(gavo.Error):
	pass


def _parseAssignments(assignments):
	"""returns a name mapping dictionary from a list of assignments.

	This is the preferred form of communicating a mapping from external names
	to field names in records to macros -- in a string that contains
	":"-seprated pairs seperated by whitespace, like "a:b  b:c", where
	the incoming names are leading, the desired names are trailing.

	If you need defaults to kick in when the incoming data is None, try
	_parseDestWithDefault in the client function.

	This function parses a dictionary mapping original names to desired names.

	>>> _parseAssignments("a:b  b:c")
	{'a': 'b', 'b': 'c'}
	"""
	return dict([(lead, trail) for lead, trail in
		[litPair.split(":") for litPair in assignments.split()]])


def _parseDestWithDefault(dest, defRe=re.compile(r"(\w+)\((.*)\)")):
	"""returns name, default from dests like bla(0).

	This can be used to provide defaulted targets to assignments parsed
	with _parseAssignments.
	"""
	mat = defRe.match(dest)
	if mat:
		return mat.groups()
	else:
		return dest, None


class Macro(parsehelpers.RowFunction):
	"""is an abstract base class for Macros.

	A Macro is RowFunction that modifies and/or adds preterminal values
	to row dictionaries (i.e. the output of a grammar).

	A Macro is used by calling it with the rowdict it is to change as
	its single argument.  Derived classes must define a _compute
	method that receives the RowFunction's arguments as keyword
	arguments.

	_compute methods work through side effects (well, changing
	the record...).  Any return values are discarded.

	Macros should, as a rule, be None-clear, i.e. shouldn't crap out
	on Nones as values (that can conceivably come from the grammar) but 
	just "propagate" the None in an appropriate way.  If there's no
	other way to cope, they should raise a gavo.Error and not let
	other exceptions escape.  It is not the macro's job to validate
	non-null constraints.
	"""
	pass


class EquatorialPositionConverter(Macro):
	"""is a macro that compute several derived quantities from 
	literal equatorial coordinates.

	Specifically, it generates alphaFloat, deltaFloat as well as
	c_x, c_y, c_z (cartesian coordinates of the intersection of the 
	direction vector with the unit sphere) and htmind (an HTM index
	for the position -- needs to be fleshed out a bit).

	TODO: Equinox handling (this will probably be handled through an
	optional arguments srcEquinox and destEquinox, both J2000.0 by default).
	
	Constructor arguments:

	* raFormat -- the literal format of Right Ascension.  By default,
	  a sexagesimal time angle is expected.  Supported formats include
		mas (RA in milliarcsecs), ...
	* decFormat -- as raFormat, only the default is sexagesimal angle.
	* sepChar (optional) -- seperator for alpha, defaults to whitespace
	
	If alpha and delta use different seperators, you'll have to fix
	this using preprocessing macros.

	Arguments: 
	 
	* alpha -- sexagesimal right ascension as time angle
	* delta -- sexagesimal declination as dms

	The field structure generated here is reflected in 
	__common__/positionfields.template.  If you change anything here,
	change it there, too.  And use that template when you use this macro.

	>>> m = EquatorialPositionConverter([("alpha", "alphaRaw", ""),
	... ("delta", "deltaRaw", "")])
	>>> r = {"alphaRaw": "00 02 32", "deltaRaw": "+45 30.6"} 
	>>> m(None, r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"]), str(r["c_x"]), str(r["c_y"])
	('0.633333333333', '45.51', '0.700741955529', '0.00774614323406')
	>>> m = EquatorialPositionConverter([("alpha", "alphaRaw", ""),
	... ("delta", "deltaRaw", ""),], sepChar=":")
	>>> r = {"alphaRaw": "10:37:19.544070", "deltaRaw": "+35:34:20.45713"}
	>>> m(None, r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"]), str(r["c_z"])
	('159.331433625', '35.5723492028', '0.581730502028')
	>>> r = {"alphaRaw": "4:38:54", "deltaRaw": "-12:7.4"}; m(None, r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"])
	('69.725', '-12.1233333333')
	>>> m = EquatorialPositionConverter([("alpha", "alphaRaw", ""), 
	... ("delta", "deltaRaw", "")], alphaFormat="mas", deltaFormat="mas")
	>>> r = {"alphaRaw": "5457266", "deltaRaw": "-184213905"}; m(None, r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"])
	('1.51590722222', '-51.1705291667')
	"""
	def __init__(self, argTuples=[], alphaFormat="hour", 
			deltaFormat="sexag", sepChar=None, *args, **kwargs):
		self.alphaFormat, self.deltaFormat = alphaFormat, deltaFormat
		self.sepChar = sepChar
		Macro.__init__(self, argTuples, *args, **kwargs)
		self.coordComputer = {
			"hour": self._timeangleToDeg,
			"sexag": self._dmsToDeg,
			"mas": lambda mas: float(mas)/3.6e6,
			"binary": lambda a: a,
		}

	name = "handleEquatorialPosition"

	def _compute(self, record, alpha, delta):
		if alpha is None or delta is None:
			alphaFloat, deltaFloat, c_x, c_y, c_z = [None]*5
		else:
			alphaFloat, deltaFloat, c_x, c_y, c_z = self._computeCoos(
				alpha, delta)
		record["alphaFloat"] = alphaFloat
		record["deltaFloat"] = deltaFloat
		record["c_x"] = c_x
		record["c_y"] = c_y
		record["c_z"] = c_z
		if supportHtm:
			record["htmid"] = pyhtm.lookup(alphaFloat, deltaFloat)

	def _timeangleToDeg(self, literal):
		return coords.timeangleToDeg(literal, self.sepChar)

	def _dmsToDeg(self, literal):
		return coords.dmsToDeg(literal, self.sepChar)

	def _convertCoo(self, literalForm, literal):
		return self.coordComputer[literalForm](literal)

	def _computeCoos(self, alpha, delta):
		alphaFloat = self._convertCoo(self.alphaFormat, alpha)
		deltaFloat = self._convertCoo(self.deltaFormat, delta)
		return (alphaFloat, deltaFloat)+tuple(coords.computeUnitSphereCoords(
			alphaFloat, deltaFloat))


class PMCombiner(Macro):
	"""is a macro that combines proper motions in RA and Dec to a total
	proper motion and position angle.

	It creates fields with the fixed names pm_total, angle_pm.  A field 
	definition could be:

	<Field dest="pm_total" source="pm_total" dbtype="real"
		tablehead="PM" description="Total proper motion" 
		unit="arcsec/yr"/>
	<Field dest="angle_pm" dbtype="real" source="angle_pm"
		unit="deg" tablehead="PA of PM"
		description="Position angle of total proper motion"/>

	Constructor Arguments:

	* alphaFactor, deltaFactor -- factors to multiply with in alpha and delta
	  to get to arcsecs/year.

	Arguments:

	* pmAlpha -- proper motion in RA
	* pmDelta -- proper motion in Declination

	Both arguments have to be angles as floats or float literals, with pmAlpha
	already multiplied with cos(delta).  Use other macros to convert fields if
	they don't have that format already.
	"""
	name = "combinePM"

	def __init__(self, argTuples=[], alphaFactor="1", 
			deltaFactor="1"):
		Macro.__init__(self, argTuples)
		self.alphaFactor, self.deltaFactor = float(alphaFactor), float(deltaFactor)
	
	def _compute(self, record, pmAlpha, pmDelta):
		if pmAlpha is None or pmDelta is None:
			tpm = pmpa = None
		else:
			pma = pmAlpha*self.alphaFactor
			pmd = pmDelta*self.deltaFactor
			tpm = math.sqrt(pma**2+pmd**2)
			pmpa = math.atan2(pma, pmd)*360/2/math.pi
		record["pm_total"] = tpm
		record["angle_pm"] = pmpa


def parsePercentExpression(literal, format):
	"""returns a dictionary of parts in the %-template format.

	format is a template with %<conv> conversions, no modifiers are
	allowed.  Each conversion is allowed to contain zero or more characters
	matched stingily.  Successive conversions without intervening literarls
	are very tricky and will usually not match what you want.  If we need
	this, we'll have to think about modifiers or conversion descriptions ("H
	is up to two digits" or so).

	This is really only meant as a quick hack to support times like 25:33.
	>>> r=parsePercentExpression("12,xy:33,","%a:%b,%c"); r["a"], r["b"], r["c"]
	('12,xy', '33', '')
	>>> r = parsePercentExpression("12,13,14", "%a:%b,%c")
	Traceback (most recent call last):
	Error: '12,13,14' cannot be parsed using format '%a:%b,%c'
	"""
	parts = re.split(r"(%\w)", format)
	newReParts = []
	for p in parts:
		if p.startswith("%"):
			newReParts.append("(?P<%s>.*?)"%p[1])
		else:
			newReParts.append(re.escape(p))
	mat = re.match("".join(newReParts)+"$", literal)
	if not mat:
		raise Error("'%s' cannot be parsed using format '%s'"%(literal, format))
	return mat.groupdict()


def parseTime(literal, format):
	"""returns some sort of DateTime object for literal parsed according
	to format.

	The formats legal here are documented in the TimeParser macro.
	"""
	if format=="!!secondsSinceMidnight":
		secs = float(literal)
		fullSecs = int(secs)
		hours = fullSecs/3600
		minutes = (fullSecs%3600)/60
		seconds = secs-hours*3600-minutes*60
		return DateTime.DateTimeDelta(0, hours, minutes, seconds)
	elif format=="!!decimalHours":
		rest, hours = math.modf(float(literal))
		rest, minutes = math.modf(rest*60)
		return DateTime.Time(int(hours), int(minutes), rest*60)
	elif format=="!!magic":
		return DateTimeISO.ParseTime(literal)
	else:
		# We can't really use prebuilt strptimes since times like 25:21:22.445
		# are perfectly ok in astronomy.
		partDict = parsePercentExpression(literal, format)
		return DateTime.DateTimeDelta(0, float(partDict.get("H", 0)),
			float(partDict.get("M", 0)), float(partDict.get("S", 0)))


class TimeParser(Macro):
	"""is a macro that converts some kind of time specification into the
	internal representation.

	Constructor Arguments:
	* destination -- the name of the result field (default: time)
	* format -- format of time using strptime(3)-compatible conversions
	  (default: "!!magic")

	The macro understands the special timeFormats !!secondsSinceMidnight,
	!!decimalHours., and !!magic (guess time format).

	Really, the only allowed conversions in format are H, M, and S, and
	they're not (yet) strptime-compatible (they rely on separator characters
	so far).  They do parse times like 25:13:56.9938, though.

	Argument:
	* time -- a string containing a time spec.  Null values and structured
	  times are copied to the destination.

	>>> m = TimeParser([("time", "t", "")])
	>>> r = {"t":"17:23:56.4567"};m(None, r);str(r["time"])
	'17:23:56.45'
	>>> r = {"t":None};m(None, r);str(r["time"])
	'None'
	>>> m=TimeParser([("time", "t", "")], timeFormat="%H-%M-%S", destination='t')
	>>> r = {"t":"00-23-56"};m(None, r);str(r["t"])
	'00:23:56.00'
	>>> r = {"t":"Rubbish"};m(None, r);str(r["t"])
	Traceback (most recent call last):
	Error: 'Rubbish' cannot be parsed using format '%H-%M-%S'
	"""
	name = "parseTime"

	def __init__(self, argTuples=[], destination="time",
			timeFormat="!!magic"):
		Macro.__init__(self, argTuples)
		self.timeFormat, self.destination = timeFormat, destination

	def _compute(self, record, time):
		if not isinstance(time, basestring):
			record[self.destination] = time
		else:
			record[self.destination] = parseTime(time, self.timeFormat)


class TimestampCombiner(Macro):
	"""is a macro that takes a date and a time in various formats
	and produces a mx.DateTime object from it.

	Use its result like
	<Field dest="someTimestamp" dbtype="timestamp" source="myTimestamp"
		literalForm="do not touch"/>

	(where myTimestamp was the value of destination).

	Constructor Arguments:
	* destination -- the name of the field the result is to be put in
	  (default: timestamp)
	* dateFormat -- format of date using strptime(3)-compatible conversions
	  (default: "%d.%m.%Y")
	* timeFormat -- format of time using strptime(3)-compatible conversions
	  (default: "%H:%M:%S")

	The macro understands the special dateFormat !!julianEp (stuff like 1980.89)
	and the time formats mentioned in parseTime's doc.

	Arguments:

	* date -- a date literal
	* time -- a time literal

	>>> m = TimestampCombiner([("date", "date", ""), ("time", "time", "")],
	... destination="stamp")
	>>> rec = {"date": "4.6.1969", "time": "4:22:33"}
	>>> m(None, rec)
	>>> rec["stamp"].strftime()
	'Wed Jun  4 04:22:33 1969'
	>>> m = TimestampCombiner([("date", "date", ""), ("time", "time", "")],
	... timeFormat="!!secondsSinceMidnight")
	>>> rec = {"date": "4.6.1969", "time": "32320"}
	>>> m(None, rec); rec["timestamp"].strftime()
	'Wed Jun  4 08:58:40 1969'
	>>> m = TimestampCombiner([("date", "date", ""), ("time", "time", "")],
	... dateFormat="!!julianEp", timeFormat="%M-%H")
	>>> rec = {"date": "1969.0027378508", "time": "30-5"}; m(None,rec)
	>>> rec['timestamp'].strftime()
	'Thu Jan  2 05:30:00 1969'
	>>> rec = {"date": "1969.0", "time": "30-27"};m(None,rec)
	>>> rec['timestamp'].strftime()
	'Thu Jan  2 03:30:00 1969'
	"""
	name = "combineTimestamps"

	def __init__(self, argTuples=[], destination="timestamp",
			dateFormat="%d.%m.%Y", timeFormat="%H:%M:%S"):
		Macro.__init__(self, argTuples)
		self.destination = destination
		self.timeFormat, self.dateFormat = timeFormat, dateFormat

	def _processDate(self, literal, format):
		if format=="!!julianEp":
			rest, year = math.modf(float(literal))
			delta = DateTime.DateTimeDeltaFromSeconds(rest*365.25*86400)
			return DateTime.DateTime(int(year))+delta
		return DateTime.Date(*time.strptime(literal, format)[:3])

	def _compute(self, record, date, time):
		timeObj = parseTime(time, self.timeFormat)
		dateObj = self._processDate(date, self.dateFormat)
		record[self.destination] = dateObj+timeObj


class MidtimeComputer(Macro):
	"""is a macro that takes two timestamps and returns the midpoint 
	between them.

	Constructor Argument:
	* destination -- the name of the field the result is to be put in
	  (default: dateObs)

	The macro expects real datetime objects that usually result from earlier
	macro invocations.

	Arguments:

	* dt1 -- an (earlier) datetime
	* dt2 -- a (later) datetime

	>>> rec={"start": DateTime.DateTime(2007, 10, 23, 12, 20, 30),
	...   "end": DateTime.DateTime(2007, 10, 23, 13, 20, 30)}
	>>> m = MidtimeComputer([("dt1", "start", ""), ("dt2", "end", "")])
	>>> m(None, rec);rec["dateObs"].strftime()
	'Tue Oct 23 12:50:30 2007'
	"""
	name = "computeMidtime"

	def __init__(self, argTuples=[], destination="dateObs"):
		Macro.__init__(self, argTuples)
		self.destination = destination

	def _compute(self, record, dt1, dt2):
		record[self.destination] = dt1+(dt2-dt1)/2


class AngleParser(Macro):
	"""is a macro that converts the various forms angles might be encountered
	to degrees.

	Constructor Arguments:

	* format -- one of hms, dms, fracHour
	* destination -- the field the processed value should be left in

	Arguments:

	* val -- the literal to be converted.

	>>> m = AngleParser([("val", "d", "")], format="hms", destination="p")
	>>> rec = {"d":"23 59 59.95"}; m(None, rec); "%s"%rec["p"]
	'359.999791667'
	>>> m = AngleParser([("val", "d", "")], format="dms", destination="p")
	>>> rec = {"d":"-20 31 05.12"}; m(None, rec); "%10.5f"%rec["p"]
	' -20.51809'
	>>> m = AngleParser([("val", "d", "")], format="fracHour", 
	...   destination="p")
	>>> rec = {"d":"21.0209556"}; m(None, rec); "%010.6f"%rec["p"]
	'315.314334'
	"""
	name = "parseAngle"

	converterTable = {
		"dms": coords.dmsToDeg,
		"hms": coords.timeangleToDeg,
		"fracHour": coords.fracHoursToDeg,
	}

	def __init__(self, argTuples=[], destination="angle",
			format="hms"):
		Macro.__init__(self, argTuples)
		self.converter = self.converterTable[format]
		self.destination = destination

	
	def _compute(self, record, val):
		if val is None:
			record[self.destination] = None
		else:
			record[self.destination] = self.converter(val)


class ValueGetter(Macro):
	"""is a macro that just enters a value into the rowdict.

	This is mainly useful to get @-expanded values into the rowdict
	for macros that want to read from fields.  It's also more convenient
	than interpolateStrings and friends to set constants.

	Construction Arguments:

	* destination -- the name of the field the value should end up in

	Arguments:

	* value -- the value to be added

	>>> v = ValueGetter(argTuples=[("value", "", "inserted")], 
	...   destination="constant")
	>>> r = {"bla": "foo"}
	>>> v(None, r)
	>>> r["constant"]
	'inserted'
	"""
	name = "enterValue"

	def __init__(self, argTuples=[], destination=None):
		Macro.__init__(self, argTuples)
		self.destination = destination
	
	
	def _compute(self, record, value):
		record[self.destination] = value


class ValueCatter(Macro):
	"""is a macro that concatenates values from various rows and puts
	the resulting value in destinationRow.

	Null values are ignored.  If all source elements are None, the
	destination will be None.

	Construction Arguments:
	
	* joiner -- a string used to glue the individual values together.  Optional,
	  defaults to the empty string.
	* destination -- a name under which the concatenated value should be stored
	* sources -- a comma seperated list of source field names

	concat takes no arguments.

	>>> v = ValueCatter(joiner="<>", argTuples=[],
	... sources="src1,src2,src3", destination="cat")
	>>> r = {"src1": "opener", "src2": "catfood", "src3": "can"}
	>>> v(None, r)
	>>> r["cat"]
	'opener<>catfood<>can'
	"""
	name = "concat"

	def __init__(self, argTuples=[], joiner="", destination="",
			sources=""):
		Macro.__init__(self, argTuples)
		self.joiner, self.destination = joiner, destination
		self.sources = self._parseSources(sources)

	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _compute(self, record):
		items = [record[src] for src in self.sources
				if record[src] is not None]
		record[self.destination] = None
		if items:
			record[self.destination] = self.joiner.join(items)


class NullValuator(Macro):
	"""is a macro that maps a certain literal to None.
	
	In general, this isn't necessary since you can define null values in fields.
	However, when another macro needs Nones to signify null values, you need
	this macro, because macros are applied before fields are even looked at.

	Constructor Argument:

	* nullvalue -- the value that should be mapped to Null
	* colName -- the name of the column to operate on

	mapToNone takes no arguments.

	>>> n = NullValuator(colName="foo", nullvalue="EMPTY")
	>>> r = {"foo": "bar", "baz": "bang"}
	>>> n(None, r); r["foo"]
	'bar'
	>>> r["foo"] = "EMPTY"
	>>> n(None, r); print r["foo"]
	None
	"""
	name = "mapToNone"

	def __init__(self, argTuples=[], nullvalue="NULL", 
			colName=""):
		Macro.__init__(self, argTuples)
		self.nullvalue = nullvalue
		self.colName = colName

	def _compute(self, record):
		if record[self.colName]==self.nullvalue:
			record[self.colName] = None


class ValueMapper(Macro):
	"""is a macro that translates vaules via a utils.NameMap
	
	Construction arguments:

	* sourceName -- an inputsDir-relative path to the NameMap source file,
	* logFailures (optional) -- if somehow true, non-resolved names will 
	  be logged
	* destination -- the field the mapped value should be written into.

	Argument:

	* value -- the value to be mapped.

	If an object cannot be resolved, a null value is entered (i.e., you
	shouldn't get an exception out of this macro but can weed out "bad"
	records through notnull-conditions later if you wish).

	Destination may of course be the source field (though that messes
	up idempotency of macro expansion, which shouldn't usually hurt).

	The format of the mapping file is

	<target key><tab><source keys>

	where source keys is a whitespace-seperated list of values that should
	be mapped to target key (sorry the sequence's a bit unusual).

	A source key must be encoded quoted-printable.  This usually doesn't
	matter except when it contains whitespace (a blank becomes =20) or equal
	signs (which become =3D).
	"""
	name = "mapValue"

	def __init__(self, argTuples=[], sourceName="", 
			destination="", logFailures=False, failuresAreNone=True):
		Macro.__init__(self, argTuples)
		self.map = utils.NameMap(os.path.join(config.get("inputsDir"), sourceName))
		self.logFailures = logFailures
		self.failuresAreNone = failuresAreNone
		self.destination = destination

	def _compute(self, record, value):
		try:
			record[self.destination] = self.map.resolve(str(value))
		except KeyError:
			if self.logFailures:
				gavo.logger.warning("Name %s could not be mapped"%value)
			if self.failuresAreNone:
				record[self.destination] = None
			else:
				raise


class StringInterpolator(Macro):
	"""is a macro that exposes %-type string interpolations.
	
	Constructor arguments:

	* destination: name of the field the result should be put in
	* format: a format with %-conversions (see the python manual.
	  Note, however, that rowdict values usually are strings).
	* sources: a comma-seperated list of preterminal names.  The
	  values of these preterminals constitute the tuple to fill
	  the conversions from.
	
	Clearly, you have to have as many items in sources as you have conversions 
	in format.  Non-existing keys are substituted by the empty string.

	StringInterpolators have no runtime arguments.

	>>> s = StringInterpolator([], destination="baz",
	... format="no %s in %s", sources="bar,foo")
	>>> r = {"foo": "42", "bar": "23"}
	>>> s(None, r); r["baz"]
	'no 23 in 42'
	"""
	name = "interpolateStrings"

	def __init__(self, argTuples=[], destination="",
			format="", sources=""):
		Macro.__init__(self, argTuples)
		self.sources = self._parseSources(sources)
		self.format, self.destination = format, destination
	
	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _compute(self, record):
		try:
			record[self.destination] = self.format%tuple(record.get(src, "")
				for src in self.sources)
		except (TypeError, ValueError), msg:
			raise Error("interpolateStrings macro failure: %s"%msg)


class ReSubstitutor(Macro):
	r"""is a macro that exposes re.sub.
	
	In short, you can substitue PCRE-compatible regular expressions in a
	string, complete with backreferences and all.  Don't overdo it.

	Constructor arguments:

	* destination -- the name of the field the result should be put in
	* srcRe -- the source regular expression
	* destRe -- the replacement pattern

	Argument:

	* data -- the value the re should be applied to

	>>> m = ReSubstitutor([("data", "broken", "")], 
	... srcRe=r"(.) \(([^)]*)\)", destRe=r"\2 \1", destination="fixed")
	>>> r = {"broken": "r (Gunn)"}
	>>> m(None, r); r["fixed"]
	'Gunn r'
	>>> r = {"broken": "Any ol' junk"}
	>>> m(None, r); r["fixed"]
	"Any ol' junk"
	"""
	name = "subsRe"
	def __init__(self, argTuples=[], destination="",
			srcRe="", destRe=""):
		Macro.__init__(self, argTuples)
		self.destination = destination
		self.srcPat, self.destRe = re.compile(srcRe), destRe
	
	def _compute(self, record, data):
		if data is None:
			record[self.destination] = None
		else:
			record[self.destination] = self.srcPat.sub(self.destRe, data)


class ProductValueCollector(Macro):
	"""is a macro that provides all values requried for the product table.
	
	See the documentation on the product interface.

	Arguments:
	* prodtblKey -- the value that identifies the product in the product table
	  (usually, but not always, it's the path to the product)
	* prodtblOwner -- the owner of the record
	* prodtblEmbargo -- date when the resource will become freely accessible
	* prodtblPath -- path to the product
	* prodtblFsize -- size of the product (optional)
	"""
	name = "setProdtblValues"

	def _compute(self, record, prodtblKey, prodtblOwner, prodtblEmbargo,
			prodtblPath, prodtblFsize=None):
		for keyName in ["prodtblKey", "prodtblOwner", "prodtblEmbargo", 
				"prodtblPath", "prodtblFsize"]:
			record[keyName] = locals()[keyName]


class LinearMapper(Macro):
	"""is a macro that applies a linear mapping to floating point data.

	The result is a float, computed as factor*data+offset

	Constructor arguments:

	* factor
	* offset
	* destination -- the name of the field the result should be put in.

	Argument:

	* val -- the value to be mapped; any blanks are removed before trying
	  an interpretation as float literal.  It is an error to pass in
	  non-NULL values that don't work as float literals.

	>>> m = LinearMapper([("val", "src", "")], destination="dest",
	... factor="7.4", offset="33")
	>>> rec = {"src": "22.3"}; m(None, rec)
	>>> str(rec["dest"])
	'198.02'
	"""
	name = "linearMap"

	def __init__(self, argTuples=[], destination="",
			factor=0, offset=0):
		Macro.__init__(self, argTuples)
		self.destination = destination
		self.factor, self.offset = float(factor), float(offset)
	
	def _compute(self, record, val):
		if val is None:
			record[self.destination] = None
		else:
			if isinstance(val, basestring):
				val = val.replace(" ", "")
			record[self.destination] = self.factor*float(val)+self.offset


class SimbadResolver(Macro):
	"""is a macro that resolves identifiers to simbad positions.

	This code caches query results (positive as well as negative ones) in
	cacheDir.  To avoid flooding simbad with repetetive requests, it
	raises an error if this directory is not writable.

	It leaves J2000.0 float positions simbadAlpha and simbadDelta in 
	the record.

	Constructor Arguments:

	* ignoreUnknowns -- don't raise an exception if the object can't be
	  resolved.
	
	Argument:

	* identifier -- something Simbad can resolve.  See macros like 
	  interpolateString to morph your inputs.
	"""
	name = "resolveObject"

	def __init__(self, argTuples=[], ignoreUnknowns=False):
		self.ignoreUnknowns = ignoreUnknowns
		Macro.__init__(self, argTuples)
		from gavo.simbadinterface import Sesame
		self.resolver = Sesame(saveNew=True)
	
	def _compute(self, record, identifier):
		try:
			simbadData = self.resolver.query(identifier)
		except KeyError:
			if not self.ignoreUnknowns:
				raise gavo.Error("resolveObject macro could not resolve object"
					" %s."%identifier)
		else:
			record["simbadAlpha"] = simbadData.get("jradeg")
			record["simbadDelta"] = simbadData.get("jdedeg")


class MxDateParser(Macro):
	"""is a macro that can insert parts of mxDateTime instances into records.

	Constructor Argument:

	* assignments -- a string specifiying what should go where.

	The assignments is a whitespace-seperated sequence of pairs of
	names seperated by colons.  A pair day:startDay, e.g., says that
	the attribute day of the DateTime instance should go into the
	startDay field of the record.  Available fields include (at least):
	year, month, day, hour, minute, second, jdn (the julian date).

	Argument:

	* date -- the date that should be parsed, either an mxDateTime instance
	  from a previous macro application or a string containing something
	  mxDateTime.Parse can cope with.
	
	>>> m = MxDateParser([("date", "startDate", "")], assignments=
	...   "day:startDay month:startMonth")
	>>> r = {"startDate": "2007-07-16"}
	>>> m(None, r); r
	{'startDate': '2007-07-16', 'startDay': 16, 'startMonth': 7}
	>>> m = MxDateParser([("date", "", "1067-10-12 13:12:00")], 
	... assignments="day:day hour:hour")
	>>> r = {}; m(None, r); r
	{'day': 12, 'hour': 13}
	>>> m = MxDateParser([("date", "foo", "")], 
	... assignments="jdn:jd")
	>>> r = {"foo": DateTime.DateTime(2038, 12, 12, 11)}; m(None, r); str(r["jd"])
	'2465769.95833'
	"""
	name = "parsemxdate"

	def __init__(self, argTuples=[], assignments="year:year"):
		Macro.__init__(self, argTuples)
		self.assignments = _parseAssignments(assignments)
	
	def _compute(self, record, date):
		if date is None:
			for fieldName in self.assignments.itervalues():
				record[fieldName] = None
			return

		if isinstance(date, basestring):
			date = DateTime.Parser.DateTimeFromString(date)
		for attName, fieldName in self.assignments.iteritems():
			record[fieldName] = getattr(date, attName)


class SimpleQuerier(Macro):
	"""is a macro that does a simple select query on a database and
	stuffs the resulting values (in whatever type they come) into
	the record.
	
	Constructor Arguments

	* items -- an assignments list like in MxDateParser; here, before
	  the colon are the column names in the db.  You can give a default
    for the item in parentheses; it's always a string, though.
	* table -- the table to query
	* column -- the column to run the test against

	Argument:

	* val -- the value that column must be equal to in the query.

	You'd use this macro like this:

	<Macro name="simplequery" items="alpha:cat_alpha delta:cat_delta rv:rv(0)"
	    table="fk5.data" column="localid">
	  <arg name="val" source="star"/>
	</Macro>

	If your record were {"star": "8894"}, we'd gernerate a query

	SELECT cat_alpha, cat_delta FROM fk5.data where localid='8894',

	and assign the first item of the first response row to alpha,
	and the second to delta.
	"""
	name = "simplequery"

	def __init__(self, argTuples=[], assignments=None,
			table=None, column=None):
		from gavo import sqlsupport
		try:
			self.querier = sqlsupport.SimpleQuerier()
		except config.Error:
			# we probably have no db connectivity.  Don't bring down the
			# whole program without knowing we actually need it -- raise an error
			# as soon as someone tries to use the connection
			class Raiser:
				def __getattr__(self, name):
					raise gavo.Error("No db connectivity available.")
			self.querier = Raiser()
		Macro.__init__(self, argTuples)
		self.assignments = _parseAssignments(assignments)
		self.table, self.column = table, column
	
	def _compute(self, record, val):
		from gavo import sqlsupport
		dbNames, recNames = self.assignments.keys(), self.assignments.values()
		query = "SELECT %s FROM %s WHERE %s=%%(val)s"%(
			", ".join(dbNames), self.table, self.column)
		try:
			res = self.querier.query(query, {"val": val}).fetchall()[0]
			for name, resVal in zip(recNames, res):
				name, default = _parseDestWithDefault(name)
				if resVal is None:
					record[name] = default
				else:
					record[name] = resVal
		except IndexError:
			gavo.raiseTb(gavo.ValidationError, "The item %s didn't match"
				" any data.  Since this data is required for further"
				" operations, I'm giving up"%val, self.getArgument("val"))
		except sqlsupport.DbError, msg:
			self.querier.close()
			self.querier = sqlsupport.SimpleQuerier()
			gavo.raiseTb(gavo.ValidationError, "Internal error (%s)"%
				sqlsupport.encodeDbMsg(msg), self.getArgument("val"))


class BboxSiapFieldsComputer(Macro):
	"""is a macro that computes fields for the bboxSiap interface.

	It takes no arguments but expects WCS-like keywords in record, i.e.,
	CRVAL1, CRVAL2 (interpreted as float deg), CRPIX1, CRPIX2 (pixel
	corresponding to CRVAL1, CRVAL2), CUNIT1, CUNIT2 (pixel scale unit,
	we bail out if it isn't deg and assume deg when it's not present), CDn_n 
	(the transformation matrix; substitutable by CDELTn), NAXISn 
	(the image size).

	It leaves the primaryBbbox, secondaryBbox (see siap.py for an explanation),
	centerDelta, centerAlpha, nAxes, pixelSize, pixelScale and imageFormat.

	For now, we only implement a tiny subset of WCS.  I guess we should
	at some point wrap wcslib or something similar.

	Records without or with insufficient wcs keys are furnished with
	all-NULL wcs info.

	>>> m = BboxSiapFieldsComputer()
	>>> r = {"NAXIS1": "100", "NAXIS2": "150", "CRVAL1": "138", "CRVAL2": 53,
	...   "CRPIX1": "70", "CRPIX2": "50", "CUNIT1": "deg", "CUNIT2": "deg",
	...   "CD1_1": 0.0002, "CD1_2": 3e-8, "CD2_1": 3e-8, "CD2_2": "-0.0002",
	...   "NAXIS": 2, "CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP', 
	...   "LONPOLE": 180.,}
	>>> m(None, r); r["primaryBbox"], r["secondaryBbox"]
	(Box((138.01,53.01), (137.977,52.98)), None)
	>>> r["CRVAL1"] = 0
	>>> m(None, r); r["primaryBbox"]
	Box((360,53.01), (359.977,52.98))
	>>> r["secondaryBbox"]
	Box((0.00996989,53.01), (0,52.98))
	>>> "%.4f %.4f"%(r["centerAlpha"], r["centerDelta"])
	'359.9935 52.9949'
	"""
	name = "computeBboxSiapFields"

	wcskeys = ["primaryBbox", "secondaryBbox", "centerAlpha", "centerDelta",
		"nAxes",  "pixelSize", "pixelScale", "imageFormat", "wcs_projection",
		"wcs_refPixel", "wcs_refValues", "wcs_cdmatrix"]

	class PixelGauge(object):
		"""is a container for information about pixel sizes.

		It is constructed with an astWCS.WCS instance and an (x, y)
		pair of pixel coordinates that should be close to the center 
		of the frame.
		"""
		def __init__(self, wcs, centerPix):
			centerPos = wcs.pix2wcs(*centerPix)
			offCenterPos = wcs.pix2wcs(centerPix[0]+1, centerPix[1]+1)
			self._computeCDs(centerPos[0]-offCenterPos[0], 
				centerPos[1]-offCenterPos[1])

		def _computeCDs(self, da, dd):
			dAngle = math.atan2(da, dd)
			self.cds = (
				(da*math.cos(dAngle), da*math.sin(dAngle)),
				(dd*math.sin(dAngle), dd*math.cos(dAngle)))

		def getPixelScales(self):
			"""returns the pixel sizes in alpha and delta in degrees.
			"""
			aVec, dVec = self.cds
			return (math.sqrt(aVec[0]**2+aVec[1]**2),
				math.sqrt(dVec[0]**2+dVec[1]**2))

	def _compute(self, record):
		def seqAbs(seq):
			return math.sqrt(sum(float(v)**2 for v in seq))
		
		wcs = coords.getWCS(record)
		record["imageFormat"] = "image/fits"
		try:
			record["primaryBbox"], record["secondaryBbox"] = siap.splitCrossingBox(
				coords.getBboxFromWCSFields(wcs))
			record["centerAlpha"], record["centerDelta"
				] = coords.getCenterFromWCSFields(wcs)
			record["nAxes"] = int(record["NAXIS"])
			axeInds = range(1, record["nAxes"]+1)
			assert len(axeInds)==2   # probably not exactly necessary
			dims = tuple(int(record["NAXIS%d"%i]) 
				for i in axeInds)
			pixelGauge = self.PixelGauge(wcs, (dims[0]/2., dims[1]/2.))
			record["pixelSize"] = dims
			record["pixelScale"] = pixelGauge.getPixelScales()

			record["wcs_projection"] = record.get("CTYPE1")
			if record["wcs_projection"]:
				record["wcs_projection"] = record["wcs_projection"][5:8]
			record["wcs_refPixel"] = (wcs.WCSStructure.xref, wcs.WCSStructure.yref)
			record["wcs_refValues"] = (wcs.WCSStructure.xrefpix, 
				wcs.WCSStructure.yrefpix)
			record["wcs_cdmatrix"] = pixelGauge.cds[0]+pixelGauge.cds[1]
		except (KeyError, AttributeError), msg:
			for key in self.wcskeys:
				record[key] = None


class SiapMetaSetter(ProductValueCollector):
	"""is a macro that sets siap meta *and* product table fields.
	
	This is common stuff for all SIAP implementations.

	Arguments: 
	* siapTitle
	* siapInstrument
	* siapObsDate,
	* siapImageFormat (defaults to image/fits)
	* siapBandpassId
	* any arguments of setProdtblValues
	"""
	name = "setSiapMeta"

	targetKeys = {
		"siapTitle": "imageTitle", 
		"siapInstrument": "instId", 
		"siapObsDate": "dateObs",
		"siapImageFormat": "imageFormat",
		"siapBandpassId": "bandpassId",}

	def _compute(self, record,  **kwargs):
		if not kwargs.has_key("siapImageFormat"):
			kwargs["siapImageFormat"] ="image/fits",
		prodtblArgs = {}
		for key, value in kwargs.iteritems():
			if key in self.targetKeys:
				record[self.targetKeys[key]] = value
			else:
				prodtblArgs[key] = value
		try:
			ProductValueCollector._compute(self, record, **prodtblArgs)
		except TypeError, msg:
			raise gavo.Error("Invalid argument for setSiapMeta; %s"%str(msg))


class FloatExpressionEvaluator(Macro):
	"""is a macro that computes simple float expressions.

	Any argument may be None, in which case the Macro evaluates to None.
	To map arbitrary literals to None, use the mapToNone macro.

	Constructor Arguments

	* expression -- a python expression with operands of the form arg<num>+
	* destination -- the name of the field the result is to be entered in

	Arguments:

	* arg1...arg<n> -- the operands mentioned in the expression.

	You'd use this macro like this:

	<Macro name="floatExpression" expression="arg1*arg2" 
			destination="seeingSecs">
		<arg name="arg1" source="SEEING"/>
		<arg name="arg2" source="CCDSCALE"/>
	</Macro>

	>>> m = FloatExpressionEvaluator([("arg1", "foo", ""), ("arg2", "bar", "")],
	...   expression="arg1+arg1**arg2", destination="res")
	>>> r = {"foo": "3", "bar": 2}; m(None, r); r["res"]
	12.0
	>>> r = {"foo": "3", "bar": None}; m(None, r); print r["res"]
	None
	>>> m = FloatExpressionEvaluator([("arg1", "foo", ""),],
	...   expression="arg1+arg1**arg2", destination="res")
	>>> r = {"foo": "3"}; m(None, r); print r["res"]
	Traceback (most recent call last):
	Error: Variable 'arg2' required by expression arg1+arg1**arg2 was not passed to macro.
	"""
	name = "floatExpression"

	def __init__(self, argTuples=[], expression="arg1", destination="res"):
		self.expression, self.destination = expression, destination
		Macro.__init__(self, argTuples)

	def _compute(self, record, **kwargs):
		if None in kwargs.values():
			record[self.destination] = None
			return
		try:
			expr = re.sub(r"arg\d+", lambda mat: repr(float(kwargs[mat.group(0)])),
				self.expression)
		except KeyError, msg:
			raise gavo.Error("Variable %s required by expression %s"
				" was not passed to macro."%(str(msg), self.expression))
		record[self.destination] = eval(expr)


class URLChopper(Macro):
	"""is a macro that cuts off http://host from an URL, yielding something
	site-relative.

	Constructor Argument: 
	
	* destination -- name of the field the result should be stored in

	Argument:

	* val -- the value to process

	>>> m = URLChopper([("val", "aU")], destination="aU")
	>>> r = {"aU": "http://foo.bar/baz/quuz?par=7"}; m(None, r); r["aU"]
	'/baz/quuz?par=7'
	>>> r = {"aU": "/baz/quuz?par=7"}; m(None, r); r["aU"]
	'/baz/quuz?par=7'
	"""
	name = "makeHostlessHTTP"

	def __init__(self, argTuples=[], destination="res"):
		self.destination = destination
		Macro.__init__(self, argTuples)

	def _compute(self, record, val):
		record[self.destination] =  urlparse.urlunparse(
			("", "")+urlparse.urlparse(val)[2:])


def compileMacro(name, code):
	"""returns a macro of name name and code as _compute body.
	"""
	code = utils.fixIndentation(code, "			")
	macCode = """class Newmacro(Macro):
		name = "%(name)s"

		def _compute(self, record):
%(code)s\n"""%vars()
	try:
		exec(macCode)
	except SyntaxError, msg:
		raise gavo.Error("Bad Macro source %s: %s"%(macCode, msg))
	return Newmacro()

getMacro = utils.buildClassResolver(Macro, globals().values())


def _test():
	import doctest, macros
	doctest.testmod(macros)


if __name__=="__main__":	
	if not utils.makeClassDocs(Macro, globals().values()):
		_test()
