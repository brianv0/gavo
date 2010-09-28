"""
Basic Code for Renderers.

Renderers are frontends for services.  They provide the glue to
somehow acquire input (typically, nevow contexts) and then format
the result for the user.
"""

import os

from nevow import tags as T, entities as E
from nevow import loaders
from nevow import inevow
from nevow import rend
from nevow import url
from nevow import util as nevowutil

from twisted.internet import defer
from twisted.internet import threads
from twisted.python import failure
from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo import rscdef
from gavo.imp import formal
from gavo.protocols import creds
from gavo.web import common
from gavo.web import htmltable
from gavo.web import weberrors



class RDBlocked(Exception):
	"""is raised when a ResourceDescriptor is blocked due to maintanence
	and caught by the root resource..
	"""


########## Useful mixins for Renderers

class GavoRenderMixin(common.CommonRenderers, base.MetaMixin):
	"""is a mixin with renderers useful throughout the data center.

	Rendering of meta information:
	<tag n:render="meta">METAKEY</tag> or
	<tag n:render="metahtml">METAKEY</tag>

	Rendering internal links (important for off-root operation):
	<tag href|src="/foo" n:render="rootlink"/>

	Rendering the sidebar (with a service attribute on the class mixing in):

	<body n:render="withsidebar">.  This will only work if the renderer
	has a service attribute that's enough of a service (i.e., carries meta
	and knows how to generate URLs).
	"""
	_sidebar = svcs.loadSystemTemplate("sidebar.html")

	# macro package to use when expanding macros.  Just set this
	# in the constructor as necessary (ServiceBasedRenderer has the
	# service here)
	macroPackage = None

	def _initGavoRender(self):
		# call this to initialize this mixin.
		base.MetaMixin.__init__(self)

	def _doRenderMeta(self, ctx, raiseOnFail=False, plain=False):
		try:
			htmlBuilder = common.HTMLMetaBuilder(self.macroPackage)
			metaKey = ctx.tag.children[0]
			if plain:
				ctx.tag.clear()
				return ctx.tag[self.getMeta(metaKey, raiseOnFail=True
					).getContent("text")]
			else:
				ctx.tag.clear()
				return ctx.tag[T.xml(self.buildRepr(metaKey, htmlBuilder,
					raiseOnFail=True))]
		except base.NoMetaKey:
			if raiseOnFail:
				raise
			return T.comment["Meta item %s not given."%metaKey]
		except Exception, ex:
			msg = "Meta %s bad (%s)"%(metaKey, str(ex))
			base.ui.notifyError(msg)
			return T.comment[msg]

	def data_meta(self, metaName):
		"""returns the value for the meta key metaName on this service.
		"""
		def get(ctx, data):
			return self.service.getMeta(metaName)
		return get
		
	def render_meta(self, ctx, data):
		return self._doRenderMeta(ctx, plain=True)
	
	def render_metahtml(self, ctx, data):
		return self._doRenderMeta(ctx)
		
	def render_rootlink(self, ctx, data):
		tag = ctx.tag
		def munge(key):
			if tag.attributes.has_key(key):
			 tag.attributes[key] = base.makeSitePath(tag.attributes[key])
		munge("src")
		munge("href")
		return tag

	def render_ifmeta(self, metaName, propagate=True):
		# accept direct parent as "own" meta as well.
		if propagate:
			hasMeta = self.getMeta(metaName) is not None
		else:
			hasMeta = (self.getMeta(metaName, propagate=False) is not None
				or self.getMetaParent().getMeta(metaName, propagate=False) is not None)
		if hasMeta:
			return lambda ctx, data: ctx.tag
		else:
			return lambda ctx, data: ""

	def render_ifownmeta(self, metaName):
		return self.render_ifmeta(metaName, propagate=False)

	def render_ifdata(self, ctx, data):
		if data:
			return ctx.tag
		else:
			return ""

	def render_ifnodata(self, ctx, data):
		if not data:
			return ctx.tag
		else:
			return ""

	def render_ifslot(self, slotName):
		"""renders the children for slotName is present and true.

		This will not work properly if the slot values come from a deferred.
		"""
		def render(ctx, data):
			try:
				if ctx.locateSlotData(slotName):
					return ctx.tag
				else:
					return ""
			except KeyError:
				return ""
		return render

	def render_ifadmin(self, ctx, data):
		# NOTE: use of this renderer is *not* enough to protect critical operations
		# since it does not check if the credentials are actually provided.
		# Use this only hide links that will give 403s (or somesuch) for
		# non-admins anyway (and the like).
		if inevow.IRequest(ctx).getUser()=="gavoadmin":
			return ctx.tag
		else:
			return ""

	def render_explodableMeta(self, ctx, data):
		metaKey = ctx.tag.children[0]
		title = ctx.tag.attributes.get("title", metaKey.capitalize())
		try:
			return T.div(class_="explodable")[
				T.h4(class_="exploHead")[
					T.a(onclick="toggleCollapsedMeta(this)", 
						class_="foldbutton")[title+" >>"],
				],
				T.div(class_="exploBody")[
					self._doRenderMeta(ctx, raiseOnFail=True)]]
		except base.MetaError, ex:
			return ""
	
	def render_authinfo(self, ctx, data):
		request = inevow.IRequest(ctx)
		nextURL = str(url.URL.fromContext(ctx))
		targetURL = url.URL.fromString("/login").add("nextURL", nextURL)
		anchorText = "Log in"
		if request.getUser():
			anchorText = "Log out %s"%request.getUser()
			targetURL = targetURL.add("relog", "True")
		return ctx.tag[T.a(href=str(targetURL))[
			anchorText]]

	def render_withsidebar(self, ctx, data):
		oldChildren = ctx.tag.children
		ctx.tag.children = []
		return ctx.tag(class_="container")[
			self._sidebar,
			T.div(id="body")[
				T.a(name="body"),
				oldChildren
			],
		]


