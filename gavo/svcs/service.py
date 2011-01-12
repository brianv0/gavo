"""
Services, i.e. combinations of a core and at least one renderer.

A Service is something that receives some sort of structured data (typically,
a nevow context, processes it into input data using a grammar (default is
the contextgrammar), pipes it through a core to receive a data set and
optionally tinkers with that data set.
"""

import cStringIO
import datetime
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
from gavo.svcs import renderers
from gavo.svcs import standardcores


def adaptTable(origTable, newColumns):
	"""returns a Data instance created from origTable with columns taken from
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
			exprStart = ""
			if col.name in colDiffs:
				exprStart = "%s*"%colDiffs[col.name]
			rmk.feedObject("map", rmkdef.MapRule(rmk, dest=col.name,
				content_="%svars[%s]"%(exprStart, repr(col.name))
				).finishElement())
		newTable = table.InMemoryTable(newTd, validate=False)
		mapper = rmk.finishElement().compileForTable(newTable)
		for r in origTable:
			newTable.addRow(mapper(r))
	return rsc.wrapTable(newTable, rdSource=origTable.tableDef)


class SvcResult(object):
	"""is a nevow.IContainer that has the result and also makes the
	input dataset accessible.

	It is constructed with an InMemoryTable instance coreResult,
	a data instance inputTable, the current querymeta, and a service
	instance.

	If a service is defined, SvcResult adapts coreResult to the
	columns defined by the service (getCurOutputFields).

	Original currently either is an InMemory table, in which case it gets
	adapted to what the service expects, or a data.Data instance (or
	something else), which are left alone, but currently can't be used
	to render HTMLTables.

	SvcResult also makes queryMeta, inputTable and the service available.	This
	should give renderers access to basically all the information they need.  The
	resultmeta data item collects some of those.

	SvcResult objects must be able to fall back to sensible behaviour
	without a service.  This may be necessary in error handling.
	"""
	implements(inevow.IContainer)
	
	def __init__(self, coreResult, inputTable, queryMeta, service=None):
		self.inputTable = inputTable
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
		return dict((k, unicode(v)) 
			for k, v in self.queryMeta.getQueryPars().iteritems())
	
	def data_inputRec(self, ctx=None):
		return self.inputTable.getParamDict()

	def data_table(self, ctx=None):
		return self.original.getPrimaryTable()

	def child(self, ctx, name):
		return getattr(self, "data_"+name)(ctx)


class Publication(base.Structure, base.ComputedMetaMixin):
	"""A specification of how a service should be published.

	This contains most of the metadata for what is an interface in
	registry speak.
	"""
	name_ = "publish"

	_rd = rscdef.RDAttribute()
	_render = base.UnicodeAttribute("render", default=base.Undefined,
		description="The renderer the publication will point at.")
	_sets = base.StringSetAttribute("sets", 
		description="Comma-separated list of sets this service will be"
			" published in.  Predefined are: local=publish on front page,"
			" ivo_managed=register with the VO registry.  If you leave it"
			" empty, 'local' publication is assumed.")

	def completeElement(self):
		if self.render is base.Undefined:
			self.render = "form"
		if not self.sets:
			self.sets.add("local")
		self._completeElementNext(Publication)

	def validate(self):
		self._validateNext(Publication)
		try:
			renderers.getRenderer(self.render)
		except KeyError:
			raise base.StructureError("Unknown renderer: %s"%self.render)

	def _meta_accessURL(self):
		return self.parent.getURL(self.render)

	def _meta_urlUse(self):
		return renderers.getRenderer(self.render).urlUse

	def _meta_requestMethod(self):
		return renderers.getRenderer(self.render).preferredMethod
	
	def _meta_resultType(self):
		return renderers.getRenderer(self.render).resultType


class CustomPageFunction(base.Structure, base.RestrictionMixin):
	"""An abstract base for nevow.rend.Page-related functions on services.
	"""
	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="Name of the render function (use this in the"
			" n:render attribute in custom templates).", copyable=True, strip=True)
	_code = base.DataContent(description="Function body of the renderer; the"
		" arguments are named ctx and data.", copyable=True)

	def onElementComplete(self):
		self._onElementCompleteNext(CustomPageFunction)
		vars = globals()
		exec ("def %s(ctx, data):\n%s"%(self.name,
				utils.fixIndentation(self.content_, newIndent="  ",
					governingLine=1).rstrip())) in vars
		self.func = vars[self.name]


class CustomRF(CustomPageFunction):
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

		return ctx.tag[T.a(href=data)[data]]
	"""
	name_ = "customRF"


