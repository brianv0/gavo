"""
Common code for the nevow based interface.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import cgi
import re
import urllib

from nevow import appserver
from nevow import tags as T
from nevow import loaders
from nevow import inevow
from nevow import rend
from nevow import static
try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http #noflake: conditional import

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.protocols import creds


# monkeypatching static's mime magic
static.File.contentTypes[".ascii"] = "application/octet-stream"
static.File.contentTypes[".f"] = "text/x-fortran"
static.File.contentTypes[".vot"] = base.votableType,
static.File.contentTypes[".rd"] = "application/x-gavo-descriptor+xml"
static.File.contentTypes[".f90"] = "text/x-fortran"
static.File.contentTypes[".skyglow"] = "text/plain"
static.File.contentTypes[".fitstable"] = "application/fits"
# this one is for co-operation with ifpages
static.File.contentTypes[".shtml"] = "text/nevow-template"


@utils.memoized
def getExtForMime(mime):
	"""returns an extension (with dot) for a mime type.

	This is the first that matches in the mime registry in of 
	nevow.static.File and thus may change between runs of the software.

	If no extension matches, ".bin" is returned.
	"""
	mediaType, paramdict = cgi.parse_header(mime)

	if mediaType==base.votableType:
		return ".vot"

	for ext, type in static.File.contentTypes.iteritems():
		if mediaType==type:
			return ext
	return ".bin"


def escapeForHTML(aString):
	return aString.replace("&", "&amp;"
		).replace("<", "&lt;"
		).replace(">", "&gt;")


def getfirst(ctx, key, default):
	"""returns the first value of key in the nevow context ctx.
	"""
	return utils.getfirst(inevow.IRequest(ctx).args, key, default)


class HTMLMetaBuilder(meta.MetaBuilder):
	def __init__(self, macroPackage=None):
		meta.MetaBuilder.__init__(self)
		self.resultTree, self.currentAtom = [[]], None
		self.macroPackage = macroPackage

	def startKey(self, atom):
		self.resultTree.append([])
		
	def enterValue(self, value):
		val = value.getContent("html", self.macroPackage)
		if val:
			self.resultTree[-1].append(T.xml(val))
		# for meta items rendering their children themselves (which return
		# in IncludesChildren object), do not fold in rendered children
		# (the None sentinel is handed in endKey)
		if isinstance(val, meta.IncludesChildren):
			self.resultTree[-1].append(None)

	def _isCompound(self, childItem):
		"""should return true some day for compound meta items that should
		be grouped in some way.
		"""
		return False

	def endKey(self, atom):
		children = [c for c in self.resultTree.pop() if c]
		# see enterValue on why we're doing this
		if (self.resultTree[-1] 
				and self.resultTree[-1][-1] is None):
			return

		if len(children)>1:
			childElements = []
			for c in children:
				if self._isCompound(c)>1:
					class_ = "compoundMetaItem"
				else:
					class_ = "metaItem"
				childElements.append(T.li(class_=class_)[c])
			self.resultTree[-1].append(T.ul(class_="metaEnum")[childElements])
		elif len(children)==1:
			self.resultTree[-1].append(children[0])
	
	def getResult(self):
		return self.resultTree[0]

	def clear(self):
		self.resultTree = [[]]


def runAuthenticated(ctx, reqGroup, fun, *args):
	"""returns the value of fun(*args) if the logged in user is in reqGroup,
	requests authentication otherwise.
	"""
	request = inevow.IRequest(ctx)
	if creds.hasCredentials(request.getUser(), request.getPassword(), reqGroup):
		return fun(*args)
	else:
		raise svcs.Authenticate()


class doctypedStan(loaders.stan):
	"""is the stan loader with a doctype and a namespace added.
	"""

	DOCTYPE = T.xml('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
		' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n')

	def __init__(self, rootEl, pattern=None):
		super(doctypedStan, self).__init__(T.invisible[self.DOCTYPE, 
			rootEl(xmlns="http://www.w3.org/1999/xhtml")], pattern)


JSEXT = ".js"


class CommonRenderers(object):
	"""A base for renderer (python) mixins within the DC.

	Including standard stylesheets/js/whatever:
	<head n:render="commonhead">...</head>

	Rendering internal links (important for off-root operation):

	* <tag href|src="/foo" n:render="rootlink"/>

	"""
	def render_unicode(self, ctx, data):
		"""returns unicode(data); use this when render="string" might have to
		format non-ASCII.
		"""
		return ctx.tag[unicode(data)]

	def render_rootlink(self, ctx, data):
		tag = ctx.tag
		def munge(key):
			if tag.attributes.has_key(key):
			 tag.attributes[key] = base.makeSitePath(tag.attributes[key])
		munge("src")
		munge("href")
		return tag

	def render_commonhead(self, ctx, data):
		#	we do not want to blindly append these things to the tag since user-
		# provided items in the header should have access to this environment,
		# in particular to jquery; thus, this stuff must be as early as possible.
		originalChildren = ctx.tag.children[:]
		ctx.tag.clear()
		res = ctx.tag[
			T.meta(**{"http-equiv": "Content-type",
				"content": "text/html;charset=UTF-8"}),
			T.link(rel="stylesheet", href=base.makeSitePath("/formal.css"),
				type="text/css"),
			T.link(rel="stylesheet", href=base.makeSitePath(
				"/static/css/gavo_dc.css"), type="text/css"),
			T.script(src=base.makeSitePath("/static/js/jquery-gavo.js"), 
				type="text/javascript"),
			T.script(type='text/javascript', src=base.makeSitePath(
				'static/js/formal'+JSEXT)),
			T.script(src=base.makeSitePath("/static/js/gavo"+JSEXT),
				type="text/javascript"),
			originalChildren,
		]
		if base.getConfig("web", "operatorCSS"):
			res[
				T.link(rel="stylesheet", type="text/css",
					href=base.getConfig("web", "operatorCSS"))]
		return res

	def render_urlescape(self, ctx, data):
		"""renders data as a url-escaped string.
		"""
		if isinstance(data, unicode):
			data = data.encode("utf-8")
		return urllib.quote(data)
	
	def render_getconfig(self, ctx, data):
		"""looks up the text child in the DaCHS configuration and inserts
		the value as a (unicode) string.

		The config key is either [section]item or just item for something
		in [general].  Behaviour for undefined config items is undefined.
		"""
		configKey = ctx.tag.children[0].strip()
		mat = re.match("\[([^]]*)\](.*)", configKey)
		if mat:
			content = base.getConfig(mat.group(1), mat.group(2))
		else:
			content = base.getConfig(configKey)
		ctx.tag.clear()
		return ctx.tag[content]


class Request(appserver.NevowRequest):
	"""a custom request class used in DaCHS' application server.

	The main change is that we enforce a limit to the size of the payload.
	This is especially crucial because nevow blocks while parsing the
	header payload.
	"""
	def gotLength(self, length):
		if length and length>base.getConfig("web", "maxUploadSize"):
			self.channel.transport.write(
				"HTTP/1.1 413 Request Entity Too Large\r\n\r\n")
			# unfortunately, http clients won't see this; they'll get a
			# connection reset instead.  Ah well, even nginx doesn't
			# do much better here.
			self.channel.transport.loseConnection()
			return
		return appserver.NevowRequest.gotLength(self, length)


class TypedData(rend.Page):
	"""A simple resource just producing bytes passed in during construction,
	declared as a special content type.
	"""
	def __init__(self, data, mime):
		rend.Page.__init__(self)
		self.data, self.mime = data, mime
	
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", self.mime)
		request.write(self.data)
		return ""

