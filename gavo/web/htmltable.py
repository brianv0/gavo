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
from gavo.web import common


class FormatterFactory:
	"""is a factory for functions mapping values to stan elements representing
	those values in HTML tables.
	"""
	def __call__(self, format, args):
		return getattr(self, "_make_%s_formatter"%format)(*args)

	def _make_product_formatter(self):
		from nevow import url
		def format(val):
			if val==None:
				return ""
			else:
				return T.a(href=common.makeSitePath(
						"/getproduct?key=%s&siap=true"%urllib.quote(val)),
					class_="productlink")[re.sub("&.*", "", os.path.basename(val))]
		return format

	def _make_filesize_formatter(self):
		return str

	def _make_string_formatter(self):
		return str

	def _make_hourangle_formatter(self, secondFracs=2):
		def format(deg):
			"""converts a float angle in degrees to an hour angle.
			"""
			if deg==None:
				return "N/A"
			rest, hours = math.modf(deg/360.*24)
			rest, minutes = math.modf(rest*60)
			return "%d %02d %02.*f"%(int(hours), int(minutes), secondFracs, rest*60)
		return format
	
	def _make_sexagesimal_formatter(self, secondFracs=1):
		def format(deg):
			"""converts a float angle in degrees to a sexagesimal angle.
			"""
			if deg==None:
				return "N/A"
			rest, degs = math.modf(deg)
			rest, minutes = math.modf(rest*60)
			return "%+d %02d %02.*f"%(int(degs), abs(int(minutes)), secondFracs,
				abs(rest*60))
		return format

	def _make_date_formatter(self, dateFormat="iso"):
		def format(date):
			if date==None:
				return "N/A"
			return date.strftime("%Y-%m-%d")
		return format

	def _make_juliandate_formatter(self, fracFigs=1):
		def format(date):
			if date==None:
				return "N/A"
			return date.jdn
		return format

	def _make_mjd_formatter(self, fracFigs=1):
		def format(date):
			if date==None:
				return "N/A"
			return date.jdn-2400000.5
		return format

	def _make_suppress_formatter(self):
		def format(val):
			return T.span(style="color:#777777")[str(val)]


class HtmlTableFragment(rend.Fragment):
	"""is an HTML renderer for gavo Tables.
	"""
	def __init__(self, table):
		self.table = table
		super(HtmlTableFragment, self).__init__()
		self.formatterFactory = FormatterFactory()

	def _makeFormatFunction(self, hint):
		if hint==None:
			return str
		parts = hint.split(",")
		return self.formatterFactory(parts[0], map(eval, parts[1:]))

	def render_usehint(self, ctx, data):
		atts = ctx.tag.attributes
		formatVal = atts.get("formatter", None)
		if formatVal==None:
			formatVal = self._makeFormatFunction(atts.get("hint", None))
		if atts.has_key("formatter"): del ctx.tag.attributes["formatter"]
		if atts.has_key("hint"): del ctx.tag.attributes["hint"]
		return ctx.tag[formatVal(data)]

	def render_headCell(self, ctx, fieldDef):
		cont = fieldDef.get_tablehead()
		if cont==None:
			cont = fieldDef.get_description()
		if cont==None:
			cont = fieldDef.get_dest()
		desc = fieldDef.get_description()
		if desc==None:
			desc = cont
		return ctx.tag(title=desc)[T.xml(cont)]

	def render_defaultRow(self, ctx, items):
		for f in self.table.getFieldDefs():
			ctx.tag(render=rend.mapping)[T.td(data=T.slot(f.get_dest()), 
				formatter=self._makeFormatFunction(f.get_displayHint()), 
				render=T.directive("usehint"))]
		return ctx.tag

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
