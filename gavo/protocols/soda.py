"""
Helper functions for SODA manipulators.

This primarily comprises various WCS helpers.  It is built on base.coords,
which is where you'll get the wcsFields.

Note that this must not use things from protocols.datalink, as it
is imported from there.  Essentially, use this space for helpers
for SODA manipulations that are generic enough to be kept outside of
the RD but not generic enough to go do base.coords.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from gavo import rscdef
from gavo import svcs
from gavo.base import coords
from gavo.utils import fitstools

from gavo.base import makeStruct as MS


def ensureSkyWCS(descriptor):
	"""furnishes a soda fits descriptor with skyWCS and spatialAxes attributes 
	if necessary.

	This is usually called by the functions needing this automatically, and
	it's a no-op if it has already run.

	skyWCS will be None after this function as run if no usable WCS is found;
	otherwise, it will be a pywcs.WCS instance.  Additionally, spatialAxes
	will be a sequence of 1-based axis indices, and an empty dictionary
	axisNames is available to be filled by metaMakers.  It will then map
	the SODA parameter name to either a FITS axis index or to the special
	WCSLONG, WCSLAT values.
	"""
	if hasattr(descriptor, "skyWCS"):
		return
	
	descriptor.skyWCS, descriptor.spatialAxes = coords.getSkyWCS(descriptor.hdr)
	descriptor.axisNames = {}


def iterSpatialAxisKeys(descriptor, axisMetaOverrides):
	"""yields SODA inputKeys for spatial cutouts along the spatial
	coordinate axes.

	This can be nothing if descriptor doesn't have a skyWCS attribute
	or if it's None.
	"""
	ensureSkyWCS(descriptor)
	if descriptor.skyWCS is None:
		return

	footprint = descriptor.skyWCS.calcFootprint(descriptor.hdr)
	wcsprm = descriptor.skyWCS.wcs

	# FIXME: UCD inference!
	for name, colInd, description, baseUCD, cutoutName in [
		(wcsprm.lattyp.strip(), wcsprm.lat, "The latitude coordinate",
			"pos.eq.dec", "WCSLAT"),
		(wcsprm.lngtyp.strip(), wcsprm.lng, "The longitude coordinate",
			"pos.eq.ra", "WCSLONG")]:
		if name:
			vertexCoos = footprint[:,colInd]
			paramArgs = {"name": name, "unit": "deg", 
					"description": description,
					"ucd": baseUCD}

			minCoo, maxCoo = min(vertexCoos), max(vertexCoos)
			# for RA, we need to move the stitching line out
			# of the way (and go to negative longitudes) if
			# 0 is on the image; we're doing a little heuristic
			# there assuming that images are smaller than 180 deg.
			if cutoutName=="WCSLONG":
				if coords.straddlesStitchingLine(minCoo, maxCoo):
					minCoo, maxCoo = maxCoo-360, minCoo

			if name in axisMetaOverrides:
				paramArgs.update(axisMetaOverrides[name])

			yield MS(svcs.InputKey,  multiplicity="single",
				type="double precision[2]", xtype="interval",
				values=MS(rscdef.Values, min=minCoo, max=maxCoo),
				**paramArgs)
			descriptor.axisNames[name] = cutoutName


def iterOtherAxisKeys(descriptor, axisMetaOverrides):
	"""yields inputKeys for all non-spatial WCS axes.

	descriptor must be a FITSDescriptor.
	"""
	ensureSkyWCS(descriptor)
	if descriptor.skyWCS is None:
		return

	axesLengths = fitstools.getAxisLengths(descriptor.hdr)
	for axIndex, length in enumerate(axesLengths):
		fitsAxis = axIndex+1
		if fitsAxis in descriptor.spatialAxes:
			continue
		if length==1:
			# no cutouts along degenerate axes
			continue
		
		try:
			ax = fitstools.WCSAxis.fromHeader(descriptor.hdr, fitsAxis)
		except ValueError:
			# probably botched WCS, or an inseparable axis.
			# Just ignore this axis, operators can add it manually
			# using forceSeparable
			continue

		descriptor.axisNames[ax.name] = fitsAxis
		minPhys, maxPhys = ax.getLimits()

		# FIXME: ucd inference
		paramArgs = {"name": ax.name, "unit": ax.cunit, 
			"description": "Coordinate along axis number %s"%fitsAxis,
			"ucd": None}
		if fitsAxis in axisMetaOverrides:
			paramArgs.update(axisMetaOverrides[fitsAxis])

		yield MS(svcs.InputKey,  multiplicity="single",
			type="double precision[2]", xtype="interval",
			values=MS(rscdef.Values, min=minPhys, max=maxPhys),
			**paramArgs)


def addPolygonSlices(descriptor, poly, srcPar="Unknown"):
	"""adds slicings in descriptor.slices for a pgsphere.SPoly poly.

	srcPar is the name of the parameter that generated the polygon
	(for making error messages)
	"""
	for axisInd, lower, upper in coords.getPixelLimits(
			poly.asCooPairs(), descriptor.skyWCS):
		descriptor.changingAxis(axisInd, srcPar)
		descriptor.slices.append((axisInd, lower, upper))


def doAxisCutout(descriptor, args):
	"""updates descriptor.data on a FITS descriptor, interpreting the
	parameters defined by iter*AxisKeys, passed in in args.

	This is the main implementation of //soda#fits_doWCSCutout
	"""
	ensureSkyWCS(descriptor)
	slices = descriptor.slices

	# limits: [minRA, maxRA], [minDec, maxDec]]
	footprint = descriptor.skyWCS.calcFootprint(descriptor.hdr)
	limits = [[min(footprint[:,0]), max(footprint[:,0])],
		[min(footprint[:,1]), max(footprint[:,1])]]
	if coords.straddlesStitchingLine(limits[0][0], limits[0][1]):
		limits[0] = [limits[0][1]-360, limits[0][0]]
	limitsChangedName = None

	for parName, fitsAxis in descriptor.axisNames.iteritems():
		if args[parName] is None:
			continue
		limitsChangedName = parName

		if not isinstance(fitsAxis, int):
			# some sort of spherical axis
			if fitsAxis=="WCSLAT":
				cooLimits = limits[1]
			elif fitsAxis=="WCSLONG":
				cooLimits = limits[0]
			else:
				assert False

			cooLimits[0] = max(cooLimits[0], args[parName][0])
			cooLimits[1] = min(cooLimits[1], args[parName][1])
			
		else:
			# 1-d axis
			transform = fitstools.WCSAxis.fromHeader(descriptor.hdr, fitsAxis)
			axMin, axMax = args[parName]
			descriptor.changingAxis(fitsAxis, parName)
			slices.append((fitsAxis, 
				transform.physToPix(axMin), transform.physToPix(axMax)))

	if limitsChangedName:
		for axisInd, lower, upper in coords.getPixelLimits([
				(limits[0][0], limits[1][0]),
				(limits[0][1], limits[1][1])], descriptor.skyWCS):
			descriptor.changingAxis(axisInd, limitsChangedName)
			slices.append((axisInd, lower, upper))

	if slices:
		descriptor.data[0] = fitstools.cutoutFITS(descriptor.data[0],
			*slices)
		descriptor.dataIsPristine = False
