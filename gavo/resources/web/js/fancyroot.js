// Javscript for treemenu-type root pages
// This depends on stuff from gavo.js, which must therefore be included
// first.

var JSONROOT = '/_portaljs/'

function fetchIntoMain(dataURL, rowFormatter, queryPars) {
	destEl = $("#mainbox");
	destEl.empty();
	ul = $('<ul class="servicelist"></ul>');
	destEl.append(ul);
	$.getJSON(dataURL,
		queryPars,
		function(data, textStatus, xhr) {
			data.map(function(row) {
				ul.append(rowFormatter(row));
			})
		}
	)
}

function updateForInput() {
	words = $("#textsearch").val();
	if (!words) {
		$("#mainbox").empty();
		$("#mainbox").append($("<ul class='servicelist'/>"));
	} else {
		fetchIntoMain(JSONROOT+'byFulltext', 
			formatResourceHeader, {'q': words});
	}
}

function textsearchKey(ev) {
	if (ev.which==13) {
		updateForInput($('#mainbox'));
	}
}


function makeMainFetcher(dataSource, recordFormatter) {
	// returns a function getting json from datasource and formatting it
	// to the main list via recordFormatter
	return function () {
		fetchIntoMain(dataSource, recordFormatter);
	}
}

function makeFormatter(templateName) {
	return function (data) {
		return renderTemplate(templateName, data);
	}
}

fetchTitles = makeMainFetcher(JSONROOT+'titles',
	formatResourceHeader);
fetchSubjects = makeMainFetcher(JSONROOT+'subjects',
	makeFormatter("tmpl_subjectHeader"));
fetchAuthors = makeMainFetcher(JSONROOT+'authors',
	makeFormatter("tmpl_authorHeader"));
fetchFulltext = updateForInput;


function formatResourceHeader(resMeta) {
	// returns DOM for a short, expandable resource header.
	return $(renderTemplate(
		resMeta["browseable"]?"tmpl_resHead":"tmpl_resHeadNobrowse", 
		resMeta));
}	

function formatResourceRecord(destObject, resDetails) {
	return renderTemplate("tmpl_resDetails", resDetails);
}

function makeMatchAdder(queryURL, keyName) {
	return function(handle) {
		destElement = $("<ul class='servicelist fold'/>");
		handle.parent().append(destElement);
		pars = {};
		pars[keyName] = handle.attr("name");
		$.getJSON(queryURL, pars,
			function(data, textStatus, xhr) {
				data.map(function(row) {destElement.append(formatResourceHeader(row))});
			});
	}
}

addResForSubjects = makeMatchAdder(JSONROOT+'bySubject', 'subject')
addResForAuthors = makeMatchAdder(JSONROOT+'byAuthor', 'author')

function addServiceInfo(handle) {
	// adds extended service metadata to handle's parent
	var parts = handle.attr("name").split(',');
	var destElement = handle.parent();
	$.getJSON(JSONROOT+'serviceInfo',
		{'resId': parts[1], 'sourceRD': parts[0]},
		function(data, textStatus, xhr) {
			destElement.append(formatResourceRecord(destElement, data[0]));
		}
	);
}

function _makeToggler(dataAdder) {
	// returns a function opening and closing "arrow handles";
	// dataFetcher is a function(handle) adding the subordinate stuff
	return function (handle) {
		var ob = $(handle);
		var childMeta = ob.parent().find(".fold");
		if (childMeta.length==0) {
			dataAdder(ob);
			var isOpen = false;
		} else {
			var isOpen = childMeta.css("display")!='none';
		}

		if (isOpen) {
			ob.find(".handlearrow").attr("src", "/static/img/arr-e.png");
			childMeta.css("display", "none");
		} else {
			ob.find(".handlearrow").attr("src", "/static/img/arr-s.png");
			childMeta.css("display", "block");
		}
	}
}


toggleDetails = _makeToggler(addServiceInfo);
toggleSubjectResources = _makeToggler(addResForSubjects);
toggleAuthorResources = _makeToggler(addResForAuthors);

$(document).ready(function() {
	$("#tab_placeholder").replaceWith(
		$(document.getElementById("tabbar_store").innerHTML));
	$("#tabset_tabs li").bind("click", makeTabCallback({
		'by-subject': fetchSubjects,
		'by-author': fetchAuthors,
		'by-title': fetchTitles,
		'by-text': fetchFulltext,
	}));
	$("#textsearch").bind("keypress", textsearchKey);
});

