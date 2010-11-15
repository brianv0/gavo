"""
Renderers that take services "as arguments".
"""

import os
import urllib

from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import tags as T, entities as E
from nevow import url

from zope.interface import implements

from gavo import base
from gavo import registry
from gavo import svcs
from gavo import utils
from gavo.web import common
from gavo.web import grend


class MetaRenderer(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""Renderers that are allowed on all services.
	"""
	checkedRenderer = False

	@classmethod
	def isCacheable(self, segments, request):
		return True

	def data_otherServices(self, ctx, data):
		"""returns a list of dicts describing other services provided by the
		the describing RD.

		The class mixing this in needs to provide a describingRD attribute for
		this to work.  This may be the same as self.service.rd, and the
		current service will be excluded from the list in this case.
		"""
		res = []
		for svc in self.describingRD.services:
			if svc is not self.service:
				res.append({"infoURL": svc.getURL("info"),
					"title": unicode(svc.getMeta("title"))})
		return res

	def render_sortOrder(self, ctx, data):
		request = inevow.IRequest(ctx)
		if "dbOrder" in request.args:
			return ctx.tag["Sorted by DB column index. ",
				T.a(href=url.URL.fromRequest(request).remove("dbOrder"))[
					"[Sort alphabetically]"]]
		else:
			return ctx.tag["Sorted alphabetically. ",
				T.a(href=url.URL.fromRequest(request).add("dbOrder", "True"))[
					"[Sort by DB column index]"]]

	def render_ifkey(self, keyName):
		def render(ctx, data):
			if data.has_key(keyName):
				return ctx.tag
			return ""
		return render


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
	def _explain_fixed(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("fixed"))["custom page"],
			", possibly with dynamic content"]
	
	@classmethod
	def _explain_soap(cls, service):

		def generateArguments():
			# Slightly obfuscated -- I need to get ", " in between the items.
			fieldIter = iter(svcs.getRenderer("soap").getInputFields(service))
			try:
				next = fieldIter.next()
				while True:
					desc = "%s/%s"%(next.name, next.type)
					if next.required:
						desc = T.strong[desc]
					yield desc
					next = fieldIter.next()
					yield ', '
			except StopIteration:
				pass

		return T.invisible["enables remote procedure calls; to use it,"
			" feed the WSDL URL "+
			service.getURL("soap")+"/go?wsdl"+
			" to your SOAP library; the function signature is"
			"  useService(",
			generateArguments(),
			").  See also our ", 
			T.a(render=T.directive("rootlink"), href="/static/doc/soaplocal.shtml")[
				"local soap hints"]]

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
			" use ", service.getURL("siap.xml"), " to access the service",
			T.invisible(render=T.directive("ifadmin"))[" -- ",
				T.a(href="http://nvo.ncsa.uiuc.edu/dalvalidate/SIAValidater?endpoint="+
					urllib.quote(service.getURL("siap.xml"))+
					"&RA=180.0&DEC=60.0&RASIZE=1.0&DECSIZE=1.0&FORMAT=ALL&"
					"format=html&show=fail&show=warn&show=rec&op=Validate")["Validate"]]]

	@classmethod
	def _explain_scs_xml(cls, service):
		return T.invisible["a standard SCS interface as defined by the"
			" IVOA to access catalog-type data; SCS clients"
			" use ", service.getURL("scs.xml"), " to access the service",
			T.invisible(render=T.directive("ifadmin"))[" -- ",
				T.a(href="http://nvo.ncsa.uiuc.edu/dalvalidate/"
					"ConeSearchValidater?endpoint="+
					urllib.quote(service.getURL("scs.xml"))+
					"&RA=180.0&DEC=60.0&SR=1.0&format=html&show=fail&show=warn&show=rec"
					"&op=Validate")["Validate"]]]

	@classmethod
	def _explain_tap(cls, service):
		return T.invisible["the interface to this site's Table Access Protocol"
			" service.  This protocol is best used using specialized clients"
			" or libraries, but an XSL-enabled web browser lets you"
			" operate ",
			T.a(href=service.getURL("tap")+"/async")["the service"],
			" as well."]

	@classmethod
	def _explain_qp(cls, service):
		return T.invisible["an interface that uses the last path element"
			" to query the column %s in the underlying table."%
			service.getProperty("queryField", "defunct")]

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
		return T.invisible["an interface to image creation targeted at machines."
			"  The interface is at %s."%service.getURL("img.jpeg"),
			"  This is probably irrelevant to you."]

	@classmethod
	def _explainEverything(cls, service):
		return T.invisible["a renderer with some custom access method that"
			" should be mentioned in the service description"]

	@classmethod
	def explain(cls, renderer, service):
		return getattr(cls, "_explain_"+renderer.replace(".", "_"), 
			cls._explainEverything)(service)


class ServiceInfoRenderer(MetaRenderer, utils.IdManagerMixin):
	"""is a renderer that shows information about a service.
	"""
	name = "info"
	
	customTemplate = svcs.loadSystemTemplate("serviceinfo.html")

	def __init__(self, *args, **kwargs):
		grend.ServiceBasedPage.__init__(self, *args, **kwargs)
		self.describingRD = self.service.rd
		self.footnotes = set()

	def render_title(self, ctx, data):
		return ctx.tag["Information on Service '%s'"%unicode(
			self.service.getMeta("title"))]

	def render_notebubble(self, ctx, data):
		if not data["note"]:
			return ""
		id = data["note"].tag
		self.footnotes.add(data["note"])
		return ctx.tag(href="#note-%s"%id)["Note %s"%id]

	def render_footnotes(self, ctx, data):
		"""renders the footnotes as a definition list.
		"""
		return T.dl(class_="footnotes")[[
				T.xml(note.getContent(targetFormat="html"))
			for note in sorted(self.footnotes, key=lambda n: n.tag)]]

	def data_inputFields(self, ctx, data):
		res = [f.asInfoDict() for f in self.service.getInputFields()+
				self.service.serviceKeys]
		res.sort(key=lambda val: val["name"].lower())
		return res

	def data_htmlOutputFields(self, ctx, data):
		res = [f.asInfoDict() for f in self.service.getCurOutputFields()]
		res.sort(key=lambda val: val["name"].lower())
		return res

	def data_votableOutputFields(self, ctx, data):
		queryMeta = svcs.QueryMeta({"_FORMAT": "VOTable", "_VERB": 3})
		res = [f.asInfoDict() for f in self.service.getCurOutputFields(queryMeta)]
		res.sort(key=lambda val: val["verbLevel"])
		return res

	def data_rendAvail(self, ctx, data):
		return [{"rendName": rend, 
				"rendExpl": RendExplainer.explain(rend, self.service)}
			for rend in self.service.allowed]

	def data_publications(self, ctx, data):
		res = [{"sets": ",".join(p.sets), "render": p.render} 
			for p in self.service.publications if p.sets]
		return sorted(res, key=lambda v: v["render"])

	def data_browserURL(self, ctx, data):
		return self.service.getBrowserURL()

	defaultDocFactory = common.doctypedStan(
		T.html[
			T.head[
				T.title["Missing Template"]],
			T.body[
				T.p["Infos are only available with a serviceinfo.html template"]]
		])


class TableInfoRenderer(MetaRenderer):
	"""A renderer for displaying table information.

	It really doesn't use the underlying service, but conventionally,
	it is run on __system__/dc_tables/show.
	"""
	name = "tableinfo"
	customTemplate = svcs.loadSystemTemplate("tableinfo.html")

	def renderHTTP(self, ctx):
		if not hasattr(self, "table"):  
			# _retrieveTableDef did not run, i.e., no tableName was given
			raise svcs.UnknownURI(
				"You must provide a table name to this renderer.")
		self.setMetaParent(self.table)
		return super(TableInfoRenderer, self).renderHTTP(ctx)

	def _retrieveTableDef(self, tableName):
		try:
			self.tableName = tableName
			self.table = registry.getTableDef(tableName)
			self.describingRD = self.table.rd
		except base.NotFoundError, msg:
			raise base.ui.logOldExc(svcs.UnknownURI(str(msg)))

	def data_forADQL(self, ctx, data):
		return self.table.adql

	def data_fields(self, ctx, data):
		res = [f.asInfoDict() for f in self.table]
		for d in res:
			if d["note"]:
				d["noteKey"] = d["note"].tag
		if not "dbOrder" in inevow.IRequest(ctx).args:
			res.sort(key=lambda item: item["name"].lower())
		return res

	def render_title(self, ctx, data):
		return ctx.tag["Table information for '%s'"%self.tableName]
	
	def render_rdmeta(self, ctx, data):
		# rdmeta: Meta info at the table's rd (since there's ownmeta)
		metaKey = ctx.tag.children[0]
		ctx.tag.clear()
		htmlBuilder = common.HTMLMetaBuilder(self.describingRD)
		try:
			return ctx.tag[T.xml(self.describingRD.buildRepr(metaKey, htmlBuilder))]
		except base.NoMetaKey:
			return ""

	def render_ifrdmeta(self, metaName):
		if self.describingRD.getMeta(metaName, propagate=False):
			return lambda ctx, data: ctx.tag
		else:
			return lambda ctx, data: ""

	def locateChild(self, ctx, segments):
		if len(segments)!=1:
			return None, ()
		self._retrieveTableDef(segments[0])
		return self, ()

	defaultDocFactory = common.doctypedStan(
		T.html[
			T.head[
				T.title["Missing Template"]],
			T.body[
				T.p["Infos are only available with a tableinfo.html template"]]
		])


class TableNoteRenderer(MetaRenderer):
	"""A renderer for displaying table notes.

	It takes a schema-qualified table name and a note tag in the segments.

	This does not use the underlying service, so it could and will run on
	any service.  However, you really should run it on __system__/dc_tables/show,
	and there's a built-in vanity name tablenote for this.
	"""
	name = "tablenote"

	def renderHTTP(self, ctx):
		if not hasattr(self, "noteTag"):  
			# _retrieveTableDef did not run, i.e., no tableName was given
			raise svcs.UnknownURI(
				"You must provide table name and note tag to this renderer.")
		return super(TableNoteRenderer, self).renderHTTP(ctx)

	def _retrieveNote(self, tableName, noteTag):
		try:
			table = registry.getTableDef(tableName)
			self.setMetaParent(table)
			self.noteHTML = table.getNote(noteTag
				).getContent(targetFormat="html")
		except base.NotFoundError, msg:
			raise base.ui.logOldExc(svcs.UnknownURI(msg))
		self.noteTag = noteTag
		self.tableName = tableName

	def locateChild(self, ctx, segments):
		if len(segments)==2:
			self._retrieveNote(segments[0], segments[1])
		elif len(segments)==3: # segments[0] may be anything, 
			# but conventionally "inner"
			self._retrieveNote(segments[1], segments[2])
			self.docFactory = self.innerDocFactory
		else:
			return None, ()
		return self, ()

	def data_tableName(self, ctx, data):
		return self.tableName
	
	def data_noteTag(self, ctx, data):
		return self.noteTag
	
	def render_noteHTML(self, ctx, data):
		return T.xml(self.noteHTML)

	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["GAVO DC -- Note for table ",
				T.invisible(render=rend.data, data=T.directive("tableName"))],
			T.invisible(render=T.directive("commonhead")),
			T.style["span.target {font-size: 180%;font-weight:bold}"],
		],
		T.body[
			T.invisible(render=T.directive("noteHTML"))]])

	innerDocFactory = loaders.stan(
		T.invisible(render=T.directive("noteHTML")))


class ExternalRenderer(grend.ServiceBasedPage):
	"""A renderer redirecting to an external resource.

	These try to access an external publication on the parent service
	and ask it for an accessURL.  If it doesn't define one, this will
	lead to a redirect loop.

	In the DC, external renderers are mainly used for registration of
	third-party browser-based services.
	"""
	name = "external"

	@classmethod
	def isBrowseable(self, service):
		return True # we probably need some way to say when that's wrong...

	def renderHTTP(self, ctx):
		# look for a matching publication in the parent service...
		for pub in self.service.publications:
			if pub.render==self.name:
				break
		else: # no publication, 404
			raise svcs.UnknownURI()
		raise svcs.WebRedirect(str(pub.getMeta("accessURL")))
