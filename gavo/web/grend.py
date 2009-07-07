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
from twisted.python import failure
from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo import rscdef
from gavo.imp import formal
from gavo.web import common
from gavo.web import weberrors



class RDBlocked(Exception):
	"""is raised when a ResourceDescriptor is blocked due to maintanence
	and caught by the dispatcher.
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
		if not metaCarrier:
			metaCarrier = self.service
		if isinstance(metaCarrier, rscdef.MacroPackage):
			htmlBuilder = common.HTMLMetaBuilder(metaCarrier)
		else:
			htmlBuilder = _htmlMetaBuilder
		metaKey = ctx.tag.children[0]
		try:
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

	def render_ifmeta(self, metaName):
		if self.service.getMeta(metaName):
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
				self._doRenderMeta(ctx, raiseOnFail=True)]
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

	def render_withsidebar(self, ctx, data):
		oldChildren = ctx.tag.children
		ctx.tag.children = []
		return ctx.tag[
			T.div(id="sidebar")[
				T.div(class_="sidebaritem")[
					T.a(href="/", render=T.directive("rootlink"))[
						T.img(src="/builtin/img/logo_medium.png", class_="silentlink",
							render=T.directive("rootlink"), alt="[Gavo logo]")],
				],
				T.a(href="#body", class_="invisible")["Skip Header"],
				T.div(class_="sidebaritem")[
					T.p[T.a(href="/builtin/help.shtml")["Help"]],
					T.p(render=T.directive("authinfo")),
					T.p[T.a(href=self.service.getURL("info"))["Service info"]],
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
			],
			T.div(id="body")[
				T.a(name="body"),
				oldChildren
			],
		]



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

	It is constructed with a resource descriptor and leave it
	in the rd attribute.
	"""
# The current dispatcher cannot handle such renderers, you'd have
# to come up with URLs for these.
	def __init__(self, ctx, rd):
		self.rd = rd
		if hasattr(self.rd, "currently_blocked"):
			raise RDBlocked()
		super(ResourceBasedRenderer, self).__init__()
	
	def renderHTTP(self, ctx):
		res = defer.maybeDeferred(
			super(ResourceBasedRenderer, self).renderHTTP, ctx)
		res.addErrback(self._crashAndBurn, ctx)
		return res
	
	def _output(self, res, ctx):
		print res
		return res

	def _crashAndBurn(self, failure, ctx):
		res = weberrors.ErrorPage()
		return res.renderHTTP_exception(ctx, failure)


class ServiceBasedRenderer(ResourceBasedRenderer):
	"""is a resource based renderer using subId as a service id.

	These have the Service instance they should use in the service attribute.
	"""
	name = None

	def __init__(self, ctx, service):
		ResourceBasedRenderer.__init__(self, ctx, service.rd)
		self.service = service
		if self.name and not self.name in self.service.allowed:
			raise svcs.ForbiddenURI("The renderer %s is not allowed on this service."%
				self.name)

	def renderer(self, ctx, name):
		"""returns code for a renderer named name.

		This overrides the method inherited from nevow's RenderFactory to
		add a lookup in the page's service service.
		"""
		if name in self.service.nevowRenderers:
			return self.service.nevowRenderers[name]
		return ResourceBasedRenderer.renderer(self, ctx, name)


_rendererRegistry = {}

def registerRenderer(name, aRenderer):
	_rendererRegistry[name] = aRenderer

def getRenderer(rendName):
	return _rendererRegistry[rendName]
