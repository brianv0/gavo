<!-- a collection of various helpers for building dataling services. 

This is a temporary location for procDefs and friends complying to
"DALI-style" (interval) params
-->

<resource resdir="__system" schema="dc">


<!-- ********************* generic SODA procs -->

	<procDef type="descriptorGenerator" id="fromStandardPubDID">
		<doc>A descriptor generator for SODA that builds a 
		ProductDescriptor for PubDIDs that have been built by getStandardsPubDID
		(i.e., the path part of the IVORN is a tilde, with the
		products table accref as the query part).
		</doc>
		<code>
			return ProductDescriptor.fromAccref(
				pubDID,
				getAccrefFromStandardPubDID(pubDID))
		</code>
	</procDef>

	<procDef type="dataFormatter" id="trivialFormatter">
		<doc>The tivial formatter for SODA processed data -- it just
		returns descriptor.data, which will only work it it works as a
		nevow resource.

		If you do not give any dataFormatter yourself in a SODA core,
		this is what will be used.
		</doc>
		<code>
			return descriptor.data
		</code>
	</procDef>


	<!-- ********************* SODA interface to generic products -->

	<procDef type="dataFunction" id="generateProduct">
		<doc>A data function for SODA that returns a product instance.
		You can restrict the mime type of the product requested so the
		following filters have a good idea what to expect.
		</doc>
		<setup>
			<par key="requireMimes" description="A set or sequence of mime type 
				strings; when given, the data generator will bail out with 
				ValidationError if the product mime is not among the mimes
				given.">frozenset()</par>
			<code>
				from gavo.protocols import products
			</code>
		</setup>
		<code>
			if requireMimes and descriptor.mime not in requireMimes:
				raise base.ValidationError("Document type not supported: %s"%
					descriptor.mime, colName="PUBDID", hint="Only source documents"
					" of the types %s are supported here."%str(requireMimes))

			descriptor.data = products.getProductForRAccref(descriptor.accref)
		</code>
	</procDef>


	<!-- ********************* SODA interface to SDM spectra -->

	<procDef type="descriptorGenerator" id="sdm_genDesc">
		<doc>A data function for SODA returning the product row
		corresponding to a PubDID within an SSA table.

		The descriptors generated have an ssaRow attribute containing
		the original row in the SSA table.
		</doc>
		<setup>
			<par key="ssaTD" description="Full reference (like path/rdname#id)
				to the SSA table the spectrum's PubDID can be found in."/>
			<par key="descriptorClass" description="The SSA descriptor
				class to use.  You'll need to override this if the dc.products
				path doesn't actually lead to the file (see
				`custom generators &lt;#custom-product-descriptor-generators&gt;`_)."
				late="True">ssap.SSADescriptor</par>
			<code>
				from gavo import rscdef
				from gavo import rsc
				from gavo import svcs
				from gavo.protocols import ssap
				ssaTD = base.resolveCrossId(ssaTD, rscdef.TableDef)
			</code>
		</setup>
		
		<code>
			with base.getTableConn() as conn:
				ssaTable = rsc.TableForDef(ssaTD, connection=conn)
				matchingRows = list(ssaTable.iterQuery(ssaTable.tableDef, 
					"ssa_pubdid=%(pubdid)s", {"pubdid": pubDID}))
				if not matchingRows:
					return DatalinkFault.NotFoundFault(pubDID,
						"No spectrum with this pubDID known here")

				# the relevant metadata for all rows with the same PubDID should
				# be identical, and hence we can blindly take the first result.
				return descriptorClass.fromSSARow(matchingRows[0],
					ssaTable.getParamDict())
		</code>
	</procDef>

	<procDef type="dataFunction" id="sdm_genData">
		<doc>A data function for SODA returning a spectral data model
		compliant table that later data functions can then work on.
		As usual for generators, it uses the implicit PUBDID argument.
		</doc>
		<setup>
			<par key="builder" description="Full reference (like path/rdname#id)
				to a data element building the SDM instance table as its
				primary table."/>
			<code>
				from gavo import rscdef
				builder = base.resolveCrossId(builder, rscdef.DataDescriptor)
			</code>
		</setup>

		<code>
			from gavo.protocols import sdm
			descriptor.data = sdm.makeSDMDataForSSARow(descriptor.ssaRow, builder)
		</code>
	</procDef>

	<STREAM id="sdm_plainfluxcalib">
		<doc>A stream inserting a data function and its metadata generator to
		do select flux calibrations in SDM data.  This expects
		sdm_generate (or at least parameters.data as an SDM data instance)
		as the generating function within the SODA core.

		Clients can select "RELATIVE" as FLUXCALIB, which does a
		normalization to max(flux)=1 here.  Everything else is rejected
		right now.

		This probably is more an example of how to write such a thing
		then genuinely useful.
		</doc>
		<metaMaker>
			<code>
				supportedCalibs = set(["RELATIVE"])
				foundCalibs = descriptor.ssaRow["ssa_fluxcalib"]
				if isinstance(foundCalibs, basestring):
					foundCalibs = set([foundCalibs])
				supportedCalibs.update(foundCalibs)

				yield MS(InputKey, name="FLUXCALIB", type="text",
					multiplicity="single",
					ucd="phot.calib",
					utype="ssa:Char.FluxAxis.Calibration",
					description="Recalibrate the spectrum.  Right now, the only"
						" recalibration supported is max(flux)=1 ('RELATIVE').",
						values=MS(Values, options=[
							MS(Option, content_=val) for val in supportedCalibs]))
			</code>
		</metaMaker>

		<dataFunction>
			<code>
				if not args.get("FLUXCALIB"):
					return

				from gavo.protocols import sdm
				# table is changed in place
				sdm.mangle_fluxcalib(descriptor.data.getPrimaryTable(), 
					args["FLUXCALIB"])
				</code>
		</dataFunction>
	</STREAM>

	<STREAM id="sdm_cutout">
		<doc>A stream inserting a data function and its metaMaker to
		do cutouts in SDM data. This expects sdm_generate (or at least
		parameters.data as an SDM data instance) as the generating function 
		within the SODA core.

		The cutout limits are always given in meters, regardless of
		the spectrum's actual units (as in SSAP's BAND parameter).
		</doc>

  	<metaMaker>
     	<code>
				yield MS(InputKey, type="double precision[2]", xtype="interval",
					name="BAND",
					unit="m", ucd="em.wl", 
					description="Spectral cutout interval",
					values=MS(Values, 
						min=descriptor.ssaRow["ssa_specstart"],
						max=descriptor.ssaRow["ssa_specend"]))
    	</code>
  	</metaMaker>

		<dataFunction>
			<code>
				if args.get("BAND") is None:
					return

				from gavo.protocols import sdm
				# table is modified in place
				sdm.mangle_cutout(
					descriptor.data.getPrimaryTable(),
					args["BAND"][0], args["BAND"][1])
			</code>
		</dataFunction>
	</STREAM>

	<STREAM id="sdm_format">
		<doc>A formatter for SDM data, together with its input key
		for FORMAT.
		</doc>

		<metaMaker>
			<code>
				formatsAvailable = {
						"application/x-votable+xml": "VOTable, binary encoding",
						"application/x-votable+xml;serialization=tabledata": 
							"VOTable, tabledata encoding",
						"application/x-votable+xml;content=spec2": 
							"VOTable, experimental spectral DM 2 serialization",
						"text/plain": "Tab separated values",
						"text/csv": "Comma separated values",
						"application/fits": "FITS binary table"}

				yield MS(InputKey, name="FORMAT", type="text",
					ucd="meta.code.mime",
					utype="ssa:Access.Format",
					multiplicity="single",
					description="MIME type of the output format",
					values = MS(Values,
						options = [MS(Option, title=value, content_=key)
							for key, value in formatsAvailable.iteritems()]))
			</code>
		</metaMaker>

		<dataFormatter>
			<code>
				from gavo.protocols import sdm

				return sdm.formatSDMData(descriptor.data, args["FORMAT"])
			</code>
		</dataFormatter>
	</STREAM>


	<!-- ********************* SODA interface for generic FITS 
		manipulations -->
	<procDef type="descriptorGenerator" id="fits_genDesc">
		<doc>A data function for SODA returning the a fits descriptor.

		This has, in addition to the standard stuff, a hdr attribute containing
		the primary header as pyfits structure.

		The functionality of this is in its setup, getFITSDescriptor.
		The intention is that customized DGs (e.g., fixing the header)
		can use this as an original.
		</doc>
		<setup>
			<code>
				def getFITSDescriptor(pubDID, cls=FITSProductDescriptor):
					try:
						accref = getAccrefFromStandardPubDID(pubDID)
					except ValueError:
						return DatalinkFault.NotFoundFault(pubDID,
							"Not a pubDID from this site.")

					if accrefPrefix and not accref.startswith(accrefPrefix):
						return DatalinkFault.AuthenticationFault(pubDID,
							"This SODA service not available"
							" with this pubDID")

					return cls.fromAccref(pubDID, accref)
			</code>

			<par key="accrefPrefix" description="A prefix for the accrefs 
				the parent SODA service works on.  Calls on all other accrefs
				will be rejected with a 403 forbidden.  You should always
				include a restriction like this when you make assumptions
				about the FITSes (e.g., what axes are available).">None</par>
		</setup>
		<code>
			return getFITSDescriptor(pubDID)
		</code>
	</procDef>


	<procDef type="metaMaker" id="fits_makeWCSParams">
		<doc>A metaMaker that generates parameters allowing cutouts along
		the various WCS axes in physical coordinates.
	
		This uses pywcs for the spatial coordinates and tries to figure out 
		what these are with some heuristics.  For the remaining coordinates,
		it assumes all are basically 1D, and it sets up separate, manual
		transformations for them.

		The metaMaker leaves an axisNames mapping in the descriptor.
		This is important for the fits_doWCSCutout, and replacement metaMakers
		must do the same.

		The meta maker also creates a skyWCS attribute in the descriptor
		if successful, containing the spatial transformation only.  All
		other transformations, if present, are in miscWCS, by a dict mapping
		axis labels to the fitstools.WCS1Trans instances.
		
		If individual metadata in the header are wrong or to give better
		metadata, use axisMetaOverrides.  This will not generate standard
		parameters for non-spatial axis (BAND and friends).  There are
		other //soda streams for those.
		</doc>
		<setup>
			<par key="stcs" description="A QSTC expression describing the
				STC structure of the parameters.  If you don't give this,
				no STC structure will be declared.">None</par>
			<par key="axisMetaOverrides" description="A python dictionary
				mapping fits axis indices (1-based) to dictionaries of
				inputKey constructor arguments; for spatial axis, use the
				axis name instead of the axis index.">{}</par>
			<code><![CDATA[
				from gavo.utils import fitstools

				def iterSpatialKeys(descriptor):
					"""yields inputKeys for spatial cutouts along the coordinate
					axes.

					This can be nothing if descriptor doesn't have a skyWCS attribute
					or if it's None.
					"""
					if not getattr(descriptor, "skyWCS", None):
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

							yield MS(InputKey,  multiplicity="single",
								type="double precision[2]", xtype="interval",
								stc=parSTC,
								values=MS(Values, min=minCoo, max=maxCoo),
								**paramArgs)
							descriptor.axisNames[name] = cutoutName

				def iterOtherKeys(descriptor, spatialAxes):
					"""yields inputKeys for all WCS axes not covered by spatialAxes.
					"""
					axesLengths = fitstools.getAxisLengths(descriptor.hdr)
					for axIndex, length in enumerate(axesLengths):
						fitsAxis = axIndex+1
						if fitsAxis in spatialAxes:
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
							"stc": parSTC,
							"description": "Coordinate along axis number %s"%fitsAxis,
							"ucd": None}
						if fitsAxis in axisMetaOverrides:
							paramArgs.update(axisMetaOverrides[fitsAxis])

						yield MS(InputKey,  multiplicity="single",
							type="double precision[2]", xtype="interval",
							values=MS(Values, min=minPhys, max=maxPhys),
							**paramArgs)

				if stcs is None:
					parSTC = None
				else:
					parSTC = stc.parseQSTCS(stcs)
			]]></code>
		</setup>

		<code>
			descriptor.axisNames = {}
			descriptor.skyWCS, spatialAxes = coords.getSkyWCS(descriptor.hdr)

			for ik in iterSpatialKeys(descriptor):
				yield ik

			for ik in iterOtherKeys(descriptor, spatialAxes):
				yield ik
		</code>
	</procDef>

	<procDef type="dataFunction" id="fits_makeHDUList">
		<doc>
			An initial data function to construct a pyfits hduList and
			make that into a descriptor's data attribute.

			This wants a descriptor as returned by fits_genDesc.

			There's a hack here: this sets a dataIsPristine boolean on
			descriptor that's made false when one of the fits manipulators
			change something.  If that's true by the time the formatter
			sees it, it will just push out the entire file.  So, if you
			use this and insert your own data functions, make sure you
			set dataIsPristine accordingly.
		</doc>
		<setup>
			<par key="crop" description="Cut away everything but the
				primary HDU?">True</par>
		</setup>
		<code>
			from gavo.utils import pyfits

			descriptor.dataIsPristine = True
			descriptor.data = pyfits.open(os.path.join(
				base.getConfig("inputsDir"), descriptor.accessPath),
				do_not_scale_image_data=True)
			if crop:
				descriptor.data = pyfits.HDUList([descriptor.data[0]])
		</code>
	</procDef>

	<procDef type="dataFunction" id="fits_doWCSCutout">
		<doc>
			A fairly generic FITS cutout function.

			It expects some special attributes in the descriptor to allow it
			to decode the arguments.  These must be left behind by the
			metaMaker(s) creating the parameters.

			This is axisNames, a dictionary mapping parameter names to
			the FITS axis numbers or the special names WCSLAT or WCSLONG. 
			It also expects a skyWCS attribute, a pywcs.WCS instance for spatial
			cutouts.

			Finally, descriptor must have a list attribute slices, containing
			zero or more tuples of (fits axis, lowerPixel, upperPixel); this
			allows things like BAND to add their slices obtained
			from parameters in standard units.

			The .data attribute must be a pyfits hduList, as generated by the
			fits_makeHDUList data function.
		</doc>
		<code>
			from gavo.utils import fitstools

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
		</code>
	</procDef>

	<procDef type="dataFormatter" id="fits_formatHDUs">
		<doc>
			Formats pyfits HDUs into a FITS file.

			This all works in memory, so for large FITS files you'd want something
			more streamlined.
		</doc>
		<code>
			if descriptor.dataIsPristine:
				return File(os.path.join(
					base.getConfig("inputsDir"), descriptor.accessPath),
					"image/fits")

			from gavo.formats import fitstable
			resultName = fitstable.writeFITSTableFile(descriptor.data)
			return TemporaryFile(resultName, "image/fits")
		</code>
	</procDef>

	<STREAM id="fits_genKindPar">
		<doc>This stream should be included in FITS-handling SODA services;
		it adds parameter and code to just retrieve the FITS header to the
		core.
		
		For this to work as expected, it must be immediately before the
		formatter.</doc>
		<metaMaker name="genKindPar">
			<code>
				yield MS(InputKey, name="KIND", type="text",
					multiplicity="single", description="Set to HEADER"
					" to retrieve just the primary header, leave empty for data.",
					values = MS(Values,
						options = [MS(Option, content_="HEADER", 
								title="Retrieve header only"),
							MS(Option, content_="DATA", 
								title="Retrieve the full data, including header (default)")]))
			</code>
		</metaMaker>

		<dataFunction>
			<setup>
				<code>
					from gavo.utils import fitstools
				</code>
			</setup>
			<code>
				if args["KIND"]=="HEADER":
					descriptor.data = ("application/fits-header", 
						fitstools.serializeHeader(descriptor.data[0].header))
					raise DeliverNow()
			</code>
		</dataFunction>
	</STREAM>

	<STREAM id="fits_genPixelPar">
		<doc>This stream should be included  in FITS-handling SODA services;
		it add parameters and code to perform cut-outs along pixel coordinates.
		</doc>
		<metaMaker name="genPixelPars">
			<code>
				for axisInd in range(descriptor.hdr["NAXIS"]):
					fitsInd = axisInd+1
					minVal, maxVal = 1, descriptor.hdr["NAXIS%s"%fitsInd]
					if maxVal==minVal:
						continue

					yield MS(InputKey, name="PIXEL_%s"%fitsInd,
						type="integer[2]", unit="", xtype="interval",
						description="Pixel coordinate along axis %s"%fitsInd,
						ucd="pos.cartesian;instr.pixel", multiplicity="single",
						values=MS(Values, min=minVal, max=maxVal))
			</code>
		</metaMaker>

		<dataFunction name="cutoutPixelPars">
			<code>
				from gavo.utils import fitstools
				slices = []
				for fitsInd in range(1, descriptor.hdr["NAXIS"]+1):
					imMin, imMax = 1, descriptor.hdr["NAXIS"+str(fitsInd)]
					parName = "PIXEL_%s"%fitsInd
					if args[parName] is None:
						continue
					axMin, axMax = args[parName]
					descriptor.changingAxis(fitsInd, parName)
					slices.append([fitsInd, axMin, axMax])

				if slices:
					descriptor.dataIsPristine = False
					descriptor.data[0] = fitstools.cutoutFITS(descriptor.data[0],
						*slices)
			</code>
		</dataFunction>
	</STREAM>

	<procDef type="metaMaker" id="fits_makeBANDMeta">
		<doc>
			Yields standard BAND params.

			This adds lambdaToMeterFactor and lambdaAxis attributes to the
			descriptor for later use by fits_makeBANDSlice
		</doc>
		<setup>
			<par key="fitsAxis" description="FITS axis index (1-based) of
				the wavelength dimension">3</par>
			<par key="wavelengthUnit" description="Override for the FITS
				unit given for the wavelength (for when it is botched or
				missing; leave at None for taking it from the header)">None</par>
			<code>
				from gavo.utils import fitstools
			</code>
		</setup>
		<code>
			if not fitsAxis:
				return
			if not wavelengthUnit:
				fitsUnit = descriptor.hdr["CUNIT%d"%fitsAxis]
			descriptor.lambdaToMeterFactor = base.computeConversionFactor(
				wavelengthUnit, "m")
			descriptor.lambdaAxis = fitstools.WCSAxis.fromHeader(
				descriptor.hdr, fitsAxis, forceSeparable=True)
			descriptor.lambdaAxisIndex = fitsAxis

			minPhys, maxPhys = descriptor.lambdaAxis.getLimits()
			yield MS(InputKey, name="BAND", unit="m",
				type="double precision[2]", xtype="interval",
				ucd="em.wl", description="Vacuum wavelength limits",
				multiplicity="single",
				values=MS(Values, 
					min=minPhys*descriptor.lambdaToMeterFactor, 
					max=maxPhys*descriptor.lambdaToMeterFactor))
		</code>
	</procDef>

	<procDef type="dataFunction" id="fits_makeBANDSlice">
		<doc>
			Computes a cutout for the parameters added by makeBANDMeta.

			This *must* sit in front of doWCSCutout.

			This also reuses internal state added by makeBANDMeta,
			so this really only makes sense together with it.
		</doc>
		<code>
			if args.get("BAND") is None:
				return
			axMin, axMax = args["BAND"]
			axMax /= descriptor.lambdaToMeterFactor
			axMin /= descriptor.lambdaToMeterFactor
		
			transform = descriptor.lambdaAxis
			descriptor.changingAxis(descriptor.lambdaAxisIndex, "BAND")
			descriptor.slices.append(
				(descriptor.lambdaAxisIndex, transform.physToPix(axMin),
					transform.physToPix(axMax)))
		</code>
	</procDef>

	<procDef type="metaMaker" id="fits_makePOSMeta">
		<doc>
			Yields a SIAv2-style POS param for cutouts.
		</doc>
		<code>
			yield MS(InputKey, name="POS", type="text", ucd="phys.angArea;obs",
				description="Region to (approximately) cut out, as Circle,"
				" Region, or Polygon", multiplicity="single")
		</code>
	</procDef>

	<procDef type="dataFunction" id="fits_makePOSSlice">
		<doc>
			Interprets the POS param.

			This will yield positional cutouts (as from RA/DEC) to the descriptor.
		</doc>
		<setup>
			<code>
				from gavo import stc
				from gavo.protocols import siap
				from gavo.stc import bboxes
				from gavo.utils import fitstools
			</code>
		</setup>
		<code>
			if args.get("POS") is None:
				return
			geom = siap.parseSIAP2Geometry(args["POS"])
			boxes = list(bboxes.getBboxes(
				stc.fromPgSphere('ICRS', geom)))
			corners = reduce(lambda a,b: a+b, [((r1, d1), (r2, d2))
				for r1, d1, r2, d2 in boxes])

			slices = coords.getPixelLimits(corners, descriptor.skyWCS)
			for fitsInd, _, _ in slices:
				descriptor.changingAxis(fitsInd, "POS")

			if slices:
				descriptor.data[0] = fitstools.cutoutFITS(descriptor.data[0],
					*slices)
				descriptor.dataIsPristine = False
		</code>
	</procDef>

	<STREAM id="fits_genPOSPar">
		<doc>
			Adds metadata and data function for a SIAPv2-style POS cutout parameter.
		</doc>
		<metaMaker procDef="//soda#fits_makePOSMeta"/>
		<dataFunction procDef="//soda#fits_makePOSSlice"/>
	</STREAM>

	<STREAM id="fits_standardBANDCutout">
		<doc>
			Adds metadata and data function for one axis containing wavelengths.

			(this could be extended to cover frequency and energy axes, I guess)
			
			To use this, give the fits axis containing the spectral coordinate
			in the spectralAxis attribute; if needed, you can override the
			unit in wavelengthUnit (if the unit in the header is somehow 
			bad or missing; don't use quotes here).

			This *must* be included  physically before fits_doWCSCutout.
			Otherwise, no cutout will be performed.
		</doc>

		<metaMaker procDef="//soda#fits_makeBANDMeta">
			<bind key="fitsAxis">\spectralAxis</bind>
			<bind key="wavelengthUnit">'\wavelengthUnit'</bind>
		</metaMaker>
		<dataFunction procDef="//soda#fits_makeBANDSlice"/>
	</STREAM>

	<STREAM id="fits_standardDLFuncs">
		<doc>
			Pulls in all "standard" SODA functions for FITSes, including
			cutouts and header retrieval.

			You can give an stcs attribute (for fits_makeWCSParams); for this
			doesn't make sense because STCS cannot express the SODA parameter
			structure.

			For cubes, you can give a spectralAxis attribute here containing the
			fits axis index of the spectral axis.  If you don't not spectral
			cutout will be generated.  If you do, you may want to fix
			wavelengthUnit (default is to take what the FITS says).

			To work, this needs a descriptor generator; you probably want
			//soda#fits_genDesc here.
		</doc>
		<DEFAULTS stcs="" spectralAxis="" wavelengthUnit=""/>
		<metaMaker procDef="//soda#fits_makeWCSParams" name="getWCSParams">
			<bind key="stcs">'\stcs'</bind>
		</metaMaker>
		<dataFunction procDef="//soda#fits_makeHDUList" name="makeHDUList"/>
		<FEED source="fits_standardBANDCutout"
			spectralAxis="\spectralAxis" wavelengthUnit="\wavelengthUnit"/>
		<dataFunction procDef="//soda#fits_doWCSCutout" name="doWCSCutout"/>
		<FEED source="//soda#fits_genPOSPar"/>
		<FEED source="//soda#fits_genPixelPar"/>
		<FEED source="//soda#fits_genKindPar"/>
		<dataFormatter procDef="//soda#fits_formatHDUs" name="formatHDUs"/>
	</STREAM>


</resource>
