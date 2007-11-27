"""
Common functions and classes for gavo web interfaces.
"""

import re
import os

import formal

from nevow import tags as T, entities as E
from nevow import loaders
from nevow import inevow
from nevow import util as nevowutil

from twisted.python import failure
from twisted.internet import defer

from zope.interface import implements

import gavo
from gavo import config
from gavo import record


class Error(gavo.Error):
	pass


def resolvePath(rootPath, relPath):
	"""joins relPath to rootPath and makes sure the result really is
	in rootPath.
	"""
	relPath = relPath.lstrip("/")
	fullPath = os.path.realpath(os.path.join(rootPath, relPath))
	if not fullPath.startswith(rootPath):
		raise Error("I believe you are cheating -- you just tried to"
			" access %s, which I am not authorized to give you."%fullPath)
	if not os.path.exists(fullPath):
		raise Error("Invalid path %s.  This should not happen."%fullPath)
	return fullPath


# this js belongs to the deprecated getSubmitButtons and should go with
# it.
_linkGeneratingJs = """<script type="text/javascript"><!--

function getSelectedEntries(selectElement) {
// returns an array of all selected entries from a select element 
// in url encoded form
	var result = new Array();
	var i;

	for (i=0; i<selectElement.length; i++) {
		if (selectElement.options[i].selected) {
			result.push(selectElement.name+"="+encodeURIComponent(
				selectElement.options[i].value))
		}
	}
	return result;
}

function makeQueryItem(element) {
// returns an url-encoded query tag item out of a form element
	var val=null;

	switch (element.nodeName) {
		case "INPUT":
			if (element.name && element.value) {
				val = element.name+"="+encodeURIComponent(element.value);
			}
			break;
		case "SELECT":
			return getSelectedEntries(element).join("&");
			break;
		default:
			alert("No handler for "+element.nodeName);
	}
	if (val) {
		return val;
	} else {
		return element.NodeName;
	}
}

function makeResultLink(form) {
	// returns a link to the result sending the HTML form form would
	// yield.
	var fragments = new Array();
	var fragment;
	var i;

	items = form.elements;
	for (i=0; i<items.length; i++) {
		fragment = makeQueryItem(items[i]);
		if (fragment) {
			fragments.push(fragment);
		}
	}
	return form.getAttribute("action")+"?"+fragments.join("&");
}

// -->
</script>
"""

def getSubmitButtons(context):
	"""returns HTML for submit buttons for the various formats we can do.

	Deprecated, for querulator.
	"""
	if config.get("web", "voplotEnable"):
		voplotAttr = ""
	else:
		voplotAttr = ' disabled="disabled"'
	votChoices = "\n".join(['<option value="%s"%s>%s</option>'%(val, attrs, label)
		for label, val, attrs in [
			("HTML", "HTML", ""), 
			("Full VOTable", "VOTable 30", ""), 
			("Medium VOTable", "VOTable 20", ""), 
			("Terse VOTable", "VOTable 10", ""), 
			("VOPlot (full)", "VOPlot 30", voplotAttr),
			("VOPlot (medium)", "VOPlot 20", voplotAttr),
			("VOPlot (terse)", "VOPlot 10", voplotAttr),
			("Predefined VOTable", "VOTable 0", "")]])
	return _linkGeneratingJs+('<p class="submitbuttons">'
		'Output Format: <select name="outputFormat" size="1">%s</select>\n'
		'<input type="submit" value="Submit">\n'
		' <a class="resultlink" href="" onMouseOver="this.href=makeResultLink('
			'this.parentNode.parentNode)">[Query]</a>'
		'</p>')%votChoices

########### End of stinky querulator related code

class UnknownURI(Error):
	"""signifies that a http 404 should be returned to the dispatcher.
	"""


