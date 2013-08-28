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
			<code>
				commonArgs = {"type": "real", "unit": "m",
					"values": MS(Values, 
						min=descriptor.ssaRow["ssa_specstart"],
						max=descriptor.ssaRow["ssa_specend"]),
					}
				yield MS(InputKey, name="LAMBDA_MIN", ucd="stat.min;em.wl",
					description="Lower bound of cutout interval.  Leave empty for"
					" half-open intervals.", **commonArgs)
				yield MS(InputKey, name="LAMBDA_MAX", ucd="stat.max;em.wl",
					description="Upper bound of cutout interval.  Leave empty for"
					" half-open intervals.", **commonArgs)
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
						"application/x-votable+xml;encoding=tabledata": 
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
		the primary header as pyfits structure, and a wcs attribute containing
		a pywcs.WCS structure for it.

		Further datalink functions should be able to deal with the wcs attribute
		being None; there's just too much that can go wrong there.
		</doc>
		<code>
			descr = ProductDescriptor.fromAccref("/".join(pubdid.split("/")[4:]))
			with open(os.path.join(base.getConfig("inputsDir"), descr.accessPath)
					) as f:
				descr.hdr = utils.readPrimaryHeaderQuick(f)
			descr.wcs = coords.getWCS(descr.hdr)
			return descr
		</code>
	</procDef>


	<procDef type="metaMaker" id="fits_makeCutoutParams">
		<doc>A metaMaker that generates parameters allowing cutouts along
		the various WCS axes in physical coordinates.
		
		Note that this is *not* optimal.  For your data with a known
		structure, you should provide much richer metadata.</doc>
		<setup>
			<code>
				def synthesizeAxisName(axDesc):
					"""returns an axis label based on a pywcs axis description.

					Note that that these are usually not unique.
					"""
					if axDesc["coordinate_type"]=="celestial":
						if axDesc.get("number")==0:
							name = "LONG"
						elif axDesc.get("number")==1: 
							name = "LAT"
						else:
							name = "COORD"%axInd
					elif axDesc["coordinate_type"]:
						name = axDesc["coordinate_type"].upper()
					else:
						name = "COO"
					return name

				from gavo.utils import fitstools
			</code>
		</setup>

		<code>
			if not descriptor.wcs:
				# no wcs, no physical cutouts
				return

			wcsprm = descriptor.wcs.wcs
			naxis = wcsprm.naxis
			axesLengths = fitstools.getAxisLengths(descriptor.hdr)
			# FIXME: pywcs might use WCSAXES, which may be different from
			# what getAxisLengths return.  Unfortunately, pywcs apparently doesn't 
			# expose the lengths of the wcs axes.  Hm.
			if len(axesLengths)!=naxis:
				raise ValidationError("FITS has WCSAXES.  This code cannot deal"
					" with it.", "PUBDID")

			footprint = wcsprm.p2s([[1]*int(naxis), axesLengths], 1)["world"]

			for axInd, axDesc in enumerate(descriptor.wcs.get_axis_types()):
				name = wcsprm.cname[axInd]
				if not name:
					name = synthesizeAxisName(axDesc)
				name = "%s_%d"%(name, axInd)
				limits = (footprint[0][axInd], footprint[1][axInd])

				yield MS(InputKey, name=name,
					unit=descriptor.wcs.wcs.cunit[axInd],
					ucd=None,
					values=MS(Values, min=min(limits), max=max(limits)))
		</code>
	</procDef>

</resource>
