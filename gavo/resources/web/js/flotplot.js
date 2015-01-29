DATETIME_RE = /^(\d\d\d\d)-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d.?\d*)$/
DATE_RE = /^(\d\d\d\d)-(\d\d)-(\d\d)$/
function _getValue(s) {
// tries to make some kind of number from a string s
// if s looks like a datetime, return a julian year
// TODO: do something with hours/sexagesimal angles
// if s looks like a float number, return a float
// else return null.
	var dm = DATETIME_RE.exec(s);
	if (dm!=null) {
		var dt = new Date(parseFloat(dm[1]), parseFloat(dm[2]), parseFloat(dm[3]),
			parseFloat(dm[4]), parseFloat(dm[5]), parseFloat(dm[6]));
		return getJYear(dt);
	}
	var dm = DATE_RE.exec(s);
	if (dm!=null) {
		var dt = new Date(parseFloat(dm[1]), parseFloat(dm[2]), parseFloat(dm[3]));
		return getJYear(dt);
	}

	var num = parseFloat(s);
	if (num==num) { // not NaN
		return num;
	}
	return null;
}
	


function _doLinePlot(table, xInd, yInd, style) {
	var data = new Array();
	var options = {"series": {}};

	table.find('tr.data').each(function(index, row) {
		var tds = $(row).children();
		var x = _getValue(tds[xInd].firstChild.data); 
		var y = _getValue(tds[yInd].firstChild.data);
		if (x!=null && y!=null) {
			data.push([x, y]);
		}
	});
	if (style=="Lines") {
		options.series["lines"] = {'show': true};
		data.sort(function(a,b){return a[0]-b[0]});
	} else {
		options.series["points"] = {'show': true};
	}
	jQuery.plot(jQuery('#plotarea'), [data], options);
}


function _makeHistogram(data, numBins) {
	if (data.length<2) {
		return new Array();
	}
	data.sort(function(a,b){return a-b});
	var zp = data[0];
	var binSize = (data[data.length-1]-zp)/numBins;
	if (binSize==0) {
		binSize = 1;
	}

	var histo = new Array();
	for (var i=0; i<numBins; i++) {
		histo.push(0);
	}
	for (index in data) {
		histo[Math.floor((data[index]-zp)/binSize)]++;
	}
	
	data = new Array();
	for (index in histo) {
		data.push([index*binSize+zp, histo[index]]);
	}
	return data;
}

function _doHistogramPlot(table, colInd) {
	var data = new Array();
	table.find('tr.data').each(function(index, row) {
		var val = _getValue($(row).children()[colInd].firstChild.data);
		if (val!=null) {
			data.push(val);
		}
	});

	var histo = _makeHistogram(data, 20);
	jQuery.plot(jQuery('#plotarea'), [{
		bars: {
			show: true,
			barWidth: histo[1][0]-histo[0][0]},
		data: histo}]);
}	


function _doFlotPlot(table, xsel, ysel, usingSel) {
	xInd = xsel.find("option:selected").val()
	yInd = ysel.find("option:selected").val()
	style = usingSel.find("option:selected").val()
	if (yInd=='Histogram') {
		_doHistogramPlot(table, xInd);
	} else {
		_doLinePlot(table, xInd, yInd, style);
	}
}


function _plotUsingFlot(table, options) {
// allows simple plotting of HTML tables.  This only works from
// within openFlotPlot since it uses javascript that's not loaded
// by default.
	// create the plot element
	var plotElement = $('<div id="plotcontainer" style="position:fixed;z-index:3000;background:white;padding-left:3px;padding-right:3px;padding-bottom:3px;border:2px solid gray"><p class="innerTitle"><span class="closer">x&nbsp;</span></p><div id="plotarea" style="width:700px;height:400px;"/></div>');
	plotElement.draggable();
	plotElement.find(".closer").bind("click", function(){
		plotElement.remove()});
	var controlPara = $('<p class="flotControl"></p>');
	plotElement.append(controlPara);

	// Make column selectors from table headings
	var xsel = $('<select/>');
	$(table.find('tr')[0]).find('th').each(function(index, head) {
		xsel.append($('<option value="'+index+'">'+$(head).text()+'</option>'));
	});
	controlPara.append(xsel);
	controlPara.append(' vs. ');
	var ysel = xsel.clone();
	ysel.append($(
		'<option value="Histogram">Histogram</option>'));
	controlPara.append(ysel);
	controlPara.append(' using ');
	var usingSel = $('<select><option selected="selected">Points</option><option>Lines</option></select>')
	controlPara.append(usingSel);

	// Set default plot features from options if given there
	var xselIndex = 0;
	if (options.xselIndex) {
		xselIndex = options.xselIndex;
	}
	var yselIndex = ysel.children().length-1;
	if (options.yselIndex) {
		yselIndex = options.yselIndex;
	}
	var usingIndex = 0;
	if (options.usingIndex) {
		usingIndex = options.usingIndex;
	}
	xsel.children()[xselIndex].setAttribute("selected", "selected")
	ysel.children()[yselIndex].setAttribute("selected", "selected")
	usingSel.children()[usingIndex].setAttribute("selected", "selected")

	// the callback any form items controlling the plot
	var updatePlot = function() {
		try {
			_doFlotPlot(table, xsel, ysel, usingSel);
		} catch (e) {
			jQuery.plot(jQuery('#plotarea'), [{data:[], label: "unplottable"}]);
			throw e;
		}
	}
	xsel.change(updatePlot);
	ysel.change(updatePlot);
	usingSel.change(updatePlot);

	$("body").prepend(plotElement);
	updatePlot();
}

function openFlotPlot(tableElement, options) {
// opens a div that lets you plot some columns of tableElement
	if (options==undefined) {
		options = {};
	}
	$.getScript("/static/js/jquery.flot.js",
		function() {_plotUsingFlot(tableElement, options)});
}

