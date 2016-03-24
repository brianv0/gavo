// Javascript for custom widgets for standard SODA parameters, and
// other JS support for the improvised soda interface.
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

// update a SODA (interval) widget for par name form a -low/-high/-unit
// split widget.
// soda_name is the name of the SODA parameter to be built.  conversions
// is a mapping going from -unit strings to converter functions to
// the SODA units.
function update_SODA_widget(input, soda_name, conversions) {
	var form = input.form;
	var low_element = form[soda_name+"-low"];
	var high_element = form[soda_name+"-high"];
	var unit_element = form[soda_name+"-unit"];
	var converter = conversions[unit_element.value];

	var low_val = low_element.value;
	if (low_val) {
		low_val = converter(parseFloat(low_val));
	} else {
		low_val = '-Inf';
	}

	var high_val = high_element.value;
	if (high_val) {
		high_val = converter(parseFloat(high_val));
	} else {
		high_val = '+Inf';
	}

	form[soda_name].value = low_val+" "+high_val;
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

	function make_limits(lim1, lim2) {
		if (lim1>lim2) {
			var tmp = lim1;
			lim1 = lim2;
			lim2 = tmp;
		}
		return lim1+" "+lim2;
	}
			
	self.to_ra = function(pix_val) {
		return high_ra-pix_val/(1.0*canvas_width)*phys_width;
	}
	self.to_dec = function(pix_val) {
		return high_dec-pix_val/(1.0*canvas_height)*phys_height;
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
			ra_widget.val(make_limits(
				self.to_ra(self.x), self.to_ra(self.x+self.width)));
		}
		if (self.height==0) {
			dec_widget.val("");
		} else {
			dec_widget.val(make_limits(
				self.to_dec(self.y), self.to_dec(self.y+self.height)));
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

function add_BAND_widget() {
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

		form.submit(
			function() {new_widget.remove();});
	});
}


function add_POS_widget() {
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

		var fov = (phys_width<phys_height) ? phys_height : phys_width;
		var image_url =	"http://alasky.u-strasbg.fr/cgi/hips-thumbnails/thumbnail"
				+"?ra="+(low_ra+phys_width/2)
				+"&dec="+(low_dec+phys_height/2)
				+"&fov="+fov
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
	add_BAND_widget();
	add_POS_widget();
}


//////////////////////////// SAMP interface/result URL building

// The thing sent to the SAMP clients is a URL built from all input
// items that have a soda class.  The stylesheet must arrange it so
// all input/select items generated from the declared service  parameters
// have a soda class.

// return a list of selected items for a selection element for URL inclusion
function get_selected_entries(select_element) {
	var result = new Array();
	var i;

	for (i=0; i<select_element.length; i++) {
		if (select_element.options[i].selected) {
			result.push(select_element.name+"="+encodeURIComponent(
				select_element.options[i].value))
		}
	}
	return result;
}

// return a URL fragment for a form item
function make_query_item(form_element, index) {
	var val = "";

	if (! $(form_element).hasClass("soda")) {
		return;
	}
	switch (form_element.nodeName) {
		case "INPUT":
		case "TEXTAREA":
			if (form_element.type=="radio" || form_element.type=="checkbox") {
				if (form_element.checked) {
					val = form_element.name+"="+encodeURIComponent(form_element.value);
				}
			} else if (form_element.name && form_element.value) {
				val = form_element.name+"="+encodeURIComponent(form_element.value);
			}
			break;
		case "SELECT":
			return get_selected_entries(form_element).join("&");
			break;
	}
	return val;
}


// return the URL that sending off cur_form would retrieve
function build_result_URL(cur_form) {
	var fragments = $.map(cur_form.elements, make_query_item);
	dest_url = cur_form.getAttribute("action")+"?"+fragments.join("&");
	return dest_url;
}


// send the current selection as a FITS image
function send_SAMP(conn, cur_form) {
	var msg = new samp.Message("image.load.fits", {
		"url": build_result_URL(cur_form),
		"name": "SODA result"});
	conn.notifyAll([msg]);
}


// return the callback for a successful hub connection
// (which disables-re-registration and sends out the image link)
function _make_SAMP_success_handler(samp_button, cur_form) {
	return function(conn) {
		conn.declareMetadata([{
			"samp.description": "SODA processed data from"+document.URL,
			"samp.icon.url": 
				"http://"+window.location.host+"/static/img/logo_tiny.png"
		}]);

		// set the button up so clicks send again without reconnection.
		$(samp_button).unbind("click");
		$(samp_button).click(function(e) {
			e.preventDefault();
			send_SAMP(conn, cur_form);
		});

		// make sure we unregister when the user leaves the page
		$(window).unload(function() {
			conn.unregister();
		});

		// send the stuff once (since the connection has been established
		// in response to a click alread)
		send_SAMP(conn, cur_form);
	};
}

// connect to a SAMP hub and, when the connection is established,
// send the current cutout result.
function connect_and_send_SAMP(samp_button, cur_form) {
	samp.register("SODA processor",
		_make_SAMP_success_handler(samp_button, cur_form),
				function(err) {
					alert("Could not connect to SAMP hub: "+err);
				}
			);
		}


// create a samp sending button in a SODA form
function enable_SAMP_on_form(index, cur_form) {
	try {
		var samp_button = $("#samp-template").clone()[0]
		$(samp_button).show()
		$(samp_button).attr({"id": ""});
		$(cur_form).prepend(samp_button);
		$(samp_button).click(function (e) {
			e.preventDefault();
			connect_and_send_SAMP(samp_button, cur_form);
		});
	} catch (e) {
		throw(e);
		// we don't care if there's no SAMP.  Log something?
	}
}

// enable SAMP sending for all forms that look promising
function enable_SAMP() {
	$("form.service-interface").each(enable_SAMP_on_form);
}

$(document).ready(replace_known_widgets);
$(document).ready(enable_SAMP);
