"""
Web Renderers.

Renderers are frontends for services.  They provide the glue to
somehow acquire input (typically, nevow contexts) and then format
the result in VOTables, HTML tables, etc.

Currently, they also know how to deliver the result of the rendering
process (i.e., push it out onto a socket), but we should have deliverers
at some point, e.g., for asynchronous operation.
"""

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


class CustomErrorMixin(object):
	"""is a mixin for renderers containing formal forms to emit
	custom error messages.

	This mixin expects to see "the" form as self.form and relies on
	the presence of a method _generateForm that arranges for that .
	This can usually be an alias for the form_xy method you need for
	formal (we actually pass a nevow context object to that function),
	but make sure you actually set self.form in there.

	You need to ctx.remember(self, inevow.ICanHandleException) in your __init__.
	"""
	implements(inevow.ICanHandleException)

	def renderHTTP(self, ctx):
		# This is mainly an extract of what we need of formal.Form.process
		# generate the form
		try:
			self._generateForm(ctx)
			request = inevow.IRequest(ctx)
			charset = nevowutil.getPOSTCharset(ctx)
			# Get the request args and decode the arg names
			args = dict([(k.decode(charset),v) for k,v in request.args.items()])
			self.form.errors.data = args
			# Iterate the items and collect the form data and/or errors.
			for item in self.form.items:
				item.process(ctx, self.form, args, self.form.errors)
			# format validation errors
			if self.form.errors:
				return self._handleInputErrors(self.form.errors.errors, ctx)
			return self.submitAction(ctx, self.form, self.form.data)
		except:
			return self.renderHTTP_exception(ctx, failure.Failure())

	def renderHTTP_exception(self, ctx, failure):
		"""override for to emit custom errors for general failures.

		You'll usually want to do all writing yourself, finishRequest(False) your
		request and return appserver.errorMarker here.
		"""
		failure.printTraceback()
		return ""

	def _handleInputErrors(self, errors, ctx):
		"""override to emit custom error messages for formal validation errors.
		"""
		if isinstance(errors, formal.FormError):
			msg = "Error(s) in given Parameters: %s"%"; ".join(
				[str(e) for e in errors])
		else:
			try:
				msg = errors.getErrorMessage()
			except AttributeError:
				msg = str(errors)
		return msg

	def _handleError(self, failure, ctx):
		"""use or override this to handle errors occurring during processing
		"""
		if isinstance(failure.value, base.ValidationError):
			return self._handleInputErrors(["Parameter %s: %s"%(
				failure.value.colName, failure.getErrorMessage())], ctx)
		return self.renderHTTP_exception(ctx, failure)


_htmlMetaBuilder = common.HTMLMetaBuilder()


class GavoRenderMixin(common.CommonRenderers):
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
	def _doRenderMeta(self, ctx, raiseOnFail=False, plain=False, 
			metaCarrier=None):
		try:
			if not metaCarrier:
				metaCarrier = self.service
			if isinstance(metaCarrier, rscdef.MacroPackage):
				htmlBuilder = common.HTMLMetaBuilder(metaCarrier)
			else:
				htmlBuilder = _htmlMetaBuilder
			metaKey = ctx.tag.children[0]
			if plain:
				ctx.tag.clear()
				return ctx.tag[metaCarrier.getMeta(metaKey, raiseOnFail=True
					).getContent("text")]
			else:
				htmlBuilder.clear()
				ctx.tag.clear()
				return ctx.tag[T.xml(metaCarrier.buildRepr(metaKey, htmlBuilder,
					raiseOnFail=True))]
		except base.NoMetaKey:
			if raiseOnFail:
				raise
			return T.comment["Meta item %s not given."%metaKey]
		except Exception, ex:
			return T.comment["Meta %s bad (%s)"%(metaKey, str(ex))]

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

	def render_ifdata(self, ctx, data):
		if data:
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

	def render_ifmeta(self, metaName, metaCarrier=None):
		if metaCarrier is None:
			metaCarrier = self.service
		if metaCarrier.getMeta(metaName):
			return lambda ctx, data: ctx.tag
		else:
			return lambda ctx, data: ""

	def render_ifnodata(self, ctx, data):
		if not data:
			return ctx.tag
		else:
			return ""

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
		except base.MetaError:
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

	def getSidebar(self, ctx):