class CustomDF(CustomPageFunction):
	"""A custom data function for a service.

	Custom data functions can be used to expose certain aspects of a service
	to Nevow templates.  Thus, their definition usually only makes sense with
	custom templates, though you could, in principle, override built-in
	render functions.

	In the data functions, you have the names ctx for nevow's context and
	data for whatever data the template passes to the renderer. 

	You can return arbitrary python objects -- whatever the render functions
	can deal with.  You could, e.g., write::

		<customDF name="now">
			return datetime.datetime.utcnow()
		</customDF>
	"""
	name_ = "customDF"


## This should really be in gavo.registry (and I could use servicelist then,
## and of course the DB table used here is defined there).
## However, registry uses svc, but we need these meta keys in service.
## Maybe at some point have something in registry just add these meta
## keys?
class RegistryMetaMixin(object):
	"""A mixin providing some metadata that is most easily read from
	servicelist.

	This needs rd and id attributes that can be resolved within the services
	table.  Thus, this metadata will only be available when the service
	is published.  Database accesses will only happen when the metadata
	actually is requested.  Only the registry subpackage should do that.

	This pertains to sets, and (at some point) status.
	"""
	def __getFromDB(self, metaKey):
		try:  # try to used cached data
			if self.__dbRecord is None:
				raise base.NoMetaKey(metaKey, carrier=self)
			return self.__dbRecord[metaKey]
		except AttributeError:
			# fetch data from DB
			pass
		# We're not going through servicelist since we don't want to depend
		# on the registry subpackage.
		q = base.SimpleQuerier()
		try:
			res = q.runIsolatedQuery("SELECT dateUpdated, recTimestamp, setName"
				" FROM dc.resources_join WHERE sourceRD=%(rdId)s AND resId=%(id)s",
				{"rdId": self.rd.sourceId, "id": self.id})
		finally:
			q.close()
		if res:
			row = res[0]
			self.__dbRecord = {
				"sets": meta.makeMetaItem(list(set(row[2] for row in res)), 
					name="sets"),
				"recTimestamp": meta.makeMetaItem(res[0][1].strftime(
					utils.isoTimestampFmt), name="recTimestamp"),
			}
		else:
			self.__dbRecord = {
				'sets': ['unpublished'],
				'recTimestamp': meta.makeMetaItem(
					datetime.datetime.utcnow().strftime(
					utils.isoTimestampFmt), name="recTimestamp"),
				}
		return self.__getFromDB(metaKey)
	
	def _meta_dateUpdated(self):
		return self.rd.getMeta("dateUpdated")

	def _meta_datetimeUpdated(self):
		return self.rd.getMeta("datetimeUpdated")
	
	def _meta_recTimestamp(self):
		return self.__getFromDB("recTimestamp")

	def _meta_sets(self):
		return self.__getFromDB("sets")

	def _meta_status(self):
		return "active"


class CoreAttribute(base.ReferenceAttribute):
	def __init__(self):
		base.ReferenceAttribute.__init__(self, "core", 
			description="The core that does the computations for this service."
			"  Instead of a reference, you can use an immediate element"
			" of some registred core.", 
			forceType=core.Core, copyable=True, aliases=core.CORE_REGISTRY.keys())
	
	def _makeChild(self, name, parent):
		return core.getCore(name)(parent)


