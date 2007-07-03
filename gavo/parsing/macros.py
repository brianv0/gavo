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
from mx import DateTime
import os
import re

import gavo
from gavo import logger
from gavo import utils
from gavo import coords
from gavo.parsing import parsehelpers
from gavo.parsing import resource

supportHtm = False

if supportHtm:
	import pyhtm

class Error(gavo.Error):
	pass


class Macro(parsehelpers.RowFunction):
	"""is an abstract base class for Macros.

	A Macro is RowFunction that modifies and/or adds preterminal values
	to row dictionaries (i.e. the output of a grammar).

	A Macro is used by calling it with the rowdict it is to change as
	its single argument.  Derived classes must define a _changeRecord
	method that receives the RowFunction's arguments as keyword
	arguments.

	_changeRecord methods work through side effects (well, changing
	the record...).  Any return values are discarded.

	Macros should, as a rule, be None-clear, i.e. shouldn't crap out
	on Nones as values (that can conceivably come from the grammar) but 
	just "propagate" the None in an appropriate way.  If there's no
	other way to cope, they should raise a gavo.Error and not let
	other exceptions escape.  It is not the macro's job to validate
	non-null constraints.
	"""
	def __call__(self, record):
		self._changeRecord(record, **self._buildArgDict(record))


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
	  a sexagesimal hour angle is expected.  Supported formats include
		mas (hour angle in milliarcsecs), ...
	* decFormat -- as raFormat, only the default is sexagesimal angle.
	* sepChar (optional) -- seperator for alpha, defaults to whitespace
	
	If alpha and delta use different seperators, you'll have to fix
	this using preprocessing macros.

	Arguments: 
	 
	* alpha -- sexagesimal right ascension as hour angle
	* delta -- sexagesimal declination as dms

	The field structure generated here is reflected in 
	__common__/positionfields.template.  If you change anything here,
	change it there, too.  And use that template when you use this macro.

	>>> m = EquatorialPositionConverter(None, [("alpha", "alphaRaw", ""),
	... ("delta", "deltaRaw", "")])
	>>> r = {"alphaRaw": "00 02 32", "deltaRaw": "+45 30.6"} 
	>>> m(r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"]), str(r["c_x"]), str(r["c_y"])
	('0.633333333333', '45.51', '0.700741955529', '0.00774614323406')
	>>> m = EquatorialPositionConverter(None, [("alpha", "alphaRaw", ""),
	... ("delta", "deltaRaw", ""),], sepChar=":")
	>>> r = {"alphaRaw": "10:37:19.544070", "deltaRaw": "+35:34:20.45713"}; m(r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"]), str(r["c_z"])
	('159.331433625', '35.5723492028', '0.581730502028')
	>>> r = {"alphaRaw": "4:38:54", "deltaRaw": "-12:7.4"}; m(r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"])
	('69.725', '-12.1233333333')
	>>> m = EquatorialPositionConverter(None, [("alpha", "alphaRaw", ""), 
	... ("delta", "deltaRaw", "")], alphaFormat="mas", deltaFormat="mas")
	>>> r = {"alphaRaw": "5457266", "deltaRaw": "-184213905"}; m(r)
	>>> str(r["alphaFloat"]), str(r["deltaFloat"])
	('1.51590722222', '-51.1705291667')
	"""
	def __init__(self, fieldComputer, argTuples=[], alphaFormat="hour", 
			deltaFormat="sexag", sepChar=None, *args, **kwargs):
		self.alphaFormat, self.deltaFormat = alphaFormat, deltaFormat
		self.sepChar = sepChar
		Macro.__init__(self, fieldComputer, argTuples, *args, **kwargs)
		self.coordComputer = {
			"hour": self._hourangleToDeg,
			"sexag": self._dmsToDeg,
			"mas": lambda mas: float(mas)/3.6e6,
		}

	@staticmethod
	def getName():
		return "handleEquatorialPosition"

	def _changeRecord(self, record, alpha, delta):
		alphaFloat, deltaFloat, c_x, c_y, c_z = self._computeCoos(
			alpha, delta)
		record["alphaFloat"] = alphaFloat
		record["deltaFloat"] = deltaFloat
		record["c_x"] = c_x
		record["c_y"] = c_y
		record["c_z"] = c_z
		if supportHtm:
			record["htmid"] = pyhtm.lookup(alphaFloat, deltaFloat)

	def _hourangleToDeg(self, literal):
		return coords.hourangleToDeg(literal, self.sepChar)

	def _dmsToDeg(self, literal):
		return coords.dmsToDeg(literal, self.sepChar)

	def _convertCoo(self, literalForm, literal):
		return self.coordComputer[literalForm](literal)

	def _computeCoos(self, alpha, delta):
		alphaFloat = self._convertCoo(self.alphaFormat, alpha)
		deltaFloat = self._convertCoo(self.deltaFormat, delta)
		return (alphaFloat, deltaFloat)+coords.computeUnitSphereCoords(
			alphaFloat, deltaFloat)


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

	The macro understands the special timeFormat !!secondsSinceMidnight.

	Arguments:

	* date -- a date literal
	* time -- a time literal

	>>> m = TimestampCombiner(None, [("date", "date", ""), ("time", "time", "")],
	... destination="stamp")
	>>> rec = {"date": "4.6.1969", "time": "4:22:33"}
	>>> m(rec)
	>>> rec["stamp"].strftime()
	'Wed Jun  4 04:22:33 1969'
	>>> m = TimestampCombiner(None, [("date", "date", ""), ("time", "time", "")],
	... timeFormat="!!secondsSinceMidnight")
	>>> rec = {"date": "4.6.1969", "time": "32320"}
	>>> m(rec)
	>>> rec["timestamp"].strftime()
	'Wed Jun  4 08:58:40 1969'
	"""
	def __init__(self, fieldComputer, argTuples=[], destination="timestamp",
			dateFormat="%d.%m.%Y", timeFormat="%H:%M:%S"):
		Macro.__init__(self, fieldComputer, argTuples)
		self.destination = destination
		self.timeFormat, self.dateFormat = timeFormat, dateFormat

	@staticmethod
	def getName():
		return "combineTimestamps"

	def _processTime(self, literal, format):
		if format=="!!secondsSinceMidnight":
			secs = float(literal)
			fullSecs = int(secs)
			hours = fullSecs/3600
			minutes = (fullSecs%3600)/60
			seconds = secs-hours*3600-minutes*60
			return DateTime.Time(hours, minutes, seconds)
		else:
			return DateTime.Time(*time.strptime(literal, format)[3:6])

	def _processDate(self, literal, format):
		return DateTime.Date(*time.strptime(literal, format)[:3])

	def _changeRecord(self, record, date, time):
		timeObj = self._processTime(time, self.timeFormat)
		dateObj = self._processDate(date, self.dateFormat)
		record[self.destination] = dateObj+timeObj


class ValueCatter(Macro):
	"""is a macro that concatenates values from various rows and puts
	the resulting value in destinationRow.

	Null values are ignored.  If all source elements are None, the
	destination will be None.

	Construction Arguments:
	
	* joiner -- a string used to glue the individual values together.  Optional,
	  defaults to the empty string.
	* destination -- a name under which the concatenated value should be stored

	Argument:
	
	* sources -- a comma seperated list of source field names

	>>> v = ValueCatter(None, joiner="<>", argTuples=[
	... ("sources", "", "src1,src2,src3")], destination="cat")
	>>> r = {"src1": "opener", "src2": "catfood", "src3": "can"}
	>>> v(r)
	>>> r["cat"]
	'opener<>catfood<>can'
	"""
	def __init__(self, fieldComputer, argTuples=[], joiner="", destination=""):
		Macro.__init__(self, fieldComputer, argTuples)
		self.joiner, self.destination = joiner, destination

	@staticmethod
	def getName():
		return "concat"

	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _changeRecord(self, record, sources):
		items = [record[src] for src in self._parseSources(sources)
				if record[src]!=None]
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

	>>> n = NullValuator(None, colName="foo", nullvalue="EMPTY")
	>>> r = {"foo": "bar", "baz": "bang"}
	>>> n(r); r["foo"]
	'bar'
	>>> r["foo"] = "EMPTY"
	>>> n(r); print r["foo"]
	None
	"""
	def __init__(self, fieldComputer, argTuples=[], nullvalue="NULL", 
			colName=""):
		Macro.__init__(self, fieldComputer, argTuples)
		self.nullvalue = nullvalue
		self.colName = colName

	@staticmethod
	def getName():
		return "mapToNone"
	
	def _changeRecord(self, record):
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
	def __init__(self, fieldComputer, argTuples=[], sourceName="", 
			destination="", logFailures=False, failuresAreNone=True):
		Macro.__init__(self, fieldComputer, argTuples)
		self.map = utils.NameMap(os.path.join(gavo.inputsDir, sourceName))
		self.logFailures = logFailures
		self.failuresAreNone = failuresAreNone
		self.destination = destination

	@staticmethod
	def getName():
		return "mapValue"
	
	def _changeRecord(self, record, value):
		try:
			record[self.destination] = self.map.resolve(str(value))
		except KeyError:
			if self.logFailures:
				gavo.logger.warning("Name %s could not be mapped"%value)
			record[self.destination] = None


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
	in format.

	StringInterpolators have no runtime arguments.

	>>> s = StringInterpolator(None, [], destination="baz",
	... format="no %s in %s", sources="bar,foo")
	>>> r = {"foo": "42", "bar": "23"}
	>>> s(r); r["baz"]
	'no 23 in 42'
	"""
	def __init__(self, fieldComputer, argTuples=[], destination="",
			format="", sources=""):
		Macro.__init__(self, fieldComputer, argTuples)
		self.sources = self._parseSources(sources)
		self.format, self.destination = format, destination

	@staticmethod
	def getName():
		return "interpolateStrings"
	
	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _changeRecord(self, record):
		try:
			record[self.destination] = self.format%tuple([record[src] 
				for src in self.sources])
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

	>>> m = ReSubstitutor(None, [("data", "broken", "")], 
	... srcRe=r"(.) \(([^)]*)\)", destRe=r"\2 \1", destination="fixed")
	>>> r = {"broken": "r (Gunn)"}
	>>> m(r); r["fixed"]
	'Gunn r'
	>>> r = {"broken": "Any ol' junk"}
	>>> m(r); r["fixed"]
	"Any ol' junk"
	"""
	def __init__(self, fieldComputer, argTuples=[], destination="",
			srcRe="", destRe=""):
		Macro.__init__(self, fieldComputer, argTuples)
		self.destination = destination
		self.srcPat, self.destRe = re.compile(srcRe), destRe

	@staticmethod
	def getName():
		return "subsRe"
	
	def _changeRecord(self, record, data):
		if data==None:
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

	This has to reflect any changes to gavo.inputsDir/products/products.vord.
	"""
	@staticmethod
	def getName():
		return "setProdtblValues"

	def _changeRecord(self, record, prodtblKey, prodtblOwner, prodtblEmbargo,
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

	* val -- the value to be mapped.

	>>> m = LinearMapper(None, [("val", "src", "")], destination="dest",
	... factor="7.4", offset="33")
	>>> rec = {"src": "22.3"}; m(rec)
	>>> str(rec["dest"])
	'198.02'
	"""
	def __init__(self, fieldComputer, argTuples=[], destination="",
			factor=0, offset=0):
		Macro.__init__(self, fieldComputer, argTuples)
		self.destination = destination
		self.factor, self.offset = float(factor), float(offset)

	@staticmethod
	def getName():
		return "linearMap"
	
	def _changeRecord(self, record, val):
		if val==None:
			record[self.destination] = None
		else:
			record[self.destination] = self.factor*float(val)+self.offset


def _fixIndentation(code, newIndent):
	"""returns code with all whitespace from the first line removed from
	every line and newIndent prepended to every line.
	"""
	codeLines = [line for line in code.split("\n") if line.strip()]
	firstIndent = re.match("\s*", codeLines[0]).group()
	fixedLines = []
	for line in codeLines:
		if line[:len(firstIndent)]!=firstIndent:
			raise Error("Bad indent in line %s"%repr(line))
		fixedLines.append(newIndent+line[len(firstIndent):])
	return "\n".join(fixedLines)


def compileMacro(name, code, fieldComputer):
	"""returns a macro of name name and code as _changeRecord body.
	"""
	code = _fixIndentation(code, "			")
	macCode = """class Newmacro(Macro):
		@staticmethod
		def getName():
			return "%(name)s"

		def _changeRecord(self, record):
%(code)s\n"""%vars()
	exec(macCode)
	return Newmacro(fieldComputer)

getMacro = utils.buildClassResolver(Macro, globals().values())


def _test():
	import doctest, macros
	doctest.testmod(macros)


if __name__=="__main__":	
	import sys
	if len(sys.argv)==2 and sys.argv[1]=="docs":
		utils.makeClassDocs(Macro, globals().values())
	else:
		_test()
