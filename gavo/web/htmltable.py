"""
A renderer for Data to HTML/stan
"""

import datetime
import math
import re
import urlparse
import urllib
import os
import sys
import traceback
import weakref

from nevow import flat
from nevow import loaders
from nevow import rend
from nevow import tags as T, entities as E

from twisted.internet import reactor, defer

from gavo import base
from gavo import formats
from gavo import svcs
from gavo import utils
from gavo.base import coords
from gavo.base import valuemappers
from gavo.protocols import products
from gavo.rscdef import rmkfuncs
from gavo.web import common


_htmlMFRegistry = valuemappers.ValueMapperFactoryRegistry()
_registerHTMLMF = _htmlMFRegistry.registerFactory


def _defaultMapperFactory(colDesc):
	def coder(val):
		if val is None:
			return "N/A"
		return unicode(val)
	return coder
_registerHTMLMF(_defaultMapperFactory)


# insert new general factories here

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
_registerHTMLMF(_sfMapperFactory)


def _hmsMapperFactory(colDesc):
	if ((colDesc["unit"]!="hms" 
			and colDesc["displayHint"].get("type")!="time")
		or colDesc["datatype"]=="char"):
		return
	colDesc["unit"] = "hms"
	sepChar = colDesc["displayHint"].get("sepChar", " ")
	sf = int(colDesc["displayHint"].get("sf", 2))
	def coder(val):
		if val is None:
			return "N/A"
		else:
			return utils.degToHms(val, sepChar, sf)
	return coder
_registerHTMLMF(_hmsMapperFactory)


def _sexagesimalMapperFactory(colDesc):
	if ((colDesc["unit"]!="dms" 
			and colDesc["displayHint"].get("type")!="sexagesimal")
		or colDesc["datatype"]=="char"):
		return
	colDesc["unit"] = "dms"
	sepChar = colDesc["displayHint"].get("sepChar", " ")
	sf = int(colDesc["displayHint"].get("sf", 2))
	def coder(val):
		if val is None:
			return "N/A"
		return utils.degToDms(val, sepChar, sf)
	return coder
_registerHTMLMF(_sexagesimalMapperFactory)

def _unitMapperFactory(colDesc):
	"""returns a factory that converts between units for fields that have
	a displayUnit displayHint.

	The stuff done here has to be done for all factories handling unit-based
	floating point values.  Maybe we want to do "decorating" meta-factories?
	"""
	if colDesc["displayHint"].get("displayUnit") and \
			colDesc["displayHint"]["displayUnit"]!=colDesc["unit"]:
		factor = base.computeConversionFactor(colDesc["unit"], 
			colDesc["displayHint"]["displayUnit"])
		colDesc["unit"] = colDesc["displayHint"]["displayUnit"]
		fmtStr = "%%.%df"%int(colDesc["displayHint"].get("sf", 2))
		def coder(val):
			if val is None:
				return "N/A"
			return fmtStr%(val*factor)
		return coder
_registerHTMLMF(_unitMapperFactory)