class Service(base.Structure, base.ComputedMetaMixin, 
		base.StandardMacroMixin, RegistryMetaMixin):
	"""A service definition.

	A service is a combination of a core and one or more renderers.  They
	can be published, and they carry the metadata published into the VO.
	"""
	name_ = "service"

	_core = CoreAttribute()
	_templates = base.DictAttribute("templates", description="Custom"
		' nevow templates for this service; use key "form" to replace the Form'
		" renderer's standard template.  Start the path with two slashes to"
		" access system templates.", 
		itemAttD=rscdef.ResdirRelativeAttribute(
			"template", description="resdir-relative path to a nevow template"
			" used for the function given in key."), copyable=True)
	_publications = base.StructListAttribute("publications",
		childFactory=Publication, description="Sets and renderers this service"
			" is published with.")
	_limitTo = base.UnicodeAttribute("limitTo", default=None,
		description="Limit access to the group given; the empty default disables"
		" access control.", copyable="True")
	_customPage = rscdef.ResdirRelativeAttribute("customPage", default=None,
		description="resdir-relative path to custom page code.  It is used"
		" by the 'custom' renderer", copyable="True")
	_allowedRenderers = base.StringSetAttribute("allowed",
		description="Names of renderers allowed on this service; leave emtpy"
		" to allow the form renderer only.", copyable=True)
	_customRF = base.StructListAttribute("customRFs",
		description="Custom render functions for use in custom templates.",
		childFactory=CustomRF, copyable=True)
	_customDF = base.StructListAttribute("customDFs",
		description="Custom data functions for use in custom templates.",
		childFactory=CustomDF, copyable=True)
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

	metaModel = ("title(1), creationDate(1), description(1),"
		"subject, referenceURL(1), shortName(!)")

	# formats that should query the same fields as HTML (the others behave
	# like VOTables and offer a "verbosity" widget in forms).
	htmlLikeFormats = ["HTML", "tar"]

	####################### Housekeeping methods

	def __repr__(self):
		return "<Service at %x>"%id(self)

	def completeElement(self):
		self._completeElementNext(Service)
		if not self.allowed:
			self.allowed.add("form")

		# undefined cores are only allowed with custom pages.
		if self.core is base.Undefined and self.customPage:
			self.core = core.getCore("nullCore")(self.rd).finishElement()

		# empty output tables are filled from the core
		if self.outputTable is base.NotGiven:
			self.outputTable = self.core.outputTable

		# store references to cores for renderers
		self._coresCache = {}
		self._loadedTemplates = {}
			
	def onElementComplete(self):
		self._onElementCompleteNext(Service)
		
		if self.outputTable is base.NotGiven:
			self.outputTable = self.core.outputTable

		# Index custom render/data functions
		self.nevowRenderers = {}
		for customRF in self.customRFs:
			self.nevowRenderers[customRF.name] = customRF.func
		self.nevowDataFunctions = {}
		for customDF in self.customDFs:
			self.nevowDataFunctions[customDF.name] = customDF.func

		self._compileCustomPage()

		self._computeResourceType()

	def _compileCustomPage(self):
		if self.customPage:
			try:
				modNs, moddesc = utils.loadPythonModule(self.customPage)
				page = modNs.MainPage
			except ImportError, msg:
				import traceback
				traceback.print_exc()
				raise base.LiteralParseError("customPage", self.customPage, 
					"While loading the custom page you specified, the following"
					" error was raised: '%s'.  See the log for a traceback."%
					unicode(msg))
			self.customPageCode = page, (os.path.basename(self.customPage),)+moddesc

	def getTemplate(self, key):
		"""returns the nevow template for the function key on this service.
		"""
		if key not in self._loadedTemplates:
			from nevow import loaders
			tp = self.templates[key]
			if tp.startswith("//"):
				self._loadedTemplates[key] = common.loadSystemTemplate(tp[2:])
			else:
				self._loadedTemplates[key] = loaders.xmlfile(
					os.path.join(self.rd.resdir, tp))
		return self._loadedTemplates[key]


	################### Registry and related methods.

	def _computeResourceType(self):
		"""sets the resType attribute.

		Services are resources, and the registry code wants to know what kind.
		This method ventures a guess.  You can override this decision by setting
		the resType meta item.
		"""
		if "tap" in self.allowed:
			self.resType = "catalogService"
		elif self.outputTable.columns or self.outputTable.verbLevel:
			# need to check for verbLevel since at that point the outputTable
			# has not onParentCompleted and thus columns is empty with verbLevel.
