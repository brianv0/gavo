"""
Support code for the Simple Image Access Protocol.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import math
import re
import urllib

import numpy

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import coords
from gavo.protocols import products
from gavo.utils import pgsphere

MS = base.makeStruct

####################### SIAPv2 magic

def parseSIAP2Geometry(aString, fieldName="POS"):
	"""parses a SIAPv2 geometry spec to a pgsphere object.

	Parse errors raise validation errors for fieldName.
	"""
	mat = re.match("(CIRCLE|RANGE|POLYGON) (.*)", aString)
	if not mat:
		raise base.ValidationError("Invalid SIAPv2 geometry: '%s'"
			" (expected a SIAPv2 shape name)"%utils.makeEllipsis(aString, 20), 
			fieldName)
	
	geoName = mat.group(1)
	try:
		args = [float(s) for s in mat.group(2).split()]
	except ValueError:
		raise base.ValidationError("Invalid SIAPv2 coordinates: '%s'"
			" (bad floating point literal '%s')"%(
				utils.makeEllipsis(mat.group(2), 20), s),
			fieldName)
	
	if geoName=="CIRCLE":
		if len(args)!=3:
			raise base.ValidationError("Invalid SIAPv2 CIRCLE: '%s'"
				" (need exactly three numbers)"%(
					utils.makeEllipsis(aString, 20)),
				fieldName)
		return pgsphere.SCircle(pgsphere.SPoint.fromDegrees(args[0], args[1]),
			args[2]*utils.DEG)
	
	elif geoName=="RANGE":
		# SBox isn't really RANGE, but RANGE shouldn't have been
		# part of the standard and people that use it deserve
		# to get bad results.
		if len(args)!=4:
			raise base.ValidationError("Invalid SIAPv2 RANGE: '%s'"
				" (need exactly four numbers)"%(
					utils.makeEllipsis(aString, 20)),
				fieldName)
		if args[0]>args[1] or args[2]>args[3]:
			raise base.ValidationError("Invalid SIAPv2 RANGE: '%s'"
				" (lower limits must be smaller than upper limits)"%(
					utils.makeEllipsis(aString, 20)),
				fieldName)
		return pgsphere.SBox(
			pgsphere.SPoint.fromDegrees(args[0], args[2]),
			pgsphere.SPoint.fromDegrees(args[1], args[3]))
	
	elif geoName=="POLYGON":
		if len(args)<6 or len(args)%2:
			raise base.ValidationError("Invalid SIAPv2 POLYGON: '%s'"
				" (need more than three coordinate *pairs*)"%(
					utils.makeEllipsis(mat.group(2), 20)),
				fieldName)
		return pgsphere.SPoly([
				pgsphere.SPoint.fromDegrees(*pair)
			for pair in utils.iterConsecutivePairs(args)])
	
	else:
		assert False
	

####################### pgsSIAP mixin

# expressions as used in getPGSQuery
_PGS_OPERATORS = {
		"COVERS": "coverage ~ %%(%s)s",
		"ENCLOSED": "%%(%s)s ~ coverage",
		"CENTER": None, # special handling below
		"OVERLAPS": "%%(%s)s && coverage",
}

def getPGSQuery(intersect, ra, dec, sizes, prefix, sqlPars):
	"""returns SQL for a SIAP query on pgsSIAP tables.
	"""
	if intersect=='CENTER':
		return "%%(%s)s @ coverage"%(base.getSQLKey(
			prefix+"center", pgsphere.SPoint.fromDegrees(ra, dec), sqlPars))

	expr = _PGS_OPERATORS[intersect]
	try:
		targetBox = pgsphere.SBox.fromSIAPPars(ra, dec, sizes[0], sizes[1])
		return expr%base.getSQLKey(prefix+"area", targetBox, sqlPars)
	except pgsphere.TwoSBoxes, ex:
		# Fold-over at pole, return a disjunction
		return "( %s OR %s )"%(
			expr%base.getSQLKey(prefix+"area1", ex.box1, sqlPars),
			expr%base.getSQLKey(prefix+"area2", ex.box2, sqlPars))
		

####################### SIAP service helpers, cores, etc.

def dissectPositions(posStr):
	"""tries to infer RA and DEC from posStr.

	In contrast to base.parseCooPair, we are quite strict here and just
	try to cope with some bad clients that leave out the comma.
	"""
	try:
		ra, dec = map(float, posStr.split(","))
	except ValueError: # maybe a sign as separator?
		if '+' in posStr:
			ra, dec = map(float, posStr.split("+"))
		elif '-' in posStr:
			ra, dec = map(float, posStr.split("-"))
		else:
			raise ValueError("No pos")
	return ra, dec


def _getQueryMaker(queriedTable):
	"""returns a query making function for SIAP appropriate for queriedTable.

	This used to have a function when we had different backends for SIAP.
	Curently, we no longer have that, so this always returns getPGSQuery.
	"""
	return getPGSQuery


def getQuery(queriedTable, parameters, sqlPars, prefix="sia"):
	"""returns an SQL fragment for a SIAP query for bboxes.

	The SQL is returned as a WHERE-fragment in a string.  The parameters
	are added in the sqlPars dictionary.

	parameters is a dictionary that maps the SIAP keywords to the
	values in the query.  Parameters not defined by SIAP are ignored.
	"""
	posStr = urllib.unquote(parameters["POS"])
	try:
		ra, dec = dissectPositions(posStr)
	except (ValueError, TypeError):
		raise base.ui.logOldExc(base.ValidationError(
			"%s is not a RA,DEC pair."%posStr, "POS", posStr))
	try:
		sizes = map(float, parameters["SIZE"].split(","))
	except ValueError:
		raise base.ui.logOldExc(base.ValidationError("Size specification"
			" has to be <degs> or <degs>,<degs>", "SIZE", parameters["SIZE"]))
	if len(sizes)==1:
		sizes = sizes*2
	intersect = parameters.get("INTERSECT", "OVERLAPS")
	query = _getQueryMaker(queriedTable)(
		intersect, ra, dec, sizes, prefix, sqlPars)
	# the following are for the benefit of cutout queries.
	sqlPars["_ra"], sqlPars["_dec"] = ra, dec
	sqlPars["_sra"], sqlPars["_sdec"] = sizes
	return query


class SIAPCutoutCore(svcs.DBCore):
	"""A core doing SIAP plus cutouts.
	
	It has, by default, an additional column specifying the desired size of
	the image to be retrieved.  Based on this, the cutout core will tweak
	its output table such that references to cutout images will be retrieved.

	The actual process of cutting out is performed by the product core and
	renderer.
	"""
	name_ = "siapCutoutCore"

	# This should become a property or something once we 
	# compress the stuff or have images with bytes per pixel != 2
	bytesPerPixel = 2

	copiedCols = ["centerAlpha", "centerDelta", "imageTitle", "instId",
		"dateObs", "nAxes", "pixelSize", "pixelScale", "mime",
		"refFrame", "wcs_equinox", "wcs_projection", "wcs_refPixel",
		"wcs_refValues", "wcs_cdmatrix", "bandpassId", "bandpassUnit",
		"bandpassHi", "bandpassLo", "pixflags"]

	def getQueryCols(self, service, queryMeta):
		cols = svcs.DBCore.getQueryCols(self, service, queryMeta)
		for name in self.copiedCols:
			cols.append(svcs.OutputField.fromColumn(
				self.queriedTable.getColumnByName(name)))
		d = self.queriedTable.getColumnByName("accsize").copy(self)
		d.tablehead = "Est. file size"
		cols.append(svcs.OutputField.fromColumn(d))
		return cols

	def _fixRecord(self, record, centerAlpha, centerDelta, sizeAlpha, sizeDelta):
		"""inserts estimates for WCS values into a cutout record.
		"""
		wcsFields = coords.getWCS({
			"CUNIT1": "deg", "CUNIT2": "deg", "CTYPE1": "RA---TAN",
			"CTYPE2": "DEC--TAN", 
			"CRVAL1": record["wcs_refValues"][0],
			"CRVAL2": record["wcs_refValues"][1],
			"CRPIX1": record["wcs_refPixel"][0],
			"CRPIX2": record["wcs_refPixel"][1],
			"CD1_1": record["wcs_cdmatrix"][0],
			"CD1_2": record["wcs_cdmatrix"][1],
			"CD2_1": record["wcs_cdmatrix"][2],
			"CD2_2": record["wcs_cdmatrix"][3],
			"LONPOLE": "180",
			"NAXIS": record["nAxes"],
			"NAXIS1": record["pixelSize"][0],
			"NAXIS2": record["pixelSize"][1],
		})
		invTrafo = coords.getInvWCSTrafo(wcsFields)
		upperLeft = invTrafo(centerAlpha-sizeAlpha/2, centerDelta-sizeDelta/2)
		lowerRight = invTrafo(centerAlpha+sizeAlpha/2, centerDelta+sizeDelta/2)
		centerPix = invTrafo(centerAlpha, centerDelta)
		record["wcs_refPixel"] = numpy.array([centerPix[0]-lowerRight[0],
			centerPix[1]-lowerRight[1]])
		record["wcs_refValues"] = numpy.array([centerAlpha, centerDelta])
		record["accref"] = products.RAccref(record["accref"], {
			"ra": centerAlpha, "dec": centerDelta, 
			"sra": sizeAlpha, "sdec": sizeDelta})
		record["centerAlpha"] = centerAlpha
		record["centerDelta"] = centerDelta
		record["accsize"] = min(record["accsize"],
			int(self.bytesPerPixel
				*abs(upperLeft[0]-lowerRight[0])*abs(upperLeft[1]-lowerRight[1])))

	def run(self, service, inputData, queryMeta):
		res = svcs.DBCore.run(self, service, inputData, queryMeta)
		sqlPars = queryMeta["sqlQueryPars"]
		try:
			sra = sdec = float(queryMeta.ctxArgs["cutoutSize"])
		except (KeyError, ValueError):
			try:
				sra, sdec = sqlPars["_sra"], sqlPars["_sdec"]
			except KeyError:
				sra, sdec = 0.5, 0.5

		if "_dec" in sqlPars:
			cosD = math.cos(sqlPars["_dec"]/180*math.pi)
			if abs(cosD)>1e-5:
				sra = sra/cosD
			else:
				sra = 360

		for record in res:
			try:
				self._fixRecord(record, 
					sqlPars.get("_ra", record["centerAlpha"]), 
					sqlPars.get("_dec", record["centerDelta"]), sra, sdec)
			except ValueError:
				# pywcs derives its (hidden) InvalidTransformError from ValueError.
				# Anwyway, deliver slightly botched records rather
				# than none at all, but warn the operators:
				base.ui.notifyWarning("Botched WCS in the record %s"%record)
		return res


def _test():
	import doctest, siap
	doctest.testmod(siap)


if __name__=="__main__":
	_test()
