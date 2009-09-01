<?xml version="1.0" encoding="utf-8"?>
<!-- mixin definition for tables implementing the siap interface(s) -->

<resource resdir="__system">
	<schema>public</schema>

	<table id="bboxSIAPcolumns" 
			original="__system__/products#productColumns">
		<column name="centerAlpha"  ucd="POS_EQ_RA_MAIN"
			type="double precision" unit="deg" 
			displayHint="type=time,sf=0" verbLevel="0" tablehead="Ctr. RA"
			description="Approximate center of image, RA"/>
		<column name="centerDelta"  ucd="POS_EQ_DEC_MAIN" tablehead="Ctr. Dec"
			type="double precision" unit="deg"
			displayHint="type=sexagesimal,sf=0" verbLevel="0"
			description="Approximate center of image, Dec"/>
		<column name="primaryBbox"  
			type="box" description="Bounding box of the image for internal use"
			displayHint="type=suppress"/>
		<column name="secondaryBbox"  
			type="box" description="Bounding box of the image for internal use"
			displayHint="type=suppress"/>
		<column name="imageTitle"  ucd="VOX:Image_Title"
			type="text" tablehead="Title" verbLevel="0"
			description="Synthetic name of the image"/>
		<column name="instId"  ucd="INST_ID"
			type="text" tablehead="Instrument" verbLevel="15"
			description="Identifier of the originating instrument"/>
		<column name="dateObs"  ucd="VOX:Image_MJDateObs"
			type="timestamp" unit="d" tablehead="Obs. date"
			verbLevel="0" description="Epoch at midpoint of observation"
			displayHint="type=humanDate"/>
		<column name="nAxes"  ucd="VOX:Image_Naxes" 
			type="integer" verbLevel="20" tablehead="#axes"
			description="Number of axes in data"/>
		<column name="pixelSize"  ucd="VOX:Image_Naxis"
			type="integer[]" verbLevel="15" tablehead="Axes Lengths"
			description="Number of pixels along each of the axes"
			unit="pix"/>
		<column name="pixelScale"  ucd="VOX:Image_Scale"
			type="real[]" verbLevel="12" tablehead="Scales"
			description="The pixel scale on each image axis"
			unit="deg/pix"/>
		<column name="imageFormat"  type="text"
			ucd="VOX:Image_Format" verbLevel="20"
			description="Format the data is delivered in"/>
		<column name="refFrame"  type="text"
			ucd="VOX:STC_CoordRefFrame" verbLevel="20"
			tablehead="Ref. Frame" 
			description="Coordinate system reference frame"/>
		<column name="wcs_equinox" ucd="VOX:STC_CoordEquinox"
			 verbLevel="20" tablehead="Equinox"
			description="Equinox of the given coordinates" unit="yr"/>
		<column name="wcs_projection" ucd="VOX:WCS_CoordProjection"
			 type="text" verbLevel="20"
			tablehead="Proj." description="FITS WCS projection type"/>
		<column name="wcs_refPixel" ucd="VOX:WCS_CoordRefPixel"
			 type="real[]" verbLevel="20"
			tablehead="Ref. pixel" description="WCS reference pixel"
			unit="pix,pix"/>
		<column name="wcs_refValues" ucd="VOX:WCS_CoordRefValue"
			 type="double precision[]"
			verbLevel="20" tablehead="Ref. values"
			description="World coordinates at WCS reference pixel"
			unit="deg,deg"/>
		<column name="wcs_cdmatrix" ucd="VOX:WCS_CDMatrix" verbLevel="20"
			 type="real[]" tablehead="CD matrix"
			description="FITS WCS CDij matrix" unit="deg/pix"/>
		<column name="bandpassId" ucd="VOX:BandPass_ID" 
			tablehead="Bandpass" description="Freeform name of the bandpass used"
			 type="text" verbLevel="10"/>
		<column name="bandpassUnit" ucd="VOX:BandPass_Unit"
			description="Unit of bandpass specifications"
			tablehead="Bandpass unit"
			 type="text" verbLevel="20"/>
		<column name="bandpassRefval" ucd="VOX:BandPass_RefValue"
			 verbLevel="20" tablehead="Band Ref."
			description="Characteristic quantity for the bandpass of the image"/>
		<column name="bandpassHi" ucd="VOX:BandPass_HiLimit"
			 verbLevel="20" tablehead="Band upper"
			description="Upper limit of the bandpass (in BandPass_Unit units)"/>
		<column name="bandpassLo" ucd="VOX:BandPass_LoLimit"
			 verbLevel="20" tablehead="Band lower"
			description="Lower limit of the bandpass (in BandPass_Unit units)"/>
		<column name="pixflags" ucd="VOX:Image_PixFlags" verbLevel="20"
			 type="text" tablehead="P. Flags"
			description="Flags specifying the processing done (C-original; F-resampled; Z-fluxes valid; X-not resampled; V-for display only"/>
	</table>

	<procDef type="apply" id="computeBboxSIAP" register="True">
		<doc>
			computes fields for the bboxSiap interface.

			It takes no arguments but expects WCS-like keywords in rowdict, i.e.,
			CRVAL1, CRVAL2 (interpreted as float deg), CRPIX1, CRPIX2 (pixel
			corresponding to CRVAL1, CRVAL2), CUNIT1, CUNIT2 (pixel scale unit,
			we bail out if it isn't deg and assume deg when it's not present), 
			CDn_n (the transformation matrix; substitutable by CDELTn), NAXISn 
			(the image size).

			It leaves the primaryBbbox, secondaryBbox, centerDelta, centerAlpha,
			nAxes, pixelSize, pixelScale and imageFormat.

			Records without or with insufficient wcs keys are furnished with
			all-NULL wcs info.
		</doc>
		<setup>
			<code>
				wcskeys = ["primaryBbox", "secondaryBbox", "centerAlpha", "centerDelta",
					"nAxes",  "pixelSize", "pixelScale", "imageFormat", "wcs_projection",
					"wcs_refPixel", "wcs_refValues", "wcs_cdmatrix", "wcs_equinox"]

				class PixelGauge(object):
					"""is a container for information about pixel sizes.

					It is constructed with an astWCS.WCS instance and an (x, y)
					pair of pixel coordinates that should be close to the center 
					of the frame.
					"""
					def __init__(self, wcs, centerPix):
						centerPos = wcs.pix2wcs(*centerPix)
						offCenterPos = wcs.pix2wcs(centerPix[0]+1, centerPix[1]+1)
						self._computeCDs(centerPos[0]-offCenterPos[0], 
							centerPos[1]-offCenterPos[1])

					def _computeCDs(self, da, dd):
						dAngle = math.atan2(da, dd)
						self.cds = (
							(da*math.cos(dAngle), da*math.sin(dAngle)),
							(dd*math.sin(dAngle), dd*math.cos(dAngle)))

					def getPixelScales(self):
						"""returns the pixel sizes in alpha and delta in degrees.
						"""
						aVec, dVec = self.cds
						return (math.sqrt(aVec[0]**2+aVec[1]**2),
							math.sqrt(dVec[0]**2+dVec[1]**2))

				from gavo.protocols import siap
			</code>
		</setup>
		<code>
			wcs = coords.getWCS(vars)
			result["imageFormat"] = "image/fits"
			try:
				result["primaryBbox"], result["secondaryBbox"
					] = siap.splitCrossingBox(coords.getBboxFromWCSFields(wcs))
				result["centerAlpha"], result["centerDelta"
					] = coords.getCenterFromWCSFields(wcs)
				result["nAxes"] = int(vars["NAXIS"])
				axeInds = range(1, result["nAxes"]+1)
				assert len(axeInds)==2   # probably not strictly necessary
				dims = tuple(int(vars["NAXIS%d"%i]) 
					for i in axeInds)
				pixelGauge = PixelGauge(wcs, (dims[0]/2., dims[1]/2.))
				result["pixelSize"] = dims
				result["pixelScale"] = pixelGauge.getPixelScales()

				result["wcs_projection"] = vars.get("CTYPE1")
				if result["wcs_projection"]:
					result["wcs_projection"] = result["wcs_projection"][5:8]
				result["wcs_refPixel"] = (
					wcs.WCSStructure.xref, wcs.WCSStructure.yref)
				result["wcs_refValues"] = (wcs.WCSStructure.xrefpix, 
					wcs.WCSStructure.yrefpix)
				result["wcs_cdmatrix"] = pixelGauge.cds[0]+pixelGauge.cds[1]
				result["wcs_equinox"] = vars.get("EQUINOX", None)
			except (KeyError, AttributeError), msg:
				for key in wcskeys:
					result[key] = None
		</code>
	</procDef>

	<procDef type="apply" id="setSIAPMeta" register="True">
		<doc>
			sets siap meta *and* product table fields.
	
			This is common stuff for all SIAP implementations.

		</doc>
		<setup>
			<par key="title" late="True">None</par>
			<par key="instrument" late="True">None</par>
			<par key="dateObs" late="True">None</par>
			<par key="imageFormat" late="True">'image/fits'</par>
			<par key="bandpassId" late="True">None</par>
			<par key="bandpassUnit" late="True">None</par>
			<par key="bandpassRefval" late="True">None</par>
			<par key="bandpassHi" late="True">None</par>
			<par key="bandpassLo" late="True">None</par>
			<par key="refFrame" late="True">'ICRS'</par>
			<par key="pixflags" late="True">None</par>
		</setup>
		<code>
			result["imageTitle"] = title
			result["instId"] = instrument
			result["dateObs"] = dateObs
			result["imageFormat"] = imageFormat
			result["bandpassId"] = bandpassId
			result["bandpassUnit"] = bandpassUnit
			result["bandpassRefval"] = bandpassRefval
			result["bandpassHi"] = bandpassHi
			result["bandpassLo"] = bandpassLo
			result["refFrame"] = refFrame
			result["pixflags"] = pixflags
		</code>
	</procDef>

	<condDesc id="siapBase">
		<phraseMaker>
			<setup id="baseSetup">
				<code>
					from gavo.protocols import siap
					def interpretFormat(inPars, sqlPars):
						# Interprets a SIA FORMAT parameter.  METADATA is caught by the
						# SIAP renderer, which of the magic values leaves ALL and 
						# GRAPHIC to us.
						fmt = inPars.get("FORMAT")
						if fmt is None or fmt=="ALL":
							return ""
						elif fmt=="GRAPHIC":
							return "imageFormat IN %%(%s)s"%base.getSQLKey("format", 
								base.getConfig("graphicMimes"), sqlPars)
						else:
							return "imageFormat=%%(%s)s"%base.getSQLKey(
								"format", fmt, sqlPars)
				</code>
			</setup>
		</phraseMaker>
	</condDesc>

	<condDesc id="siap" register="True">
		<inputKey name="POS" type="text" unit="deg,deg"
			ucd="pos.eq"
			description="J2000.0 Position, RA,DEC decimal degrees (e.g., 234.234,-32.46)"
			tablehead="Position" required="True"/>
		<inputKey name="SIZE" type="text" unit="deg,deg" id="siapSIZE"
			description="Size in decimal degrees (e.g., 0.2 or 1,0.1)"
			tablehead="Field size" required="True"/>
		<inputKey name="INTERSECT" type="text" required="False"
			description="Should the image cover, enclose, overlap the ROI or contain its center?"
			tablehead="Intersection type">
			<values default="OVERLAPS">
				<option>OVERLAPS</option>
				<option>COVERS</option>
				<option>ENCLOSED</option>
				<option>CENTER</option>
			</values>
		</inputKey>
		<inputKey name="FORMAT" id="siapFORMAT" type="text" required="False"
			description="Requested format of the image data"
			tablehead="Output format" widgetFactory='Hidden'>
			<values default="image/fits"/>
		</inputKey>
		<phraseMaker>
			<setup original="baseSetup"/>
			<code>
				yield siap.getBboxQuery(inPars, outPars)
				yield interpretFormat(inPars, outPars)
			</code>
		</phraseMaker>
	</condDesc>

	<condDesc id="humanSIAP" register="True">
		<inputKey name="POS" type="text" unit="deg,deg" ucd="pos.eq" description=
			"ICRS Position, RA,DEC, or Simbad object (e.g., 234.234,-32.45)"
			tablehead="Position" required="True"/>
		<inputKey original="siapSIZE"/>
		<inputKey name="INTERSECT" type="text" description=
			"Relation of image and specified Region of Interest."
			tablehead="Intersection type">
			<values default="COVERS">
				<option title="Image overlaps RoI">OVERLAPS</option>
				<option title="Image covers RoI">COVERS</option>
				<option title="RoI covers image">ENCLOSED</option>
				<option title="The given position is shown on image">CENTER</option>
			</values>
		</inputKey>
		<inputKey original="siapFORMAT"/>
		<phraseMaker>
			<setup original="baseSetup"/>
			<code>
				pos = inPars["POS"]
				try:
					ra, dec = base.parseCooPair(pos)
				except ValueError:
					data = base.caches.getSesame("web").query(pos)
					if not data:
						raise base.ValidationError("%r is neither a RA,DEC pair nor a simbad"
						" resolvable object"%inPars.get("POS", "Not given"), "POS")
					ra, dec = float(data["RA"]), float(data["dec"])
				inPars = {
					"POS": "%f, %f"%(ra, dec), "SIZE": inPars["SIZE"],
					"INTERSECT": inPars["INTERSECT"], "FORMAT": inPars.get("FORMAT")}
				yield siap.getBboxQuery(inPars, outPars)
				yield interpretFormat(inPars, outPars)
			</code>
		</phraseMaker>
	</condDesc>

</resource>
