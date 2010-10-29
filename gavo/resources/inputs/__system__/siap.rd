<?xml version="1.0" encoding="utf-8"?>
<!-- mixin definition for tables implementing the siap interface(s) -->

<resource resdir="__system" schema="dc">

	<STREAM id="SIAPbase">
		<FEED source="//products#tablecols"/>
		<column name="centerAlpha"  ucd="POS_EQ_RA_MAIN"
			type="double precision" unit="deg" 
			displayHint="type=time,sf=0" verbLevel="0" tablehead="Ctr. RA"
			description="Approximate center of image, RA"/>
		<column name="centerDelta"  ucd="POS_EQ_DEC_MAIN" tablehead="Ctr. Dec"
			type="double precision" unit="deg"
			displayHint="type=sexagesimal,sf=0" verbLevel="0"
			description="Approximate center of image, Dec"/>
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
	</STREAM>

	<mixinDef id="bbox">
		<doc>
			A table mixin for simple support of SIAP based on hand-made bboxes.

			The columns added into the tables include

				- (certain) FITS WCS headers 
				- imageTitle (interpolateString should come in handy for these)
				- instId -- some id for the instrument used
				- dateObs -- a timestamp of the "characteristic" observation time
				- the bandpass* values.  You're on your own with them...
				- the values of the product interface.  
				- mimetype -- the mime type of the product.
				- the primaryBbox, secondaryBbox, centerAlpha and centerDelta, nAxes, 
					pixelSize, pixelScale, wcs* fields calculated by the 
					computeBboxSIAPFields macro.   

			(their definition is in the siap system RD)

			Tables mixing in //siap#bbox can be used for SIAP querying and
			automatically mix in `the products mixin`_.

			To feed these tables, use the //siap#computeBbox and 
			//siap#setMeta procs.  Since you are dealing with products, you will also
			need the //products#define rowgen in your grammar.

			If you have pgSphere, you definitely should use the pgs mixin in
			preference to this.
		</doc>
		
		<FEED source="//products#hackProductsData"/>

		<events>
			<FEED source="//siap#SIAPbase"/>
			<column name="primaryBbox"  
				type="box" description="Bounding box of the image for internal use"
				displayHint="type=suppress"/>
			<column name="secondaryBbox"  
				type="box" description="Bounding box of the image for internal use"
				displayHint="type=suppress"/>
		</events>
	</mixinDef>


	<mixinDef id="pgs">
		<doc>
			A table mixin for simple support of SIAP.

			The columns added into the tables include

				- (certain) FITS WCS headers 
				- imageTitle (interpolateString should come in handy for these)
				- instId -- some id for the instrument used
				- dateObs -- a timestamp of the "characteristic" observation time
				- the bandpass* values.  You're on your own with them...
				- the values of the product interface.  
				- mimetype -- the mime type of the product.
				- the coverage, centerAlpha and centerDelta, nAxes, 
					pixelSize, pixelScale, wcs* fields calculated by the 
					computePGS macro.   

			(their definition is in the siap system RD)

			Tables mixing in pgs can be used for SIAP querying and
			automatically mix in `the products mixin`_.

			To feed these tables, use the //siap#computePGS and 
			//siap#setMeta procs.  Since you are dealing with products, 
			you will also need the //products#define rowgen in your grammar.
		</doc>
		<FEED source="//products#hackProductsData"/>

		<events>
			<FEED source="//siap#SIAPbase"/>
			<column name="coverage" type="spoly" unit="deg"
				description="Field covered by the image"
				displayHint="type=suppress"/>
		</events>
	</mixinDef>


	<procDef type="apply" id="computeInputBase">
		<doc>
			computes input for SIAP tables.

			It takes no arguments but expects WCS-like keywords in rowdict, i.e.,
			CRVAL1, CRVAL2 (interpreted as float deg), CRPIX1, CRPIX2 (pixel
			corresponding to CRVAL1, CRVAL2), CUNIT1, CUNIT2 (pixel scale unit,
			we bail out if it isn't deg and assume deg when it's not present), 
			CDn_n (the transformation matrix; substitutable by CDELTn), NAXISn 
			(the image size).

			Records without or with insufficient wcs keys are furnished with
			all-NULL wcs info.
		</doc>
		<!-- Actually, this is a common base for both bbox and pgsphere based
		procs -->
		<setup>
			<code>
				from gavo.protocols import siap

				wcskeys = ["centerAlpha", "centerDelta",
					"nAxes",  "pixelSize", "pixelScale", "wcs_projection",
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

				def copyFromWCS(vars, wcs, result):
					"""adds the "simple" WCS kes from the wcstools instance wcs to
					the record result.
					"""
					result["mime"] = "image/fits"
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

				def nullOutWCS(result, additionalKeys):
					"""clears all wcs fields, plus the ones in additonalKeys.
					"""
					for key in wcskeys+additionalKeys:
						result[key] = None
			</code>
		</setup>
	</procDef>

	<procDef type="apply" id="computeBbox"
			original="computeInputBase">
		<code>
			wcs = coords.getWCS(vars)
			try:
				copyFromWCS(vars, wcs, result)
				result["primaryBbox"], result["secondaryBbox"
					] = siap.splitCrossingBox(coords.getBboxFromWCSFields(wcs))
			except (KeyError, AttributeError), msg:
				nullOutWCS(result, ["primaryBbox", "secondaryBbox"])
		</code>
	</procDef>

	<procDef type="apply" id="computePGS" original="computeInputBase">
		<code>
			wcs = coords.getWCS(vars)
			try:
				copyFromWCS(vars, wcs, result)
				result["coverage"] = coords.getSpolyFromWCSFields(wcs)
			except (KeyError, AttributeError), msg:
				nullOutWCS(result, ["coverage"])
		</code>
	</procDef>

	<procDef type="apply" id="setMeta">
		<doc>
			sets siap meta *and* product table fields.
	
			This is common stuff for all SIAP implementations.
		</doc>
		<setup>
			<par key="title" late="True">None</par>
			<par key="instrument" late="True">None</par>
			<par key="dateObs" late="True">None</par>
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
		<!-- This just contains some components the real SIAP conditions build
		upon.  Do not inherit from this, do not instanciate it. -->
		<phraseMaker>
			<setup id="baseSetup">
				<code>
					from gavo import rscdef
					from gavo.protocols import siap

					def interpretFormat(inPars, sqlPars):
						# Interprets a SIA FORMAT parameter.  METADATA is caught by the
						# SIAP renderer, which of the magic values leaves ALL and 
						# GRAPHIC to us.
						fmt = inPars.get("FORMAT")
						if fmt is None or fmt=="ALL":
							return ""
						elif fmt=="GRAPHIC":
							return "mime IN %%(%s)s"%base.getSQLKey("format", 
								base.getConfig("graphicMimes"), sqlPars)
						else:
							return "mime=%%(%s)s"%base.getSQLKey(
								"format", fmt, sqlPars)

					def getQueriedTable(inputKeys):
						"""tries to infer the table queried from the inputKeys passed to
						the condDesc.

						This will return None if it cannot find this parent table.
						"""
						try:
							res = inputKeys[0].parent.parent.queriedTable
						except (AttributeError, IndexError):
							traceback.print_exc()
							return None
						if not isinstance(res, rscdef.TableDef):
							return None
						return res
				</code>
			</setup>
		</phraseMaker>

		<inputKey id="base_POS" name="POS" type="text" unit="deg,deg"
			ucd="pos.eq"
			description="ICRS Position, RA,DEC decimal degrees (e.g., 234.234,-32.46)"
			tablehead="Position" required="True">
		</inputKey>

		<inputKey name="SIZE" type="text" unit="deg,deg" id="base_SIZE"
			description="Size in decimal degrees (e.g., 0.2 or 1,0.1)"
			tablehead="Field size" required="True">
		</inputKey>

		<inputKey name="INTERSECT" id="base_INTERSECT" type="text" description=
			"Relation of image and specified Region of Interest."
			tablehead="Intersection type" required="False">
			<values default="OVERLAPS" id="base_INTERSECT_values">
				<option title="Image overlaps RoI">OVERLAPS</option>
				<option title="Image covers RoI">COVERS</option>
				<option title="RoI covers image">ENCLOSED</option>
				<option title="The given position is shown on image">CENTER</option>
			</values>
		</inputKey>

		<inputKey name="FORMAT" id="base_FORMAT" type="text" required="False"
			description="Requested format of the image data"
			tablehead="Output format">
			<values default="image/fits"/>
		</inputKey>
	</condDesc>

	<condDesc id="protoInput">
		<inputKey original="base_POS">
			<property name="onlyForRenderer">siap.xml</property>
		</inputKey>
		<inputKey original="base_SIZE">
			<property name="onlyForRenderer">siap.xml</property>
		</inputKey>
		<inputKey original="base_INTERSECT">
			<property name="onlyForRenderer">siap.xml</property>
		</inputKey>
		<inputKey original="base_FORMAT">
			<property name="onlyForRenderer">siap.xml</property>
		</inputKey>
		<phraseMaker>
			<setup original="baseSetup"/>
			<code>
				yield siap.getQuery(getQueriedTable(inputKeys), inPars, outPars)
				yield interpretFormat(inPars, outPars)
			</code>
		</phraseMaker>
	</condDesc>

	<condDesc id="humanInput">
		<inputKey original="base_POS" name="hPOS"
			description="ICRS Position, RA,DEC, or Simbad object (e.g., 234.234,-32.45)">
			<property name="notForRenderer">siap.xml</property>
		</inputKey>
		<inputKey original="base_SIZE" name="hSIZE">
			<property name="notForRenderer">siap.xml</property>
		</inputKey>
		<inputKey original="base_INTERSECT" name="hINTERSECT">
			<property name="notForRenderer">siap.xml</property>
			<values original="base_INTERSECT_values" default="COVERS"/>
		</inputKey>
		<inputKey original="base_FORMAT" name="hFORMAT" widgetFactory='Hidden'>
			<property name="notForRenderer">siap.xml</property>
		</inputKey>

		<phraseMaker>
			<setup original="baseSetup"/>
			<code>
				pos = inPars["hPOS"]
				try:
					ra, dec = base.parseCooPair(pos)
				except ValueError:
					data = base.caches.getSesame("web").query(pos)
					if not data:
						raise base.ValidationError("%r is neither a RA,DEC pair nor"
								" a simbad resolvable object"%inPars.get("POS", "Not given"), 
							"hPOS")
					ra, dec = float(data["RA"]), float(data["dec"])
				inPars = {
					"POS": "%f, %f"%(ra, dec), "SIZE": inPars["hSIZE"],
					"INTERSECT": inPars["hINTERSECT"], "FORMAT": inPars.get("hFORMAT")}
				yield siap.getQuery(getQueriedTable(inputKeys), inPars, outPars)
				yield interpretFormat(inPars, outPars)
			</code>
		</phraseMaker>
	</condDesc>

</resource>
