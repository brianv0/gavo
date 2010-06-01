"""
The root resource of the data center.
"""


import os
import traceback
from cStringIO import StringIO

from twisted.internet import defer
from twisted.python import failure
from twisted.python import log
# we put some calculations into threads.
from twisted.python import threadable
threadable.init()

from nevow import appserver
from nevow import context
from nevow import inevow
from nevow import rend
from nevow import static
from nevow import url

from gavo import base
from gavo import svcs
from gavo import registry    # for registration
from gavo.imp import formal
from gavo.web import caching
from gavo.web import common
from gavo.web import grend
from gavo.web import ifpages
from gavo.web import weberrors

from gavo.svcs import Error, UnknownURI, ForbiddenURI, WebRedirect, BadMethod, Authenticate


###  some global manipulations of nevow/twisted
# monkeypatch static's mime magic
static.File.contentTypes[".ascii"] = "application/octet-stream"
static.File.contentTypes[".vot"] = "application/x-votable+xml"
static.File.contentTypes[".rd"] = "application/x-gavo-descriptor+xml"
# this one is for co-operation with ifpages
static.File.contentTypes[".shtml"] = "text/nevow-template"


class VanityLineError(Error):
	"""parse error in vanity file.
	"""
	def __init__(self, msg, lineNo, src):
		Error.__init__("Mapping file %s, line %d: %s"%(repr(src), msg, lineNo))
		self.msg, self.lineNo, self.src = msg, lineNo, src


builtinVanity = """
	__system__/products/p/get getproduct
	__system__/services/registry/pubreg.xml oai.xml
	__system__/services/overview/external odoc
	__system__/dc_tables/show/tablenote tablenote
	__system__/dc_tables/show/tableinfo tableinfo
	__system__/adql/query/form adql !redirect
	__system__/services/overview/admin seffe
	__system__/tap/run/tap tap
"""


def makeDynamicPage(pageClass):
	"""returns a resource that returns a "dynamic" resource of pageClass.

	pageClass must be a rend.Page subclass that is constructed with a
	request context (like ifpages.LoginPage).  We want such things
	when the pages have some internal state (since you're not supposed
	to keep such things in the context any more, which I personally agree
	with).

	The dynamic pages are directly constructed, their locateChild methods
	are not called (do we want to change this)?
	"""
	class DynPage(rend.Page):
		def renderHTTP(self, ctx):
			return pageClass(ctx)
	return DynPage()


def _hackHostHeader(ctx):
	"""works around host-munging of forwarders.

	This is a hack in that I hardcode port 80 for the forwarder.  Ah
	well, I don't think I have a choice there.
	"""
	request = inevow.IRequest(ctx)
	fwHost = request.getHeader("x-forwarded-host")
	if fwHost:
		request.setHost(fwHost, 80)


# A cache for RD-specific page caches.  Each of these maps segments
# (tuples) to a finished text document.  The argument is the id of the
# RD responsible for generating that data.  This ensures that pre-computed
# data is cleared when the RD is reloaded.
base.caches.makeCache("getPageCache", lambda rdId: {})


