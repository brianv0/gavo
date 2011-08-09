// javascript support code for the GAVO data center


////////////////////////////// possibly generic functions

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

function insertPreviewURL(node, previewHref) {
// replaces the text content of node with a preview image pointed to
// by previewHref (for products).
	node.removeAttribute("onmouseover");
	node.attributes["class"].nodeValue += " busy";
	var image = document.createElement("img")
	image.setAttribute("src", previewHref);

	function checkFinished(self, nextCheck) {
		if (image.complete) {
			if (image.height>0) { // make sure there's an image (if mozilla).
				node.replaceChild(image, node.firstChild);
			} else { // load of preview image failed; could be ok for non-images.
				node.style.textDecoration = 'underline';
			}
			node.attributes["class"].nodeValue = 
				node.attributes["class"].nodeValue.slice(0, -5);
		} else {
			window.setTimeout(function() {self(self, nextCheck*1.1);}, nextCheck);
		}
	}

	checkFinished(checkFinished, 100);
}

function insertPreview(node, width) {
// replaces the text content of node with a DC-generated preview
// image.  node has to have a href attribute pointing to a DC
// FITS product for this to work.
	if (node.getAttribute("href")) {
		var oldHref = node.getAttribute("href");
		var newPars = "preview=True&width="+width;
		var joiner = "?";
		// TODO: do actual URL parsing here
		if (oldHref.indexOf("?")!=-1) { // assume we have a query
			joiner = "&";
		}
		insertPreviewURL(node, oldHref+joiner+newPars);
	}
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
			if (element.type=="radio" || element.type=="checkbox") {
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
		case "BUTTON":  // no state here
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

var expandedMetaWidth = '200px';

function markFold(title, markstr) {
	return title.slice(0, title.length-2)+markstr;
}

function toggleCollapsedMeta(el) {
	var contentBox = el.parentNode.nextSibling;
	if (contentBox.style.visibility=='visible') {
		el.childNodes[0].data = markFold(el.childNodes[0].data, ">>");
		collapseMeta(contentBox);
	} else {
		el.childNodes[0].data = markFold(el.childNodes[0].data, "<<");
		expandMeta(contentBox);
	}
}

function collapseMeta(box) {
	box.style.visibility = 'hidden';
	box.style.height = '0px';
	box.style.maxHeight = '0px';
	var parent = box.parentNode;
	parent.style.border = '0px none #707ca0';
	parent.style.padding = '1px';
	parent.style.background = 'none';
}

function expandMeta(box) {
	box.style.visibility = 'visible';
	box.style.height = 'auto';
	box.style.maxHeight = '200px';
	box.style.width = expandedMetaWidth;
	var parent = box.parentNode;
	parent.style.border = '1px solid #707ca0';
	parent.style.padding = '3px';
	parent.style.background = '#ffffff';
	parent.style.width = expandedMetaWidth;
}

function followEmbeddedLink(parent) {
// forwards the browser to the href of the first child that has one.
// this is for the button-type decoration around links.
	for (index in parent.childNodes) {
		child = parent.childNodes[index];
		if (child.href) {
			window.location = child.href;
			break;
		}
	}
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
//
//  In the DC, the static QueryMeta method getOutputWidget worries about this.


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
	var root = document.createElement("span");
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


function output_makePopupCleanup(child, govButton) {
// returns a function to put destNode back into the main form
	return function() {
		child.parentNode.removeChild(child);
		child.style.visibility = "hidden";
		child.style.position = "absolute";
		appendChildNodes(document.getElementById("genForm"), child);
		govButton.onclick = output_popupAddSel;
		govButton.firstChild.data = "More output fields";
	}
}


function output_popupAddSel() {
// pops up the dialog with the additional output items.  The popup
// receives a cleanup function.
	child = getElement("genForm-_ADDITEMS");
	child.parentNode.removeChild(child);
	child.style.visibility = "visible";
	child.style.position = "static";
	// I'd like to access the button via its id, but firefox doesn't let me.
	govButton = output_bussedElements[2];
	closer = openDOMsubwindow(getElement("genForm-_OUTPUT"), child,
		output_makePopupCleanup(child, govButton), true);
	govButton.onclick = closer;
	govButton.firstChild.data = "Pop down field selection";
	return false;
}


function output_itemSelector(pars) {
	// returns a Bussedelement to pop up the element Selector
	var root = document.createElement("button");

	root["type"] = "button";
	root["id"] = "op_addbutton";
	root.setAttribute("class", "popButton");
	root.onclick = output_popupAddSel;
	root.appendChild(document.createTextNode("More output fields"));

	// show nowhere unless there actually is a dialogue
	var showFor = new Array();
	if (getElement("genForm-_ADDITEMS")) {
		showFor.push('HTML');
	}
	return output_BussedElement(root, "op_additem", showFor);
}


function output_hide(el) {
	if (document.getElementById(el.id)) {
		el.parentNode.removeChild(el);
	}
}


function output_show(el) {
	if (!document.getElementById(el.id)) {
		dest = document.getElementById("genForm-_OUTPUT");
		dest.appendChild(document.createTextNode(" "));
		dest.appendChild(el);
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


///////////////// New, MochiKit dependent code (should grow over time)

function makeCloser(node, callback) {
	function close() {
		if (callback) {
			callback();
		}
		removeElement(node);
		return false;  // make this work as an event handler
	}
	return close;
};


function makeDraggable(handle, item) {
// makes item drabbable by handle
// item needs to be positioned (i.e., position absolute or relative)
	function startDrag(ev) {
		mouseX0 = ev.clientX;
		mouseY0 = ev.clientY;
		pos0 = getElementPosition(item);

		function moveHandler(inEv) {
			alert("  "+pos0.x+" "+pos0.y);
			curPos = {
				'x': pos0.x+inEv.clientX-mouseX0,
				'y': pos0.y+inEv.clientY-mouseY0};
			setElementPosition(item, curPos);
			return false;
		};

		function upHandler(inEv) {
			document.removeEventListener("mousemove", moveHandler, true);
			document.removeEventListener("mouseup", upHandler, true);
		};

		document.addEventListener("mousemove", moveHandler, true);
		document.addEventListener("mouseup", upHandler, false);

		return false;
	}
	handle.addEventListener("mousedown", startDrag, false);
};


function openDOMsubwindow(parent, innerDOM, callback) {
// open a "subwindow" containing innerDOM.
//
// parent is a DOM element innerDOM is to be centered on.  callback
// can be a function that is called when the window is being closed.
//
// returns a function that, when called, closes the "subwindow".
	makePositioned(parent);
	docWin = DIV({'class': 'innerWin'});
	closeSubWindow = makeCloser(docWin, callback);
	titlebar = P({'class': 'innerTitle'}, 
			SPAN({'onclick': closeSubWindow, 'title': 'Close this'}, 'x'));
	appendChildNodes(docWin, titlebar, innerDOM);
	docWin.style.position = 'absolute';
	appendChildNodes(parent, docWin);

//	makeDraggable(titlebar, docWin);
	return closeSubWindow;
}


function bubbleUpDOM(srcNode, innerDOM) {
// opens a "subwindow" containing innerURL, replacing srcNode.
//
// returns false for cheapo event handling
	var parent = srcNode.parentNode
	parent.removeChild(srcNode);
	function callback() {
		parent.appendChild(srcNode);
	}
	openDOMsubwindow(parent, innerDOM, callback);
	return false;
}

function bubbleUpByURL(srcNode, innerURL) {
// opens a "subwindow" containing innerURL.  This replaces srcNode in
// the doc tree.
//
// returns false for cheapo event handling
	function callback(result) {
		newNode = MochiKit.DOM.createDOM('div', {'class': 'innerBody'});
		newNode.innerHTML = result.responseText;
		bubbleUpDOM(srcNode, newNode);
	}
	doXHR(innerURL).addCallback(callback);
	return false;
}
