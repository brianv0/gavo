<?xml version="1.0" encoding="utf-8"?>

<!-- definitions needed for the product mixin and the products delivery
machinery -->

<resource resdir="__system" schema="dc">

	<STREAM id="basicColumns">
		<column name="accref" type="text" tablehead="Product key"
			description="Access key for the data"
			verbLevel="1" displayHint="type=product"
			utype="Access.Reference"/>
		<column name="owner" type="text" tablehead="Owner"
			verbLevel="25" description="Owner of the data"/>
		<column name="embargo" type="date" 
			unit="a"
			tablehead="Embargo ends" 
			verbLevel="25" 
			description="Date the data will become/became public"
			displayHint="type=humanDate"/>
		<column name="mime" type="text" verbLevel="20"
			tablehead="Type"
			description="MIME type of the file served"
			utype="Access.Format"/>
	</STREAM>

	<table id="products" primary="accref" system="True" onDisk="True"
			dupePolicy="overwrite" forceUnique="True">
		<meta name="description">
			The products table keeps information on "products", i.e. datasets
			delivered to the users.  
			
			It is normally fed through the products#define rowfilter and a mixin
			like products#table (or other mixins using it like siap#pgs or 
			ssap#mixc).

			/getproducts inspects this table before handing out data to enforce
			embargoes and similar restrictions, and this is also where it figures
			out where to go for previews.
		</meta>
		<index columns="sourceTable"/>

		<!-- Warning: column names and table structure are reflected at least
		in protocols.products, so be careful if you change things here. -->
		<FEED source="basicColumns"/>
		<column name="accessPath" type="text" tablehead="Path to access data" 
			required="True" verbLevel="5" 
			description="Inputs-relative filesystem path to the file"/>
		<column name="sourceTable" type="text" verbLevel="10"
			tablehead="Source Table"
			description="Name of table containing metadata" required="True"/>
		<column name="preview" type="text"
			description="Location of a preview; this can be NULL if no preview
				is available, 'AUTO' if DaCHS is supposed to try and make its
				own previews based on MIME guessing, or a file name, or an URL."
			verbLevel="40"/>
		<column name="datalink" type="text"
			description="A fully qualified URL of a datalink document for
				this dataset.  This is to allow the global datalink service 
				(sitting on the ~ resource and used by obscore) to
				forward datalink requests globally."
			verbLevel="40"/>
		<column name="preview_mime" type="text"
			description="MIME type of a preview (if any)"
			verbLevel="40"/>
	</table>

	<!-- as the result definition, use this: -->
	<table original="products" id="productsResult" onDisk="False"/>

	<data id="import">
		<make table="products"/>
	</data>

	<rowmaker id="productsMaker">
		<!-- the row maker for the products table itself -->
		<map dest="accref" src="prodtblAccref"/>
		<map dest="owner" src="prodtblOwner"/>
		<map dest="embargo" src="prodtblEmbargo"/>
		<map dest="accessPath" src="prodtblPath"/>
		<map dest="sourceTable" src="prodtblTable"/>
		<map dest="mime" src="prodtblMime"/>
		<map dest="preview" src="prodtblPreview"/>
		<map dest="preview_mime" src="prodtblPreviewMime"/>
		<map dest="datalink" src="prodtblDatalink"/>
	</rowmaker>

	<!-- material for tables mixing in products -->
	<STREAM id="tablecols">
		<FEED source="//products#basicColumns"/>
		<column name="accsize" ucd="VOX:Image_FileSize"
			tablehead="File size" description="Size of the data in bytes"
			type="bigint" verbLevel="11" unit="byte" utype="Access.Size">
			<values nullLiteral="-1"/>
		</column>
	</STREAM>

	<table id="instance">
		<!-- actual sample columns for reference (this should not be necessary,
		really) -->
		<FEED source="tablecols"/>
	</table>

	<STREAM id="mapUserItems">
		<doc>
			Standard mappings copying the standard //products#define rowdict items
			to their target columns in tables containing products.

			You only need this if you do not have "standard" products
			(as for siap, ssap, etc.)
		</doc>
		<map dest="accref" src="prodtblAccref"/>
		<map dest="accsize" src="prodtblFsize"/>
		<map dest="owner" src="prodtblOwner"/>
		<map dest="embargo" src="prodtblEmbargo"/>
		<map dest="mime" src="prodtblMime"/>
	</STREAM>

	<procDef type="rowfilter" id="define">
		<doc>
			Enters the values defined by the product interface into 
			a grammar's result.

			See the documentation on the //products#table mixin.  In short:
			you will always  have to touch table (to the name of the
			table this row is managed in).  
			
			Everything else is optional: You may want to set preview
			and preview_mime if DaCHS can't do previews of your stuff 
			automatically.  datalink is there if you have  a datalink
			thing.  What's left is for special situations.

			This will create the keys prodblAccref, prodtblOwner, prodtblEmbargo,
			prodtblPath, prodtblFsize, prodtblTable, prodtblMime, prodtblPreview,
			prodtbleMime, and prodtblDatalink keys in rawdict -- you can
			refer to them in the usual @foo way, which is sometimes useful
			even outside products processing proper (in particular for
			prodtblAccref).
		</doc>
		<setup>
			<par key="table" description="the table this product is managed in.
				You must fill this in, and don't forget the quotes."/>
			<par late="True" key="accref" description="an access reference
				(this ususally is the input-relative path; only file names
				well-behaved in URLs are accepted here by default for easier
				operation with ObsTAP)"
				>\inputRelativePath{False}</par>
			<par late="True" key="owner" description="for proprietary data,
				the owner as a gavo creds-created user">None</par>
			<par late="True" key="embargo" description="for proprietary data,
				the date the file will become public">None</par>
			<par late="True" key="path" description="the inputs-relative path
				to the product file (change at your peril)"
				>\inputRelativePath{True}</par>
			<par late="True" key="fsize" description="the size of the input in bytes"
				>\inputSize</par>
			<par late="True" key="mime" description="MIME-type for the product"
				>'image/fits'</par>
			<par late="True" key="preview" description="file path to a preview,
				dcc://rd.id/svcid id of a preview-enabled datalink service, None
				to disable previews, or 'AUTO' to make DaCHS guess."
				>'AUTO'</par>
			<par late="True" key="preview_mime" 
				description="MIME-type for the preview (if there is one).">None</par>
			<par key="datalink" description="id of a datalink service that
				understands this file's pubDID." late="True">None</par>
		</setup>
		<code>
			newVars = {}
			if path is None:
				path = accref
			row["prodtblAccref"] = accref
			row["prodtblOwner"] = owner
			row["prodtblEmbargo"] = embargo
			row["prodtblPath"] = path
			row["prodtblFsize"] = fsize
			row["prodtblTable"] = table
			row["prodtblMime"] = mime
			row["prodtblPreview"] = preview
			row["prodtblPreviewMime"] = preview_mime
			row["prodtblDatalink"] = datalink
			yield row
		</code>
	</procDef>

	<STREAM id="prodcolMaps">
		<!-- this was an idiotic thing to do.  Can I get rid of it again? -->
		<doc>
			Fragment for mapping the result of the define proc into a user table;
			this is replayed into every rowmaker making a table mixing in
			products.
		</doc>
		<map dest="accref" src="prodtblAccref"/>
		<map dest="owner" src="prodtblOwner"/>
		<map dest="embargo" src="prodtblEmbargo"/>
		<map dest="accsize" src="prodtblFsize"/>
		<map dest="mime" src="prodtblMime"/>
	</STREAM>

	<STREAM id="productsMake">
		<make table="//products#products" rowmaker="//products#productsMaker"/>
	</STREAM>

	<STREAM id="hostTableMakerItems">
		<doc>
			These items are mixed into every make bulding a table mixing
			in products.
		</doc>
		<script type="postCreation" lang="SQL" name="product cleanup"
				notify="False">
			CREATE OR REPLACE RULE cleanupProducts AS ON DELETE TO \\curtable 
			DO ALSO
			DELETE FROM dc.products WHERE accref=OLD.accref
		</script>
		<script type="beforeDrop" lang="SQL" name="clean product table"
				notify="False">
			DELETE FROM dc.products WHERE sourceTable='\\curtable'
		</script>
	</STREAM>

	<STREAM id="hackProductsData">
		<doc>
			This defines a processLate proc that hacks data instances
			building tables with products such that the products table
			is fed and the products instance columns are assigned to.
		</doc>
		<!-- This sucks.  We want a mechanism that lets us
			deposit events within the table definition; strutures referring
			to them could then replay them -->
		<processLate>
			<setup>
				<code>
					from gavo import rscdef
				</code>
			</setup>
			<code><![CDATA[
				if not substrate.onDisk:
					raise base.StructureError("Tables mixing in product must be"
						" onDisk, but %s is not"%substrate.id)

				# Now locate all DDs we are referenced in and...
				prodRD = base.caches.getRD("//products")
				for dd in substrate.rd.iterDDs():
					for td in dd:
						if td.id==substrate.id:
							# ...feed instructions to make the row table to it and...
							dd._makes.feedObject(dd, rscdef.Make(dd, 
								table=prodRD.getTableDefById("products"),
								rowmaker=prodRD.getById("productsMaker"),
								role="products"))

							# ...add some rules to ensure prodcut table cleanup,
							# and add mappings for the embedding table.
							for make in dd.makes:
								if make.table.id==substrate.id:
									# it was stupid to hack the host rowmaker from the mixin.
									# I need some exit strategy here.
									# Meanwhile: we're suppressing the hack if it'd fail
									# anyway.
									if "owner" in make.table.columns.nameIndex:
										base.feedTo(make.rowmaker,
											prodRD.getById("prodcolMaps").getEventSource(), context,
											True)

									base.feedTo(make,
										prodRD.getById("hostTableMakerItems").getEventSource(), 
										context, True)
			]]></code>
		</processLate>
	</STREAM>

	<mixinDef id="table">
		<doc>
			A mixin for tables containing "products".

			A "product" here is some kind of binary, typically a FITS file.
			The table receives the columns accref, accsize, owner, and embargo
			(which is defined in //products#prodcolUsertable).

			By default, the accref is the path to the file relative to the inputs
			directory; this is also what /getproduct expects for local products.
			You can of course enter URLs to other places.
			
			For local files, you are strongly encouraged to keep the accref URL- and
			shell-clean, the most important reason being your users' sanity. 
			Another is that obscore in the current implementation does no 
			URL escaping for local files.  So, just don't use characters like
			like +, the ampersand, apostrophes and so on; the default
			accref parser will reject those anyway.  Actually, try
			making do with alphanumerics, the underscore, the dash, and the dot,
			ok?

			owner and embargo let you introduce access control.  Embargo is a
			date at which the product will become publicly available.  As long
			as this date is in the future, only authenticated users belonging to
			the *group* owner are allowed to access the product.

			In addition, the mixin arranges for the products to be added to the
			system table products, which is important when delivering the files.

			Tables mixing this in should be fed from grammars using the 
			//products#define row filter.

		</doc>
		
		<FEED source="//products#hackProductsData"/>
		<events>
			<FEED source="//products#tablecols"/>
		</events>

	</mixinDef>

	<productCore id="core" queriedTable="products">
		<!-- core used for the product delivery service -->
		<condDesc>
			<inputKey original="accref" id="coreKey" type="raw"/>
		</condDesc>

		<outputTable id="pCoreOutput">
			<column name="source" type="raw"
				tablehead="Access info" verbLevel="1"/>
		</outputTable>
	</productCore>

	<productCore id="forTar" original="core" limit="10000">
		<inputTable namePath="products" id="forTarIn">
			<meta name="description">Input table for the tar making core</meta>
			<!-- these are expected to be FatProductKeys or plain strings -->
			<column original="accref" type="raw"/>
		</inputTable>
	</productCore>

	<service id="getTar" core="forTar">
		<!-- a standalone service that delivers selectable tars.
		-->
		<meta name="title">Tar deliverer</meta>
		<inputDD>
			<contextGrammar rowKey="pattern">
				<inputKey name="pattern" type="text" description="Product pattern
					in the form tablePattern#filePatterns, where both parts
					are interpreted as SQL patterns." required="True"/>
				<rowfilter name="expandProductPattern">
					<setup>
						<code>
							from gavo import rsc
							prodTD = base.caches.getRD("//products").getById("products")
						</code>
					</setup>
					<code>
						try:
							tablepat, filepat = row["pattern"].split("#")
						except (ValueError,), ex:
							raise base.ValidationError(
								"Must be of the form table.sqlpattern", "pattern")
						prodTbl = rsc.TableForDef(prodTD)
						for row in prodTbl.iterQuery(
								[prodTbl.tableDef.getColumnByName("accref")],
								"accref LIKE %(filepat)s AND sourceTable LIKE %(tablepat)s",
								{"filepat": filepat, "tablepat": tablepat}):
							yield row
						prodTbl.close()
					</code>
				</rowfilter>
			</contextGrammar>
			<make table="forTarIn"/>
		</inputDD>
	</service>

	<table id="parsedKeys">
		<meta name="description">Used internally by the product core.</meta>
		<column original="products.accref"/>
		<column name="ra"/>
		<column name="dec"/>
		<column name="sra"/>
		<column name="sdec"/>
	</table>

	<service id="dl" allowed="dlmeta">
		<meta name="description">A simple datalink service for everything
		that's in DaCHS' product table.  This only exposes the dataset
		itself and its preview, if existing.</meta>
		<datalinkCore>
			<!-- the built-in links are good enough for us -->
		</datalinkCore>
	</service>

	<service id="p" core="core" allowed="get,form">
		<!-- this service is the one mentioned in the standard PubDIDs that
			we produce.  It must be published once you put out such PubDIDs,
			as all IVORIs must resolve in the registry. -->

		<meta name="identifier">ivo://\getConfig{ivoa}{authority}/~</meta>
		<meta name="creationDate">\metaString{authority.creationDate}</meta>
		<meta name="shortName">\metaString{authority.shortName} DL</meta>
		<meta name="subject">Data retrieval</meta>
		<meta name="title"
			>\getConfig{web}{sitename} Dataset Delivery</meta>
		<meta name="description">
			This service delivers (most of) the datasets held at
			\getConfig{web}{sitename}.  In addition to the default (nonstandard) way
			of just appending accrefs to the get access URL, there is also a very
			simple datalink service here that, for each dataset, essentially just
			gives the dataset itself and possibly a preview.  More advanced datalink
			services might be available.

			Some datasets may be embargoed, in which case the access yields
			a 403.  Credentials for individual files may be obtained by contacting
			the site operators.
		</meta>
		<publish render="get" sets="ivo_managed">
			<meta name="accessURL">\getConfig{web}{serverURL}/getproduct</meta>
			<meta name="urlUse">base</meta>
		</publish>
		<publish render="dlmeta" sets="ivo_managed" service="dl"/>
	</service>
</resource>