def _stringWrapMF(baseMF):
	"""returns a factory that returns None when baseMF does but stringifies
	any results from baseMF's handlers if they fire.
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
					return lambda val: fmtstr%(handler(val))
				else:
					return res
			return realHandler
	return factory

_registerHTMLMF(_stringWrapMF(valuemappers.datetimeMapperFactory))


def humanDatesFactory(colDesc):
	format, unit = {"humanDatetime": ("%Y-%m-%d %H:%M:%S", "Y-M-D h:m:s"),
		"humanDate": ("%Y-%m-%d", "Y-M-D"), }.get(
			colDesc["displayHint"].get("type"), (None, None))
	if format:
		colDesc["unit"] = unit
		def coder(val):
			if val is None:
				return "N/A"
			else:
				try:
					return val.strftime(format)
				except ValueError:  # probably too old a date, fall back to a hack
					return val.isoformat()
		return coder
_registerHTMLMF(humanDatesFactory)


def humanTimesFactory(colDesc):
	if (colDesc["displayHint"].get("type")=="humanTime" and
			isinstance(colDesc["sample"], (datetime.timedelta, datetime.time))):
		sf = int(colDesc["displayHint"].get("sf", 0))
		fmtStr = "%%02d:%%02d:%%0%d.%df"%(sf+3, sf)
		if isinstance(colDesc["sample"], datetime.time):
			def coder(val):
				if val is None:
					return "N/A"
				else:
					return fmtStr%(val.hours, val.minutes, val.seconds)
		else:
			def coder(val):
				if val is None:
					return "N/A"
				else:
					hours = val.seconds//3600
					minutes = (val.seconds-hours*3600)//60
					seconds = (val.seconds-hours*3600-minutes*60)+val.microseconds/1e6
					return fmtStr%(hours, minutes, seconds)
		return coder
_registerHTMLMF(humanTimesFactory)


def _sizeMapperFactory(colDesc):
	"""is a factory for formatters for file sizes and similar.
	"""
	if colDesc["unit"]!="byte":
		return
	sf = int(colDesc["displayHint"].get("sf", 1))
	def coder(val):
		return utils.formatSize(val, sf)
	return coder
_registerHTMLMF(_sizeMapperFactory)


def _barMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="bar":
		return
	def coder(val):
		if val:
			return T.hr(style="width: %dpx"%int(val), title="%.2f"%val,
				class_="scoreBar")
		return ""
	return coder
_registerHTMLMF(_barMapperFactory)


def _productMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="product":
		return
	if colDesc["displayHint"].get("nopreview"):
		mouseoverHandler = None
	else:
		try:
			pWidth = int(colDesc["displayHint"].get("width", "200"))
		except ValueError:
			pWidth = 200
		mouseoverHandler = "insertPreview(this, %s)"%pWidth
	fixedArgs = ""
	def coder(val):
		if val:
# there's -- use it.
			return T.a(href=products.makeProductLink(val)+fixedArgs,
				onmouseover=mouseoverHandler,
				class_="productlink")[re.sub("&.*", "", 
					os.path.basename(urllib.unquote_plus(str(val)[4:])))]
		else:
			return ""
	return coder
_registerHTMLMF(_productMapperFactory)


def _simbadMapperFactory(colDesc):
	"""is a mapper yielding links to simbad.

	To make this work, you need to furnish the OutputField with a
	select="array[alphaFloat, deltaFloat]" or similar.

	You can give a coneMins displayHint to specify the search radius in
	minutes.
	"""
	if colDesc["displayHint"].get("type")!="simbadlink":
		return
	radius = float(colDesc["displayHint"].get("coneMins", "1"))
	def coder(data):
		alpha, delta = data[0], data[1]
		if alpha and delta:
			return T.a(href="http://simbad.u-strasbg.fr/simbad/sim-coo?Coord=%s"
				"&Radius=%f"%(urllib.quote("%.5fd%+.5fd"%(alpha, delta)),
					radius))["[Simbad]"]
		else:
			return ""
	return coder
_registerHTMLMF(_simbadMapperFactory)


def _feedbackSelectMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="feedbackSelect":
		return
	def coder(data):
		return T.input(type="checkbox", name="feedbackSelect", 
			value=data)
	return coder
_registerHTMLMF(_feedbackSelectMapperFactory)


def _bibcodeMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="bibcode":
		return
	def coder(data):
		if data:
			return T.a(href=base.getConfig("web", "adsMirror")+
					"/cgi-bin/nph-bib_query?bibcode="+urllib.quote(data))[
				data]
		else:
			return ""
	return coder
_registerHTMLMF(_bibcodeMapperFactory)


def _keepHTMLMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="keephtml":
		return
	def coder(data):
		if data:
			return T.raw(data)
		return ""
	return coder
_registerHTMLMF(_keepHTMLMapperFactory)


def _urlMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="url":
		return
	def coder(data):
		if data:
			return T.a(href=data)[urlparse.urlparse(data)[2].split("/")[-1]]
		return ""
	return coder
_registerHTMLMF(_urlMapperFactory)


def _booleanCheckmarkFactory(colDesc):
	"""inserts mappers for values with displayHint type=checkmark.

	These render a check mark if the value is python-true, else nothing.
	"""
	if colDesc["displayHint"].get("type")!="checkmark":
		return
	def coder(data):
		if data:
			return u"\u2713"
		return ""
	return coder
_registerHTMLMF(_booleanCheckmarkFactory)




#  Insert new, more specific factories here


class HeadCellsMixin(object):
	"""A mixin providing renders for table headings.

	The class mixing in must provide the table column definitions as
	self.fieldDefs, and the column properties as computed by
	HTMLDataRenderer as colDesc.
	"""
	def data_fielddefs(self, ctx, ignored):
		return self.fieldDefs

	def render_headCell(self, ctx, fieldDef):
		cd = self.colDescIndex[fieldDef.name]
		cont = fieldDef.getLabel()
		desc = cd["description"]
		if not desc:
			desc = cont
		tag = ctx.tag(title=desc)[T.xml(cont)]
		if cd["unit"]:
			tag[T.br, "[%s]"%cd["unit"]]
		note = cd["note"]
		if note:
			noteURL = "#note-%s"%note.tag
			ctx.tag[T.sup[T.a(href=noteURL)[note.tag]]]
		return tag


class HeadCells(rend.Page, HeadCellsMixin):
	def __init__(self, fieldDefs, colDescIndex):
		self.fieldDefs = fieldDefs
		self.colDescIndex = colDescIndex

	docFactory = loaders.stan(
		T.tr(data=T.directive("fielddefs"), render=rend.sequence) [
			T.th(pattern="item", render=T.directive("headCell"), 
				class_="thVertical")
		])


_htmlMetaBuilder = common.HTMLMetaBuilder()


class HTMLDataRenderer(rend.Fragment):
	"""A base class for rendering tables and table lines.

	Both HTMLTableFragment (for complete tables) and HTMLKeyValueFragment
	(for single rows) inherit from this.
	"""
	def __init__(self, table, queryMeta, yieldNowAndThen=True):
		self.table, self.queryMeta = table, queryMeta
		self.yieldNowAndThen = yieldNowAndThen
		self.fieldDefs = self.table.tableDef.columns
		super(HTMLDataRenderer, self).__init__()
		self._computeDefaultTds()
		self._computeHeadCellsStan()

	def _compileRenderer(self, source):
		"""returns a function object from source.

		Source must be the function body of a renderer.  The variable data
		contains the entire row, and the thing must return a string or at
		least stan (it can use T.tag).
		"""
		ns = dict(globals())
		ns["queryMeta"] = self.queryMeta
		ns["source"] = source
		code = ("def format(data):\n"
			"  try:\n"+
			utils.fixIndentation(source, "     ")+"\n"
			"  except:\n"
			"    sys.stderr.write('Error in\\n%s\\n'%source)\n"
			"    traceback.print_exc()\n"
			"    raise\n")
		try:
			exec code in ns
		except SyntaxError:
			sys.stderr.write("Invalid source:\n%s\n"%code)
			raise
		return ns["format"]

	def _computeDefaultTds(self):
		"""leaves a sequence of children for each row in the
		defaultTds attribute.

		It also creates the attributes serManager and colDescIndex
		that should be used to obtain the units for the respective
		columns since the formatters might have changed them.
		"""
		self.serManager = valuemappers.SerManager(self.table, withRanges=False,
			mfRegistry=_htmlMFRegistry)
		self.colDescIndex = dict((c["name"], c) for c in self.serManager)
		self.defaultTds = []
		for index, (desc, field) in enumerate(
				zip(self.serManager, self.table.tableDef)):
			formatter = self.serManager.mappers[index]
			try:
				if field.wantsRow:
					desc["wantsRow"] = True
				if field.formatter:
					formatter = self._compileRenderer(field.formatter)
			except AttributeError: # a column rather than an OutputField
				pass
			if desc.has_key("wantsRow"):
				self.defaultTds.append(
					T.td(formatter=formatter, render=T.directive("useformatter")))
			else:
				self.defaultTds.append(T.td(data=T.slot(desc["name"]),
					formatter=formatter,
					render=T.directive("useformatter")))

	def render_footnotes(self, ctx, data):
		"""renders the footnotes as a definition list.
		"""
		yield T.hr(class_="footsep")
		yield T.dl(class_="footnotes")[[
			T.xml(note.getContent(targetFormat="html"))
			for tag, note in sorted(self.serManager.notes.items())]]

	def render_useformatter(self, ctx, data):
		attrs = ctx.tag.attributes
		formatVal = attrs["formatter"]
		if formatVal is None:
			formatVal = str
		del ctx.tag.attributes["formatter"]
		return ctx.tag[formatVal(data)]

	def _computeHeadCellsStan(self):
		self.headCells = HeadCells(self.table.tableDef, self.colDescIndex)
		self.headCellsStan = T.xml(self.headCells.renderSynchronously())

	def render_headCells(self, ctx, data):
		"""returns the header line for this table as an XML string.
		"""
# The head cells are prerendered and memoized since they might occur 
# quite frequently in long tables.  Also, we return a deferred to
# give other requests a chance to be processed when we render
# huge tables.
		if self.yieldNowAndThen:
			d = defer.Deferred()
			reactor.callLater(0.05, d.callback, self.headCellsStan)
			return d
		else:
			return self.headCellsStan

	def data_fielddefs(self, ctx, data):
		return self.table.tableDef.columns

	def render_iffeedback(self, ctx, data):
		fields = self.table.tableDef.columns
		if fields and fields[0].name=="feedbackSelect":
			return ctx.tag
		else:
			return ""

	def render_meta(self, ctx, data):
		metaKey = ctx.tag.children[0]
		if self.table.getMeta(metaKey, propagate=False):
			ctx.tag.clear()
			_htmlMetaBuilder.clear()
			return ctx.tag[self.table.buildRepr(metaKey, _htmlMetaBuilder)]
		else:
			return ""


class HTMLTableFragment(HTMLDataRenderer):
	"""A nevow renderer for result tables.
	"""
	def render_defaultRow(self, ctx, items):
		return ctx.tag(render=rend.mapping)[self.defaultTds]

	def data_table(self, ctx, data):
		return self.table

	docFactory = loaders.stan(T.form(action="feedback", method="post")[
		T.div(render=T.directive("meta"), class_="warning")["_warning"],
		T.table(class_="results", render=rend.sequence,
					data=T.directive("table")) [
				T.invisible(pattern="header", render=T.directive("headCells")),
				T.tr(pattern="item", render=T.directive("defaultRow")),
				T.tr(pattern="item", render=T.directive("defaultRow"), class_="even"),
				T.invisible(pattern="divider"),  # only put a header every bla divisions
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider"),
				T.invisible(pattern="divider", render=T.directive("headCells")),
			],
			T.input(type="submit", value="Feedback Selected",
				render=T.directive("iffeedback")),
			T.invisible(render=T.directive("footnotes")),
		]
	)


class HTMLKeyValueFragment(HTMLDataRenderer, HeadCellsMixin):
	"""A nevow renderer for single-row result tables.
	"""
	def data_firstrow(self, ctx, data):
		return self.table.rows[0]

	def makeDocFactory(self):
		return loaders.stan([
			T.div(render=T.directive("meta"), class_="warning")["_warning"],
			T.table(class_="keyvalue", render=rend.mapping,
					data=T.directive("firstrow")) [
				[[T.tr[
						T.th(data=colDef, render=T.directive("headCell"),
							class_="thHorizontal"),
						td],
					T.tr(class_="keyvaluedesc")[T.td(colspan=2)[
						colDef.description]]]
					for colDef, td in zip(self.fieldDefs, self.defaultTds)]],
			T.invisible(render=T.directive("footnotes")),
			])
	
	docFactory = property(makeDocFactory)


def writeDataAsHTML(data, outputFile):
	"""writes data's primary table to outputFile.  
	"""
	fragment = HTMLTableFragment(data.getPrimaryTable(), svcs.emptyQueryMeta,
		yieldNowAndThen=False)
	outputFile.write(flat.flatten(fragment))


formats.registerDataWriter("html", writeDataAsHTML)
