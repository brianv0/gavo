<!-- a collection of various helpers for building dataling services. -->

<resource resdir="__system" schema="dc">

<!-- ********************* generic datalink procs -->

	<procDef type="descriptorGenerator" id="fromStandardPubDID">
		<doc>A descriptor generator for datalink that builds a 
		ProductDescriptor for PubDIDs that have been built by getStandardsPubDID
		(i.e., the path part of the IVORN is a tilda followed by the 
		products table accref).
		</doc>
		<setup>
			<code>
				from gavo.protocols import datalink
			</code>
		</setup>
		<code>
			return datalink.ProductDescriptor.fromAccref(
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

				class SSADescriptor(datalink.ProductDescriptor):
					ssaRow = None

					@classmethod
					def fromSSARow(cls, ssaRow):
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
				return SSADescriptor.fromSSARow(matchingRows[0])
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
		<doc>A stream inserting a data function and its parameters to
		do select flux calibrations in SDM data.  This expects
		sdm_generate (or at least parameters.data as an SDM data instance)
		as the generating function within the datalink core.

		Clients can select "relative" as FLUXCALIB, which does a
		normalization to max(flux)=1 here.  Everything else is rejected
		right now.

		This probably is more an example of how to write such a thing
		then genuinely useful.
		</doc>
		<inputKey name="FLUXCALIB" type="text" 
			multiplicity="single"
			description="Recalibrate
			the spectrum.  Right now, only calibration to max(flux)=1 ('relative')
			is supported.">
			<values>
				<option>relative</option>
			</values>
		</inputKey>

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
		<doc>A stream inserting a data function and its parameters to
		do cutouts in SDM data. This expects sdm_generate (or at least
		parameters.data as an SDM data instance) as the generating function 
		within the datalink core.

		The cutout limits are always given in meters, regardless of
		the spectrum's actual units (as in SSAP's BAND parameter).
		</doc>

		<inputKey name="LAMBDA_MIN" type="real" 
			unit="m" ucd="stat.min;em.wl"
			description="Lower bound of cutout interval.  Leave empty for
				half-open intervals."/>
		<inputKey name="LAMBDA_MAX" type="real" 
			unit="m" ucd="stat.min;em.wl"
			description="Upper bound of cutout interval.  Leave empty for
				half-open intervals."/>
			
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

		<inputKey name="FORMAT" type="text"
			multiplicity="single"
			description="MIME type of the output format">
			<values default="application/x-votable+xml">
				<option title="VOTable, binary encoding"
					>application/x-votable+xml</option>
				<option title="VOTable, tabledata encoding"
					>application/x-votable+xml;encoding=tabledata</option>
				<option title="Tab separated values">text/plain</option>
				<option title="Comma separated values">text/csv</option>
				<option title="FITS binary table">application/fits</option>
			</values>
		</inputKey>

		<dataFormatter>
			<code>
				from gavo.protocols import sdm

				return sdm.formatSDMData(descriptor.data, args["FORMAT"])
			</code>
		</dataFormatter>
	</STREAM>

</resource>