def parseServicePath(serviceParts):
	"""returns a tuple of resourceDescriptor, serviceName.

	A serivce id consists of an inputsDir-relative path to a resource 
	descriptor, a slash, and the name of a service within this descriptor.

	This function returns a tuple of inputsDir-relative path and service name.
	It raises a gavo.Error if sid has an invalid format.  The existence of
	the resource or the service are not checked.
	"""
	return "/".join(serviceParts[:-1]), serviceParts[-1]


class CustomErrorMixin(object):
	"""is a mixin for renderers containing formal forms to emit
	custom error messages.

	This mixin expects to see "the" form as self.form and relies on
	the presence of a method _generateForm that arranges for that .
	This can usually be an alias for the form_xy method you need for
	formal (we actually pass a nevow context object to that function),
	but make sure you actually set self.form in there.

	You furthermore need to define methods:

	* _getInputData -- receives the form data and returns something
	* _handleInputData -- receives the result of _getInputData and the context
	  and returns something renderable (the result of renderHTTP)
	
	Both may return deferreds.

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
			return defer.maybeDeferred(self._getInputData, self.form.data
				).addCallback(self._handleInputData, ctx
				).addErrback(self._handleError, ctx)
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
		if isinstance(failure.value, gavo.ValidationError):
			return self._handleInputErrors(["Parameter %s: %s"%(
				failure.value.fieldName, failure.getErrorMessage())], ctx)
		return self.renderHTTP_exception(ctx, failure)


class GavoRenderMixin(object):
	"""is a mixin that allows inclusion of meta information.

	To do that, you say <tag n:render="meta">METAKEY</tag> or
	<tag n:render="metahtml">METAKEY</tag>
	"""
	def _doRenderMeta(self, ctx, flattenerFunc):
		metaKey = ctx.tag.children[0]
		metaVal = self.service.getMeta(metaKey)
		if metaVal:
			return ctx.tag.clear()[flattenerFunc(metaVal)]
		else:
			return T.comment["Meta item %s not given."%metaKey]

	def render_meta(self, ctx, data):
		return self._doRenderMeta(ctx, str)
	
	def render_metahtml(self, ctx, data):
		return self._doRenderMeta(ctx, lambda c: T.xml(c.asHtml()))

	def render_rootlink(self, ctx, data):
		tag = ctx.tag
		def munge(key):
			if tag.attributes.has_key(key):
			 tag.attributes[key] = config.get("web", "nevowRoot")+tag.attributes[key]
		munge("src")
		munge("href")
		return tag


class QueryMeta(dict):
	"""is a class keeping all data *about* a query, e.g., the
	requested output format.

	It is constructed with either a nevow context (we'll look
	at the args of the embedded request) or a plain dictionary.  Note,
	however, that the values obtained from the net must be in *sequences*
	(of course, they're usually length 1).  This is what IRequest delivers,
	and there's no sense in special-casing this, even more since having
	a sequence might come in handy at some point (e.g., for sort keys).
	If you pass an empty dict, some sane defaults will be used.  You
	can get that "empty" query meta as common.emptyQueryMeta

	Not all services need to interpret all meta items; e.g., things writing
	fits files or VOTables only will ignore _FORMAT, and the dboptions
	won't make sense for many applications.

	If you're using nevow formal, you should set the formal_data item
	to the dictionary created by formal.  This will let people use
	the parsed parameters in templates.
	"""

	# a list of keys handled by query meta to be ignored in parameter
	# lists because they are used internally.  This covers everything 
	# QueryMeta interprets, but also keys by introduced by certain gwidgets
	# and the nevow infrastructure
	metaKeys = set(["_DBOPTIONS", "_FILTER", "_OUTPUT", "_charset_",
		"__nevow_form__", "_FORMAT", "_VERB", "_TDENC", "formal_data"])

	def __init__(self, ctxArgs):
		try:
			ctxArgs = inevow.IRequest(ctxArgs).args
		except TypeError:
			pass
		self["formal_data"] = {}
		self._fillOutput(ctxArgs)
		self._fillOutputFilter(ctxArgs)
		self._fillDbOptions(ctxArgs)
	
	def _fillOutput(self, ctxArgs):
		"""interprets values left by gwidget.OutputOptions.
		"""
		self["format"] = ctxArgs.get("_FORMAT", ["VOTable"])[0]
		try:
			self["verbosity"] = int(ctxArgs.get("_VERB", ['2'])[0])*10
		except ValueError:
			self["verbosity"] = 20
		try:
			self["tdEnc"] = record.parseBooleanLiteral(
				ctxArgs.get("tdEnc", ["False"])[0])
		except gavo.Error:
			self["tdEnc"] = False
	
	def _fillOutputFilter(self, ctxArgs):
		self["outputFilter"] = ctxArgs.get("_FILTER", ["default"])[0] or "default"

	def _fillDbOptions(self, ctxArgs):
		try:
			self["dbLimit"] = int(ctxArgs.get("_DBOPTIONS_LIMIT", [100])[0])
		except ValueError:
			self["dbLimit"] = 100
		self["dbSortKey"] = ctxArgs.get("_DBOPTIONS_ORDER", [None])[0]

	def asSql(self, limitOverride=None, orderOverride=None):
		"""returns the dbLimit and dbSortKey values as an SQL fragment.
		"""
		frag, pars = [], {}
		sortKey = orderOverride or self["dbSortKey"]
		dbLimit = int(limitOverride or self["dbLimit"])
		if sortKey:
			# Ok, we need to do some emergency securing here.  There should be
			# pre-validation that we're actually seeing a column key, but
			# just in case let's make sure we're seeing an SQL identifier.
			# (We can't rely on dbapi's escaping since we're not talking values here)
			sortKey = re.sub("[^A-Za-z_]+", "", sortKey)
			frag.append("ORDER BY %s"%sortKey)
		if dbLimit:
			frag.append("LIMIT %(_matchLimit)s")
			pars["_matchLimit"] = dbLimit+1
		return " ".join(frag), pars

emptyQueryMeta = QueryMeta({})


class CoreResult(object):
	"""is a nevow.IContainer that has the result and also makes the input
	dataset accessible.
	"""
	implements(inevow.IContainer)

	def __init__(self, resultData, inputData, queryMeta):
		self.original = resultData
		self.queryPars = queryMeta.get("formal_data", {})
		self.inputData = inputData
		self.queryMeta = queryMeta
		for n in dir(self.original):
			if not n.startswith("_"):
				setattr(self, n, getattr(self.original, n))

	def data_resultmeta(self, ctx):
		result = self.original.getTables()[0]
		return {
			"itemsMatched": len(result.rows),
		}

	def data_queryseq(self, ctx=None):
		s = [(k, str(v)) for k, v in self.queryPars.iteritems()
			if not k in QueryMeta.metaKeys]
		s.sort()
		return s

	def data_querypars(self, ctx=None):
		return dict(self.data_queryseq(ctx))

	def data_inputRec(self, ctx=None):
		return self.inputData.getDocRec()

	def data_table(self, ctx=None):
		return self.original.getPrimaryTable()

	def child(self, ctx, name):
		return getattr(self, "data_"+name)(ctx)


class CustomTemplateMixin(object):
	"""is a mixin providing for customized templates.

	This works by making docFactory a property first checking if the instance has
	a customTemplate attribute evaluating to true.  If it has, its content is
	used as a resdir-relative path to a nevow XML template, if not, the
	defaultDocFactory attribute of the instance is used.
	"""
	customTemplate = None

	def getDocFactory(self):
		if self.customTemplate:
			res = loaders.xmlfile(self.customTemplate)
		else:
			res = self.defaultDocFactory
		return res
	
	docFactory = property(getDocFactory)


def makeSitePath(uri):
# XXX TODO: scrap that, GavoRenderMixin.render_rootlink is a better place
# for this functionality.
	"""adapts uri for use in an off-root environment.

	uri itself needs to be server-absolute (i.e., start with a slash).
	"""
	assert uri[0]=="/"
	return config.get("web", "nevowRoot")+uri
