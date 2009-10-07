"""
A renderer for DataSets to HTML/stan
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

from nevow import rend
from nevow import loaders
from nevow import tags as T, entities as E

from twisted.internet import reactor, defer

from gavo import base
from gavo import utils
from gavo.base import coords
from gavo.base import valuemappers
from gavo.rscdef import rmkfuncs
from gavo.web import common


_htmlMFRegistry = valuemappers.ValueMapperFactoryRegistry()
_registerHTMLMF = _htmlMFRegistry.registerFactory


def _defaultMapperFactory(colProps):
	def coder(val):
		if val is None:
			return "N/A"
		return unicode(val)
	return coder
_registerHTMLMF(_defaultMapperFactory)


# insert new general factories here

floatTypes = set(["real", "float", "double", "double precision"])

def _sfMapperFactory(colProps):
	if colProps["dbtype"] not in floatTypes:
		return
	if colProps["displayHint"].get("sf"):
		fmtStr = "%%.%df"%int(colProps["displayHint"].get("sf"))
		def coder(val):
			if val is None:
				return "N/A"
			else:
				return fmtStr%val
		return coder
_registerHTMLMF(_sfMapperFactory)


def _hmsMapperFactory(colProps):
	if ((colProps["unit"]!="hms" 
			and colProps["displayHint"].get("type")!="time")
		or colProps["datatype"]=="char"):
		return
	colProps["unit"] = "hms"
	sepChar = colProps["displayHint"].get("sepChar", " ")
	sf = int(colProps["displayHint"].get("sf", 2))
	def coder(val):
		if val is None:
			return "N/A"
		else:
			return utils.degToHms(val, sepChar, sf)
	return coder
_registerHTMLMF(_hmsMapperFactory)


def _sexagesimalMapperFactory(colProps):
	if ((colProps["unit"]!="dms" 
			and colProps["displayHint"].get("type")!="sexagesimal")
		or colProps["datatype"]=="char"):
		return
	colProps["unit"] = "dms"
	sepChar = colProps["displayHint"].get("sepChar", " ")
	sf = int(colProps["displayHint"].get("sf", 2))
	def coder(val):
		if val is None:
			return "N/A"
		return utils.degToDms(val, sepChar, sf)
	return coder
_registerHTMLMF(_sexagesimalMapperFactory)

def _unitMapperFactory(colProps):
	"""returns a factory that converts between units for fields that have
	a displayUnit displayHint.

	The stuff done here has to be done for all factories handling unit-based
	floating point values.  Maybe we want to do "decorating" meta-factories?
	"""
	if colProps["displayHint"].get("displayUnit") and \
			colProps["displayHint"]["displayUnit"]!=colProps["unit"]:
		factor = base.computeConversionFactor(colProps["unit"], 
			colProps["displayHint"]["displayUnit"])
		colProps["unit"] = colProps["displayHint"]["displayUnit"]
		fmtStr = "%%.%df"%int(colProps["displayHint"].get("sf", 2))
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
	def factory(colProps):
		handler = baseMF(colProps)
		if colProps["displayHint"].get("sf", None):
			fmtstr = "%%.%df"%int(colProps["displayHint"]["sf"])
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


def humanDatesFactory(colProps):
	format, unit = {"humanDatetime": ("%Y-%m-%d %H:%M:%S", "Y-M-D h:m:s"),
		"humanDate": ("%Y-%m-%d", "Y-M-D"), }.get(
			colProps["displayHint"].get("type"), (None, None))
	if format and isinstance(colProps["sample"], datetime.date):
		colProps["unit"] = unit
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


def humanTimesFactory(colProps):
	if (colProps["displayHint"].get("type")=="humanTime" and
			isinstance(colProps["sample"], (datetime.timedelta, datetime.time))):
		sf = int(colProps["displayHint"].get("sf", 0))
		fmtStr = "%%02d:%%02d:%%0%d.%df"%(sf+3, sf)
		if isinstance(colProps["sample"], datetime.time):
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


def _sizeMapperFactory(colProps):
	"""is a factory for formatters for file sizes and similar.
	"""
	if colProps["unit"]!="byte":
		return
	sf = int(colProps["displayHint"].get("sf", 1))
	def coder(val):
		return utils.formatSize(val, sf)
	return coder
_registerHTMLMF(_sizeMapperFactory)


def _barMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="bar":
		return
	def coder(val):
		if val:
			return T.hr(style="width: %dpx"%int(val), title="%.2f"%val,
				class_="scoreBar")
		return ""
	return coder
_registerHTMLMF(_barMapperFactory)


def _productMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="product":
		return
	if colProps["displayHint"].get("nopreview"):
		mouseoverHandler = None
	else:
		try:
			pWidth = int(colProps["displayHint"].get("width", "200"))
		except ValueError:
			pWidth = 200
		mouseoverHandler = "insertPreview(this, %s)"%pWidth
	fixedArgs = ""
	def coder(val):
		if val:
			return T.a(href=base.makeSitePath(
#					"/__system__/products/products/p/get?key=%s%s"%(urllib.quote(val), fixedArgs)),
					"/getproduct?key=%s%s"%(urllib.quote(val), fixedArgs)),
				onmouseover=mouseoverHandler,
				class_="productlink")[re.sub("&.*", "", os.path.basename(val))]
		else:
			return ""
	return coder
_registerHTMLMF(_productMapperFactory)


def _simbadMapperFactory(colProps):
	"""is a mapper yielding links to simbad.

	To make this work, you need to furnish the OutputField with a
	select="array[alphaFloat, deltaFloat]" or similar.

	You can give a coneMins displayHint to specify the search radius in
	minutes.
	"""
	if colProps["displayHint"].get("type")!="simbadlink":
		return
	radius = float(colProps["displayHint"].get("coneMins", "1"))
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


def _feedbackSelectMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="feedbackSelect":
		return
	def coder(data):
		return T.input(type="checkbox", name="feedbackSelect", 
			value=data)
	return coder
_registerHTMLMF(_feedbackSelectMapperFactory)


def _bibcodeMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="bibcode":
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


def _keepHTMLMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="keephtml":
		return
	def coder(data):
		if data:
			return T.raw(data)
		return ""
	return coder
_registerHTMLMF(_keepHTMLMapperFactory)


def _urlMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="url":
		return
	def coder(data):
		if data:
			return T.a(href=data)[urlparse.urlparse(data)[2].split("/")[-1]]
		return ""
	return coder
_registerHTMLMF(_urlMapperFactory)

#  Insert new, more specific factories here


def makeCutoutURL(accref, ra, dec, sra, sdec):
	key = (accref+"&amp;ra=%s&amp;dec=%s&amp;sra=%s"
		"&amp;sdec=%s"%(ra, dec, sra, sdec))
	return base.makeSitePath("/getproduct?key="+urllib.quote(key))


class HeadCellsMixin(object):
	"""A mixin providing renders for table headings.

	The class mixing in must provide the table column definitions as
	self.fieldDefs, and the column properties as computed by
	HTMLDataRenderer as colPropsIndex.  HTMLDataRenderers already do
	that.
	"""
	def data_fielddefs(self, ctx, ignored):
		return self.fieldDefs

	def render_headCell(self, ctx, fieldDef):
		props = self.colPropsIndex[fieldDef.name]
		cont = fieldDef.tablehead
		if cont is None:
			cont = props["description"]
		if cont is None:
			cont = fieldDef.name
		desc = props["description"]
		if desc is None:
			desc = cont
		tag = ctx.tag(title=desc)[T.xml(cont)]
		if props["unit"]:
			tag[T.br, "[%s]"%props["unit"]]
		if fieldDef.note is not None and fieldDef.parent:
			noteURL = base.makeSitePath(
				"/tablenote/%s"%(urllib.quote(fieldDef.note)))
			tag[T.br, 
				T.a(href=noteURL, onclick="return bubbleUpByURL(this, '%s')"%noteURL)[
						"Note"]]
		return tag


class HeadCells(rend.Page, HeadCellsMixin):
	def __init__(self, fieldDefs, colPropsIndex):
		self.fieldDefs = fieldDefs
		self.colPropsIndex = colPropsIndex

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
	def __init__(self, table, queryMeta):
		self.table, self.queryMeta = table, queryMeta
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

		It also creates the attributes colProps and colPropsIndex
		that should be used to obtain the units for the respective
		columns since the formatters might have changed them.
		"""
		self.colProps = [valuemappers.ColProperties(f)
			for f in self.table.tableDef]
		self.colPropsIndex = dict((props["name"], props) 
			for props in self.colProps)
		valuemappers.acquireSamples(self.colPropsIndex, self.table)
		self.defaultTds = []
		for props, field in zip(self.colProps, self.table.tableDef):
			if field.wantsRow:
				props["wantsRow"] = True
			if field.formatter:
				formatter = self._compileRenderer(field.formatter)
			else:
				formatter=_htmlMFRegistry.getMapper(props) # This may change props!
			if props.has_key("wantsRow"):
				self.defaultTds.append(
					T.td(formatter=formatter, render=T.directive("useformatter")))
			else:
				self.defaultTds.append(T.td(data=T.slot(props["name"]),
					formatter=formatter,
					render=T.directive("useformatter")))

	def render_useformatter(self, ctx, data):
		attrs = ctx.tag.attributes
		formatVal = attrs["formatter"]
		if formatVal is None:
			formatVal = str
		del ctx.tag.attributes["formatter"]
		return ctx.tag[formatVal(data)]

	def _computeHeadCellsStan(self):
		self.headCells = HeadCells(self.table.tableDef,
				self.colPropsIndex)
		self.headCellsStan = T.xml(self.headCells.renderSynchronously())

	def render_headCells(self, ctx, data):
		"""returns the header line for this table as an XML string.
		"""
# The head cells are prerendered and memoized since they might occur 
# quite frequently in long tables.  Also, we return a deferred to
# give other requests a chance to be processed when we render
# huge tables.
		d = defer.Deferred()
		reactor.callLater(0.05, d.callback, self.headCellsStan)
		return d

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
					for colDef, td in zip(self.fieldDefs, self.defaultTds)]]])
	
	docFactory = property(makeDocFactory)
