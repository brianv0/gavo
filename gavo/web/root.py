"""
The root resource of the data center.
"""


import cStringIO
import glob
import math
import new
import os
import pkg_resources
import re
import sys
import traceback
import urllib
import urlparse


from twisted.internet import defer
from twisted.internet import reactor
from twisted.python import components
from twisted.python import failure
# we put some calculations into threads.
from twisted.python import threadable
threadable.init()

from nevow import appserver
from nevow import context
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E
from nevow import url

from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo import registry    # for registration
from gavo.imp import formal
from gavo.web import common
from gavo.web import grend
from gavo.web import ifpages
from gavo.web import weberrors

from gavo.svcs import Error, UnknownURI, ForbiddenURI, WebRedirect, BadMethod, Authenticate



class VanityLineError(Error):
	"""parse error in vanity file.
	"""
	pass


class VanityMap(object):
	"""is a container for redirects and URI rewriting.

	VanityMaps are constructed from files containing lines of the format

	<target> <key> [<option>]

	Target is a path that must *not* include nevowRoot and must *not* start
	with a slash (unless you're going for special effects).

	Key is a single path element.  If this path element is found in the
	first segment, it is replaced with the segments in target.  This
	could be used at some point to hide the inputsDir structure even
	for user RDs, but it's a bit hard to feed the vanity map then (since
	the service would have to know about its vanity name, and we don't want
	to have to parse all RDs to come up with the VanityMap).

	<option> can be !redirect right now.  If it is, target is interpreted
	as a server-relative URI, and a redirect to it is generated, but only
	if only one or two segements are in the original query.  You can
	use this to create shortcuts with the resource dir names.  This would
	otherwise create endless loops.

	Empty lines and #-on-a-line-comments are allowed in the input.
	"""

	knownOptions = set(["!redirect"])

	builtinRedirects = """
		__system__/products/p/get getproduct
		__system__/services/registry/pubreg.xml oai.xml
		__system__/services/overview/external odoc
		__system__/dc_tables/show/tablenote tablenote
		__system__/dc_tables/show/tableinfo tableinfo
		__system__/adql/query/form adql !redirect
		__system__/services/overview/admin seffe
	"""

	def __init__(self):
		self.redirects, self.mappings = {}, {}
		for ln in self.builtinRedirects.split("\n"):
			self._parseLine(ln)
		self._loadFromFile()

	def _loadFromFile(self):
		srcName = os.path.join(base.getConfig("webDir"), 
			base.getConfig("web", "vanitynames"))
		if not os.path.isfile(srcName):
			return
		f = open(srcName)
		lineNo = 1
		for ln in f:
			try:
				self._parseLine(ln)
			except VanityLineError, msg:
				raise VanityLineError("%s, line %s: %s"%(srcName, lineNo, str(msg)))
			lineNo += 1
		f.close()

	def _parseLine(self, ln):
		ln = ln.strip()
		if not ln or ln.startswith("#"):
			return
		parts = ln.split()
		if not 1<len(parts)<4:
			raise VanityLineError("Wrong number of words in '%s'"%ln)
		option = None
		if len(parts)>2:
			option = parts.pop()
			if option not in self.knownOptions:
				raise VanityLineError("Bad option '%s'"%option)
		dest, src = parts
		if option=='!redirect':
			self.redirects[src] = dest
		else:
			self.mappings[src] = dest.split("/")

	def map(self, segments):
		"""changes the nevow-type segments list according to the mapping.

		It may raise a WebRedirect exception.
		"""
		if not segments:
			return segments
		key = segments[0]
		if key in self.redirects and len(segments)<3:
			raise WebRedirect(self.redirects[key])
		if key in self.mappings:
			segments = self.mappings[key]+list(segments[1:])
		return segments
		

_vanityMap = VanityMap()


class RootPage(common.CustomTemplateMixin, rend.Page, grend.GavoRenderMixin):
	"""The data center's "home page".
	"""
	def data_chunkedServiceList(self, ctx, data):
		"""returns a service list alphabetically chunked.
		"""
		# The weird key to the cache makes it clear when you reload services
		return base.caches.getChunkedServiceList("__system__/services")[:]

	def data_subjectServiceList(self, ctx, data):
		# The weird key to the cache makes it clear when you reload services
		return base.caches.getSubjectsList("__system__/services")

	def render_ifprotected(self, ctx, data):
		if data["owner"]:
			return ctx.tag
		else:
			return ""

	defaultDocFactory = common.loadSystemTemplate("root.html")


