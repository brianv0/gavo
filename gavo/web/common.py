"""
Common functions and classes for gavo web interfaces.

(Much of what would belong here currently lives within querulator.
We'll move the stuff as we see fit...)
"""

import os

from nevow import tags as T, entities as E

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
				val = element.name+"="+encodeURI(element.value);
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


class MetaRenderMixin(object):
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


class QueryMeta(dict):
	"""is a class keeping all data *about* a query, e.g., the requested
	output format.

	It is constructed with the dictionary-like thing mapping keys from
	the qwidget.OutputOptions (and possibly more) to their values.
	If you pass an empty dict, some safe defaults will be used.
	"""
	def __init__(self, formData):
		self._fillOutputOptions(formData)
		self._fillOutputFilter(formData)
	
	def _fillOutputOptions(self, formData):
		"""interprets values left by gwidget.OutputOptions.
		"""
		outputOptions = formData.get("output", {})
		self["format"] = outputOptions.get("format", "VOTable")
		self["verbosity"] = int(outputOptions.get("verbosity", '2'))*10
		self["tdEnc"] = outputOptions.get("tdEnc", False)
	
	def _fillOutputFilter(self, formData):
		self["outputFilter"] = formData.get("FILTER", "default")