class HTMLResultRenderMixin(object):
	"""is a mixin with render functions for HTML tables and associated 
	metadata within other pages.

	This is primarily used for the Form renderer.
	"""
	result = None

	def render_resulttable(self, ctx, data):
		if hasattr(data, "child"):
			return htmltable.HTMLTableFragment(data.child(ctx, "table"), 
				data.queryMeta)
		else:
			# a FormError, most likely
			return ""

	def render_resultline(self, ctx, data):
		if hasattr(data, "child"):
			return htmltable.HTMLKeyValueFragment(data.child(ctx, "table"), 
				data.queryMeta)
		else:
			# a FormError, most likely
			return ""

	def render_parpair(self, ctx, data):
		if data is None or data[1] is None or "__" in data[0]:
			return ""
		return ctx.tag["%s: %s"%data]

	def render_ifresult(self, ctx, data):
		if self.result.queryMeta.get("Matched", 1)!=0:
			return ctx.tag
		else:
			return ""
	
	def render_ifnoresult(self, ctx, data):
		if self.result.queryMeta.get("Matched", 1)==0:
			return ctx.tag
		else:
			return ""

	def data_result(self, ctx, data):
		return self.result

	def _makeParPair(self, key, value, fieldDict):
		title = key
		if key in fieldDict:
			title = fieldDict[key].tablehead
			if fieldDict[key].type=="file":
				value = "File upload '%s'"%value[0]
			else:
				value = unicode(value)
		return title, value

	__suppressedParNames = set(["submit"])

	def data_queryseq(self, ctx, data):
		if not self.result:
			return []

		if self.service:
			fieldDict = dict((f.name, f) 
				for f in self.getInputFields(self.service))
		else:
			fieldDict = {}
	
		s = [self._makeParPair(k, v, fieldDict) 
			for k, v in self.result.queryMeta.getQueryPars().iteritems()
			if k not in self.__suppressedParNames and not k.startswith("_")]
		s.sort()
		return s


