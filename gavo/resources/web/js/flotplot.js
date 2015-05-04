var DATETIME_RE = /^(\d\d\d\d)-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d.?\d*)$/;
var DATE_RE = /^(\d\d\d\d)-(\d\d)-(\d\d)$/;
var CURRENT_PLOT;

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


function _getFlotSeries(table, xInd, yInd, style, options) {
	// returns a flot series object for plotting a line/point plot
	// of xInd vs. yInd from table.
	//
	// options, if given, must be a dict pre-filled with series options.
	// It will be modified and returned.

	var data = new Array();

	if (options===undefined) {
		options = {};
	}

	table.find('tr.data').each(function(index, row) {
		var tds = $(row).children();
		var x = _getValue(tds[xInd].firstChild.data); 
		var y = _getValue(tds[yInd].firstChild.data);
		if (x!=null && y!=null) {
			data.push([x, y]);
		}
	});
	options["data"] = data;

	if (style=="Lines") {
		options["lines"] = {'show': true,
			'lineWidth': 1};
		data.sort(function(a,b){return a[0]-b[0]});
	} else {
		options["points"] = {'show': true};
	}

	return options;
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
	CURRENT_PLOT = jQuery.plot(jQuery('#plotarea'), [{
		bars: {
			show: true,
			barWidth: histo[1][0]-histo[0][0]},
		data: histo}]);
}	


function _doFlotPlot(table, xsel, ysel, usingSel,
		xIndex2, yIndex2, style2) {
	var xIndex = xsel.find("option:selected").val();
	var yIndex = ysel.find("option:selected").val();
	var style = usingSel.find("option:selected").val();

	if (yIndex=='Histogram') {
		_doHistogramPlot(table, xIndex);
	} else {
		var toPlot = [];

		if (style2!=undefined) {
			var options = {
				"color": "#99aa00",};
			toPlot.push(_getFlotSeries(table, xIndex2, yIndex2, style2, options));
		}

		var options = {
			"color": "#444444",};
		toPlot.push(_getFlotSeries(table, xIndex, yIndex, style, options));

		CURRENT_PLOT = jQuery.plot(jQuery('#plotarea'), toPlot, {});
	}
}


function _plotUsingFlot(table, options) {
// allows simple plotting of HTML tables.  This only works from
// within openFlotPlot since it uses javascript that's not loaded
// by default.
// In options, have xselIndex, yselIndex (column indices of columsn to
// plot), usingIndex (1 for lines instead of dots), plotContainer (if
// given, becomes the parent of the plot; note that right now it MUST
// contain an element with id plotarea with nonzero size).
// 
// For overplotting, there's now also xselIndex2, yselIndex2, style2.
// No UI to manipulate that exists right now.

	// create the plot element
	if (options.plotContainer) {
		var plotElement = $(options.plotContainer);
	} else {
		var plotElement = $('<div id="plotcontainer" style="position:fixed;z-index:3000;background:white;padding-left:3px;padding-right:3px;padding-bottom:3px;border:2px solid gray"><p class="innerTitle"><span class="closer">x&nbsp;</span></p><div id="plotarea" style="width:700px;height:400px;"/></div>');
		plotElement.draggable();
		plotElement.find(".closer").bind("click", function(){
			plotElement.remove()});
	}

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
	var usingSel = $('<select><option selected="selected">Points</option><option>Lines</option></select>');
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
	xsel.children()[xselIndex].setAttribute("selected", "selected");
	ysel.children()[yselIndex].setAttribute("selected", "selected");
	usingSel.children()[usingIndex].setAttribute("selected", "selected");

	// the callback any form items controlling the plot
	var updatePlot = function() {
		try {
			_doFlotPlot(table, xsel, ysel, usingSel,
				options.xselIndex2, options.yselIndex2, options.style2);
		} catch (e) {
			CURRENT_PLOT = jQuery.plot(
				jQuery('#plotarea'), [{data:[], label: "unplottable"}]);
			throw e;
		}
	}
	xsel.change(updatePlot);
	ysel.change(updatePlot);
	usingSel.change(updatePlot);

	if (! options.plotContainer) {
		$("body").prepend(plotElement);
	}
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
