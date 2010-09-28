"""
"Output drivers" for various formats, for the use of form-like renderers.
"""

import os
import urllib
import urlparse

from nevow import inevow
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E
from twisted.internet import threads


from gavo import base
from gavo import utils
from gavo.formats import csvtable
from gavo.formats import fitstable
from gavo.formats import texttable
from gavo.imp import formal
from gavo.imp.formal import types as formaltypes
from gavo.imp.formal.util import render_cssid
from gavo.svcs import customwidgets
from gavo.web import common
from gavo.web import producttar
from gavo.web import streaming


class ServiceResult(object):
	"""A base class for objects producing formatted output.

	ServiceResults are constructed with a context and the service.
	On renderHTTP, they will spawn a thread to compute the service
	result (usually, an rsc.Data instance) and hand that over
	to _formatOutput.

	All methods on these objects are class methods -- they are never
	instanciated.

	Deriving classes can override 
	
	- _formatOutput(result, ctx) -- receives the service result and
	  has to format it.
	- canWrite(table) -- a that returns true when table
	  can be serialized by this service result.
	- code -- an identifier used in HTTP query strings to select the format
	- label (optional) -- a string that is used in HTML forms to select
	  the format (defaults to label).
	- compute -- if False, at least the form renderer will not run
	  the service (this is when you just return a container).
	"""
	compute = True
	code = None
	label = None

	@classmethod
	def _formatOutput(cls, res, ctx):
		return ""

	@classmethod
	def getLabel(cls):
		if cls.label is not None:
			return cls.label
		return cls.code

	@classmethod
	def canWrite(cls, tableDef):
		return True


class VOTableResult(ServiceResult):
	"""A ResultFormatter for VOTables.

	The VOTables come as attachments, i.e., if all goes well the form
	will just stand as it is.
	"""
	code = "VOTable"

	@classmethod
	def _formatOutput(cls, data, ctx):
		request = inevow.IRequest(ctx)
		if data.queryMeta.get("Overflow"):
			fName = "truncated_votable.xml"
		else:
			fName = "votable.xml"
		request.setHeader("content-type", "application/x-votable")
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%fName)
		return streaming.streamVOTable(request, data)


tag_embed = T.Proto("embed")
tag_noembed = T.Proto("noembed")


class VOPlotResponse(rend.Page, common.CommonRenderers):
	"""returns a page embedding the VOPlot applet.
	"""
	def render_voplotArea(self, ctx, data):
		request = inevow.IRequest(ctx)
		parameters = request.args.copy()
		parameters[formal.FORMS_KEY] = "genForm"
		parameters["_FORMAT"]=["VOTable"]
		parameters["_TDENC"]=["True"]
		return ctx.tag[tag_embed(type = "application/x-java-applet",
				code="com.jvt.applets.PlotVOApplet",
				codebase=base.getConfig("web", "voplotCodebase"),
				votablepath=urlparse.urljoin(base.getConfig("web", "serverURL"),
					request.path)+"?",
				userguideURL=base.getConfig("web", "voplotUserman"),
				archive="voplot.jar",
				width="850",
				height="650",
				parameters=urllib.urlencode(parameters, doseq=True),
				MAYSCRIPT="true",
				background="#faf0e6",
				scriptable="true",
				pluginspage="http://java.sun.com/products/plugin"
					"plugin-install.html")[
					tag_noembed["You need proper Java support for VOPlot"]]]

	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["DaCHS VOPlot"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.div(class_="voplotarea", render=T.directive("voplotArea"),
				style="text-align:center"),
		]
	])


class VOPlotResult(ServiceResult):
	"""A ResultFormatter that returns a VOPlot container loading the
	current result.
	"""
	compute = False
	code = "VOPlot"

	@classmethod
	def _formatOutput(cls, data, ctx):
		return VOPlotResponse()

	@classmethod
	def getFormat(self, tableDef):
		return base.getConfig("web", "voplotCodeBase")

class FITSTableResult(ServiceResult):
	"""returns data as a FITS binary table.
	"""
	code = "FITS"
	label = "FITS table"

	@classmethod
	def getTargetName(cls, data):
		if data.queryMeta.get("Overflow"):
			return "truncated_data.fits", "application/x-fits"
		else:
			return "data.fits", "application/x-fits"

	@classmethod
	def _formatOutput(cls, data, ctx):
		return threads.deferToThread(fitstable.makeFITSTableFile, data.original
			).addCallback(cls._serveFile, data, ctx)

	@classmethod
	def _serveFile(cls, filePath, data, ctx):
		request = inevow.IRequest(ctx)
		name, mime = cls.getTargetName(data)
		request.setHeader("content-type", mime)
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%name)
		static.FileTransfer(open(filePath), os.path.getsize(filePath),
			request)
		os.unlink(filePath)
		return request.deferred