# XXX the NVO registry can't cope with tableService, so we declare
# everything as a catalogService for now
			self.resType = "catalogService"
			return
# XXX end NVO brain damage fixing hack
			if (self.outputTable.getColumnsByUCDs("pos.eq.ra", 
						"pos.eq.ra;meta.main", "POS_EQ_RA_MAIN")
					or self.getMeta("coverage", default=None) is not None):
				# There's either coverage or a position: A CatalogService
				self.resType = "catalogService"
			else: # We have an output table, but no discernible positions
				self.resType = "tableService"
		else: # no output table defined, we're a plain service
			self.resType = "nonTabularService"

	def getPublicationsForSet(self, names):
		"""returns publications for set names in names.

		names must be a set.  If ivo_managed is in names and there is any
		publication at all, artificial VOSI publications are added.
		"""
		res = [pub for pub in self.publications if pub.sets & names]
		vosiSet = set(["ivo_managed"])
		if res and "ivo_managed" in names:
			res.extend((
				base.makeStruct(Publication, render="availability", sets=vosiSet,
					parent_=self),
				base.makeStruct(Publication, render="capabilities", sets=vosiSet,
					parent_=self),
				base.makeStruct(Publication, render="tableMetadata", sets=vosiSet,
					parent_=self),
			))
		return res

	def getURL(self, rendName, absolute=True):
		"""returns the full canonical access URL of this service together 
		with renderer.

		rendName is the name of the intended renderer in the registry
		of renderers.

		With absolute, a fully qualified URL is being returned.
		"""
		basePath = "%s%s/%s"%(base.getConfig("web", "nevowRoot"),
			self.rd.sourceId, self.id)
		if absolute:
			basePath = base.getConfig("web", "serverURL")+basePath
		return renderers.getRenderer(rendName).makeAccessURL(basePath)

	# used by getBrowserURL; keep external higher than form as long as
	# we have mess like Potsdam CdC.
	_browserScores = {"form": 10, "external": 12, "fixed": 15,
		"custom": 3, "static": 1}

	def getBrowserURL(self, fq=True):
		"""returns a published URL that's suitable for a web browser or None if
		no such URL can be guessed.

		If you pass fq=False, you will get a path rather than a URL.
		"""
		# There can be multiple candidates for browser URLs (like when a service
		# has both form, static, and external renderers).  If so, we select
		# by plain scores.
		browseables = []
		for rendName in self.allowed:
			if self.isBrowseableWith(rendName):
				browseables.append((self._browserScores.get(rendName, -1), rendName))
		if browseables:
			return self.getURL(max(browseables)[1], absolute=fq)
		else:
			return None
		
	def isBrowseableWith(self, rendName):
		"""returns true if rendering this service through rendName results 
		in something pretty in a web browser.
		"""
		try:
			return bool(renderers.getRenderer(rendName).isBrowseable(self))
		except base.NotFoundError: # renderer name not known
			return False

	def getTableSet(self):
		"""returns a list of table definitions that have something to do with
		this service.

		This is for VOSI-type queries.  Usually, that's just the core's
		queried table, except when there is a TAP renderer on the service.
		"""
		tables = [getattr(self.core, "queriedTable", None)]
		if "tap" in self.allowed:
			mth = base.caches.getMTH(None)
			for row in mth.queryTablesTable("adql"):
				try:
					tables.append(mth.getTableDefForTable(row["tableName"]))
				except base.NotFoundError:
					pass
		return [t for t in tables if t is not None]

	########################## Output field selection (ouch!)

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
		properly caught).
		"""
		requireSet = queryMeta["columnSet"]
		res = rscdef.ColumnList()

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
					col = cofs.getColumnByName(fieldName)
					if isinstance(col, outputdef.OutputField):
						res.append(col)
					else:
						res.append(outputdef.OutputField.fromColumn(col))
			except base.NotFoundError, msg:
				if raiseOnUnknown:
					raise base.ValidationError("The additional field %s you requested"
						" does not exist"%repr(msg.lookedFor), colName="_OUTPUT")
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

	def getAllOutputFields(self):
		"""Returns a sequence of all available output fields.

		This is mainly for the registry.  It basically asks the core
		what it has and returns that.

		Unfortunately, this does not reflect what the service actually
		does, but for the registry it's probably the most useful information.
		"""
		return self.core.outputTable.columns

	################### running and input computation.

	def getCoreFor(self, renderer):
		"""returns a core tailored for renderer.

		See svcs.core's module docstring. 
		
		The argument can be a renderer or a renderer name.
		"""
		if isinstance(renderer, basestring):
			renderer = renderers.getRenderer(renderer)

		# non-checked renderers use the core for info purposes only; don't
		# bother for those
		if not renderer.checkedRenderer:
			return self.core

		if renderer.name not in self._coresCache:
			self._coresCache[renderer.name] = self.core.adaptForRenderer(renderer)
		return self._coresCache[renderer.name]

	def getInputKeysFor(self, renderer):
		"""returns a sequence of input keys, adapted for certain renderers.

		The renderer argument may either be a renderer name, a renderer
		class or a renderer instance.

		If the service has an inputDD, the result is the context grammar's
		input keys.  Otherwise, it will be a subset of the core's input
		fields as determined by the renderer.
		"""
		if self.inputDD is not base.NotGiven:
			return self.inputDD.grammar.inputKeys
		return self.getCoreFor(renderer).inputTable.params

	def _makeDefaultInputTable(self, renderer, contextData):
		"""turns contextData into the parameters of the core's input table.

		This is what builds the core input table when the service
		does not define an inputDD.
		"""
		res = rsc.TableForDef(self.getCoreFor(renderer).inputTable)
		missingRequired = []
		for par in res.iterParams():
			# check "None" to avoid clobbering defaults (querying for NULLs
			# is a difficult matter anyway)
			if par.name in contextData and contextData[par.name] is not None:
				try:
					par.set(contextData[par.name])
					_ = par.value  # validate input
				except ValueError, ex:
					raise base.ui.logOldExc(base.ValidationError(unicode(ex),
						par.name))
			if par.required and par.value is None:
				missingRequired.append(par.name)
		if missingRequired:
			raise base.ValidationError("Mandatory field(s) %s empty"%
				", ".join(missingRequired), missingRequired[0])
		return res

	def _makeInputTableFor(self, renderer, contextData):
		"""returns an input table for the core, filled from contextData and
		adapted for renderer.
		"""
		if self.inputDD:
			return rsc.makeData(self.inputDD,
				parseOptions=rsc.parseValidating, forceSource=contextData
					).getPrimaryTable()
		return self._makeDefaultInputTable(renderer, contextData)

	def runWithData(self, renderer, contextData, queryMeta):
		"""runs the service, returning an SvcResult.

		This is the main entry point.  contextData usually is what
		the nevow machinery delivers or simply a dictionary, but if
		service has an inputDD, it can be anything the grammar can
		grok.
		"""
		inputTable = self._makeInputTableFor(renderer, contextData)
		coreRes = self.getCoreFor(renderer).run(self, inputTable, queryMeta)
		return SvcResult(coreRes, inputTable, queryMeta, self)

	def runFromDict(self, contextData, renderer="form", queryMeta=None):
		"""runs the service with a dictionary input and within a given renderer.

		This is mainly a convenience method for unit tests, supplying some
		defaults.
		"""
		if queryMeta is None:
			queryMeta = common.QueryMeta(contextData)
		return self.runWithData(renderer, contextData, queryMeta)
		

	#################### meta and such

	def _meta_referenceURL(self):
		return meta.makeMetaItem(self.getURL("info"),
			type="link", title="Service info")

	def _meta_identifier(self):
		return "ivo://%s/%s/%s"%(base.getConfig("ivoa", "authority"),
				self.rd.sourceId, self.id)

	def _meta_available(self):
# XXX TODO: have this ask the core
		return "true"

	def macro_tablesForTAP(self):  # who needs this?
		from gavo.protocols import tap
		return ", ".join(tap.getAccessibleTables())
