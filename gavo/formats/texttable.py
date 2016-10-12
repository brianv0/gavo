"""
Writing data as plain text.

Currently, we only do TSV.  It would probably be nice to support "formatted
ASCII as well, though that may be a bit tricky given that we do not
really store sane formatting hints for most columns.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import cStringIO
import datetime

from gavo import base
from gavo import rsc
from gavo import stc
from gavo import utils
from gavo.formats import common
from gavo.utils import serializers

# A mapper function registry for formats directed at humans
displayMFRegistry = serializers.ValueMapperFactoryRegistry()
registerDisplayMF = displayMFRegistry.registerFactory

def _defaultMapperFactory(colDesc):
	def coder(val):
		if val is None:
			return "N/A"
		return unicode(val)
	return coder
registerDisplayMF(_defaultMapperFactory)


floatTypes = set(["real", "float", "double", "double precision"])

def _sfMapperFactory(colDesc):
	if colDesc["dbtype"] not in floatTypes:
		return
	if colDesc["displayHint"].get("sf"):
		fmtStr = "%%.%df"%int(colDesc["displayHint"].get("sf"))
		def coder(val):
			if val is None:
				return "N/A"
			else:
				return fmtStr%val
		return coder
registerDisplayMF(_sfMapperFactory)


def _hmsMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="hms":
		return
	colDesc["unit"] = "h:m:s"
	sepChar = colDesc["displayHint"].get("sepChar", " ")
	sf = int(colDesc["displayHint"].get("sf", 2))
	def coder(val):
		if val is None:
			return "N/A"
		else:
			return utils.degToHms(val, sepChar, sf)
	return coder
registerDisplayMF(_hmsMapperFactory)


def _dmsMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="dms":
		return
	colDesc["unit"] = "d:m:s"
	sepChar = colDesc["displayHint"].get("sepChar", " ")
	sf = int(colDesc["displayHint"].get("sf", 2))
	def coder(val):
		if val is None:
			return "N/A"
		return utils.degToDms(val, sepChar, sf)
	return coder
registerDisplayMF(_dmsMapperFactory)


def _unitMapperFactory(colDesc):
	"""returns a factory that converts between units for fields that have
	a displayUnit displayHint.

	The stuff done here has to be done for all factories handling unit-based
	floating point values.  Maybe we want to do "decorating" meta-factories?
	"""
	if colDesc["displayHint"].get("displayUnit") and \
			colDesc["displayHint"]["displayUnit"]!=colDesc["unit"]:
		try:
			factor = base.computeConversionFactor(colDesc["unit"], 
				colDesc["displayHint"]["displayUnit"])
		except base.BadUnit:
			# bad unit somewhere; ignore display hint
			base.ui.notifyError("Bad unit while computing conversion factor.")
			return None

		colDesc["unit"] = colDesc["displayHint"]["displayUnit"]
		fmtStr = "%%.%df"%int(colDesc["displayHint"].get("sf", 2))
		
		if "[" in colDesc["dbtype"]:
			def coder(val):
				if val is None:
					return "N/A"
				return "[%s]"%", ".join("N/A" if item is None else fmtStr%(item*factor)
					for item in val)

		else:
			def coder(val):
				return "N/A" if val is None else fmtStr%(val*factor)

		return coder
registerDisplayMF(_unitMapperFactory)


def _stringWrapMF(baseMF):
	"""returns a factory that that stringifies floats and makes N/A from
	Nones coming out of baseMF and passes everything else through.
	"""
	def factory(colDesc):
		handler = baseMF(colDesc)
		if colDesc["displayHint"].get("sf", None):
			fmtstr = "%%.%df"%int(colDesc["displayHint"]["sf"])
		fmtstr = "%s"
		if handler:
			def realHandler(val):
				res = handler(val)
				if isinstance(res, float):
					return fmtstr%res
				else:
					if res is None:
						return "N/A"
					else:
						return res
			return realHandler
	return factory

registerDisplayMF(_stringWrapMF(stc.datetimeMapperFactory))


def humanDatesFactory(colDesc):
	format, unit = {"humanDate": ("%Y-%m-%d %H:%M:%S", ""),
		"humanDay": ("%Y-%m-%d", "") }.get(
			colDesc["displayHint"].get("type"), (None, None))
	if format and colDesc["dbtype"] in ("date", "timestamp"):
		colDesc["unit"] = unit
		def coder(val):
			if val is None:
				return "N/A"
			else:
				colDesc["datatype"], colDesc["arraysize"] = "char", "*"
				colDesc["xtype"] = "adql:TIMESTAMP"
				colDesc["unit"] = ""
				try:
					return val.strftime(format)
				except ValueError:  # probably too old a date, fall back to a hack
					return val.isoformat()
		return coder
registerDisplayMF(humanDatesFactory)


def humanTimesFactory(colDesc):
	if colDesc["displayHint"].get("type")=="humanTime":
		sf = int(colDesc["displayHint"].get("sf", 0))
		fmtStr = "%%02d:%%02d:%%0%d.%df"%(sf+3, sf)
		def coder(val):
			if val is None:
				return "N/A"
			else:
				if isinstance(val, (datetime.time, datetime.datetime)):
					return fmtStr%(val.hours, val.minutes, val.second)
				elif isinstance(val, datetime.timedelta):
					hours = val.seconds//3600
					minutes = (val.seconds-hours*3600)//60
					seconds = (val.seconds-hours*3600-minutes*60)+val.microseconds/1e6
					return fmtStr%(hours, minutes, seconds)
		return coder
registerDisplayMF(humanTimesFactory)


def jdMapperFactory(colDesc):
	"""maps JD, MJD, unix timestamp, and julian year columns to 
	human-readable datetimes.

	MJDs are caught by inspecting the UCD.
	"""
	if (colDesc["displayHint"].get("type")=="humanDate"
			and colDesc["dbtype"] in ("double precision", "real")):

		if colDesc["unit"]=="d":
			if "mjd" in colDesc["ucd"].lower() or colDesc["xtype"]=="mjd":
				converter = stc.mjdToDateTime
			else:
				converter = stc.jdnToDateTime
		elif colDesc["unit"]=="s":
			converter = datetime.datetime.utcfromtimestamp
		elif colDesc["unit"]=="yr":
			converter = stc.jYearToDateTime
		else:
			return None

		def fun(val):
			if val is None:
				return "N/A"
			return utils.formatISODT(converter(val))
		colDesc["datatype"], colDesc["arraysize"] = "char", "*"
		colDesc["xtype"] = "adql:TIMESTAMP"
		colDesc["unit"] = ""
		return fun
registerDisplayMF(jdMapperFactory)


def _sizeMapperFactory(colDesc):
	"""is a factory for formatters for file sizes and similar.
	"""
	if colDesc["unit"]!="byte":
		return
	sf = int(colDesc["displayHint"].get("sf", 1))
	def coder(val):
		if val is None:
			return "N/A"
		else:
			return utils.formatSize(val, sf)
	return coder
registerDisplayMF(_sizeMapperFactory)


registerDisplayMF(serializers._pgSphereMapperFactory)


def _makeString(val):
# this is a cheap trick to ensure everything non-ascii is escaped.
	if val is None:
		return "N/A"
	if isinstance(val, basestring):
		return repr(unicode(val))[2:-1]
	return str(val)


def renderAsColumns(table, target, acquireSamples=False):
	"""writes a fixed-column representation of table to target.
	"""
	if isinstance(table, rsc.Data):
		table = table.getPrimaryTable()
	sm = base.SerManager(table, acquireSamples=acquireSamples,
		mfRegistry=displayMFRegistry)
	target.write(utils.formatSimpleTable(
			(_makeString(s) for s in row)
		for row in sm.getMappedTuples()))
	return ""


def renderAsText(table, target, acquireSamples=True):
	"""writes a text (TSV) rendering of table to the file target.
	"""
	if isinstance(table, rsc.Data):
		table = table.getPrimaryTable()
	sm = base.SerManager(table, acquireSamples=acquireSamples)
	for row in sm.getMappedTuples():
		target.write("\t".join([_makeString(s) for s in row])+"\n")


def getAsText(data):
	target = cStringIO.StringIO()
	renderAsText(data, target)
	return target.getvalue()


def readTSV(inFile):
	"""returns a list of tuples for a tab-separated-values file.

	Lines starting with # and lines containing only whitespace are ignored.  
	Whitespace at front and back is stripped.

	No checks are done at this point, i.e., the tuples could be of varying 
	lengths.
	"""
	data = []
	for ln in inFile:
		ln = ln.strip()
		if not ln or ln.startswith("#"):
			continue
		data.append(tuple(ln.split("\t")))
	return data


# NOTE: This will only serialize the primary table.
common.registerDataWriter("tsv", renderAsText, "text/tab-separated-values",
	"Tab separated values")
common.registerDataWriter("txt", renderAsColumns, "text/plain",
	"Fixed-column plain text")
