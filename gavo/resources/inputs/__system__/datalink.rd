<!-- a collection of various helpers for building dataling services. -->

<resource resdir="__system" schema="dc">

<!-- ********************* generic datalink procs -->

	<procDef type="descriptorGenerator" id="fromStandardPubDID">
		<doc>A descriptor generator for datalink that builds a 
		ProductDescriptor for PubDIDs that have been built by getStandardsPubDID
		(i.e., the path part of the IVORN is a tilda followed by the 
		products table accref).
		</doc>
		<code>
			return ProductDescriptor.fromAccref(
				"/".join(pubdid.split("/")[4:]))
		</code>
	</procDef>

	<procDef type="dataFormatter" id="trivialFormatter">
		<doc>The tivial formatter for datalink processed data -- it just
		returns descriptor.data, which will only work it it works as a
		nevow resource.

		If you do not give any dataFormatter yourself in a datalink core,
		this is what will be used.
		</doc>
		<code>
			return descriptor.data
		</code>
	</procDef>


	<!-- ********************* datalink interface to generic products -->

	<procDef type="dataFunction" id="generateProduct">
		<doc>A data function for datalink that returns a product instance.
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


	<!-- ********************* datalink interface to SDM spectra -->

	<procDef type="descriptorGenerator" id="sdm_genDesc">
		<doc>A data function for datalink returning the product row
		corresponding to a PubDID within an SSA table.

		The descriptors generated have an ssaRow attribute containing
		the original row in the SSA table.
		</doc>
		<setup>
			<par key="ssaTD" description="Full reference (like path/rdname#id)
				to the SSA table the spectrum's PubDID can be found in."/>

			<code>
				from gavo import rsc
				from gavo import rscdef
				from gavo import svcs
				from gavo.protocols import datalink

				class SSADescriptor(ProductDescriptor):
					ssaRow = None

					@classmethod
					def fromSSARow(cls, ssaRow, paramDict):
						"""returns a descriptor from a row in an ssa table and
						the params of that table.
						"""
						paramDict.update(ssaRow)
						ssaRow = paramDict
						res = cls.fromAccref(ssaRow['accref'])
						res.ssaRow = ssaRow
						return res
			
				ssaTD = base.resolveCrossId(ssaTD, rscdef.TableDef)
			</code>
		</setup>
		
		<code>

			with base.getTableConn() as conn:
				ssaTable = rsc.TableForDef(ssaTD, connection=conn)
				matchingRows = list(ssaTable.iterQuery(ssaTable.tableDef, 
					"ssa_pubdid=%(pubdid)s", {"pubdid": pubdid}))
				if not matchingRows:
					raise svcs.UnknownURI("No spectrum with pubdid %s known here"%
						pubdid)

				# the relevant metadata for all rows with the same PubDID should
				# be identical, and hence we can blindly take the first result.
				return SSADescriptor.fromSSARow(matchingRows[0],
					ssaTable.getParamDict())
		</code>
	</procDef>

	<procDef type="dataFunction" id="sdm_genData">
		<doc>A data function for datalink returning a spectral data model
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
		as the generating function within the datalink core.

		Clients can select "relative" as FLUXCALIB, which does a
		normalization to max(flux)=1 here.  Everything else is rejected
		right now.

		This probably is more an example of how to write such a thing
		then genuinely useful.
		</doc>
		<metaMaker>
			<code>
				supportedCalibs = set(["relative"])
				supportedCalibs.add(descriptor.ssaRow["ssa_fluxcalib"])

				yield MS(InputKey, name="FLUXCALIB", type="text",
					multiplicity="single", 
					description="Recalibrate the spectrum.  Right now, the only"
						" recalibration supported is max(flux)=1 ('relative').",
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
		within the datalink core.

		The cutout limits are always given in meters, regardless of
		the spectrum's actual units (as in SSAP's BAND parameter).
		</doc>

  	<metaMaker>
    	<setup>
      	<code>
        	parSTC = stc.parseQSTCS('SpectralInterval "LAMBDA_MIN" "LAMBDA_MAX"')
      	</code>
    	</setup>
    	<code>
				for ik in genLimitKeys(MS(InputKey, name="LAMBDA",
					unit="m", stc=parSTC, ucd="em.wl", 
					description="Spectral cutout interval",
					values=MS(Values, 
						min=descriptor.ssaRow["ssa_specstart"],
						max=descriptor.ssaRow["ssa_specend"]))):
					yield ik
    	</code>
  	</metaMaker>

		<dataFunction>
			<code>
				if not args.get("LAMBDA_MIN") and not args.get("LAMBDA_MAX"):
					return

				from gavo.protocols import sdm
				# table is modified in place
				sdm.mangle_cutout(
					descriptor.data.getPrimaryTable(),
					args["LAMBDA_MIN"] or -1, args["LAMBDA_MAX"] or 1e308)
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
						"text/plain": "Tab separated values",
						"text/csv": "Comma separated values",
						"application/fits": "FITS binary table"}

				if descriptor.mime not in formatsAvailable:
					formatsAvailable[descriptor.mime] = "Original format"

				yield MS(InputKey, name="FORMAT", type="text",
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

				if len(descriptor.data.getPrimaryTable().rows)==0:
					raise base.ValidationError("Spectrum is empty.", "(various)")

				return sdm.formatSDMData(descriptor.data, args["FORMAT"])
			</code>
		</dataFormatter>
	</STREAM>



	<!-- ********************* datalink interface for generic FITS 
		manipulations -->
	<procDef type="descriptorGenerator" id="fits_genDesc">
		<doc>A data function for datalink returning the a fits descriptor.

		This has, in addition to the standard stuff, a hdr attribute containing
		the primary header as pyfits structure.

		The functionality of this is in its setup, getFITSDescriptor.
		The intention is that customized DGs (e.g., fixing the header)
		can use this as an original.
		</doc>
		<setup>
			<code>
				def getFITSDescriptor(accref):
					descriptor = ProductDescriptor.fromAccref(accref)
					with open(os.path.join(base.getConfig("inputsDir"), 
							descriptor.accessPath)) as f:
						descriptor.hdr = utils.readPrimaryHeaderQuick(f)
					return descriptor
				
				from gavo.svcs import ForbiddenURI, UnknownURI
			</code>

			<par key="accrefStart" description="A start of accrefs the parent
				datalink service works of.  Procedures on all other accrefs
				will be rejected with a 403 forbidden.  You should always
				include a restriction like this when you make assumptions
				about the FITSes (e.g., what axes are available).">None</par>
		</setup>
		<code>
			try:
				accref = getAccrefFromStandardPubDID(pubdid)
				print "=================", accref
			except ValueError:
				raise UnknownURI("Not a pubDID from this site: %s"%pubdid)

			if accrefStart and not accref.startswith(accrefStart):
				raise ForbiddenURI("This datalink service not available"
					" with the pubdid '%s'"%pubdid)
			return getFITSDescriptor(accref)

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

		Note that this is neither optimal in the metadata transmitted
		nor general in the sense that any valid WCS header would be handled.  
		For your data with a known structure, you should provide much richer 
		metadata.
		</doc>
		<setup>
			<par key="stcs" description="A QSTC expression describing the
				STC structure of the parameters.  If you don't give this,
				no STC structure will be declared.">None</par>
			<code>
				from gavo.utils import fitstools

				def getSkyWCS(hdr):
					"""uses some heuristics to guess how spatial WCS might be
					in hdr.

					The function returns a pair of a pywcs.WCS instance (or
					None, if no spatial WCS was found) and a sequence of 
					the axes used.
					"""
					wcsAxes = []
					# heuristics: iterate through CTYPEn, anything that's got
					# a - is supposed to be a position (needs some refinement :-)
					for ind in range(1, hdr["NAXIS"]+1):
						if "-" in hdr.get("CTYPE%s"%ind, ""):
							wcsAxes.append(ind)

					if not wcsAxes:
						# more heuristics to be inserted here
						return None, ()

					if len(wcsAxes)!=2:
						raise base.ValidationError("This FITS has !=2"
							" spatial WCS axes.  Please contact the DaCHS authors and"
							" make them support it.", "PUBDID")

					return coords.getWCS(hdr, naxis=wcsAxes), wcsAxes

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

					for name, colInd, description, cutoutName in [
						(wcsprm.lattyp.strip(), wcsprm.lat, "The latitude coordinate",
							"WCSLAT"),
						(wcsprm.lngtyp.strip(), wcsprm.lng, "The longitude coordinate",
							"WCSLONG")]:
						if name:
							vertexCoos = footprint[:,colInd]
							for ik in genLimitKeys(MS(InputKey, name=name,
									unit="deg", stc=parSTC,
									description=description,
									ucd=None, multiplicity="single",
									values=MS(Values, min=min(vertexCoos), max=max(vertexCoos)))):
								yield ik
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

						ax = fitstools.WCSAxis.fromHeader(descriptor.hdr, fitsAxis)
						descriptor.axisNames[ax.name] = fitsAxis
						minPhys, maxPhys = ax.getLimits()

						for ik in genLimitKeys(MS(InputKey, name=ax.name,
								unit=ax.cunit, stc=parSTC,
								description="Coordinate along axis number %s"%fitsAxis,
								ucd=None, multiplicity="single",
								values=MS(Values, min=minPhys, max=maxPhys))):
							yield ik

				if stcs is None:
					parSTC = None
				else:
					parSTC = stc.parseQSTCS(stcs)
			</code>
		</setup>

		<code>
			descriptor.axisNames = {}
			descriptor.skyWCS, spatialAxes = getSkyWCS(descriptor.hdr)

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
		</doc>
		<code>
			from gavo.utils import pyfits

			descriptor.data = pyfits.open(os.path.join(
				base.getConfig("inputsDir"), descriptor.accessPath))
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

			The .data attribute must be a pyfits hduList, as generated by the
			fits_makeHDUList data function.
		</doc>
		<code>
			from gavo.utils import fitstools
			import numpy

			slices = []

			footprint  = descriptor.skyWCS.calcFootprint(descriptor.hdr)
			# limits: [minRA, maxRA], [minDec, maxDec]]
			limits = [[min(footprint[:,0]), max(footprint[:,0])],
				[min(footprint[:,1]), max(footprint[:,1])]]

			for parBase, fitsAxis in descriptor.axisNames.iteritems():
				if not isinstance(fitsAxis, int):
					if fitsAxis=="WCSLAT":
						cooLimits = limits[1]
					elif fitsAxis=="WCSLONG":
						cooLimits = limits[0]
					else:
						assert False

					if args[parBase+"_MIN"] is not None:
						cooLimits[0] = max(cooLimits[0], args[parBase+"_MIN"])
					if args[parBase+"_MAX"] is not None:
						cooLimits[1] = min(cooLimits[1], args[parBase+"_MAX"])
					
				else:
					transform = fitstools.WCSAxis.fromHeader(descriptor.hdr, fitsAxis)
					axMax = args.get(parBase+"_MAX", 100000000)
					axMin = args.get(parBase+"_MIN", -1)
					slices.append((fitsAxis, 
						transform.physToPix(axMin), transform.physToPix(axMax)))
		
			pixelFootprint = numpy.asarray(
				numpy.round(descriptor.skyWCS.wcs_sky2pix([
					(limits[0][0], limits[1][0]),
					(limits[0][1], limits[1][1])], 1)), numpy.int32)
			pixelLimits = [[min(pixelFootprint[:,0]), max(pixelFootprint[:,0])],
				[min(pixelFootprint[:,1]), max(pixelFootprint[:,1])]]
			latAxis = descriptor.skyWCS.wcs.lat+1
			longAxis = descriptor.skyWCS.wcs.lng+1
			if pixelLimits[0]!=[1, descriptor.hdr["NAXIS%d"%longAxis]]:
				slices.append([longAxis]+pixelLimits[0])
			if pixelLimits[1]!=[1, descriptor.hdr["NAXIS%d"%latAxis]]:
				slices.append([latAxis]+pixelLimits[1])

			if slices:
				descriptor.data[0] = fitstools.cutoutFITS(descriptor.data[0],
					*slices)
		</code>
	</procDef>

	<procDef type="dataFormatter" id="fits_formatHDUs">
		<doc>
			Formats pyfits HDUs into a FITS file.

			This all works in memory, so for large FITS files you'd want something
			more streamlined.
		</doc>
		<code>
			from gavo.formats import fitstable
			resultName = fitstable.writeFITSTableFile(descriptor.data)
			with open(resultName) as f:
				data = f.read()
			os.unlink(resultName)
			return "application/fits", data
		</code>
	</procDef>
</resource>
