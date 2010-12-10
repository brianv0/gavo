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
		<column name="embargo" type="date" tablehead="Embargo ends" 
			verbLevel="25" unit="Y-M-D" description=
			"Date the data will become/became public"/>
		<column name="mime" type="text" verbLevel="20"
			tablehead="Type"
			description="MIME type of the file served"
			utype="Access.Format"/>
	</STREAM>

	<table id="products" primary="accref" system="True" onDisk="True">
		<FEED source="basicColumns"/>
		<column name="accessPath" type="text" tablehead="Path to access data" 
			required="True" verbLevel="5" 
			description="Inputs-relative filesystem path to the file"/>
		<column name="sourceTable" type="text" verbLevel="10"
			tablehead="Source Table"
			description="Name of table containing metadata" required="True"/>
	</table>

	<!-- as the result definition, use this: -->
	<table original="products" id="productsResult" onDisk="False"/>

	<data id="import">
		<make table="products"/>
	</data>

	<rowmaker id="productsMaker">
 		<map dest="accref" src="prodtblAccref"/>
		<map dest="owner" src="prodtblOwner"/>
		<map dest="embargo" src="prodtblEmbargo"/>
		<map dest="accessPath" src="prodtblPath"/>
		<map dest="sourceTable" src="prodtblTable"/>
		<map dest="mime" src="prodtblMime"/>
	</rowmaker>

	<!-- material for tables mixing in products -->
	<STREAM id="tablecols">
		<FEED source="//products#basicColumns"/>
		<column name="accsize" ucd="VOX:Image_FileSize"
			tablehead="File size" description="Size of the data in bytes"
			type="integer" verbLevel="11" unit="byte" utype="Access.Size"/>
	</STREAM>

	<table id="instance">
		<!-- actual sample columns for reference (this should not be necessary,
		really) -->
		<FEED source="tablecols"/>
	</table>

	<procDef type="rowfilter" id="define">
		<doc>
			enters the values defined by the product interface into result.

			See the documentation on the product interface.
		</doc>
		<setup>
			<par key="table" description="the table this product is managed in.
				You must fill this in, and don't forget the quotes."/>
			<par late="True" key="accref" description="an access reference
				(this ususally is the input-relative path)">\inputRelativePath</par>
			<par late="True" key="owner" description="for proprietary data,
				the owner as a gavo creds-created user">None</par>
			<par late="True" key="embargo" description="for proprietary data,
				the date the file will become public">None</par>
			<par late="True" key="path" description="the inputs-relative path
				to the product file (change at your peril)">\inputRelativePath</par>
			<par late="True" key="fsize" description="the size of the input"
				>\inputSize</par>
			<par late="True" key="mime" description="MIME-type for the product"
				>'image/fits'</par>
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
			yield row
		</code>
	</procDef>

	<STREAM id="prodcolMaps">
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
								rowmaker=prodRD.getById("productsMaker")))
							# ...add some rules to ensure prodcut table cleanup,
							# and add mappings for the embedding table.
							for make in dd.makes:
								if make.table.id==substrate.id:
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
			(which is defined in __system__/products#prodcolUsertable).

			owner and embargo let you introduce access control.  Embargo is a
			date at which the product will become publicly available.  As long
			as this date is in the future, only authenticated users belonging to
			the *group* owner are allowed to access the product.

			In addition, the mixin arranges for the products to be added to the
			system table products, which is important when delivering the files.

			Tables mixing this in should be fed from grammars using the define
			rowgen.
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
		<inputTable namePath="products">
			<meta name="description">Input table for the tar making core</meta>
			<column original="accref" type="raw"/>
		</inputTable>
	</productCore>

	<service id="getTar" core="forTar">
		<meta name="title">Tar deliverer</meta>
		<inputDD>
			<contextGrammar>
				<inputKey name="pattern" type="text" description="Product pattern
					in the form tablePattern.filePatterns, where both parts
					are interpreted as SQL patterns."/>
				<rowfilter name="expandProductPattern">
					<code>
						try:
							tablepat, filepat = row["pattern"].split(".")
						except (ValueError,), ex:
							raise base.ValidationError(
								"Must be of the form table.sqlpattern", "pattern")
						prodTbl = rsc.TableForDef(self.rd.getById("products"),
							connection=base.caches.getTableConn())
						for row in prodTbl.iterQuery([protTbl.getColumnByName("accref")],
							"WHERE accref LIKE %(filepat)s AND sourceTable LIKE %(tablepat)s",
							{"filepat": filepat, "tablepat": tablepat}):
							yield row
					</code>
				</rowfilter>
			</contextGrammar>
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

	<service id="p" core="core" allowed="get, form">
		<meta name="description">The main product deliverer</meta>
	</service>
</resource>
