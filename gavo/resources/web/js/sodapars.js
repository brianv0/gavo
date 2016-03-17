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


/////////////////// Rubber band for 2D selection

function Rubberband(canvas,
		ra_widget, dec_widget, 
		low_ra, high_ra, low_dec, high_dec,
		canvas_width, canvas_height) {
	var self = {};
	self.x = 0;
	self.y = 0;
	self.width = 0;
	self.height = 0;

	var phys_width = high_ra-low_ra;
	var phys_height = high_dec-low_dec;

	var canvas = canvas
	var ctx = canvas.getContext("2d");
	var bg_store = ctx.getImageData(0, 0, canvas.width, canvas.height);
	ctx.strokeStyle = "red";
	ctx.lineWidth = 1;

	function make_limits(lim1, lim2, transform) {
		if (lim1>lim2) {
			var tmp = lim1;
			lim1 = lim2;
			lim2 = lim1;
		}
		return transform(lim1)+" "+transform(lim2);
	}
			
	self.to_ra = function(pix_val) {
		return low_ra+pix_val/(1.0*canvas_width)*phys_width;
	}
	self.to_dec = function(pix_val) {
		return low_dec+pix_val/(1.0*canvas_height)*phys_height;
	}

	self.start_rubberband = function(e) {
		e.preventDefault();
		self.x = e.offsetX;
		self.y = e.offsetY;
		$(canvas).mousemove(self.update_rubberband);
		$(canvas).mouseup(self.finish_rubberband);
		self.update_rubberband(e);
	}
	
	self.update_rubberband = function(e) {
		e.preventDefault();
		var rel_x = e.offsetX;
		var rel_y = e.offsetY;
		self.width = rel_x-self.x;
		self.height = rel_y-self.y;
		ctx.putImageData(bg_store, 0, 0);
		ctx.strokeRect(self.x, self.y, self.width, self.height);
		if (self.width==0) {
			ra_widget.val("");
		} else {
			ra_widget.val(make_limits(self.x, self.x+self.width, self.to_ra));
		}
		if (self.height==0) {
			dec_widget.val("");
		} else {
			dec_widget.val(make_limits(
				self.y, self.y+self.height, self.to_dec));
		}
	}

	self.finish_rubberband = function(e) {
		e.preventDefault();
		$(canvas).unbind("mousemove");
		$(canvas).unbind("mouseup");
	}

	$(canvas).mousedown(self.start_rubberband);

	return self;
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

		var new_widget = renderTemplate(
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


function replace_POS_widget() {
	var ra_widget = $(".RA-deg-pos_eq_ra").first();
	var dec_widget = $(".DEC-deg-pos_eq_dec").first();
	
	if (ra_widget && dec_widget) {
		var low_ra = parseFloat(ra_widget.find(".low-limit").text());
		var high_ra = parseFloat(ra_widget.find(".high-limit").text());
		var low_dec = parseFloat(dec_widget.find(".low-limit").text());
		var high_dec = parseFloat(dec_widget.find(".high-limit").text());
		var phys_width = high_ra-low_ra;
		var phys_height = high_dec-low_dec;

		var width = 300;
		var height = Math.round(width/phys_width*phys_height);
		if (height<5) {
			height = 5;
		}
		if (height>900) {
			height = 900;
		}

		var new_widget = $("#pos-template").clone(); 
		new_widget.attr({
			id: ""});
		new_widget.find("canvas").attr({
			width: width,
			height: height});
		ra_widget.parent().prepend(new_widget);
		new_widget.show();

		var image_url =	"http://alasky.u-strasbg.fr/cgi/hips-thumbnails/thumbnail"
				+"?ra="+(low_ra+phys_width/2)
				+"&dec="+(low_dec+phys_height/2)
				+"&fov="+phys_width
				+"&width="+width
				+"&height="+height
				+"&hips=CDS/P/DSS2/color";
		$(new_widget).find("img").attr({
			src: image_url,
			width: width,
			height: height});

		Rubberband($(new_widget).find("canvas")[0], 
			ra_widget.find("input"), 
			dec_widget.find("input"), 
			low_ra, high_ra, low_dec, high_dec, width, height);
	}
}

// call the various handler functions for known three-factor widgets.
// (this is called from the document's ready handler and thus is the
// main entry point into the magic here)
function replace_known_widgets() {
	replace_BAND_widget();
	replace_POS_widget();
}

$(document).ready(replace_known_widgets);
	
