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
from gavo.protocols import creds
from gavo.web import common
from gavo.web import htmltable
from gavo.web import serviceresults
from gavo.web import weberrors



class RDBlocked(Exception):
	"""is raised when a ResourceDescriptor is blocked due to maintanence
	and caught by the root resource..
	"""


########## Useful mixins for Renderers

class GavoRenderMixin(common.CommonRenderers, base.MetaMixin):
	"""A mixin with renderers useful throughout the data center.

	Rendering of meta information:
	* <tag n:render="meta">METAKEY</tag> or
	* <tag n:render="metahtml">METAKEY</tag>

	Rendering internal links (important for off-root operation):
	* <tag href|src="/foo" n:render="rootlink"/>

	Rendering the sidebar --
	<body n:render="withsidebar">.  This will only work if the renderer
	has a service attribute that's enough of a service (i.e., carries meta
	and knows how to generate URLs).

	Conditional rendering:
	* ifmeta
	* imownmeta
	* ifdata
	* ifnodata
	* ifslot
	* ifnoslot
	* ifadmin
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
			return self.getMeta(metaName)
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

	def render_ifnoslot(self, slotName):
		"""renders if slotName is missing or not true.

		This will not work properly if the slot values come from a deferred.
		"""
		# just repeat the code from ifslot -- this is called frequently,
		# and additional logic just is not worth it.
		def render(ctx, data):
			try:
				if not ctx.locateSlotData(slotName):
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

	def render_servicestyle(self, ctx, data):
		"""enters custom service styles into ctx.tag.

		They are taken from the service's customCSS property.
		"""
		if self.service and self.service.getProperty("customCSS", False):
			return ctx.tag[self.service.getProperty("customCSS")]
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
				for f in self.service.getInputKeysFor(self))
		else:
			fieldDict = {}
	
		s = [self._makeParPair(k, v, fieldDict) 
			for k, v in self.result.queryMeta.getQueryPars().iteritems()
			if k not in self.__suppressedParNames and not k.startswith("_")]
		s.sort()
		return s


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
	# parameterStyle is a hint for inputKeys how to transform themselves
	# "clear" keeps types, "form" gives vizier-like expressions
	# "vo" gives parameter-like expressions.
	parameterStyle = "clear"
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

		if service.limitTo:
			request = inevow.IRequest(ctx)
			if not creds.hasCredentials(request.getUser(), request.getPassword(),
					service.limitTo):
				raise svcs.Authenticate(base.getConfig("web", "realm"))
		self.service = service

		# Do our input fields differ from the service's?
		self.fieldsChanged = False 

		if self.checkedRenderer and self.name not in self.service.allowed:
			raise svcs.ForbiddenURI(
				"The renderer %s is not allowed on this service."%self.name,
				rd=self.service.rd)
		self.setMetaParent(self.service)
		self.macroPackage = self.service

	def processData(self, rawData, queryMeta):
		"""produces input data for the service in runs the service.
		"""
		return self.service.runWithData(self, rawData, queryMeta)
	
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

