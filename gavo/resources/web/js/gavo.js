// javascript support code for the GAVO data center


function decodeGetPars(queryString) {
// an incredibly crappy approach to getting whatever was in the query string
// into javascript.
	var pars = new Object();
  var pairs = queryString.slice(1).split("&");
  for (var ind in pairs) {
		var pair = pairs[ind].split("=");
		var key = 'arg'+unescape(pair[0]).replace("+", " ");
    var value = unescape(pair[1]).replace("+", " ");
		if (pars[key]==undefined) {
	    pars[key] = new Array();
		}
		pars[key].push(value);
  }
	return pars;
}


function isIn(item, arr) {
// does a linear search through arr to see if item is in there
// (can't we use assoc. arrs for that?)
	for (var ind in arr) {
		if (arr[ind]==item) {
			return true;
		}
	}
	return false;
}


///////////// Code handling previews
function insertPreview(node, width) {
// replaces the text content of node with a preview image if node has
// a href attribute (this is used for products)
	if (node.getAttribute("href")) {
		var image = document.createElement("img")
		image.setAttribute("src", node.getAttribute("href")+"&preview=True"+
			"&width="+width);
		node.replaceChild(image, node.firstChild);
	}
	node.removeAttribute("onmouseover");
}

///////////// Code for generating GET-URLs for forms