class FormMixin(formal.ResourceMixin):
	"""A mixin to produce input forms for services and display
	errors within these forms.
	"""
	def _handleInputErrors(self, failure, ctx):
		"""goes as an errback to form handling code to allow correction form
		rendering at later stages than validation.
		"""
		if isinstance(failure.value, formal.FormError):
			self.form.errors.add(failure.value)
		elif isinstance(failure.value, base.ValidationError) and isinstance(
				failure.value.colName, basestring):
			try:
				# Find out the formal name of the failing field...
				failedField = self.translateFieldName(failure.value.colName)
				# ...and make sure it exists
				self.form.items.getItemByName(failedField)
				self.form.errors.add(formal.FieldValidationError(
					str(failure.getErrorMessage()), failedField))
			except KeyError: # Failing field cannot be determined
				self.form.errors.add(formal.FormError("Problem with input"
					" in the internal or generated field '%s': %s"%(
						failure.value.colName, failure.getErrorMessage())))
		else:
			failure.printTraceback()
			return failure
		return self.form.errors

	def translateFieldName(self, name):
		return self.service.translateFieldName(name)

	def _addDefaults(self, ctx, form):
		"""adds defaults from request arguments.
		"""
		if ctx is None:  # no request context, no arguments
			return
		args = inevow.IRequest(ctx).args
		for item in form.items:
			try:
				form.data[item.key] = item.makeWidget().processInput(
					ctx, item.key, args)
			except:  # don't fail on junky things in default arguments
				pass
			
	def _addInputKey(self, form, inputKey):
		"""adds a form field for an inputKey to the form.
		"""
		unit = ""
		if inputKey.type!="date":  # Sigh.
			unit = inputKey.inputUnit or inputKey.unit or ""
			if unit:
				unit = " [%s]"%unit
		label = inputKey.tablehead
		form.addField(inputKey.name,
			inputKey.getCurrentFormalType(),
			inputKey.getCurrentWidgetFactory(),
			label=label+unit,
			description=inputKey.description)
		if inputKey.values and inputKey.values.default:
			form.data[inputKey.name] = inputKey.values.default

	def _addFromInputKey(self, form, inputKey):
		self._addInputKey(form, inputKey)

	def _addQueryFields(self, form):
		"""adds the inputFields of the service to form, setting proper defaults
		from the field or from data.
		"""
		for inputKey in self.getInputFields(self.service):
			self._addFromInputKey(form, inputKey)

	def _addMetaFields(self, form, queryMeta):
		"""adds fields to choose output properties to form.
		"""
		for serviceKey in self.service.serviceKeys:
			self._addFromInputKey(form, serviceKey)
		try:
			if self.service.core.wantsTableWidget():
				form.addField("_DBOPTIONS", svcs.FormalDict,
					formal.widgetFactory(svcs.DBOptions, self.service, queryMeta),
					label="Table")
		except AttributeError: # probably no wantsTableWidget method on core
			pass

	def _getFormLinks(self):
		"""returns stan for widgets building GET-type strings for the current 
		form content.
		"""
		return T.div(class_="formLinks")[
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeResultLink(getEnclosingForm(this))")
					["[Result link]"],
				" ",
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeBookmarkLink(getEnclosingForm(this))")[
					T.img(src=base.makeSitePath("/static/img/bookmark.png"), 
						class_="silentlink", title="Link to this form", alt="[bookmark]")
				],
			]

	def form_genForm(self, ctx=None, data=None):
		queryMeta = svcs.QueryMeta.fromContext(ctx)
		form = formal.Form()
		self._addQueryFields(form)
		self._addMetaFields(form, queryMeta)
		self._addDefaults(ctx, form)
		if self.name=="form":
			form.addField("_OUTPUT", formal.String, 
				formal.widgetFactory(svcs.OutputFormat, self.service, queryMeta),
				label="Output format")
		form.addAction(self.submitAction, label="Go")
		form.actionMaterial = self._getFormLinks()
		self.form = form
		return form


class CustomTemplateMixin(object):
	"""is a mixin providing for customized templates.

	This works by making docFactory a property first checking if
	the instance has a customTemplate attribute evaluating to true.
	If it has and it is referring to a string, its content is used
	as an absolute path to a nevow XML template.  If it has and
	it is not a string, it will be used as a template directly
	(it's already "loaded"), else defaultDocFactory attribute of
	the instance is used.
	"""
	customTemplate = None

	def getDocFactory(self):
		if not self.customTemplate:
			return self.defaultDocFactory
		elif isinstance(self.customTemplate, basestring):
			if not os.path.exists(self.customTemplate):
				return self.defaultDocFactory
			return loaders.xmlfile(self.customTemplate)
		else:
			return self.customTemplate
	
	docFactory = property(getDocFactory)



############# nevow Resource derivatives used here.


class ResourceBasedRenderer(GavoRenderMixin):
	"""A base for renderers based on RDs.

	It is constructed with the resource descriptor and leaves it
	in the rd attribute.

	You will have to override the renderHTTP(ctx) -> whatever method, 
	possibly locateChild(ctx, segments) -> resource, too.

	The preferredMethod attribute is used for generation of registry records
	and currently should be either GET or POST.  urlUse should be one
	of full, base, post, or dir, in accord with VOResource.

	Renderers with fixed result types should fill out resultType.

	The makeAccessURL class method is called by service.getURL; it
	receives the service's base URL and must return a mogrified string
	that corresponds to an endpoint this renderer will operate on (this
	could be used to make a Form renderer into a ParamHTTP interface by
	attaching ?__nevow_form__=genForm&, and the soap renderer does
	nontrivial things there).

	Within DaCHS, this class is mainly used as a base for ServiceBasedRenderer,
	since almost always only services talk to the world.
	"""
	implements(inevow.IResource)

	preferredMethod = "GET"
	urlUse = "full"
	resultType = None
	name = None

	def __init__(self, ctx, rd):
		self.rd = rd
		if hasattr(self.rd, "currently_blocked"):
			raise RDBlocked()
		self._initGavoRender()

	def renderHTTP(self, ctx):
		return super(ResourceBasedRenderer, self).renderHTTP(ctx)
	
	def locateChild(self, ctx, segments):
		return self, ()

	@classmethod
	def isBrowseable(self, service):
		"""returns True if this renderer applied to service is usable using a
		plain web browser.
		"""
		return False

	@classmethod
	def isCacheable(self, segments, request):
		"""should return true if the content rendered will only change
		when the associated RD changes.

		request is a nevow request object.  web.root.ArchiveService already
		makes sure that you only see GET request without arguments and
		without a user, so you do not need to check this.
		"""
		return False

	@classmethod
	def makeAccessURL(cls, baseURL):
		"""returns an accessURL for a service with baseURL to this renderer.
		"""
		return "%s/%s"%(baseURL, cls.name)

	def data_rdId(self, ctx, data):
		return self.service.rd.sourceId


