"""
This is the web interface to the querulator, a rapid simple service deployer.

The code *currently* assumes it's running as a cgi.  We should change
this, though I'm not really sure what kind of framework (or just
templating engine) we'd want.
"""

import cgi
import os
import sys
import textwrap

from gavo import utils
import gavo
from gavo.web import querulator
from gavo.web.querulator import forms
from gavo.web.querulator import queryrun

fitspreviewLocation = os.path.join(gavo.rootDir, "web", "bin", "fitspreview")

class Error(gavo.Error):
	pass


def showAvailableQueries(subdir):
	queries, folders = forms.getAvailableQueries(subdir)
	formattedQueries = "\n".join(['<li><a href="%s/query/%s">%s</a></li>'%(
			querulator.rootURL, qPath, title)
		for title, qPath in queries])
	if not formattedQueries.strip():
		formattedQueries = "<p>None.</p>"
	else:
		formattedQueries = "<ul>%s</ul>"%formattedQueries
	formattedFolders = "\n".join(['<li><a href="%s/list/%s">%s</a></li>'%(
			querulator.rootURL, path, title)
		for title, path in folders])
	if not formattedFolders.strip():
		formattedFolders = "<p>None.</p>"
	else:
		formattedFolders = "<ul>%s</ul>"%formattedFolders
	if not subdir:
		subdir = "root"
	return "text/html", """<head><title>Queries available here</title></head>
		<body>
		<h1>Queries at %s</h1>
		%s
		<h1>Further Queries</h1>
		%s
		</body>"""%(
			subdir,
			formattedQueries,
			formattedFolders,
		), {}


def getProductObsoleteAndStinking(subPath):
	template = forms.Template(subPath)
	form = cgi.FieldStorage()
	path = querulator.resolvePath(
		os.path.join(gavo.rootDir, template.getMeta("PRODUCT_ROOT")),
		form.getfirst("path"))
	return "image/fits", open(path).read(), {
		"Content-disposition": 'attachment; filename="%s"'%os.path.basename(
			form.getfirst("path")),}


def getProduct(subPath):
	return queryrun.getProduct(context)


if os.path.exists(fitspreviewLocation):

	def _computeThumbnail(path):
		pipe = os.popen("%s '%s'"%(fitspreviewLocation, path))
		data = pipe.read()
		if pipe.close():
			raise Error("Image generation failed for %s"%path)
		return data

else:

	def _computeThumbnail(path):
		if path.lower().endswith(".gz"):
			firststage = "zcat '%s' | fitstopnm "%path
		else:
			firststage = "fitstopnm -scanmax '%s' "%path
		pipe = os.popen(firststage+"| pnmscale -xsize 200 | cjpeg 2>/dev/null")
		data = pipe.read()
		if pipe.close():
			raise Error("Image generation failed for %s"%path)
		return data


def getProductThumbnail(subPath):
	template = forms.Template(subPath)
	form = cgi.FieldStorage()
	path = querulator.resolvePath(
		os.path.join(gavo.rootDir, template.getMeta("PRODUCT_ROOT")),
		form.getfirst("path"))
	return "image/jpg", _computeThumbnail(path), {}


def getForm(subPath):
	template = forms.Template(subPath)
	return "text/html", forms.getForm(template), {}


def processQuery(subPath):
	template = forms.Template(subPath)
	return queryrun.processQuery(template, context)


def _doErrorResponse(msg):
	print "Content-type: text/html\n"
	print "<head><title>Error</title></head>"
	print "<body><h1>An error as occurred</h1>"
	print "<p>We are sorry, but we cannot fulfil your request.  The"
	print "reason given by the program is:</p><pre>"
	print "\n".join(textwrap.wrap(str(msg)))
	print "</pre>"
	print "<p>If you believe what you were trying to do should have worked,"
	print "please contact gavo@ari.uni-heidelberg.de.</p>"
	print "</body>"


_procConfig = {
	"": showAvailableQueries,
	"list": showAvailableQueries,
	"getproduct": getProduct,
	"thumbnail": getProductThumbnail,
	"query": getForm,
	"run": processQuery,
}

def _doHtmlResponse(contentType, content, moreHeaders={}):
	print "Content-type: %s"%contentType
	try:
		print "Content-length: %d"%len(content)
	except TypeError:
		pass
	print "Connection: close"
	for key, value in moreHeaders.iteritems():
		print "%s: %s"%(key, value)
	print ""
	if isinstance(content, basestring):
		sys.stdout.write(content)
	else:
		content(sys.stdout)


def _checkForBlock():
	"""checks if we are in maintainance mode and rejects queries if so.

	Maintainance mode is signified by the presence of a "MAINTAINANCE"
	file in templateRoot.
	"""
	if os.path.exists(os.path.join(querulator.templateRoot, "MAINTAINANCE")):
		remoteAddr = os.environ.get("REMOTE_ADDR", "")
		if remoteAddr.startswith("127") or remoteAddr=="129.206.110.59":
			return
		sys.stderr.write("%s\n"%os.environ)
		_doHtmlResponse("text/html", """<head><title>Down for
			maintainance</title></head><body><h1>Down for
			maintainance</h1><p>Sorry -- we're down for maintainance.  If
			this persists for longer than, say, an hour, please complain to
			gavo@ari.uni-heidelberg.de.  Thanks.</p></body>""")
		sys.exit(0)


def main():
	"""dispatches the queries and outputs the results.

	Yes, we want a real framework, but as long as I don't know
	what I'm going to do, I can't really choose one...
	"""
	global context
	context = Context()
	_checkForBlock()
	pathParts = os.environ.get("PATH_INFO", "").strip("/").split("/")
	func = _procConfig.get(pathParts[0],
		lambda _: showAvailableQueries("/".join(pathParts)))
	queryPath = "/".join(pathParts[1:])
	try:
		contentType, content, headers = func(queryPath)
		_doHtmlResponse(contentType, content, headers)
	except querulator.Error, msg:
		_doErrorResponse(msg)


class Context:
	"""will be taken over by the context of a real framework.
	"""
	def __init__(self):
		self.loggedUser = None
		if 	os.environ.get("AUTH_TYPE") and os.environ.get("REMOTE_USER"):
			self.loggedUser = os.environ.get("REMOTE_USER")
		self.form = cgi.FieldStorage()