# XXX TODO: get this from disk soon.
		res = T.div(id="sidebar")[
				T.div(class_="sidebaritem")[
					T.a(href="/", render=T.directive("rootlink"))[
						T.img(src="/builtin/img/logo_medium.png", class_="silentlink",
							render=T.directive("rootlink"), alt="[Gavo logo]")],
				],
				T.a(href="#body", class_="invisible")["Skip Header"],
				T.div(class_="sidebaritem")[
					T.p[T.a(href="/builtin/help.shtml")["Help"]],
					T.p(render=T.directive("authinfo")),
					T.p[T.a(href=self.service.getURL("info", absolute=False))[
						"Service info"]],
				],
				T.div(render=T.directive("ifdata"), class_="sidebaritem",
					data=self.service.getMeta("_related"))[
					T.h3["Related"],
					T.invisible(render=T.directive("metahtml"))["_related"],
				],
				T.div(class_="sidebaritem")[
					T.h3["Metadata"],
					T.invisible(title="News",
						render=T.directive("explodableMeta"))["_news"],
					T.invisible(
						render=T.directive("explodableMeta"))["description"],
					T.invisible(title="Keywords",
						render=T.directive("explodableMeta"))["subject"],
					T.invisible(
						render=T.directive("explodableMeta"))["creator"],
					T.invisible(title="Created",
						render=T.directive("explodableMeta"))["creationDate"],
					T.invisible(title="Data updated",
						render=T.directive("explodableMeta"))["dateUpdated"],
					T.invisible(
						render=T.directive("explodableMeta"))["copyright"],
					T.invisible(
						render=T.directive("explodableMeta"))["source"],
					T.invisible(title="Reference URL",
						render=T.directive("explodableMeta"))["referenceURL"],
				],
				T.div(class_="sidebaritem", style="font-size: 90%; padding-top:10px;"
					" border-top: 1px solid grey; margin-top:40px")[
						"Try ",
						T.a(href="/__system__/adql/query/form")["ADQL"],
						" to query our data."],
				T.div(class_="sidebaritem", style="font-size: 62%; padding-top:5px;"
						" border-top: 1px solid grey; margin-top:10px;")[
					T.p(class_="breakable")["Please report errors and problems to ",
						T.a(href="mailto:gavo.ari.uni-heidelberg.de")["GAVO staff"],
						".  Thanks."],
					T.p[T.a(href="/static/doc/privpol.shtml", 
							render=T.directive("rootlink"))["Privacy"],
						" | ",
						T.a(href="/static/doc/disclaimer.shtml",
							render=T.directive("rootlink"))["Disclaimer"],],],
			]
		if inevow.IRequest(ctx).getUser()=="gavoadmin":
			res[
				T.hr,
				T.a(href=base.makeSitePath("seffe/%s"%self.service.rd.sourceId))[
					"Admin me"]]
		return res

	def render_withsidebar(self, ctx, data):
		oldChildren = ctx.tag.children
		ctx.tag.children = []
		return ctx.tag[
			self.getSidebar(ctx),
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


class ErrorPage(GavoRenderMixin, rend.Page):
	def __init__(self, failure, *args, **kwargs):
		self.failure = failure
		super(ErrorPage, self).__init__(*args, **kwargs)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		return defer.maybeDeferred(super(ErrorPage, self).renderHTTP(ctx)
			).addErrback(lambda _: request.finishRequest(False) or "")
	
	def render_errmsg(self, ctx, data):
		return ctx.tag[str(self.failure.getErrorMessage())]


class ResourceBasedRenderer(common.CustomTemplateMixin, rend.Page, 
		GavoRenderMixin):
	"""is a page based on a resource descriptor.

	It is constructed with a resource descriptor and leaves it
	in the rd attribute.

	This class is abstract in the sense that it doesn't to anything
	sensible.

	The preferredMethod attribute is used for generation of registryRecords
	and currently should be either GET or POST.  urlUse should be one
	of full, base, post, or dir, in accord with VOResource.

	Renderers with fixed result types should fill out resultType.

	The makeAccessURL class method is called by service.getURL; it
	receives the service's base URL and must return a mogrified string
	that corresponds to an endpoint this renderer will operate on (this
	could be used to make a Form renderer into a ParamHTTP interface by
	attaching ?__nevow_form__=genForm&, and the soap renderer does
	nontrivial things there).
	"""
	preferredMethod = "GET"
	urlUse = "full"
	resultType = None
	name = None

	def __init__(self, ctx, rd):
		self.rd = rd
		if hasattr(self.rd, "currently_blocked"):
			raise RDBlocked()
		super(ResourceBasedRenderer, self).__init__()
	
	def _output(self, res, ctx):
		print res
		return res

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


class ServiceBasedRenderer(ResourceBasedRenderer):
	"""A resource based renderer using subId as a service id.

	All of our renderers inherit from this, since there is no way
	a resource could define anything to render (now).
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

	def renderer(self, ctx, name):
		"""returns code for a nevow render function named name.

		This overrides the method inherited from nevow's RenderFactory to
		add a lookup in the page's service service.
		"""
		if name in self.service.nevowRenderers:
			return self.service.nevowRenderers[name]
		return ResourceBasedRenderer.renderer(self, ctx, name)

	def child(self, ctx, name):
		"""returns code for a nevow data function named name.

		In addition to nevow's action, this also looks methods up in the
		service.
		"""
		if name in self.service.nevowDataFunctions:
			return self.service.nevowDataFunctions[name]
		return ResourceBasedRenderer.child(self, ctx, name)


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

