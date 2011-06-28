<resource schema="tap_schema" resdir="__system">
	<meta name="description">Data and services dealing with the
		Table Access Protocol TAP.</meta>
	<meta name="creationDate">2009-12-01T10:00:00</meta>
	<meta name="subject">Virtual observatory</meta>
	<meta name="subject">Catalogs</meta>


	<property name="TAP_VERSION">1.0</property>

	<meta name="_longdoc" format="rst"><![CDATA[
	You will usually want to use some sort of client to query TAP services;
	the VODesktop_ suite contains one, the `GAVO VOTable library`_ another,
	and there's the `TAP shell`_.
	You can, however, use our service in an XML-enabled browser (see below under
	`Overview <#overview>`_), too: click on "New job..." in the job list,
	enter your query, click "Set query", then "Execute query".  Reload the
	page you are redirected to now and then to see when your job is finished,
	then retrieve the result.

	For use within a browser, the local `ADQL form`_ may be more convenient,
	though.

	Also see the `table metadata`_ of the tables exposed here.

	.. _VODesktop: http://www.astrogrid.org/wiki/Install/Downloads
	.. _GAVO VOTable library: http://vo.ari.uni-heidelberg.de/soft/subpkgs
	.. _TAP shell: http://vo.ari.uni-heidelberg.de/soft/tapsh
	.. _table metadata: /__system__/tap/run/tableMetadata
	.. _ADQL form: /adql


	Issues
	======

	For information on our ADQL implementation, see the
	\RSTservicelink{__system__/adql/query/info}{ADQL service info}.

	While columns with xtype adql:POINT are correctly ingested into the
	database, adql:REGION columns are left alone (i.e., they are
	strings in the database).  The reason for this behaviour is that
	in order to infer a column type, one would have to inspect the
	entire table up front.

	If multiple output columns in a query would end up having the same name,
	in the output VOTable they are disambiguated by appending underscores.
	This is in violation of the specification, but since fixing it would
	require rather intrusive changes into our software and it is not
	clear why one should want to use names when they are not unique to begin
	with, this will probably not be fixed.]]>
	</meta>

	<table id="schemas" onDisk="True" system="True"
			forceUnique="True" dupePolicy="drop" primary="schema_name"
			readRoles="defaults,untrusted">
		<meta name="description">Schmemas containing tables available for ADQL
			querying.</meta>
	<!-- since schemata may be shared between RDs, nothing will ever
	     get deleted from here -->
		<column name="schema_name" type="text" 
			description="Fully qualified schema name"/>
		<column name="description" type="text"
			description="Brief description of the schema"/>
		<column name="utype" type="text"
			description="utype if schema corresponds to a data model"/>
	</table>
	
	<table id="tables" onDisk="True" system="True" primary="table_name"
			readRoles="defaults,untrusted">
		<meta name="description">Tables available for ADQL querying.</meta>
		<column name="schema_name" type="text" 
			description="Fully qualified schema name"/>
		<column name="table_name" type="text" 
			description="Fully qualified table name"/>
		<column name="table_type" type="text" 
			description="One of: table, view"/>
		<column name="description" type="text" 
			description="Brief description of the table"/>
		<column name="utype" type="text" 
			description="utype if the table corresponds to a data model"/>
		<column name="sourceRD" type="text" description="Id of the originating rd"/>
	</table>

	<table id="columns" onDisk="True" system="True"
			primary="table_name,column_name" readRoles="defaults,untrusted">
		<meta name="description">Columns in tables available for ADQL querying.
		</meta>
		<column name="table_name" type="text" 
			description="Fully qualified table name"/>
		<column name="column_name" type="text" description="Column name"/>
		<column name="description" type="text" 
			description="Brief description of column"/>
		<column name="unit" type="text" 
			description="Unit in VO standard format"/>
		<column name="ucd" type="text" 
			description="UCD of column if any"/>
		<column name="utype" type="text" 
			description="Utype of column if any"/>
		<column name="datatype" type="text" 
			description="ADQL datatype"/>
		<column name="size" type="integer" 
			description="Length of variable length datatypes"/>
		<column name="principal" type="text" 
			description="Is column principal?"/>
		<column name="indexed" type="integer" 
			description="Is there an index on this column?"/>
		<column name="std" type="text" 
			description="Is this a standard column?"/>
		<column name="sourceRD" type="text" 
			description="Id of the originating rd"/>
	</table>

	<table id="keys" onDisk="True" system="True"
			primary="key_id" readRoles="defaults,untrusted">
		<meta name="description">Foreign key relationships between tables 
			available for ADQL querying.
		</meta>
		<column name="key_id" type="text" 
			description="Unique key identifier"/>
		<column name="from_table" type="text" 
			description="Fully qualified table name"/>
		<column name="target_table" type="text" 
			description="Fully qualified table name"/>
		<column name="description" type="text" 
			description="Description of this key"/>
		<column name="utype" type="text" 
			description="Utype of this key"/>
		<column name="sourceRD" type="text" description="Id of the originating rd"/>
	</table>

	<table id="key_columns" onDisk="True" system="True"
			readRoles="defaults,untrusted">
		<meta name="description">Columns participating in foreign key 
			relationships between tables available for ADQL querying.
		</meta>
		<column name="key_id" type="text" 
			description="Key identifier from TAP_SCHEMA.keys"/>
		<column name="from_column" type="text" 
			description="Key column name in the from table"/>
		<column name="target_column" type="text" 
			description="Key column in the target table"/>
		<column name="sourceRD" type="text" description="Id of the originating rd"/>
	</table>

	<data id="importTablesFromRD" auto="False">
		<embeddedGrammar>
			<iterator>
				<code>
					rd = self.sourceToken
					# the moribund property is set by external code if the
					# rd is to be removed from TAP_SCHEMA.  The removal
					# is already done by the the newSource script in make
					# below, thus we only need to do nothing here.
					if rd.getProperty("moribund", False):
						return
					for table in rd.tables:
						if not table.adql:
							continue
						if table.viewStatement:
							tableType = "view"
						else:
							tableType = "table"
						yield {
							"schema_name": rd.schema,
							"schema_description": None,
							"schema_utype": None,
							"table_name": table.getQName(),
							"table_description": base.getMetaText(table, "description",
								propagate=True),
							"table_type": tableType,
							"table_utype": None,
							"sourceRD": rd.sourceId,
						}
				</code>
			</iterator>
		</embeddedGrammar>

		<rowmaker id="make_schemas">
			<simplemaps>
				schema_name: schema_name,
				description: schema_description, 
				utype: schema_utype
			</simplemaps>
		</rowmaker>

		<rowmaker id="make_tables" idmaps="*">
			<simplemaps>
				utype: table_utype,
				description: table_description
			</simplemaps>
		</rowmaker>


		<make table="schemas" rowmaker="make_schemas"/>
		<make table="tables" rowmaker="make_tables">
			<script type="newSource" lang="python" id="removeStale"
					notify="False" name="delete stale TAP_SCHEMA entries">
				table.deleteMatching("sourceRD=%(sourceRD)s",
					{"sourceRD": sourceToken.sourceId})
			</script>
		</make>
	</data>

	<data id="importColumnsFromRD" auto="False">
		<embeddedGrammar>
			<iterator>
				<setup>
					<code>
						from gavo.base.typesystems import sqltypeToADQL
					</code>
				</setup>
				<code>
					rd = self.sourceToken
					if rd.getProperty("moribund", False):
						return
					for table in rd.tables:
						if not table.adql:
							continue
						for col in table:
							indexed = 0
							if col.isIndexed():
								indexed = 1
							type, size = sqltypeToADQL(col.type)
							yield {
								"table_name": table.getQName().lower(),
								"column_name": col.name.lower(),
								"description": col.description,
								"unit": col.unit,
								"ucd": col.ucd,
								"utype": col.utype,
								"datatype": type,
								"size": size,
								"principal": col.verbLevel&lt;=10,
								"indexed": indexed,
								"std": parseInt(col.getProperty("std", "0")),
								"sourceRD": rd.sourceId,
							}
				</code>
			</iterator>
		</embeddedGrammar>
		<make table="columns">
			<script original="removeStale"/>
		</make>
	</data>

	<data id="importFkeysFromRD" auto="False">
		<embeddedGrammar>
			<iterator>
				<code>
					rd = self.sourceToken
					if rd.getProperty("moribund", False):
						return
					for table in rd.tables:
						if not table.adql:
							continue
						for fkey in table.foreignKeys:
							fkeyId = rd.sourceId+utils.intToFunnyWord(id(fkey))
							yield {
								"key_id": fkeyId.lower(),
								"from_table": table.getQName().lower(),
								"target_table": fkey.table.lower(),
								"description": None,
								"utype": None,
								"sourceRD": rd.sourceId,
								"dest": "keys",
							}
							for src, dst in zip(fkey.source, fkey.dest):
								yield {
									"key_id": fkeyId.lower(),
									"from_column": src.lower(),
									"target_column": dst.lower(),
									"sourceRD": rd.sourceId,
									"dest": "cols",
								}
				</code>
			</iterator>
		</embeddedGrammar>

		<!-- XXX TODO: We should let the DB do our work here by properly
			defining the fkey relationship between keys and key_columns -->

		<rowmaker id="build_keys" idmaps="*">
			<ignoreOn><not><keyIs key="dest" value="keys"/></not></ignoreOn>
		</rowmaker>

		<rowmaker id="build_key_columns" idmaps="*">
			<ignoreOn><not><keyIs key="dest" value="cols"/></not></ignoreOn>
		</rowmaker>

		<make table="keys" rowmaker="build_keys">
			<script original="removeStale"/>
		</make>
		<make table="key_columns" rowmaker="build_key_columns">
			<script original="removeStale"/>
		</make>
	</data>

	<data id="createSchema">
		<!-- run this to create the TAP schema initially, or to recreate it
		later.  Use gavo pub -ma to re-insert info on the currently published
		tables after recreation. -->
		<make table="schemas"/>
		<make table="tables"/>
		<make table="columns"/>
		<make table="keys"/>
		<make table="key_columns">
			<!-- this script is for bootstrapping.  The tables have no
			  adql attribute since tap_schema isn't there when the tables
				are imported.  Thus, I need to fiddle them in when they are
				there; this happens here" -->
			<script type="postCreation" lang="python" 
					name="Add TAP_SCHEMA to TAP_SCHEMA">
				from gavo.protocols import tap
				rd = table.tableDef.rd
				for id in "schemas tables columns keys key_columns".split():
					rd.getById(id).adql = True
				tap.publishToTAP(rd, table.connection)
			</script>
		</make>
	</data>

	<nullCore id="null"/>

	<service id="run" core="null" allowed="tap">
		<meta name="shortName">GAVO DC TAP</meta>
		<meta name="title">GAVO Data Center TAP service</meta>
		<meta name="supportsModel">ObsCore 1.0</meta>
		<meta name="supportsModel.ivoId">ivo://ivoa.net/std/ObsCore-1.0</meta>

		<meta name="description">The GAVO data center's TAP end point.  The
			Table Access Protocol (TAP) lets you execute queries against our
			database tables, inspect various metadata, and upload your own
			data.  It is thus the VO's premier way to access public data
			holdings.

			Tables exposed through this endpoint include: \tablesForTAP.
			</meta>
		<publish render="tap" sets="ivo_managed,local"/>
	</service>
</resource>
