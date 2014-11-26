"""
Helpers for manipulating FITS files.

In contrast to fitstools, this is not for online processing or import of
files, but just for the manipulation before processing.

Rough guideline: if it's about writing fixed fits files, it probably belongs
here, otherwise it goes to fitstools.

Realistically, this module has been hemorraghing functions to
fitstools and probably should be removed completely.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

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
			header.add_blank(card.value, card.comment)
		elif card.key.lower() in ignoredHeaders:
			pass
		else:
			header.update(card.key, card.value, card.comment)


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


# Internal representation of Tuvikene et al FITS headers for plates
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

		pyfits.Card(value="-------------------- Data files"),
		("FILENAME", "Filename of this file"),
		("FN-WEDGE", "Filename of the wedge scan"),
		("FN-PRE", "Filename of the preview image"),
		("FN-COVER", "Filename of the envelope image"),
		("FN-LOGB", "Filename of the logbook image"),
		("ORIGIN", "Origin of this file"),
		("DATE", "File last changed"),

		pyfits.Card(value="-------------------- Other header cards"),]


def makeHeaderFromTemplate(template, **values):
	"""returns a new pyfits.Header from template with values filled in.

	template is a sequence of fixed pyfits.Cards and paris of keyword
	and description pairs.  The function will then look for each key
	in the keyword arguments and add a header card if a value is present.

	values for which no template item is given are ignored (but a
	warning is issued if there are leftover values).
	"""
	values = values.copy()
	hdr = pyfits.Header()

	for tp in template:
		if isinstance(tp, pyfits.Card):
			hdr.append(tp, end=True)
		else:
			key, comment = tp
			argKey = key.replace("-", "_")
			if values.get(argKey) is not None:
				hdr.append(pyfits.Card(key, values[argKey], comment), end=True)
				values.pop(argKey)
	
	if values:
		base.ui.notifyWarning("The following headers were left after"
			" applying a FITS template: %s"%(", ").join(values.keys()))
	return hdr

