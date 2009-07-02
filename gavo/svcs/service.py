"""
Services.

A Service is something that receives some sort of structured data (typically,
a nevow context, processes it into input data using a grammar (default is
the contextgrammar), pipes it through a core to receive a data set and
optionally tinkers with that data set.
"""

import cStringIO
import os
import weakref

from nevow import inevow
from nevow import tags as T, entities as E
from twisted.internet import defer
from twisted.python import components

from zope.interface import implements

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import utils
from gavo.base import meta
from gavo.rsc import table
from gavo.rscdef import rmkdef
from gavo.svcs import common
from gavo.svcs import core
from gavo.svcs import inputdef
from gavo.svcs import outputdef
from gavo.svcs import standardcores


def adaptTable(origTable, newColumns):
	"""returns an InMemoryTable created from origTable with columns taken from
	newColumns.

	The adaptation works like this:

	(1) if names and units of newColumns are a subset of origTable.columns,
	return a table with the rows from origTable and the columns from
	newColumns.

	(1a) if origTable has a noPostprocess attribute, proceed to (4)

	(2) if names of newColumns are a subset of origTable.columns match
	but one or more units don't, set up a conversion routine and create
	new rows, combining them with newColumns to the result.

	(3) else raise an error.

	(4) Finally, stick the whole thing into a data container.
	"""
	if hasattr(origTable, "noPostprocess"):
		colDiffs = None
		newTd = origTable.tableDef
	else:
		colDiffs = base.computeColumnConversions(
			newColumns, origTable.tableDef.columns)
		newTd = origTable.tableDef.copy(origTable.tableDef.parent)
		newTd.columns = newColumns
	if not colDiffs:
		newTable = table.InMemoryTable(newTd, rows=origTable.rows)
		newTable.meta_ = origTable.meta_
	else: # we need to do work
		rmk = rscdef.RowmakerDef(None)
		for col in newColumns:
			if col.name in colDiffs:
				rmk.feedObject("map", rmkdef.MapRule(rmk, dest=col.name,
					content_="%s*%s"%(colDiffs[col.name], col.name)
					).finishElement())
			else:
				rmk.feedObject("map", rmkdef.MapRule(rmk, dest=col.name,
					content_=col.name))
		newTable = table.InMemoryTable(newTd, validate=False)
		mapper = rmk.finishElement().compileForTable(newTable)
		for r in origTable:
			newTable.addRow(mapper(r))
	newDD = rscdef.DataDescriptor(origTable.tableDef.rd, tables=[newTd])
	return rsc.Data(newDD, tables={newTable.tableDef.id: newTable})


class SvcResult(object):
	"""is a nevow.IContainer that has the result and also makes the
	input dataset accessible.

	It is constructed with an InMemoryTable instance coreResult,
	a data instance inputData, the current querymeta, and a service
	instance.

	If a service is defined, SvcResult adapts coreResult to the
	columns defined by the service (getCurOutputFields).

	Original currently either is an InMemory table, in which case it gets
	adapted to what the service expects, or a data.Data instance (or
	something else), which are left alone, but currently can't be used
	to render HTMLTables.

	SvcResult also makes queryMeta, inputData and the service available.	This
	should give renderers access to basically all the information they need.  The
	resultmeta data item collects some of those.

	SvcResult objects must be able to fall back to sensible behaviour
	without a service.  This may be necessary in error handling.
	"""
	implements(inevow.IContainer)
	
	def __init__(self, coreResult, inputData, queryMeta, service=None):
		self.queryPars = queryMeta["formal_data"]
		self.inputData = inputData
		self.queryMeta = queryMeta
		self.service = service
		if (service and isinstance(coreResult, rsc.BaseTable)):
			coreResult = adaptTable(coreResult, 
				service.getCurOutputFields(queryMeta))
		self.original = coreResult

	def data_resultmeta(self, ctx):
		resultmeta = {
			"itemsMatched": self.queryMeta.get("Matched", 
				len(self.original.getPrimaryTable())),
			"Overflow": self.queryMeta.get("Overflow", False),
			"message": "",
		}
		return resultmeta

	def data_querypars(self, ctx=None):
		return dict((k, str(v)) for k, v in self.queryPars.iteritems()
			if not k in common.QueryMeta.metaKeys and v and v!=[None])

	suppressedParNames = set(["submit"])
		
	def data_queryseq(self, ctx=None):
		if self.service:
			fieldDict = dict((f.name, f) 
				for f in self.service.getInputFields())
		else:
			fieldDict = {}

		def getTitle(key):
			title = None
			if key in fieldDict:
				title = fieldDict[key].tablehead
			return title or key
		
		s = [(getTitle(k), v) for k, v in self.data_querypars().iteritems()
			if k not in self.suppressedParNames and not k.startswith("_")]
		s.sort()
		return s

	def data_inputRec(self, ctx=None):
		try:
			row = self.inputData.getTableWithRole("parameters").rows[0]
			return row
		except (AttributError, IndexError): # No or empty parameters table
			return {}

	def data_table(self, ctx=None):
		return self.original.getPrimaryTable()

	def child(self, ctx, name):
		return getattr(self, "data_"+name)(ctx)


