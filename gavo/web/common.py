"""
Common functions and classes for gavo web interfaces.
"""

import re
import os

from nevow import tags as T, entities as E
from nevow import loaders
from nevow import inevow

from zope.interface import implements

import gavo
from gavo import config

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


class GavoRenderMixin(object):
	"""is a mixin that allows inclusion of meta information.

	To do that, you say <tag render="meta">METAKEY</tag> or
	<tag render="metahtml">METAKEY</tag>
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
	"""is a class keeping all data *about* a query, e.g., the requested
	output format.

	It is constructed with the dictionary-like thing mapping keys from
	the qwidget.OutputOptions (and possibly more) to their values.
	If you pass an empty dict, some safe defaults will be used.
	"""

	# a list of keys handled by query meta
	metaKeys = ["_DBOPTIONS", "_FILTER", "_OUTPUT"]

	def __init__(self, formData):
		self.queryPars = formData
		self._fillOutput(formData)
		self._fillOutputFilter(formData)
		self._fillDbOptions(formData)
	
	def _fillOutput(self, formData):
		"""interprets values left by gwidget.OutputOptions.
		"""
		output = formData.get("_OUTPUT", {})
		self["format"] = output.get("format", "VOTable")
		self["verbosity"] = int(output.get("verbosity", '2'))*10
		self["tdEnc"] = output.get("tdEnc", False)
	
	def _fillOutputFilter(self, formData):
		self["outputFilter"] = formData.get("_FILTER", "default") or "default"

	def _fillDbOptions(self, formData):
		dbOptions = formData.get("_DBOPTIONS", {})
		self["dbLimit"] = dbOptions.get("limit", 100)
		self["dbSortKey"] = dbOptions.get("order", None)

	def asSql(self):
		"""returns the dbLimit and dbSortKey values as an SQL fragment.
		"""
		frag, pars = [], {}
		if self["dbSortKey"]:
			# Ok, we need to do some emergency securing here.  There should be
			# pre-validation that we're actually seeing column key, but
			# just in case let's make sure we're seeing an SQL identifier.
			# (We can't rely on dbapi's escaping since we're not talking values here)
			key = re.sub("[^A-Za-z_]+", "", self["dbSortKey"])
			frag.append("ORDER BY %s"%key)
		if self["dbLimit"]:
			frag.append("LIMIT %(_matchLimit)s")
			pars["_matchLimit"] = self["dbLimit"]+1
		return " ".join(frag), pars


class CoreResult(object):
	"""is a nevow.IContainer that has the result and also makes the input
	dataset accessible.
	"""
	implements(inevow.IContainer)

	def __init__(self, resultData, inputData, queryMeta):
		self.original = resultData
		self.queryPars = queryMeta.queryPars
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

	def data_queryseq(self, ctx):
		return [(k, str(v)) for k, v in self.queryPars.iteritems()
			if not k in QueryMeta.metaKeys]

	def data_querypars(self, ctx):
		return dict(self.data_queryseq(ctx))

	def data_inputRec(self, ctx):
		return self.inputData.getDocRec()

	def data_table(self, ctx):
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
