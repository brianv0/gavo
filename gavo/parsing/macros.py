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
try:
	import pyhtm
except ImportError:
	logger.warning("Pyhtm module not found, coordinate conversion macros"
		" will not work.")
from gavo import utils
from gavo import coords
from gavo.parsing import parsehelpers
from gavo.parsing import resource


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
	"""
	def __call__(self, record):
		self._changeRecord(record, **self._buildArgDict(record))


class EquatorialPositionConverter(Macro):
	"""is a macro to compute all kinds of derived quantities from 
	conventional equatorial coordinates.

	The field structure generated here is reflected in 
	__common__/positionfields.template.  If you change anything here,
	change it there, too.  And use that template when you use this macro.

	>>> m = EquatorialPositionConverter()
	>>> map(str, m._computeCoos("00 02 32", "+45 30.6"))
	['0.633333333333', '45.51', '0.700741955529', '0.00774614323406', '0.713372770034']
	>>> map(str, m._computeCoos("10 37 19.544070", "+35 34 20.45713"))
	['159.331433625', '35.5723492028', '-0.761030579345', '0.287092459516', '0.581730502028']
	>>> map(str, m._computeCoos("4 38 54", "-12 7.4"))
	['69.725', '-12.1233333333', '0.338798083012', '0.917119854377', '-0.21001674137']
	"""
	@staticmethod
	def getName():
		return "handleEquatorialPosition"

	def _changeRecord(self, record, alpha, delta, alphaSepChar=None, 
			deltaSepChar=None):
		alphaFloat, deltaFloat, c_x, c_y, c_z = self._computeCoos(
			alpha, delta, alphaSepChar, deltaSepChar)
		record["alphaFloat"] = alphaFloat
		record["deltaFloat"] = deltaFloat
		record["c_x"] = c_x
		record["c_y"] = c_y
		record["c_z"] = c_z
		record["htmid"] = pyhtm.lookup(alphaFloat, deltaFloat)

	def _computeCoos(self, alpha, delta, alphaSepChar=" ", deltaSepChar=" "):
		alphaFloat = coords.hourangleToDeg(alpha, alphaSepChar)
		deltaFloat = coords.dmsToDeg(delta, deltaSepChar)
		return (alphaFloat, deltaFloat)+coords.computeUnitSphereCoords(
			alphaFloat, deltaFloat)


class TimestampCombiner(Macro):
	"""is a macro that takes a date and a time in various formats
	and produces a mx.DateTime object from it.

	Use its result like
	<Field dest="someTimestamp" dbtype="timestamp" source="myTimestamp"
		literalForm="do not touch"/>
	
	myTimestamp is the value of the destination argument.

	>>> m = TimestampCombiner([("destination", "", "stamp"),
	...   ("date", "date", ""), ("dateFormat", "", "%d.%m.%Y"),
	...   ("time", "time", ""), ("timeFormat", "", "%H:%M:%S")])
	>>> rec = {"date": "4.6.1969", "time": "4:22:33"}
	>>> m(rec)
	>>> rec["stamp"].strftime()
	'Wed Jun  4 04:22:33 1969'
	>>> m = TimestampCombiner([("destination", "", "stamp"),
	...   ("date", "date", ""), ("dateFormat", "", "%d.%m.%Y"),
	...   ("time", "time", ""), ("timeFormat", "", "!!secondsSinceMidnight")])
	>>> rec = {"date": "4.6.1969", "time": "32320"}
	>>> m(rec)
	>>> rec["stamp"].strftime()
	'Wed Jun  4 08:58:40 1969'
	"""
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

	def _changeRecord(self, record, destination, date, time, 
			dateFormat, timeFormat):
		assert destination!=""
		timeObj = self._processTime(time, timeFormat)
		dateObj = self._processDate(date, dateFormat)
		record[destination] = dateObj+timeObj


class ValueCatter(Macro):
	"""is a macro that concatenates values from various rows and puts
	the resulting value in destinationRow.

	This processes raw strings, i.e., it does not know about types, NULL
	values, and the like.  If a source field was not matched, the concat will
	throw a KeyError
	"""
	def __init__(self, fieldComputer, joiner=""):
		Macro.__init__(self, fieldComputer)
		self.joiner = joiner

	@staticmethod
	def getName():
		return "concat"

	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _changeRecord(self, record, destination, sources):
		record[destination] = self.joiner.join(
			[record[src] for src in self._parseSources(sources)
				if record[src]!=None])


class NullValuator(Macro):
	"""is a macro that maps a certain literal to None.

	In general, this isn't necessary since you can define null values in fields.
	However, when another macro needs Nones to signify null values, you need
	this macro, because macros are applied before fields are even looked at.
	"""
	@staticmethod
	def getName():
		return "mapToNone"
	
	def _changeRecord(self, record, colName, nullvalue):
		if record[colName]==nullvalue:
			record[colName] = None


class ValueMapper(Macro):
	"""is a macro that translates vaules via a utils.NameMap

	The constructor takes arguments:
	* sourceName -- an inputsDir-relative path to the NameMap source file,
	* logFailures (optional) -- if somehow true, non-resolved names will 
	  be logged

	If an object cannot be resolved, a null value is entered (i.e., you
	shouldn't get an exception out of this macro but can weed out "bad"
	records through notnull-conditions later if you wish).
	"""
	def __init__(self, fieldComputer, sourceName, 
			logFailures=False, failuresAreNone=True):
		Macro.__init__(self, fieldComputer)
		self.map = utils.NameMap(os.path.join(gavo.inputsDir, sourceName))
		self.logFailures = logFailures
		self.failuresAreNone = failuresAreNone

	@staticmethod
	def getName():
		return "mapValue"
	
	def _changeRecord(self, record, value, destination):
		try:
			record[destination] = self.map.resolve(value)
		except KeyError:
			if self.logFailures:
				gavo.logger.warning("Name %s could not be mapped"%value)
			record[destination] = None


class StringInterpolator(Macro):
	"""is a macro that exposes %-like string interpolations.
	"""
	@staticmethod
	def getName():
		return "interpolateStrings"
	
	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _changeRecord(self, record, destination, format, sources):
		record[destination] = format%tuple([record[src] 
			for src in self._parseSources(sources)])


class ReSubstitutor(Macro):
	"""is a macro at exposes re.sub.
	"""
	@staticmethod
	def getName():
		return "subsRe"
	
	def _changeRecord(self, record, destination, data, srcRe, destRe):
		record[destination] = re.sub(srcRe, destRe, data)


class ProductValueCollector(Macro):
	"""is a macro that provides all values requried for the product table.

	See gavo.inputsDir/products/.

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

getMacro = utils._buildClassResolver(Macro, globals().values())
		
		
def _test():
	import doctest, macros
	doctest.testmod(macros)


if __name__=="__main__":
	_test()
