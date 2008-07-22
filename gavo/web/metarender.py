"""
Renderers that take services "as arguments".
"""

import os

import pkg_resources

from nevow import inevow
from nevow import loaders
from nevow import tags as T, entities as E

from zope.interface import implements

from gavo.parsing import contextgrammar
from gavo.web import common
from gavo.web import resourcebased



class BlockRdRenderer(resourcebased.ServiceBasedRenderer):
	"""is a renderer used for blocking RDs from the web interface.
	"""
	name = None   # may be used on all services

	def data_blockstate(self, ctx, data):
		if hasattr(self.rd, "currently_blocked"):
			return "blocked"
		return "unblocked"

	def data_rdId(self, ctx, data):
		return str(self.rd.sourceId)

	def renderHTTP(self, ctx):
		return creds.runAuthenticated(ctx, "admin", self.realRenderHTTP,
			ctx)

	def realRenderHTTP(self, ctx):
		self.rd.currently_blocked = True
		return ServiceBasedRenderer.renderHTTP(self, ctx)

	defaultDocFactory = loaders.stan(
		T.html[
			T.head[
				T.title["RD blocked"],
			],
			T.body[
				T.h1["RD blocked"],
				T.p["All services defined in ", 
					T.invisible(render=T.directive("data"), data=T.directive(
						"rdId")),
					" are now ",
					T.invisible(render=T.directive("data"), data=T.directive(
						"blockstate")),
					".  To unblock, restart the server.",
				],
			]
		])


class RendExplainer(object):
	"""is a container for various functions having to do with explaining
	renderers on services.

	Use the explain(renderer, service) class method.
	"""

	@classmethod
	def _explain_form(cls, service):
		return T.invisible["allows access via an ",
			T.a(href=service.getURL("form"))["HTML form"]]

	@classmethod
	def _explain_soap(cls, service):
		return T.invisible["enables remote procedure calls; to use it,"
			" feed the ", 
			T.a(href=service.getURL("soap")+"/go?wsdl")["WSDL URL"],
			" to your SOAP library"]

	@classmethod
	def _explain_custom(cls, service):
		return T.invisible["a custom rendering of the service, typically"
			" for interactive web applications; see ", 
			T.a(href=service.getURL("custom"))["entry page"]]
	
	@classmethod
	def _explain_static(cls, service):
		return T.invisible["static (i.e. prepared) data or custom client-side"
			" code; probably used to access ancillary files here"]
	
	@classmethod
	def _explain_text(cls, service):
		return T.invisible["a text interface not intended for user"
			" applications"]
	
	@classmethod
	def _explain_siap_xml(cls, service):
		return T.invisible["a standard SIAP interface as defined by the"
			" IVOA to access collections of celestial images; SIAP clients"
			" use ", service.getURL("siap.xml"), " to access the service"]

	@classmethod
	def _explain_scs_xml(cls, service):
		return T.invisible["a standard SCS interface as defined by the"
			" IVOA to access catalog-type data; SCS clients"
			" use ", service.getURL("siap.xml"), " to access the service"]

	@classmethod
	def _explain_upload(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("upload"))["form-based interface"],
			" for uploading data"]

	@classmethod
	def _explain_mupload(cls, service):
		return T.invisible["an upload interface for use with custom"
			" upload programs.  These should access ",
			service.getURL("mupload")]
	
	@classmethod
	def _explain_img_jpeg(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("img.jpeg"))["form-based interface"],
			" to generate jpeg images from the underlying data"]

	@classmethod
	def _explain_mimg_jpeg(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("img.jpeg"))["form-based interface"],
			" to generate jpeg images from the underlying data; the replies"
			" are intended for machine consumption"]

	@classmethod
	def _explainEverything(cls, service):
		return T.invisible["a renderer with some custom access method that"
			" should be mentioned in the service description"]

	@classmethod
	def explain(cls, renderer, service):
		return getattr(cls, "_explain_"+renderer.replace(".", "_"), 
			cls._explainEverything)(service)


class ServiceInfoRenderer(resourcebased.ServiceBasedRenderer):
	"""is a renderer that shows information about a service.
	"""
	name = None  # allow on all services
	
	customTemplate = common.loadSystemTemplate("serviceinfo.html")

	def render_title(self, ctx, data):
		return ctx.tag["Information on Service '%s'"%unicode(
			self.service.getMeta("title"))]

	defaultColNames = "name,tablehead,description,unit,ucd"
	defaultHeading = T.tr[
		T.th["Name"], T.th["Table Head"], T.th["Description"],
		T.th["Unit"], T.th["UCD"]]

	def render_tableOfFields(self, ctx, data):
		"""renders a list of dicts in data as a table.

		The columns and header of the table are defined in the headers and data
		patterns.  See the serviceinfo.html template for examples.
		"""
		colNames = [s.strip() for s in 
			ctx.tag.attributes.get("columns", self.defaultColNames).split(",")]
		header = ctx.tag.patternGenerator("header", default=self.defaultHeading)
		return ctx.tag.clear()(
				render=T.directive("sequence"), class_="shorttable")[
			header(pattern="header"),
			T.tr(pattern="item", render=T.directive("mapping"))[
				[T.td[T.slot(name=name)] for name in colNames]]]
			
	def data_inputFields(self, ctx, data):
		grammar = self.service.get_inputFilter().get_Grammar()
		if isinstance(grammar, contextgrammar.ContextGrammar):
			res = [f.asInfoDict() for f in grammar.get_inputKeys()]
			res.sort(lambda a,b: cmp(a["name"], b["name"]))
		else:
			res = None
		return res

	def data_htmlOutputFields(self, ctx, data):
		res = [f.asInfoDict() for f in self.service.getCurOutputFields()]
		res.sort(lambda a,b: cmp(a["name"], b["name"]))
		res.sort()
		return res

	def data_votableOutputFields(self, ctx, data):
		queryMeta = common.QueryMeta({"_FORMAT": ["VOTable"], "_VERB": [3]})
		res = [f.asInfoDict() for f in self.service.getCurOutputFields(queryMeta)]
		res.sort(lambda a,b: cmp(a["verbLevel"], b["verbLevel"]))
		return res

	def data_rendAvail(self, ctx, data):
		return [{"rendName": rend, 
				"rendExpl": RendExplainer.explain(rend, self.service)}
			for rend in self.service.get_allowedRenderers()]

	def data_otherServices(self, ctx, data):
		"""returns a list of dicts describing other services provided by the
		service's RD.
		"""
		res = []
		for svcId in self.service.rd.itemsof_service():
			svc = self.service.rd.get_service(svcId)
			if svc is not self.service:
				res.append({"infoURL": svc.getURL("info"),
					"title": unicode(svc.getMeta("title"))})
		return res

	defaultDocFactory = common.doctypedStan(
		T.html[
			T.head[
				T.title["Missing Template"]],
			T.body[
				T.p["Infos are only available with a serviceinfo.html template"]]
		])