class ServiceBasedRenderer(ResourceBasedRenderer):
	"""A mixin for pages based on RD services.

	"""
	# set to false for renderers intended to be allowed on all services
	# (i.e., "meta" renderers).
	checkedRenderer = True

	def __init__(self, ctx, service):
		ResourceBasedRenderer.__init__(self, ctx, service.rd)
		request = inevow.IRequest(ctx)

		if service.limitTo:
			if not creds.hasCredentials(request.getUser(), request.getPassword(),
					service.limitTo):
				raise svcs.Authenticate(base.getConfig("web", "realm"))
		self.service = service

		# Do our input fields differ from the service's?
		# This becomes true when getInputFields swallows InputKeys.
		self.fieldsChanged = False 

		if self.checkedRenderer and self.name not in self.service.allowed:
			raise svcs.ForbiddenURI(
				"The renderer %s is not allowed on this service."%self.name)
		self.setMetaParent(self.service)
		self.macroPackage = self.service

	@classmethod
	def getInputDD(cls, service):
		"""returns an inputDD appropriate for service and this renderer.

		This will return None if the service can use the core's default DD.
		"""
		sfs = service.getInputFields()
		ifs = cls.getInputFields(service)
		if sfs is ifs:
			return None
		return base.makeStruct(svcs.InputDescriptor,
			grammar=base.makeStruct(svcs.ContextGrammar, inputKeys=ifs))

	@classmethod
	def getInputFields(cls, service):
		"""filters input fields given by the service for whether they are
		appropriate for the renderer in question.

		This method will return the result of service.getInputFields()
		identically if no fields were filtered.
		"""
		res, changed = [], False
		serviceFields = service.getInputFields()
		for field in serviceFields:
			if field.getProperty("onlyForRenderer", None) is not None:
				if field.getProperty("onlyForRenderer")!=cls.name:
					changed = True
					continue
			if field.getProperty("notForRenderer", None) is not None:
				if field.getProperty("notForRenderer")==cls.name:
					changed = True
					continue
			res.append(field)
		if changed:
			return res
		return serviceFields

	def processData(self, rawData, queryMeta):
		"""produces input data for the service in runs the service.
		"""
		inputData = self.service.makeDataFor(self, rawData)
		return self.service.runWithData(inputData, queryMeta)
	
	def runService(self, rawData, queryMeta):
		"""takes raw data and returns a deferred firing the service result.
		"""
		return threads.deferToThread(self.processData, rawData, queryMeta)

	def runServiceWithContext(self, rawData, context):
		"""calls runService, first making a queryMeta from nevow context.
		"""
		queryMeta = svcs.QueryMeta.fromContext(context)
		queryMeta["formal_data"] = rawData
		return self.runService(rawData, queryMeta)

	def data_serviceURL(self, renderer):
		"""returns a relative URL for this service using the renderer.

		This is ususally used like this:

		<a><n:attr name="href" n:data="serviceURL info" n:render="data">x</a>
		"""
		def get(ctx, data):
			return self.service.getURL(renderer, absolute="False")
		return get


class ServiceBasedPage(ServiceBasedRenderer, rend.Page):
	"""the base class for renderers turning service-based info into HTML.

	You will need to provide some way to give rend.Page nevow templates,
	either by supplying a docFactory or (usually preferably) mixing in
	CustomTemplateMixin.

	The class overrides nevow's child and render methods to allow the
	service to define render_X and data_X methods, too.
	"""
	def __init__(self, ctx, service):
		# I don't want super() here since the constructors have different
		# signatures.
		rend.Page.__init__(self)
		ServiceBasedRenderer.__init__(self, ctx, service)

	def renderer(self, ctx, name):
		"""returns a nevow render function named name.

		This overrides the method inherited from nevow's RenderFactory to
		add a lookup in the page's service service.
		"""
		if name in self.service.nevowRenderers:
			return self.service.nevowRenderers[name]
		return rend.Page.renderer(self, ctx, name)

	def child(self, ctx, name):
		"""returns a nevow data function named name.

		In addition to nevow's action, this also looks methods up in the
		service.
		"""
		if name in self.service.nevowDataFunctions:
			return self.service.nevowDataFunctions[name]
		return rend.Page.child(self, ctx, name)

	def renderHTTP(self, ctx):
		return rend.Page.renderHTTP(self, ctx)
