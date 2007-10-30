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
import math

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

	This function parses a dictionary mapping original names to desired names.

	>>> _parseAssignments("a:b  b:c")
	{'a': 'b', 'b': 'c'}
	"""
	return dict([(lead, trail) for lead, trail in
		[litPair.split(":") for litPair in assignments.split()]])


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
			"hour": self._hourangleToDeg,
			"sexag": self._dmsToDeg,
			"mas": lambda mas: float(mas)/3.6e6,
			"binary": lambda a: a,
		}

	@staticmethod
	def getName():
		return "handleEquatorialPosition"

	def _compute(self, record, alpha, delta):
		if alpha==None or delta==None:
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

	def _hourangleToDeg(self, literal):
		return coords.hourangleToDeg(literal, self.sepChar)

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
	@staticmethod
	def getName():
		return "combinePM"

	def __init__(self, argTuples=[], alphaFactor="1", 
			deltaFactor="1"):
		Macro.__init__(self, argTuples)
		self.alphaFactor, self.deltaFactor = float(alphaFactor), float(deltaFactor)
	
	def _compute(self, record, pmAlpha, pmDelta):
		if pmAlpha==None or pmDelta==None:
			tpm = pmpa = None
		else:
			pma = pmAlpha*self.alphaFactor
			pmd = pmDelta*self.deltaFactor
			tpm = math.sqrt(pma**2+pmd**2)
			pmpa = math.atan2(pma, pmd)*360/2/math.pi
		record["pm_total"] = tpm
		record["angle_pm"] = pmpa


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

	>>> m = TimestampCombiner([("date", "date", ""), ("time", "time", "")],
	... destination="stamp")
	>>> rec = {"date": "4.6.1969", "time": "4:22:33"}
	>>> m(None, rec)
	>>> rec["stamp"].strftime()
	'Wed Jun  4 04:22:33 1969'
	>>> m = TimestampCombiner([("date", "date", ""), ("time", "time", "")],
	... timeFormat="!!secondsSinceMidnight")
	>>> rec = {"date": "4.6.1969", "time": "32320"}
	>>> m(None, rec)
	>>> rec["timestamp"].strftime()
	'Wed Jun  4 08:58:40 1969'
	"""
	def __init__(self, argTuples=[], destination="timestamp",
			dateFormat="%d.%m.%Y", timeFormat="%H:%M:%S"):
		Macro.__init__(self, argTuples)
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

	def _compute(self, record, date, time):
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
	* sources -- a comma seperated list of source field names

	concat takes no arguments.

	>>> v = ValueCatter(joiner="<>", argTuples=[],
	... sources="src1,src2,src3", destination="cat")
	>>> r = {"src1": "opener", "src2": "catfood", "src3": "can"}
	>>> v(None, r)
	>>> r["cat"]
	'opener<>catfood<>can'
	"""
	def __init__(self, argTuples=[], joiner="", destination="",
			sources=""):
		Macro.__init__(self, argTuples)
		self.joiner, self.destination = joiner, destination
		self.sources = self._parseSources(sources)

	@staticmethod
	def getName():
		return "concat"

	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _compute(self, record):
		items = [record[src] for src in self.sources
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

	>>> n = NullValuator(colName="foo", nullvalue="EMPTY")
	>>> r = {"foo": "bar", "baz": "bang"}
	>>> n(None, r); r["foo"]
	'bar'
	>>> r["foo"] = "EMPTY"
	>>> n(None, r); print r["foo"]
	None
	"""
	def __init__(self, argTuples=[], nullvalue="NULL", 
			colName=""):
		Macro.__init__(self, argTuples)
		self.nullvalue = nullvalue
		self.colName = colName

	@staticmethod
	def getName():
		return "mapToNone"
	
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
	def __init__(self, argTuples=[], sourceName="", 
			destination="", logFailures=False, failuresAreNone=True):
		Macro.__init__(self, argTuples)
		self.map = utils.NameMap(os.path.join(config.get("inputsDir"), sourceName))
		self.logFailures = logFailures
		self.failuresAreNone = failuresAreNone
		self.destination = destination

	@staticmethod
	def getName():
		return "mapValue"
	
	def _compute(self, record, value):
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

	>>> s = StringInterpolator([], destination="baz",
	... format="no %s in %s", sources="bar,foo")
	>>> r = {"foo": "42", "bar": "23"}
	>>> s(None, r); r["baz"]
	'no 23 in 42'
	"""
	def __init__(self, argTuples=[], destination="",
			format="", sources=""):
		Macro.__init__(self, argTuples)
		self.sources = self._parseSources(sources)
		self.format, self.destination = format, destination

	@staticmethod
	def getName():
		return "interpolateStrings"
	
	def _parseSources(self, sources):
		return [src.strip() for src in sources.split(",")]

	def _compute(self, record):
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

	>>> m = ReSubstitutor([("data", "broken", "")], 
	... srcRe=r"(.) \(([^)]*)\)", destRe=r"\2 \1", destination="fixed")
	>>> r = {"broken": "r (Gunn)"}
	>>> m(None, r); r["fixed"]
	'Gunn r'
	>>> r = {"broken": "Any ol' junk"}
	>>> m(None, r); r["fixed"]
	"Any ol' junk"
	"""
	def __init__(self, argTuples=[], destination="",
			srcRe="", destRe=""):
		Macro.__init__(self, argTuples)
		self.destination = destination
		self.srcPat, self.destRe = re.compile(srcRe), destRe

	@staticmethod
	def getName():
		return "subsRe"
	
	def _compute(self, record, data):
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
	def __init__(self, argTuples=[], destination="",
			factor=0, offset=0):
		Macro.__init__(self, argTuples)
		self.destination = destination
		self.factor, self.offset = float(factor), float(offset)

	@staticmethod
	def getName():
		return "linearMap"
	
	def _compute(self, record, val):
		if val==None:
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
	def __init__(self, argTuples=[], ignoreUnknowns=False):
		self.ignoreUnknowns = ignoreUnknowns
		Macro.__init__(self, argTuples)
		from gavo.simbadinterface import Sesame
		self.resolver = Sesame(saveNew=True)
	
	@staticmethod
	def getName():
		return "resolveObject"
	
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
	def __init__(self, argTuples=[], assignments="year:year"):
		Macro.__init__(self, argTuples)
		self.assignments = _parseAssignments(assignments)
	
	@staticmethod
	def getName():
		return "parsemxdate"
	
	def _compute(self, record, date):
		if date==None:
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
	  the colon are the column names in the db.
	* table -- the table to query
	* column -- the column to run the test against

	Argument:

	* val -- the value that column must be equal to in the query.

	You'd use this macro like this:

	<Macro name="simplequery" items="alpha:cat_alpha delta:cat_delta"
	    table="fk5.data" column="localid">
	  <arg name="val" source="star"/>
	</Macro>

	If your record were {"star": "8894"}, we'd gernerate a query

	SELECT cat_alpha, cat_delta FROM fk5.data where localid='8894',

	and assign the first item of the first response row to alpha,
	and the second to delta.
	"""
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
	
	@staticmethod
	def getName():
		return "simplequery"
	
	def _compute(self, record, val):
		dbNames, recNames = self.assignments.keys(), self.assignments.values()
		query = "SELECT %s FROM %s WHERE %s=%%(val)s"%(
			", ".join(dbNames), self.table, self.column)
		try:
			res = self.querier.query(query, {"val": val}).fetchall()[0]
			for name, resVal in zip(recNames, res):
				record[name] = resVal
		except IndexError:
			utils.raiseTb(Error, "The item %s didn't match"
				" any data.  Since this data is required for further"
				" operations, I'm giving up"%val)


class BboxSiapFieldsComputer(Macro):
	"""is a macro that computes fields for the bboxSiap interface.

	It takes no arguments but expects WCS-like keywords in record, i.e.,
	CRVAL1, CRVAL2 (interpreted as float deg), CRPIX1, CRPIX2 (pixel
	corresponding to CRVAL1, CRVAL2), CUNIT1, CUNIT2 (pixel scale unit,
	we bail out if it isn't deg), CDn_n (the transformation matrix), NAXIS1,
	NAXIS2 (the image size).

	It leaves the primaryBbbox, secondaryBbox (see siap.py for an explanation),
	centerDelta, centerAlpha, nAxes, pixelSize, pixelScale and imageFormat.

	For now, we only implement a tiny subset of WCS.  I guess we should
	at some point wrap wcslib or something similar.

	>>> m = BboxSiapFieldsComputer()
	>>> r = {"NAXIS1": "100", "NAXIS2": "150", "CRVAL1": "138", "CRVAL2": 53,
	...   "CRPIX1": "70", "CRPIX2": "50", "CUNIT1": "deg", "CUNIT2": "deg",
	...   "CD1_1": 0.0002, "CD1_2": 3e-8, "CD2_1": 3e-8, "CD2_2": "-0.0002",
	...   "NAXIS": 2}
	>>> m(None, r); r["primaryBbox"], r["secondaryBbox"]
	(Box(((138.006,53.01), (137.986,52.98))), None)
	>>> r["CRVAL1"] = 0
	>>> m(None, r); r["primaryBbox"], r["secondaryBbox"]
	(Box(((360,53.01), (359.986,52.98))), Box(((0.006003,53.01), (0,52.98))))
	>>> str(r["centerAlpha"]), str(r["centerDelta"])
	('-0.00399925', '52.9949994')
	"""
	@staticmethod
	def getName():
		return "computeBboxSiapFields"

	def _compute(self, record):
		def seqAbs(seq):
			return math.sqrt(sum(float(v)**2 for v in seq))

		record["primaryBbox"], record["secondaryBbox"] = siap.splitCrossingBox(
			siap.getBboxFromWCSFields(record))
		record["centerAlpha"], record["centerDelta"] = siap.getCenterFromWCSFields(
			record)
		record["nAxes"] = int(record["NAXIS"])
		axeInds = range(1, record["nAxes"]+1)
		assert len(axeInds)==2   # probably not exactly necessary
		record["pixelSize"] = tuple(int(record["NAXIS%d"%i]) 
			for i in axeInds)
		assert(record["CUNIT1"], "deg")  # XXX TODO: see what else can be there.
		record["pixelScale"] = tuple(
				seqAbs(record["CD%d_%d"%(i, j)] for j in axeInds)
			for i in axeInds)
		record["imageFormat"] = "image/fits"

		# XXX TODO: siap only wants one value for projection.  I admit
		# that I don't really know what I'm doing here.
		record["wcs_projection"] = record.get("CTYPE1")
		if record["wcs_projection"]:
			record["wcs_projection"] = record["wcs_projection"][5:8]
		record["wcs_refPixel"] = tuple(float(record["CRPIX%d"%i]) 
			for i in axeInds)
		record["wcs_refValues"] = tuple(float(record["CRVAL%d"%i]) 
			for i in axeInds)
		record["wcs_cdmatrix"] = tuple(float(record["CD%d_%d"%(i, j)])
			for i in axeInds for j in axeInds)


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


def compileMacro(name, code):
	"""returns a macro of name name and code as _compute body.
	"""
	code = _fixIndentation(code, "			")
	macCode = """class Newmacro(Macro):
		@staticmethod
		def getName():
			return "%(name)s"

		def _compute(self, record):
%(code)s\n"""%vars()
	exec(macCode)
	return Newmacro()

getMacro = utils.buildClassResolver(Macro, globals().values())


def _test():
	import doctest, macros
	doctest.testmod(macros)


if __name__=="__main__":	
	if not utils.makeClassDocs(Macro, globals().values()):
		_test()
