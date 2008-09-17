"""
This is the web interface to the querulator, a rapid simple service deployer.
"""

import os
import sys
import textwrap
import traceback

from gavo import utils
import gavo
from gavo import config
from gavo.web import common
from gavo.web import wsdl
from gavo.web import querulator
from gavo.web.querulator import forms
from gavo.web.querulator import queryrun
from gavo.web.querulator import context


class Error(gavo.Error):
	pass


def showAvailableQueries(context, subdir):
	queries, folders = forms.getAvailableQueries(subdir)
	formattedQueries = "\n".join(sorted(['<li><a href="%s/query/%s">%s</a></li>'%(
			config.get("web", "rootURL"), qPath, title)
		for title, qPath in queries]))
	if not formattedQueries.strip():
		formattedQueries = "<p>None.</p>"
	else:
		formattedQueries = "<ul>%s</ul>"%formattedQueries
	formattedFolders = "\n".join(sorted(['<li><a href="%s/list/%s">%s</a></li>'%(
			config.get("web", "rootURL"), path, title)
		for title, path in folders]))
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


def getProduct(context, subPath):
	return queryrun.getProduct(context)



def _computeThumbnailFp(fpPath, path):
	pipe = os.popen("%s '%s'"%(fpPath, path))
	data = pipe.read()
	if pipe.close():
		raise Error("Image generation failed for %s"%path)
	return data


def _computeThumbnailNetpbm(path):
	if path.lower().endswith(".gz"):
		firststage = "zcat '%s' | fitstopnm "%path
	else:
		firststage = "fitstopnm -scanmax '%s' "%path
	pipe = os.popen(firststage+"| pnmscale -xsize 200 | cjpeg 2>/dev/null")
	data = pipe.read()
	if pipe.close():
		raise Error("Image generation failed for %s"%path)
	return data


def getProductThumbnail(context, subPath):
	template = forms.Template(subPath)
	path = common.resolvePath(
		config.get("inputsDir"), context.getfirst("path"))
	fitspreviewLocation = config.get("querulator", "fitspreview")
	if os.path.exists(fitspreviewLocation):
		return "image/jpeg", _computeThumbnailFp(fitspreviewLocation, path), {}
	else:
		return "image/jpeg", _computeThumbnailNetpbm(path), {}


def getWsdl(context, subPath):
	"""returns very simple-minded WSDL for the given template.
	"""
	template = forms.Template(subPath)
	fieldInfos = template.getConditionsAsFieldInfos(context)
	portBinding, elements = wsdl.makeHTTPBinding(template.getName()+"votable", 
		"run/"+template.getPath(), 
		fieldInfos, "application/x-votable")
	wsdlTree = wsdl.makeWSDLDefinitions(template.getName(), [
		wsdl.makeService(template.getName(), 
			context.getServerURL()+config.get("web", "rootURL"),
			[portBinding])]+elements)
	def produceOutput(outputFile):
		wsdlTree.write(outputFile)
	return "text/xml", produceOutput, {}
		

def getForm(context, subPath):
	template = forms.Template(subPath)
	return "text/html", template.asHtml(context), {}


def processQuery(context, subPath):
	template = forms.Template(subPath)
	return queryrun.processQuery(template, context)


def getMasqForm(context, subPath):
	from gavo.web.masquerator import main
	return main.getMasqForm(context, subPath)


def processMasqQuery(context, subPath):
	from gavo.web.masquerator import main
	return main.processMasqQuery(context, subPath)


def _doErrorResponse(msg, context):
	statusCode = 500
	if hasattr(msg, "statusCode"):
		statusCode = msg.statusCode
	context.doHttpResponse("text/html",  "\n".join([
		'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"'
		' "http://www.w3.org/TR/html4/loose.dtd">'
		"<head><title>Error</title></head>"
		"<body><h1>An error has occurred</h1>"
		"<p>We are sorry we cannot fulfil your request.  The"
		" error message given by the program is:</p><pre>",
		"%s\n"%msg.__class__.__name__,
		"\n".join(textwrap.wrap(str(msg))),
		"</pre>"
		"<p>If you believe what you were trying to do should have worked,"
		" please contact gavo@ari.uni-heidelberg.de.</p>"
		"</body>"]), statusCode=statusCode)


_procConfig = {
	"list": showAvailableQueries,
	"getproduct": getProduct,
	"thumbnail": getProductThumbnail,
	"query": getForm,
	"run": processQuery,
	"wsdl": getWsdl,
	"masq": getMasqForm,
	"masqrun": processMasqQuery,
}


def _checkForBlock(context):
	"""checks if we are in maintainance mode and rejects queries if so.

	Maintainance mode is signified by the presence of a "MAINTAINANCE"
	file in templateRoot.
	"""
	if (os.path.exists(os.path.join(
				config.get("querulator", "templateRoot"), "MAINTAINANCE"))
			or context.getQuerier() is None):
		remoteAddr = context.getRemote()
		if remoteAddr.startswith("127") or remoteAddr=="129.206.110.59":
			return False
		context.doHttpResponse("text/html", """<head><title>Down for
			good</title></head><body><h1>Down for
			good</h1><p>The querulator design study has been discontinued.
			Please use the new interface at 
			<a href="http://vo.ari.uni-heidelberg.de/nv">http://vo.ari.uni-heidelberg.de/nv</a>.
			If you need anything from the querulator-based services that is
			not yet available there, please contact
			gavo@ari.uni-heidelberg.de.  Thanks.</p></body>""")
		return True


def dispatch(context):
	"""dispatches the queries and outputs the results.

	Yes, we want a real framework, but as long as I don't know
	what I'm going to do, I can't really choose one...
	"""
	if _checkForBlock(context):
		return
	pathParts = context.getPathInfo().split("/")
	reqFunction = pathParts[0].strip() or "list"
	try:
		func = _procConfig[reqFunction]
	except KeyError:
		raise Error("You requested an undefined function (%s)"%repr(reqFunction))
	queryPath = "/".join(pathParts[1:])
	try:
		contentType, content, headers = func(context, queryPath)
		context.doHttpResponse(contentType, content, headers)
	except querulator.Error, msg:
		traceback.print_exc()
		sys.stderr.flush()
		_doErrorResponse(msg, context)


def main():
	"""is the entry point for CGIs.
	"""
	config.setDbProfile(config.get("querulator", "dbProfile"))
	qContext = context.CGIContext()
	try:
		dispatch(qContext)
	except Exception, msg:
		traceback.print_exc()
		_doErrorResponse(msg, qContext)


def handler(req):
	"""is the entry point for naked modpython.
	"""
	from mod_python import apache
	config.setDbProfile(config.get("querulator", "dbProfile"))

	qContext = context.ModpyContext(req)
	try:
		dispatch(qContext)
	except Exception, msg:
		traceback.print_exc()
		sys.stderr.flush()
		_doErrorResponse(msg, qContext)
	return apache.OK
