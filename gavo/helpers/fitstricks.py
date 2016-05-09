"""
Helpers for manipulating FITS files.

In contrast to fitstools, this is not for online processing or import of
files, but just for the manipulation before processing.

Rough guideline: if it's about writing fixed fits files, it probably belongs
here, otherwise it goes to fitstools.

Realistically, this module has been hemorraghing functions to
fitstools and probably should be removed completely.

One important function it has grown is FITS header templates.  These
can be used by processors.  If these use custom templates, they should
register them (or regret it later).  See registerTemplate's docstring.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import re

from gavo import base
from gavo.utils import pyfits

DEFAULT_IGNORED_HEADERS = ["simple", "bitpix", "naxis", "imageh", 
	"imagew", "naxis1", "naxis2", "datamin", "datamax", "date"]

def copyFields(header, cardList, 
		ignoredHeaders=frozenset(DEFAULT_IGNORED_HEADERS)):
	"""copies over all cards from cardList into header, excluding headers
	named in ignoredHeaders.

	ignoredHeaders must be all lowercase.
	"""
	for card in cardList:
		if card.key=="COMMENT":
			header.add_comment(card.value)
		elif card.key=="HISTORY":
			header.add_history(card.value)
		elif card.key=="":
			header.append(pyfits.Card("", card.value), end=True)
		elif card.key.lower() in ignoredHeaders:
			pass
		else:
			header.update(card.key, card.value, card.comment)


def getHeaderAsDict(hdr):
	"""returns the "normal" key-value pairs from hdr in a dictionary.

	Comment, history and blank cards are excluded; the comments from the
	cards are lost, too.
	"""
	ignored = frozenset(["", "HISTORY", "COMMENT"])
	return dict((k,v) for k,v in hdr.iteritems()
		if k not in ignored)


def _makeHeaderSequence(keyTpl, commentTpl):
	try:
		return [
			(keyTpl%ind, commentTpl%numeral) 
			for ind, numeral in [
				(1, "1st"),
				(2, "2nd"),
				(3, "3rd"),]]
	except TypeError:
		raise base.ReportableError("Invalid header sequence templates: %r %r"%(
			keyTpl, commentTpl))


# FITS header template for a minimal pixel array
MINIMAL_IMAGE_TEMPLATE = [
	pyfits.Card("SIMPLE", True),
	pyfits.Card("EXTEND", True),
	("BITPIX", "Array data type"),
	pyfits.Card("NAXIS", 2),
	("NAXIS1", "Number of elements along 1st axis"),
	("NAXIS2", "Number of elements along 2nd axis"),
	("BZERO", "Zero point of pixel scaling function"),
	("BSCALE", "Slope of pixel scaling function"),]


WCS_TEMPLATE = [
		pyfits.Card(value="-------------------- Spatial WCS"),
	('EQUNIOX', "Equinox of RA and Dec"),
	('WCSAXES', "Number of FITS axes covered by WCS"),
	('CTYPE1', "Projection on axis 1"),
	('CTYPE2', "Projection on axis 2"),
	('LONPOLE', "See sect 2.4 of WCS paper II"),
	('LATPOLE', "See sect 2.4 of WCS paper II"),
	('CRVAL1', "Longitude  of reference point"),
	('CRVAL2', "Latitude of reference point"),
	('CRPIX1', "X reference pixel"),
	('CRPIX2', "Y reference pixel"),
	('CUNIT1', "X pixel scale units"),
	('CUNIT2', "Y pixel scale units"),
	('CD1_1', "(1,1) Full transformation matrix"),
	('CD1_2', "(1,2) Full transformation matrix"),
	('CD2_1', "(2,1) Full transformation matrix"),
	('CD2_2', "(2,2) Full transformation matrix"),
	('PC1_1', "(1,1) Transformation matrix"),
	('PC1_2', "(1,2) Transformation matrix"),
	('PC2_1', "(2,1) Transformation matrix"),
	('PC2_2', "(2,2) Transformation matrix"),
	('A_ORDER', "Correction polynomial order, axis 1"),
	('A_0_0', "Axis 1 correction polynomial, coefficient"),
	('A_0_1', "Axis 1 correction polynomial, coefficient"),
	('A_0_2', "Axis 1 correction polynomial, coefficient"),
	('A_1_0', "Axis 1 correction polynomial, coefficient"),
	('A_1_1', "Axis 1 correction polynomial, coefficient"),
	('A_2_0', "Axis 1 correction polynomial, coefficient"),
	('B_ORDER', "Correction polynomial order, axis 2"),
	('B_0_0', "Axis 2 correction polynomial, coefficient"),
	('B_0_1', "Axis 2 correction polynomial, coefficient"),
	('B_0_2', "Axis 2 correction polynomial, coefficient"),
	('B_1_0', "Axis 2 correction polynomial, coefficient"),
	('B_1_1', "Axis 2 correction polynomial, coefficient"),
	('B_2_0', "Axis 2 correction polynomial, coefficient"),
	('AP_ORDER', "Inverse polynomial order, axis 1"),
	('AP_0_0', "Axis 1 inverse polynomial, coefficient"),
	('AP_0_1', "Axis 1 inverse polynomial, coefficient"),
	('AP_0_2', "Axis 1 inverse polynomial, coefficient"),
	('AP_1_0', "Axis 1 inverse polynomial, coefficient"),
	('AP_1_1', "Axis 1 inverse polynomial, coefficient"),
	('AP_2_0', "Axis 1 inverse polynomial, coefficient"),
	('BP_ORDER', "Inverse polynomial order, axis 2"),
	('BP_0_0', "Axis 2 inverse polynomial, coefficient"),
	('BP_0_1', "Axis 2 inverse polynomial, coefficient"),
	('BP_0_2', "Axis 2 inverse polynomial, coefficient"),
	('BP_1_0', "Axis 2 inverse polynomial, coefficient"),
	('BP_1_1', "Axis 2 inverse polynomial, coefficient"),
	('BP_2_0', "Axis 2 inverse polynomial, coefficient"),]

# Internal representation of Tuvikene et al FITS headers for plates
# See https://www.plate-archive.org/wiki/index.php/FITS_header_format
WFPDB_TEMPLATE = MINIMAL_IMAGE_TEMPLATE+[
		pyfits.Card(value="-------------------- Original data of observation"),
		("DATEORIG", "Original recorded date of the observation"),
		("TMS-ORIG", "Start of the observation (logs)"),
		("TME-ORIG", "End of the observation (logs)"),
		("TIMEFLAG", "Quality flag of the recorded observation time"),
		("RA-ORIG",  "RA of plate center as given in source"),
		("DEC-ORIG", "Dec of plate center as given in source"),
		("COORFLAG", "Quality flag of the recorded coordinates"),
		("OBJECT",   "Observed object or field"),
		("OBJTYPE",  "Object type as in WFPDB"),
		("EXPTIME",  " [s] Exposure time of the first exposure"),
		("NUMEXP", 	"Number of exposures"),
		]+_makeHeaderSequence(
			"DATEOR%d",  "Original recorded date of the %s exposure"
		)+_makeHeaderSequence(
			"TMS-OR%d",  "Start of %s exposure (logs)"
		)+_makeHeaderSequence(
			"TME-OR%d",  "End of %s exposure (logs)"
		)+_makeHeaderSequence(
			"OBJECT%d",  "Object name for %s exposure"
		)+_makeHeaderSequence(
			"OBJTYP%d",  "Object type of %s OBJECT"
		)+_makeHeaderSequence(
			"EXPTIM%d",  " [s] Exposure time %s exposure")+[

		pyfits.Card(value="-------------------- Observatory and instrument"),
		("OBSERVAT", "Observatory name"),
		("SITENAME", "Observatory site name."),
		("SITELONG", " [deg] East longitude of observatory"),
		("SITELAT", " [deg] Latitude of observatory"),
		("SITEELEV", " [m] Elevation of the observatory"),
		("TELESCOP", "Telescope name"),
		("TELAPER", " [m] Clear aperture of the telescope"),
		("TELFOC", " [m] Focal length of the telescope"),
		("TELSCALE", " [arcsec/mm] Plate scale"),
		("INSTRUME", "Instrument name"),
		("DETNAM", "Detector name"),
		("METHOD", "Observation method as in WFPDB"),
		("FILTER",  "Filter type"),
		("PRISM", "Objective prism used"),
		("PRISMANG", " [deg] Angle of the objective prism"),
		("DISPERS", " [Angstrom/mm] Dispersion"),
		("GRATING",  "Fix this comment."),
		("FOCUS", "Focus value (from logbook)."),
		("TEMPERAT", "Air temperature (from logbook)"),
		("CALMNESS", "Calmness (seeing conditions), scale 1-5"),
		("SHARPNES", "Sharpness, scale 1-5"),
		("TRANSPAR", "Transparency, scale 1-5"),
		("SKYCOND", "Notes on sky conditions (logs)"),
		("OBSERVER", ""),
		("OBSNOTES", "Observer notes (logs)"),

		pyfits.Card(value="-------------------- Photographic plate"),
		("PLATENUM", "Plate number in logs"),
		("WFPDB-ID", "Plate identifier in WFPDB"),
		("SERIES", "Series or survey of plate"),
		("PLATEFMT", "Informal designation of plate format"),
		("PLATESZ1", " [cm] Plate size along axis1"),
		("PLATESZ2", " [cm] Plate size along axis2"),
		("FOV1", "Field of view along axis 1"),
		("FOV2", "Field of view along axis 2"),
		("EMULSION", "Type of the photographic emulsion"),
		("PQUALITY", "Quality of the plate"),
		("PLATNOTE", "Notes about the plate"),

		pyfits.Card(value="-------------------- Derived observation data"),
		("DATE-OBS", "UT date and time of obs. start"),
		]+_makeHeaderSequence(
			"DT-OBS%d", "UT d/t of start of %s exposure")+[
		("DATE-AVG", "UT d/t mid-point of observation"),
		]+_makeHeaderSequence(
			"DT-AVG%d", "UT d/t mid-point of %s exposure")+[
		("DATE-END", "UT d/t end of observation"),
		]+_makeHeaderSequence(
			"DT-END%d", "UT d/t of end of %s exposure")+[
		("YEAR", "Julian year at start of obs"),
		]+_makeHeaderSequence(
			"YEAR%d", "Julian year at start of %s obs")+[
		("YEAR-AVG", "Julian year at mid-point of obs"),
		]+_makeHeaderSequence(
			"YR-AVG%d", "Julian year at mid-point of %s obs")+[
		("JD", "Julian date at start of obs"),
		]+_makeHeaderSequence(
			"JD%d", "Julian date at start of %s obs")+[
		("JD-AVG", "Julian date at mid-point of obs")
		]+_makeHeaderSequence(
			"JD-AVG%d", "Julian date at mid-point of %s obs")+[
		("JD-AVG", "Julian date at mid-point of obs"),
		]+_makeHeaderSequence(
			"JD-AVG%d", "Julian date at mid-point of %s obs")+[
		("RA", "ICRS center of plate RA h:m:s"),
		("DEC", "ICRS center of plate Dec d:m:s"),
		("RA_DEG", "[deg] ICRS center of plate RA"),
		("DEC_DEG", "[deg] ICRS center of plate Dec"),
		]+_makeHeaderSequence(
			"RA_DEG%d", " [deg] ICRS center RA %s obs"
		)+_makeHeaderSequence(
			"DEC_DE%d", " [deg] ICRS center DEC %s obs")+[
		("AIRMASS", "Airmass at mean epoch"),
		("HA", "Hour angle at mean epoch"),
		("ZD", "Zenith distance at mean epoch"),

		pyfits.Card(value="-------------------- Scan details"),
		("SCANNER", "Scanner hardware used"),
		("SCANRES1", " [in-1] Scan resolution along axis 1"),
		("SCANRES2", " [in-1] Scan resolution along axis 2"),
		("PIXSIZE1", " [um] Pixel size along axis 1"),
		("PIXSIZE2", " [um] Pixel size along axis 2"),
		("SCANSOFT", "Scan software used"),
		("SCANGAM",  "Scan gamma value"),
		("SCANFOC",  "Scan focus"),
		("WEDGE",    "Photometric step-wedge type"),
		("DATESCAN", "UT scan date and time"),
		("SCANAUTH", "Author of the scan"),
		("SCANNOTE", "Notes about the scan"),
		("DATAMIN",  "Min pixel value in image"),
		("DATAMAX",  "Max pixel value in image"),

		pyfits.Card(value="-------------------- Data files"),
		("FILENAME", "Filename of this file"),
		("FN-WEDGE", "Filename of the wedge scan"),
		("FN-PRE", "Filename of the preview image"),
		("FN-COVER", "Filename of the envelope image"),
		("FN-LOGB", "Filename of the logbook image"),
		("ORIGIN", "Origin of this file"),
		("DATE", "File last changed"),
		
		] + WCS_TEMPLATE + [

		pyfits.Card(value="-------------------- Other header cards"),]


_TEMPLATE_NAMES = [
	("minimal", MINIMAL_IMAGE_TEMPLATE),
	("wfpdb", WFPDB_TEMPLATE),]


def registerTemplate(templateName, template):
	"""registers a named FITS header template.

	Registering lets DaCHS figure out the template from a history entry
	it leaves, so it's certainly a good idea to do that.

	For templateName, use something containing a bit of your signature
	(e.g., ariAncientPlate rather than just ancientPlate).
	"""
	_TEMPLATE_NAMES.append((templateName, template))


def getTemplateForName(templateName):
	"""returns the FITS template sequence for templateName.

	A NotFoundError is raised if no such template exists.
	"""
	for name, template in _TEMPLATE_NAMES:
		if name==templateName:
			return template
	raise base.NotFoundError(templateName, "FITS template",
		"registred templates", hint="If you used a custom template,"
		" have you called fitstricks.registerTemplate(name, template)"
		" for it?")


def getNameForTemplate(template):
	"""returns the name under which the FITS template has been registred.
	"""
	for name, namedTemplate in _TEMPLATE_NAMES:
		if template is namedTemplate:
			return name
	raise base.NotFoundError("template "+str(id(template)), 
		"FITS template",
		"registred templates", hint="If you used a custom template,"
		" have you called fitstricks.registerTemplate(name, template)"
		" for it?")


def getTemplateNameFromHistory(hdr):
	"""returns the template name used for generating hdr.

	A ReportableError is raised if the info signature is missing.
	"""
	for card in hdr.get_history():
		mat = re.search("GAVO DaCHS template used: (\w+)", card)
		if mat:
			return mat.group(1)
	raise base.ReportableError("DaCHS template signature not found.",
		hint="This means that a function needed to figure out which"
		" FITS template DaCHS used to generate that header, and no"
		" such information was found in the Header's HISTORY cards."
		"  Either this file hasn't been written by DaCHS FITS templating"
		" engine, or some intervening thing hosed the history.")


def _applyTemplate(hdr, template, values):
	"""helps makeHeaderFromTemplate.

	Specifically, it moves items in values mentioned in template into
	header in template's order.  hdr and values are modified in that process.
	"""
	for tp in template:
		if isinstance(tp, pyfits.Card):
			tp.value = values.pop(tp.key, tp.value)
			hdr.append(tp, end=True)
		else:
			key, comment = tp
			argKey = key.replace("-", "_")
			if values.get(argKey) is not None:
				try:
					val = values[argKey]
					if isinstance(val, unicode):
						val = val.encode("ascii")

					hdr.append(pyfits.Card(key, val, comment), end=True)
				except Exception, ex:
					if hasattr(ex, "args") and isinstance(ex.args[0], basestring):
						ex.args = ("While constructing card %s: %s"%(
							key, ex.args[0]),)+ex.args[1:]
					raise

			values.pop(argKey, None)


def _copyMissingCards(newHdr, oldHdr):
	"""helps makeHeaderFromTemplate.

	Specifically, it copies over all cards from oldHder to newHdr not yet
	present there.  It will also move over history and comment cards.

	This will modify newHdr in place.
	"""
	commentCs, historyCs = [], []

	for card in oldHdr.ascardlist():
		if card.key=="COMMENT":
			commentCs.append(card)
		elif card.key=="HISTORY":
			if not "GAVO DaCHS template used" in card.value:
				historyCs.append(card)
		elif card.key:
			if card.key not in newHdr:
				newHdr.append(card, end=True)

	for card in historyCs:
		newHdr.append(card, end=True)
	newHdr.append(pyfits.Card(value=""), end=True)
	for card in commentCs:
		newHdr.append(card, end=True)


def makeHeaderFromTemplate(template, originalHeader=None, **values):
	"""returns a new pyfits.Header from template with values filled in.

	template usually is the name of a template previously registered with
	registerTemplate, or one of DaCHS predefined template names (currently,
	minimal and wfpdb).  In a pinch, you can also pass in an immediate 
	headers.

	originalHeader can be a pre-existing header; the history and comment
	cards are copied over from it, and if any of its other cards have not
	yet been added to the header, they will be added in the order that they 
	apprear there.

	values for which no template item is given are added in random order
	after the template unless an originalHeader is passed.  In that case,
	they are assumed to originate there and are ignored.
	"""
	values = values.copy()
	hdr = pyfits.Header()

	if isinstance(template, basestring):
		templateName = template
		template = getTemplateForName(templateName)
	else:
		try:
			templateName = getNameForTemplate(template)
		except base.NotFoundError:
			base.notifyWarning("Using anonymous FITS template.")
			templateName = "anonymous"

	_applyTemplate(hdr, template, values)

	if originalHeader:
		_copyMissingCards(hdr, originalHeader)
	elif values:
		base.ui.notifyWarning("The following values were left after"
			" applying a FITS template and will be added in random order: %s"%
			(", ").join(values.keys()))
		for key, value in values.iteritems():
			hdr.append(pyfits.Card(key, value), end=True)


	hdr.add_history("GAVO DaCHS template used: "+templateName)
	return hdr


def updateTemplatedHeader(hdr, templateName=None, **kwargs):
	"""return hdr updated with kwargs.

	hdr is assumed to have been created with makeHeaderFromTemplate
	and contain the template name in a history entry.  

	You can pass in templateName to keep DaCHS from trying to get things
	from the header.

	[It is probably better to use makeHeaderFromTemplate directly, passing
	in the orginalHeader; that preserves the order of non-templated
	headers].
	"""
	if templateName is None:
		templateName = getTemplateNameFromHistory(hdr)
	template = getTemplateForName(templateName)

	vals = getHeaderAsDict(hdr)
	vals.update(kwargs)

	res = makeHeaderFromTemplate(template, originalHeader=hdr, **vals)
	return res