class Publication(base.Structure):
	"""A specification of how a service should be published.
	"""
	name_ = "publish"

	_rd = rscdef.RDAttribute()
	_render = base.UnicodeAttribute("render", default=base.Undefined,
		description="The renderer the publication will point at.")
	_sets = base.StringListAttribute("sets", default="local",
		description="Comma-separated list of sets this service will be"
			" published in.  Predefined are: local=publish on front page,"
			" ivo_managed=register with the VO registry")

	def completeElement(self):
		if self.render is base.Undefined:
			self.renderer = "form"


class CustomRF(base.Structure):
	"""A custom render function for a service.

	Custom render functions can be used to expose certain aspects of a service
	to Nevow templates.  Thus, their definition usually only makes sense with
	custom templates, though you could, in principle, override built-in
	render functions.

	In the render functions, you have the names ctx for nevow's context and
	data for whatever data the template passes to the renderer. 

	You can return anything that can be in a stan DOM.  Usually, this will be
	a string.  To return HTML, use the stan DOM available under the T namespace.

	As an example, the following code returns the current data as a link::

		return ctx.data[T.a(href=data)[data]]
	"""
	name_ = "customRF"
	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="Name of the render function (use this in the"
			" n:render attribute in custom templates).", copyable=True)
	_code = base.DataContent(description="Function body of the renderer; the"
		" arguments are named ctx and data.", copyable=True)

	def onElementComplete(self):
		self._onElementCompleteNext(CustomRF)
		vars = globals()
		exec ("def %s(ctx, data):\n%s"%(self.name,
				utils.fixIndentation(self.content_, newIndent="  ",
					governingLine=1).rstrip())) in vars
		self.func = vars[self.name]
	