function getEnclosingForm(element) {
// returns the form element immediately enclosing element.
	if (element.nodeName=="FORM") {
		return element;
	}
	return getEnclosingForm(element.parentNode);
}

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
		case "TEXTAREA":
			if (element.type=="radio") {
				if (element.checked) {
					val = element.name+"="+encodeURIComponent(element.value);
				}
			} else if (element.name && element.value) {
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

function getFormQuery(form, ignoreNames) {
	// returns a link to the result sending the HTML form form would
	// yield.
	var fragments = new Array();
	var fragment;
	var i;

	items = form.elements;
	for (i=0; i<items.length; i++) {
		fragment = makeQueryItem(items[i]);
		if (fragment && ignoreNames[items[i].name]==undefined) {
			fragments.push(fragment);
		} else {
			window.status = "ignoring "+items[i].name;
		}
	}
	return form.getAttribute("action")+"?"+fragments.join("&");
}


function makeResultLink(form) {
	return getFormQuery(form, []);
}


function makeBookmarkLink(form) {
	return getFormQuery(form, {'__nevow_form__': 1});
}


///////////// Functions for the sidebar

function markFold(title, markstr) {
	return title.slice(0, title.length-2)+markstr;
}

function toggleCollapsedMeta(el) {
	parentBox = el.parentNode.parentNode;
	if (parentBox.style.width=='200px') {
		el.childNodes[0].data = markFold(el.childNodes[0].data, ">>");
		collapseMeta(parentBox);
	} else {
		el.childNodes[0].data = markFold(el.childNodes[0].data, "<<");
		expandMeta(parentBox);
	}
}

function collapseMeta(box) {
	box.style.minHeight = '12px';
	box.style.height = '12px';
	box.style.overflow = 'hidden';
	box.style.width = '100px';
	box.style.border = '0px none #707ca0';
	box.style.background = 'none';
}

function expandMeta(box) {
	box.style.width = '200px';
	box.style.minHeight = '70px';
	box.style.maxHeight = '200px';
	box.style.overflow = 'auto';
	box.style.border = '1px solid #707ca0';
	box.style.background = 'white';
}


///////////// Functions dealing with the output format widget
// This incredibly verbose crap hides and shows widgets selecting aspects
// of the output format.  Basically, you have widgets in output_bussedElements
// that get notified when the output format changes and then (un)attach 
// themselves to a container.
//
// To use this, you need:
//  * a block element with id "genForm-_OUTPUT" in which the subwidgets are 
//    displayed
//  * a form element calling output_broadcast(this.value) on a change
//  * an element with id op_selectItems (preferably invisible) that has
//    one item per line, key first, then a space, finally a title, encoded
//    for decodeURI
//
//  In the DC, the static QueryMeta method getOutputWidget cares for this.


function output_BussedElement(domNode, id, visibleFor) {
	// is an element that can be passed to output_broadcast and does something
	// in response.
	domNode.id = id;
	for (var ind in visibleFor) {
		domNode["visibleFor_"+visibleFor[ind]] = true;
	}
	return domNode;
}


function output_verbSelector(pars) {
	// returns a BussedElement for the selector for output verbosity
	var verbosities = new Array("H", "1", "2", "3");
	var root = document.createElement("span")
	var sel = document.createElement("select");
	var curSetting;

	root["class"] = "op_widget";
	root.appendChild(document.createTextNode(" output verbosity "));
	sel.name = "_VERB";
	if (pars['arg'+sel.name]!=undefined) {
		curSetting = pars['arg'+sel.name][0];
	} else {
		curSetting = "H";
	}
	for (verbInd in verbosities) {
		var el = sel.appendChild(document.createElement("option"));
		var verb = verbosities[verbInd];
		el.appendChild(document.createTextNode(verb));
		if (verb==curSetting) {
			el.selected = "selected";
		}
	}
	root.appendChild(sel);
	return output_BussedElement(root, "op_verb", ["VOTable", "VOPlot", "FITS",
		"TSV"]);
}


function output_tdEncSelector(pars) {
	// returns a BussedElement to select VOTable encoding
	var root = document.createElement("span")
	var box = document.createElement("input");
	var curSetting;

	root["class"] = "op_widget";
	box.name = "_TDENC";
	if (pars['arg'+box.name]!=undefined) {
		curSetting = pars['arg'+box.name][0];
	} else {
		curSetting = "false";
	}
	box.type = "checkbox";
	box.style.width = "auto";
	root.appendChild(box);
	root.appendChild(document.createTextNode(" human-readable "));
	if (curSetting=="true") {
		box.checked = "checked";
	}
	return output_BussedElement(root, "op_tdenc", ["VOTable"]);
}


function output_getAvailableItems() {
	// returns a mapping from keys to title for available items; see above
	var res = new Array();
	var node = document.getElementById("op_selectItems");
	if (!node) {
		return res;
	}
	var pairs = node.firstChild.nodeValue.split("\n");
	for (var ind in pairs) {
		res.push(pairs[ind].split(" ", 2));
	}
	return res;
}

function output_expandSelectNode(ev) {
	ev.currentTarget.size = 10;
}

function output_collapseSelectNode(ev) {
	ev.currentTarget.size = 1;
}

function output_itemSelector(pars) {
	// returns a BussedElement to select additional fields
	var root = document.createElement("span");
	var selector = document.createElement("select");

	root["class"] = "op_widget";
	selector.name = "_ADDITEM";
	var selected = pars['arg'+selector.name];
	if (selected==undefined) {
		selected = new Array();
	}
	selector.size = 1;
	selector.style.maxWidth = '200px';
	selector.addEventListener("mouseover", output_expandSelectNode, false);
	selector.addEventListener("mouseout", output_collapseSelectNode, false);
	selector.multiple = "multiple";
	var availableItems = output_getAvailableItems();
	for (var ind in availableItems) {
		var key = availableItems[ind][0];
		var opt = document.createElement("option");
		opt.appendChild(document.createTextNode(
			decodeURIComponent(availableItems[ind][1])));
		opt.value = key;
		if (isIn(opt.value, selected)) {
			opt.selected = "selected";
		}
		selector.appendChild(opt);
	}
	if (availableItems.length) {
		root.appendChild(document.createTextNode(" additional output fields "));
		root.appendChild(selector);
	}
	return output_BussedElement(root, "op_addfields", ["HTML"]);
}	


function output_hide(el) {
	if (document.getElementById(el.id)) {
		el.parentNode.removeChild(el);
	}
}


function output_show(el) {
	if (!document.getElementById(el.id)) {
		document.getElementById("genForm-_OUTPUT").appendChild(el);
	}
}


function output_setFormat(format) {
	var opts=document.getElementById("genForm-_FORMAT").options;
	for (var optInd=0; optInd<opts.length; optInd++) {
		if (opts[optInd].value==format) {
			opts[optInd].selected = true;
		} else {
			opts[optInd].selected = false;
		}
	}
}

var output_bussedElements = Array();


function output_init() {
	var pars = decodeGetPars(location.search);
	var format = pars["arg_FORMAT"];

	if (!document.getElementById("genForm-_OUTPUT")) { // no form on page
		return;
	}
	output_bussedElements.push(output_verbSelector(pars));
	output_bussedElements.push(output_tdEncSelector(pars));
	output_bussedElements.push(output_itemSelector(pars));
	if (format==undefined) {
		format = "HTML";
	}
	output_broadcast(format);
	outputInited = true;
}

function output_broadcast(newFormat) {
	var visibleForThis = "visibleFor_"+newFormat;

	output_setFormat(newFormat);
	for (var ind in output_bussedElements) {
		var el=output_bussedElements[ind];
		if (el[visibleForThis]) {
			output_show(el);
		} else {
			output_hide(el);
		}
	}
}


if (window.addEventListener) {
	window.addEventListener("load", output_init, false);
} else {
	window.load = output_init;
}