class ArchiveService(rend.Page):
	"""The root resource on the data center.

	It does the main dispatching based on four mechanisms:

	(0) redirects -- one-segments fragments that redirect somewhere else.
	    This is for "bad" shortcuts corresponding to input directory name
	    exclusively (since it's so messy).  These will not match if
	    path has more than one segment.
	(1) statics -- first segment leads to a resource that gets passed any
	    additional segments.
	(2) mappings -- first segment is replaced by something else, processing
	    continues.
	(3) resource based -- consisting of an RD id, a service id, a renderer and
	    possibly further segments.
	
	The first three mechanisms only look at the first segment to determine
	any action (except that redirect is skipped if len(segments)>1).

	The statics and mappings are configured on the class level.
	"""
	statics = {}
	mappings = {}
	redirects = {}

	def __init__(self):
		rend.Page.__init__(self)
		self.maintFile = os.path.join(base.getConfig("stateDir"), "MAINT")
		self.rootSegments = tuple(s for s in 
			base.getConfig("web", "nevowRoot").split("/") if s)
		self.rootLen = len(self.rootSegments)

	@classmethod
	def addRedirect(cls, key, destination):
		cls.redirects[key] = destination

	@classmethod
	def addStatic(cls, key, resource):
		cls.statics[key] = resource

	@classmethod
	def addMapping(cls, key, segments):
		cls.mappings[key] = segments

	knownVanityOptions = set(["!redirect"])

	@classmethod
	def _parseVanityLines(cls, src):
		"""a helper for parseVanityMap.
		"""
		lineNo = 0
		for ln in src:
			lineNo += 1
			ln = ln.strip()
			if not ln or ln.startswith("#"):
				continue
			parts = ln.split()
			if not 1<len(parts)<4:
				raise VanityLineError("Wrong number of words in '%s'"%ln, lineNo, src)
			options = []
			if len(parts)>2:
				options.append(parts.pop())
				if options[-1] not in cls.knownVanityOptions:
					raise VanityLineError("Bad option '%s'"%option, lineNo, src)
			dest, src = parts
			yield src, dest, options
	
	@classmethod
	def _addVanityRedirect(cls, src, dest, options):
		"""a helper for parseVanityMap.
		"""
		if '!redirect' in options:
			cls.addRedirect(src, base.makeSitePath(dest))
		else:
			cls.addMapping(src, dest.split("/"))

	@classmethod
	def parseVanityMap(cls, inFile):
		"""adds mappings from inFile (which can be a file object or a name).

		The input files contain lines of the format

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
		if only one or two segments are in the original query.  You can
		use this to create shortcuts with the resource dir names.  This would
		otherwise create endless loops.

		Empty lines and #-on-a-line-comments are allowed in the input.

		In case inFile is a file object, it will be closed as a side effect.
		"""
		if isinstance(inFile, basestring):
			if not os.path.isfile(inFile):
				return
			inFile = open(inFile)
		try:
			for src, dest, options in cls._parseVanityLines(inFile):
				cls._addVanityRedirect(src, dest, options)
		finally:
			inFile.close()
		
	def renderHTTP(self, ctx):
		# this is only ever executed on the root URL.  For consistency
		# (e.g., caching), we route this through locateChild though
		# we know we're going to return RootPage.  locateChild must
		# thus *never* return self, ().
		return self.locateChild(ctx, self.rootSegments)

	def _processCache(self, ctx, service, rendC, segments):
		"""shortcuts if ctx's request can be cached with rendC.

		This function returns a cached item if a page is in the cache and
		request allows caching, None otherwise.  For cacheable requests,
		it instruments the request such that the page is actually cached.

		Requests with arguments or a user info are never cacheable.
		"""
		request = inevow.IRequest(ctx)
		if request.method!="GET" or request.args or request.getUser():
			return None
		if not rendC.isCacheable(segments, request):
			return None
		cache = base.caches.getPageCache(service.rd.sourceId)
		segments = tuple(segments)
		if segments in cache:
			return cache[segments]
		caching.instrumentRequestForCaching(request,
			caching.enterIntoCacheAs(segments, cache))
		return None

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
# XXX TODO: set the last modified header to the larger of (rdModTime, serverStartTime) here.
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

		cached = self._processCache(ctx, service, rendC, segments)
		if cached:
			return cached, ()
		else:
			return rendC(ctx, service), segments[srvInd+2:]

	def locateChild(self, ctx, segments):
		_hackHostHeader(ctx)
		if os.path.exists(self.maintFile):
			return static.File(common.getTemplatePath("maintenance.html")), ()
		if self.rootSegments:
			if segments[:self.rootLen]!=self.rootSegments:
				raise UnknownURI("Misconfiguration: Saw a URL outside of the server's"
					" scope")
			segments = segments[self.rootLen:]
		
		if segments==('',):
			segments = ("__system__", "services", "root", "fixed")

		if ((len(segments)==1 or (
					len(segments)==2 and segments[1]==''))
				and segments[0] in self.redirects):
			raise WebRedirect(self.redirects[segments[0]])

		if segments[0] in self.statics:
			return self.statics[segments[0]], segments[1:]

		if segments[0] in self.mappings:
			segments = self.mappings[segments[0]]+list(segments[1:])

		try:
			return self._locateResourceBasedChild(ctx, segments)
		except grend.RDBlocked:
			return static.File(common.getTemplatePath("blocked.html")), () 


ArchiveService.addStatic("login", makeDynamicPage(ifpages.LoginPage))
ArchiveService.addStatic("reload", makeDynamicPage(ifpages.ReloadPage))
ArchiveService.addStatic("static", ifpages.StaticServer())

ArchiveService.addStatic('formal.css', formal.defaultCSS)
ArchiveService.addStatic('js', formal.formsJS)

if base.getConfig("web", "enabletests"):
	from gavo.web import webtests
	ArchiveService.addStatic("test", webtests.Tests())
if (base.getConfig("web", "favicon")
		and os.path.exists(base.getConfig("web", "favicon"))):
	ArchiveService.addStatic("favicon.ico",
		static.File(base.getConfig("web", "favicon")))

ArchiveService.parseVanityMap(StringIO(builtinVanity))
ArchiveService.parseVanityMap(os.path.join(base.getConfig("webDir"), 
	base.getConfig("web", "vanitynames")))

root = ArchiveService()

# Nevow's ICanHandleException and friends is completely broken for my
# purposes (or just extremely obscure).  Let's go monkeypatching...

def processingFailed(error, request, ctx):
	try:
		handler = weberrors.getDCErrorPage(error)
		handler.renderHTTP(ctx)
	except:
		error = failure.Failure()
		weberrors.PanicPage(error).renderHTTP_exception(ctx, error)
	request.finishRequest(False)
	return appserver.errorMarker

appserver.processingFailed = processingFailed

site = appserver.NevowSite(root)
# the next line unfortunately has no effect with 2010 twisted, but
# should eventually replace the processingFailed hack above.
site.remember(weberrors.DCExceptionHandler)