class Service(base.Structure, base.ComputedMetaMixin, 
		rscdef.StandardMacroMixin):
	"""A service definition.

	A service is a combination of a core and one or more renderers.  They
	can be published, and they carry the metadata published into the VO.
	"""
	name_ = "service"

	# formats that should query the same fields as HTML (the others behave
	# like VOTables and offer a "verbosity" widget in forms).
	htmlLikeFormats = ["HTML", "tar"]

	_core = base.ReferenceAttribute("core", description="The core that"
		" does the computations for this service.", forceType=core.Core,
		copyable=True)
	_templates = base.DictAttribute("templates", description="Custom"
		" nevow templates for this service.", 
		itemAttD=rscdef.ResdirRelativeAttribute(
			"template", description="resdir-relative path to a nevow template"
			" used for the function given in key.  Currently, the form renderer"
			" uses 'form' and 'response' as keys."), copyable=True)
	_publications = base.StructListAttribute("publications",
		childFactory=Publication, description="Sets and renderers this service"
			" is published with.")
	_limitTo = base.UnicodeAttribute("limitTo", default=None,
		description="Limit access to the group given; the empty default disables"
		" access control.", copyable="True")
	_staticData = rscdef.ResdirRelativeAttribute("staticData",
		default=None, description="resdir-relative path to static data.  This"
		" is used by the static renderer.", copyable=True)
	_customPage = rscdef.ResdirRelativeAttribute("customPage", default=None,
		description="resdir-relative path to custom page code.  It is used"
		" by the 'custom' renderer", copyable="True")
	_allowedRenderers = base.StringSetAttribute("allowed",
		description="Names of renderers allowed on this service; leave emtpy"
		" to allow the form renderer only.", copyable=True)
	_customRF = base.StructListAttribute("customRFs",
		description="Custom render functions for use in custom templates.",
		childFactory=CustomRF, copyable=True)
	_inputData = base.StructAttribute("inputDD", default=base.NotGiven,
		childFactory=inputdef.InputDescriptor, description="A data descriptor"
			" for obtaining the core's input, usually based on a contextGrammar."
			"  For many cores (e.g., DBCores), you do not want to give this"
			" but rather want to let service figure this out from the core.",
		copyable=True)
	_outputTable = base.StructAttribute("outputTable", default=base.NotGiven,
		childFactory=outputdef.OutputTableDef, copyable=True, description=
		"The output fields of this service.")
	_serviceKeys = base.StructListAttribute("serviceKeys",
		childFactory=inputdef.InputKey, description="Input widgets for"
			" processing by the service, e.g. output sets.", copyable=True)
	_rd = rscdef.RDAttribute()
	_props = base.PropertyAttribute()
	_original = base.OriginalAttribute()

	def completeElement(self):
		self._completeElementNext(Service)
		if not self.allowed:
			self.allowed.add("form")
		# undefined cores are only allowed with custom pages.
		if self.core is base.Undefined and self.customPage:
			self.core = core.getCore("staticCore")(self.rd,
				file=None).finishElement()
			

	def onElementComplete(self):
		self._onElementCompleteNext(Service)

		# Fill in missing I/O definitions from core
		if self.inputDD is base.NotGiven:
			self.inputDD = self.core.inputDD
		if self.outputTable is base.NotGiven:
			self.outputTable = self.core.outputTable

		# Load local templates if necessary
		if self.templates:
			from nevow import loaders
			for key, tp in self.templates.iteritems():
				if isinstance(tp, basestring):
					self.templates[key] = loaders.xmlfile(
						os.path.join(self.rd.resdir, tp))

		# Index custom render functions
		self.nevowRenderers = {}
		for customRF in self.customRFs:
			self.nevowRenderers[customRF.name] = customRF.func

		# compile custom page if present
		if self.customPage:
			try:
				modNs, moddesc = utils.loadPythonModule(self.customPage)
				page = modNs.MainPage
			except ImportError:
				import traceback
				traceback.print_exc()
				raise base.LiteralParseError("Custom page missing or bad: %s"%
					self.customPage, "customPage", self.customPage)
			self.customPageCode = page, (os.path.basename(self.customPage),)+moddesc

	def __repr__(self):
		return "<Service at %x>"%id(self)

	def _getVOTableOutputFields(self, queryMeta):
		"""returns a list of OutputFields suitable for a VOTable response 
		described by queryMeta
		"""
		verbLevel = queryMeta.get("verbosity", 20)
		if verbLevel=="HTML":
			fieldList = rscdef.ColumnList([
					f for f in self.getHTMLOutputFields(queryMeta)
				if f.displayHint.get("noxml")!="true"])
		else:
			baseFields = self.core.outputTable.columns
			fieldList = rscdef.ColumnList([f for f in baseFields
				if f.verbLevel<=verbLevel and 
					f.displayHint.get("type")!="suppress" and
					f.displayHint.get("noxml")!="true"])
		return fieldList

	_allSet = set(["ALL"])

	def getHTMLOutputFields(self, queryMeta, ignoreAdditionals=False,
			raiseOnUnknown=True):
		"""returns a list of OutputFields suitable for an HTML response described
		by queryMeta.

		raiseOnUnknown is used by customwidgets to avoid exceptions because of
		bad additional fields during form construction (when they aren't
		properly caught.
		"""
		requireSet = queryMeta["columnSet"]
		res = rscdef.ColumnList()

		# prepare for feedback queries if the core want that
		if isinstance(self.core, standardcores.DBCore) and self.core.feedbackColumn:
			res.append(standardcores.makeFeedbackColumn(
				self.core.queriedTable.columns, self.core.feedbackColumn))

		# add "normal" output fields
		if requireSet:
			res.extend([f for f in self.outputTable
					if f.sets==self._allSet or requireSet in f.sets])
		else:
			res.extend([f for f in self.outputTable
				if f.displayHint.get("type")!="suppress"])

		# add user-selected fields
		if not ignoreAdditionals and queryMeta["additionalFields"]:
			cofs = self.core.outputTable.columns
			try:
				for fieldName in queryMeta["additionalFields"]:
					res.append(outputdef.OutputField.fromColumn(
						cofs.getColumnByName(fieldName)))
			except KeyError, msg:
				if raiseOnUnknown:
					raise base.ValidationError("The additional field %s you requested"
						" does not exist"%str(msg), colName="_OUTPUT")
		return res

	def getCurOutputFields(self, queryMeta=None, raiseOnUnknown=True):
		"""returns a list of desired output fields for query meta.

		This is for both the core and the formatter to figure out the
		structure of the tables passed.

		If queryMeta is not None, both the format and the verbLevel given
		there can influence this choice.
		"""
		queryMeta = queryMeta or common.emptyQueryMeta
		format = queryMeta.get("format", "HTML")
		if format in self.htmlLikeFormats:
			return self.getHTMLOutputFields(queryMeta, raiseOnUnknown=raiseOnUnknown)
		else:
			return self._getVOTableOutputFields(queryMeta)

	def getInputFields(self):
		return self.inputDD.grammar.inputKeys

	def getInputData(self, rawInput):
		"""returns a data instance appropriate for the core.
		"""
		return rsc.makeData(self.inputDD, parseOptions=rsc.parseValidating,
			forceSource=rawInput)

	def run(self, data, queryMeta):
		"""runs the service, returning a ServiceResult.

		data is some valid input to a ContextGrammar.
		"""
		inputData = self.getInputData(data)
		coreRes = self.core.run(self, inputData, queryMeta)
		return SvcResult(coreRes, inputData, queryMeta, self)

	def runFromDictlike(self, dictlike):
		queryMeta = common.QueryMeta(dictlike)
		return self.run(dictlike, queryMeta)

	def runFromContext(self, data, ctx):
		"""runs the service with a nevow context (or similar) as input, returning 
		a ServiceResult.

		data is some valid input to a ContextGrammar.
		"""
		queryMeta = common.QueryMeta.fromContext(ctx)
		queryMeta["formal_data"] = data
		return self.run(data, queryMeta)
	
	def getURL(self, renderer, method="POST", includeServerURL=True):
		"""returns the full canonical access URL of this service together 
		with renderer.
		"""
		qSep = ""
		if method=="GET":
			qSep = "?"
		elif renderer=="soap":
			qSep = "/go"
		elements = []
		if includeServerURL:
			elements.append(base.getConfig("web", "serverURL"))
		elements.extend([
			 base.getConfig("web", "nevowRoot"),
				self.rd.sourceId, "/", self.id, "/", renderer, qSep])
		return "".join(elements)
	
	def _meta_referenceURL(self):
		return meta.MetaItem(meta.makeMetaValue(self.getURL("info"),
			type="link", title="Service info"))
	
	def translateFieldName(self, name):
		return name