class TextResponse(ServiceResult):
	code = "TSV"
	label = "Text (with Tabs)"

	@classmethod
	def _formatOutput(cls, data, ctx):
		request = inevow.IRequest(ctx)
		content = texttable.getAsText(data.original)
		request.setHeader('content-disposition', 
			'attachment; filename=table.tsv')
		request.setHeader("content-type", "text/tab-separated-values")
		request.setHeader("content-length", len(content))
		request.write(content)
		return ""


class TarResponse(ServiceResult):
	"""delivers a tar of products requested.
	"""
	code = "tar"

	@classmethod
	def _formatOutput(cls, data, ctx):
		queryMeta = data.queryMeta
		request = inevow.IRequest(ctx)
		return producttar.getTarMaker().deliverProductTar(
			data, request, queryMeta)

	@classmethod
	def canWrite(cls, tableDef):
		if tableDef.getProductColumns():
			return True
		return False


################# Helpers


_getFormat = utils.buildClassResolver(ServiceResult, 
	globals().values(), key=lambda obj: obj.code)


def getFormat(formatName):
	try:
		return _getFormat(formatName)
	except KeyError, ex:
		raise base.ValidationError("Unknown format '%s'."%formatName,
			"_OUTPUT")


class OutputFormat(object):
	"""is a widget that offers various output options in close cooperation
	with gavo.js and QueryMeta.

	The javascript provides options for customizing output that non-javascript
	users will not see.  Also, formal doesn't see any of these.  See gavo.js
	for details.

	This widget probably only makes sense in the Form renderer and thus
	should probably go there.
	"""
	def __init__(self, typeOb, service, queryMeta):
		self.service = service
		self.typeOb = typeOb
		self._computeAvailableFields(queryMeta)
		self._computeAvailableFormats(queryMeta)

	def _computeAvailableFormats(self, queryMeta):
		"""sets the availableFormats property.

		It contains a list of strings of possible output formats.  Since
		OutputFormat is rendered by resourcebased.Form, this is pretty
		much constant; we add tar if the service delivers products.
		"""
		self.availableFormats = [
			(code, format.getLabel())
				for code, format in _getFormat.registry.iteritems()
				if format.canWrite(self.service.outputTable)]
		
	def _computeAvailableFields(self, queryMeta):
		"""computes the fields a Core provides but are not output by
		the service by default.

		This of course only works if the core defines its output table.
		Otherwise, availableFields is an empty list.
		"""
		self.availableFields = []
		core = self.service.core
		if not core.outputTable or self.service.getProperty("noAdditionals", False):
			return
		coreNames = set(f.name for f in core.outputTable)
		defaultNames = set([f.name
			for f in self.service.getHTMLOutputFields(queryMeta, 
				ignoreAdditionals=True)])
		selectedFields = set(queryMeta["additionalFields"])
		for key in coreNames-defaultNames:
			try:
				self.availableFields.append((core.outputTable.getColumnByName(key),
					key in queryMeta["additionalFields"]))
			except KeyError: # Core returns fields not in its table, 
		                   # probably computes them
				pass

	def _makeAdditionalSelector(self):
		"""returns an ul element containing form material for additional output
		columns.
		"""
		checkLiterals = {True: "checked", False: None}
		fields = [] 
		for column, checked in sorted(
				self.availableFields, key=lambda p:p[0].name):
			fields.append(T.tr[
				T.td[
					T.input(type="checkbox", name="_ADDITEM", value=column.name,
						style="width:auto",
						checked=checkLiterals[checked])],
				T.td(style="vertical-align:middle")[
					" %s -- %s"%(column.name, column.description)]])
		return T.table(id="addSelection")[fields]

	def render(self, ctx, key, args, errors):
		res = T.div(id=render_cssid("_OUTPUT"), style="position:relative")[
			customwidgets.SelectChoice(formaltypes.String(), 
				options=self.availableFormats,
				noneOption=("HTML", "HTML")).render(ctx, "_FORMAT", args, errors)(
					onchange="output_broadcast(this.value)")]
		if self.availableFields:
			res[
				T.div(title="Additional output column selector", 
					id=render_cssid("_ADDITEMS"),
					style="visibility:hidden;position:absolute;")[
							self._makeAdditionalSelector()]]
		return res
	
	renderImmutable = render  # This is a lost case

	def processInput(self, ctx, key, args):
		return args.get("_FORMAT", ["HTML"])[0]