class ArchiveService(rend.Page):

	def __init__(self):
		self.maintFile = os.path.join(base.getConfig("stateDir"), "MAINT")
		rend.Page.__init__(self)
		self.rootSegments = tuple(s for s in 
			base.getConfig("web", "nevowRoot").split("/") if s)
		self.rootLen = len(self.rootSegments)

	def renderHTTP(self, ctx):
		# this is only ever executed on the root URL.  For consistency
		# (e.g., caching), we route this through locateChild though
		# we know we're going to return RootPage.  locateChild must
		# thus *never* return self.
		return self.locateChild(ctx, (""))

	def _hackHostHeader(self, ctx):
		"""works around host-munging of forwarders.

		This is a hack in that I hardcode port 80 for the forwarder.  Ah
		well, I don't think I have a choice there.
		"""
		request = inevow.IRequest(ctx)
		fwHost = request.getHeader("x-forwarded-host")
		if fwHost:
			request.setHost(fwHost, 80)
		
	if base.getConfig("web", "enabletests"):
		from gavo.web import webtests
		child_test = webtests.Tests()

	child_static = ifpages.StaticServer()
	child_builtin = ifpages.BuiltinServer()
	child_debug = weberrors.DebugPage()

	def _locateResourceBasedChild(self, ctx, segments):
		"""returns a standard, resource-based service renderer.

		Their URIs look like <rd id>/<service id>{/<anything>}.

		This works by successively trying to use parts of the query path 
		of increasing length as RD ids.  If one matches, the next
		segment is the service id, and the following one the renderer.

		The remaining segments are returned unconsumed.

		If no RD matches, an UnknwownURI exception is raised.
		"""
		for srvInd in range(1, len(segments)-1):
			try:
				rd = base.caches.getRD("/".join(segments[:srvInd]))
			except base.RDNotFound:
				continue
			else:
				break
		else:
			raise UnknownURI("No matching RD")
		try:
			subId, rendName = segments[srvInd], segments[srvInd+1]
		except IndexError:
			raise UnknownURI("Bad segments after existing resource: %s"%(
				"/".join(segments[srvInd:])))
			
		service = rd.getService(subId)
		if service is None:
			raise UnknownURI("No such service: %s"%subId)
		rendC = svcs.getRenderer(rendName)
		return rendC(ctx, service), segments[srvInd+2:]

	def _realLocateChild(self, ctx, segments):
# XXX TODO: refactor this mess, clean up strange names by pulling more
# into proper services.
		self._hackHostHeader(ctx)
		if os.path.exists(self.maintFile):
			return static.File(common.getTemplatePath("maintenance.html")), ()

		if self.rootSegments:  # remove off-root path elements
			if segments[:self.rootLen]!=self.rootSegments:
				return None, ()
			segments = segments[self.rootLen:]

		if not segments or len(segments)==1 and segments[0]=='':
			return RootPage(), ()

		# handle vanity names and shortcuts
		segments = _vanityMap.map(segments)

		# Hm... there has to be a smarter way to do such things...?
		# Pending sanitized dispatcher...
		if segments[0]=="login":
			return ifpages.LoginPage(ctx), ()
		elif segments[0]=="reload":
			return ifpages.ReloadPage(ctx), ()

		# base handling
		name = segments[0]
		if name and hasattr(self, "child_"+name):
			res = getattr(self, "child_"+name), segments[1:]
		else:
			try:
				res = self._locateResourceBasedChild(ctx, segments)
			except grend.RDBlocked:
				return static.File(common.getTemplatePath("blocked.html")), () 
		return res
	
	def locateChild(self, ctx, segments):
		try:
			res, segments = self._realLocateChild(ctx, segments)
		except WebRedirect, redirTo:
			return weberrors.RedirectPage(redirTo.args[0]), ()
		except ForbiddenURI, exc:
			return weberrors.ForbiddenPage(str(exc)), ()
		except UnknownURI, exc:
			traceback.print_exc()
			return weberrors.NotFoundPage(str(exc)), ()
		except BadMethod, exc:
			return weberrors.BadMethodPage(str(exc)), ()
		except Authenticate, exc:
			return weberrors.AuthenticatePage(exc.args[0]), ()
		except Exception, msg:
			traceback.print_exc()
			raise
		if res is None:
			return weberrors.NotFoundPage(), ()
		else:
			return res, segments


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)
if (base.getConfig("web", "favicon")
		and os.path.exists(base.getConfig("web", "favicon"))):
	setattr(ArchiveService, "child_favicon.ico",
		static.File(base.getConfig("web", "favicon")))


if base.getConfig("web", "errorPage")=="debug":
	appserver.DefaultExceptionHandler = weberrors.ErrorPageDebug
else:
	appserver.DefaultExceptionHandler = weberrors.ErrorPage
#root = ArchiveService()
