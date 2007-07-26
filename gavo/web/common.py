"""
Common functions and classes for gavo web interfaces.

(Much of what would belong here currently lives within querulator.
We'll move the stuff as we see fit...)
"""

import os

import gavo

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


_linkGeneratingJs = """<script type="text/javascript"><!--

function getSelectedEntries(selectElement) {
// returns an array of all selected entries from a select element 
// in url encoded form
	var result = new Array();
	var i;

	for (i=0; i<selectElement.length; i++) {
		if (selectElement.options[i].selected) {
			result.push(selectElement.name+"="+encodeURI(
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
	"""
	votChoices = "\n".join(['<option value="%s">%s</option>'%(val, label)
		for label, val in [
			("HTML", "HTML"), 
			("Full VOTable", "VOTable 30"), 
			("Medium VOTable", "VOTable 20"), 
			("Terse VOTable", "VOTable 10"), 
			("VOPlot", "VOPlot"), 
			("Predefined VOTable", "VOTable 0")]])
	return _linkGeneratingJs+('<p class="submitbuttons">'
		'Output Format: <select name="outputFormat" size="1">%s</select>\n'
		'<input type="submit" value="Submit">\n'
		' <a class="resultlink" href="" onMouseOver="this.href=makeResultLink('
			'this.parentNode.parentNode)">[Query]</a>'
		'</p>')%votChoices
