"""
A renderer for DataSets to HTML/stan
"""

import math
import re
import urlparse
import urllib
import os

from nevow import rend
from nevow import loaders
from nevow import tags as T, entities as E

from gavo import config
from gavo import coords
from gavo import unitconv
from gavo import votable
from gavo.web import common


_htmlMFRegistry = votable.ValueMapperFactoryRegistry()
_registerHTMLMF = _htmlMFRegistry.registerFactory


def _defaultMapperFactory(colProps):
	def coder(val):
		if val==None:
			return "N/A"
		return str(val)
	return coder
_registerHTMLMF(_defaultMapperFactory)


# insert new general factories here

def _unitMapperFactory(colProps):
	"""returns a factory that converts between units for fields that have
	a displayUnit displayHint.

	The stuff done here has to be done for all factories handling unit-based
	floating point values.  Maybe we want to do "decorating" meta-factories?
	"""
	if colProps["displayHint"].get("displayUnit") and \
			colProps["displayHint"]["displayUnit"]!=colProps["unit"]:
		factor = unitconv.getFactor(colProps["unit"], 
			colProps["displayHint"]["displayUnit"])
		colProps["unit"] = colProps["displayHint"]["displayUnit"]
		fmtStr = "%%.%dg"%int(colProps["displayHint"].get("sf", 2))
		def coder(val):
			if val==None:
				return "N/A"
			return fmtStr%(val*factor)
		return coder
_registerHTMLMF(_unitMapperFactory)


def _hourangleMapperFactory(colProps):
	if (colProps["unit"]!="hms" and 
			colProps["displayHint"].get("type")!="hourangle"):
		return
	colProps["unit"] = "hms"
	sepChar = colProps["displayHint"].get("sepChar", " ")
	sf = int(colProps["displayHint"].get("sf", 2))
	def coder(val):
		if val==None:
			return "N/A"
		else:
			return coords.degToHourangle(val, sepChar, sf)
	return coder
_registerHTMLMF(_hourangleMapperFactory)

def _sexagesimalMapperFactory(colProps):
	if (colProps["unit"]!="dms" and 
			colProps["displayHint"].get("type")!="sexagesimal"):
		return
	colProps["unit"] = "dms"
	sepChar = colProps["displayHint"].get("sepChar", " ")
	sf = int(colProps["displayHint"].get("sf", 2))
	def coder(val):
		if val==None:
			return "N/A"
		return coords.degToDms(val, sepChar, sf)
	return coder
_registerHTMLMF(_sexagesimalMapperFactory)


def _stringWrapMF(baseMF):
	"""returns a factory that returns None when baseMF does but stringifies
	any results from baseMF's handlers if they fire.
	"""
	def factory(colProps):
		fmtstr = "%s"
		if colProps["displayHint"].get("sf"):
			fmtstr = "%%.%df"%int(colProps["displayHint"]["sf"])
		handler = baseMF(colProps)
		if handler:
			return lambda val: fmtstr%(handler(val))
	return factory


try:
	_registerHTMLMF(_stringWrapMF(votable.mxDatetimeMapperFactory))
except AttributeError:
	pass
_registerHTMLMF(_stringWrapMF(votable.datetimeMapperFactory))


def _sizeMapperFactory(colProps):
	"""is a factory for formatters for file sizes and similar.
	"""
	if colProps["unit"]!="byte":
		return
	sf = int(colProps["displayHint"].get("sf", 1))
	def coder(val):
		if val<1e3:
			return "%d"%int(val)
		elif val<1e6:
			return "%.*fk"%(sf, val/1024.)
		elif val<1e9:
			return "%.*fM"%(sf, val/1024./1024.)
		else:
			return "%.*fG"%(sf, val/1024./1024./1024)
_registerHTMLMF(_sizeMapperFactory)


def _productMapperFactory(colProps):
	if colProps["displayHint"].get("type")!="product":
		return
	def coder(val):
		if val:
			return T.a(href=common.makeSitePath(
					"/getproduct?key=%s&siap=true"%urllib.quote(val)),
				class_="productlink")[re.sub("&.*", "", os.path.basename(val))]
		else:
			return ""
	return coder
_registerHTMLMF(_productMapperFactory)


#  Insert new, more specific factories here


class HTMLTableFragment(rend.Fragment):
	"""is an HTML renderer for gavo Tables.
	"""
	def __init__(self, table):
		self.table = table
		super(HTMLTableFragment, self).__init__()
		self._computeDefaultTds()

	def _computeDefaultTds(self):
		"""leaves a sequence of children for each row in the
		defaultTds attribute.

		It also creates the attributes colProps and colPropsIndex
		that should be used to obtain the units for the respective
		columns since the formatters might have changed them.
		"""
		self.colProps = [votable.ColProperties(f)
			for f in self.table.getFieldDefs()]
		self.colPropsIndex = dict((props["name"], props) 
			for props in self.colProps)
		votable.acquireSamples(self.colPropsIndex, self.table)
		self.defaultTds = [T.td(data=T.slot(props["name"]),
				formatter=_htmlMFRegistry.getMapper(props),
				render=T.directive("useformatter"))
			for props in self.colProps]

	def render_useformatter(self, ctx, data):
		attrs = ctx.tag.attributes
		formatVal = attrs.get("formatter", None)
		if formatVal==None:
			formatVal = str
		del ctx.tag.attributes["formatter"]
		return ctx.tag[formatVal(data)]

	def render_headCell(self, ctx, fieldDef):
		props = self.colPropsIndex[fieldDef.get_dest()]
		cont = fieldDef.get_tablehead()
		if cont==None:
			cont = props["description"]
		if cont==None:
			cont = fieldDef.get_dest()
		desc = props["description"]
		if desc==None:
			desc = cont
		unit = props["unit"]
		if unit:
			return ctx.tag(title=desc)[T.xml(cont), T.br, "[%s]"%unit]
		else:
			return ctx.tag(title=desc)[T.xml(cont)]

	def render_defaultRow(self, ctx, items):
		return ctx.tag(render=rend.mapping)[self.defaultTds]

	def data_table(self, ctx, data):
		return self.table

	def data_fielddefs(self, ctx, data):
		return self.table.getFieldDefs()

	docFactory = loaders.stan(T.table(class_="results")[
		T.tr(data=T.directive("fielddefs"), render=rend.sequence) [
			T.th(pattern="item", render=T.directive("headCell"))
		],
		T.invisible(
				render=rend.sequence,
				data=T.directive("table")) [
			T.tr(pattern="item", render=T.directive("defaultRow")),
			T.tr(pattern="item", render=T.directive("defaultRow"), class_="even"),
		]
	])
