// Javascript for custom widgets for standard SODA parameters.
// See https://github.com/msdemlei/datalink-xslt.git
//
// The needs jquery loaded before it


///////////// Micro templating.  
/// See http://docs.g-vo.org/DaCHS/develNotes.html#built-in-templating
function htmlEscape(str) {
	return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
		.replace(/'/g, '&apos;').replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
}

(function () {
	var _tmplCache = {};
	this.renderTemplate = function (templateId, data) {
		var err = "";
		var func = _tmplCache[templateId];
		if (!func) {
			str = document.getElementById(templateId).innerHTML;
			var strFunc =
				"var p=[],print=function(){p.push.apply(p,arguments);};"
				+ "with(obj){p.push('"
				+ str.replace(/[\r\t\n]/g, " ")
				.split("'").join("\\'")
				.split("\t").join("'")
				.replace(/\$([a-zA-Z_]+)/g, "',htmlEscape($1),'")
				.replace(/\$!([a-zA-Z_]+)/g, "',$1,'")
				+ "');}return $.trim(p.join(''));";
				func = new Function("obj", strFunc);
				_tmplCache[str] = func;
		}
		return func(data);
	}
})()


/////////////////// misc. utils

// set the contents of clsid within container to val
function update_class_elements(container, clsid, val) {
	container.find("."+clsid).map(
		function(i, el) {
			$(el).text(val);
		});
}

// returns a function to perform the conversion from custom UI to SODA
// parameters for par_name -- el is the widget's div, conversions is the unit
// conversion.  This needs input fields <par_name>-low, <par_name>-high,
// and <par_name>-unit
function make_submission_converter(el, old_widget,
		conversions, par_name) {
	return function() {
		var converter = conversions[this[par_name+"-unit"].value];

		var low_val = this[par_name+"-low"].value;
		if (low_val) {
			low_val = converter(parseFloat(low_val));
		} else {
			low_val = '-Inf';
		}

		var high_val = this[par_name+"-high"].value;
		if (high_val) {
			high_val = converter(parseFloat(high_val));
		} else {
			high_val = '+Inf';
		}

		this["BAND"].value = low_val+" "+high_val;
		$(this).find(".inputpars").find(".custom-BAND").remove()
	}
}


/////////////////// Unit conversion

LIGHT_C = 2.99792458e8;
PLANCK_H_EV = 4.135667662e-15;

// conversions from meters to
TO_SPECTRAL_CONVERSIONS = {
	'm': function(val) { return val; },
	'µm': function(val) { return val*1e6; },
	'Ångstrøm': function(val) { return val*1e10; },
	'MHz': function(val) { return LIGHT_C/val*1e-6; },
	'keV': function(val) { return LIGHT_C*PLANCK_H_EV/val*1e-3; }};

// conversions to meters from
FROM_SPECTRAL_CONVERSIONS = {
	'm': function(val) { return val; },
	'µm': function(val) { return val/1e6; },
	'Ångstrøm': function(val) { return val/1e10; },
	'MHz': function(val) { return LIGHT_C/val/1e-6; },
	'keV': function(val) { return LIGHT_C*PLANCK_H_EV/val/1e-3; }};


// set properly marked up limits.
// this assumes that el is the unit select and the whole widget is
// within a div.
function convert_spectral_units(el, low, high) {
	var converter = TO_SPECTRAL_CONVERSIONS[el.value];
	var input_group = $(el).parents("div").first();
	update_class_elements(input_group, "low-limit", converter(low));
	update_class_elements(input_group, "high-limit", converter(high));
}


/////////////////// Individual widgets

function replace_BAND_widget() {
	var old = $(".BAND-m-em_wl");
	old.map(function(index, el) {
		el = $(el);
		var form = el.parents("form");
		var low_limit = parseFloat(el.find(".low-limit").text());
		var high_limit = parseFloat(el.find(".high-limit").text());
		// TODO: validate limits?

		new_widget = renderTemplate(
			"fancy-band-widget", {
				low_limit: low_limit,
				high_limit: high_limit});
		el.parent().prepend(new_widget);
		el.hide();

	form.submit(
			make_submission_converter(
				new_widget, el, FROM_SPECTRAL_CONVERSIONS, "BAND"));
	});
}

// call the various handler functions for known three-factor widgets.
// (this is called from the document's ready handler and thus is the
// main entry point into the magic here)
function replace_known_widgets() {
	replace_BAND_widget();
}

$(document).ready(replace_known_widgets);
	
