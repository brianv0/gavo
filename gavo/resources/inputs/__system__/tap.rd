<resource schema="tap_schema" resdir="__system">
	<meta name="creationDate">2009-12-01T10:00:00</meta>
	<meta name="subject">Virtual observatory</meta>
	<meta name="subject">Catalogs</meta>
	<meta name="subject">ADQL</meta>

	<meta name="description">
		\getConfig{web}{sitename}'s Table Access Protocol
		(TAP) service with table metadata.
	</meta>

	<property name="TAP_VERSION">1.0</property>



<!--**************************** the TAP schema *********************-->

	<table id="schemas" onDisk="True" system="True"
			forceUnique="True" dupePolicy="drop" primary="schema_name"
			readProfiles="defaults,untrustedquery" adql="True">
		<meta name="description">Schemas containing tables available for ADQL
			querying.</meta>
	<!-- since schemata may be shared between RDs, nothing will ever
	     get deleted from here -->
		<column name="schema_name" type="text" 
			description="Fully qualified schema name">
			<property name="std">1</property>
		</column>
		<column name="description" type="text"
			description="Brief description of the schema">
			<property name="std">1</property>
		</column>
		<column name="utype" type="text"
			description="utype if schema corresponds to a data model">
			<property name="std">1</property>
		</column>
	</table>
	
	<table id="tables" onDisk="True" system="True" primary="table_name"
			readProfiles="defaults,untrustedquery" adql="True">
		<meta name="description">Tables available for ADQL querying.</meta>
		<column name="schema_name" type="text" 
			tablehead="Schema"
			description="Fully qualified schema name">
			<property name="std">1</property>
		</column>
		<column name="table_name" type="text" 
			tablehead="Table"
			description="Fully qualified table name">
			<property name="std">1</property>
		</column>
		<column name="table_type" type="text" 
			tablehead="Type"
			description="One of: table, view">
			<property name="std">1</property>
		</column>
		<column name="description" type="text" 
			description="Brief description of the table">
			<property name="std">1</property>
		</column>
		<column name="utype" type="text" 
			description="utype if the table corresponds to a data model">
			<property name="std">1</property>
		</column>
		<column name="sourceRD" type="text" 
			description="Id of the originating rd (local information)"/>
	</table>

	<table id="columns" onDisk="True" system="True"
			primary="table_name,column_name" readProfiles="defaults,untrustedquery"
			adql="True">
		<meta name="description">Columns in tables available for ADQL querying.
		</meta>
		<foreignKey source="table_name" inTable="tables"/>

		<column name="table_name" type="text" 
			tablehead="Table"
			description="Fully qualified table name">
			<property name="std">1</property>
		</column>
		<column name="column_name" type="text" 
			tablehead="Name"
			description="Column name">
			<property name="std">1</property>
		</column>
		<column name="description" type="unicode" 
			description="Brief description of column">
			<property name="std">1</property>
		</column>
		<column name="unit" type="text" 
			description="Unit in VO standard format">
			<property name="std">1</property>
		</column>
		<column name="ucd" type="text" 
			tablehead="UCD"
			description="UCD of column if any">
			<property name="std">1</property>
		</column>
		<column name="utype" type="text" 
			description="Utype of column if any">
			<property name="std">1</property>
		</column>
		<column name="datatype" type="text" 
			tablehead="Type"
			description="ADQL datatype">
			<property name="std">1</property>
		</column>
		<column name="quoted/size" type="integer" 
				description="Length of variable length datatypes">
			<values nullLiteral="-1"/>
			<property name="std">1</property>
		</column>
		<column name="principal" type="integer" required="True"
			tablehead="Princ?"
			description="Is column principal?">
			<property name="std">1</property>
		</column>
		<column name="indexed" type="integer" required="True"
			tablehead="Indexed?"
			description="Is there an index on this column?">
			<property name="std">1</property>
		</column>
		<column name="std" type="integer" required="True"
			tablehead="Std?"
			description="Is this a standard column?">
			<property name="std">1</property>
		</column>
		<column name="sourceRD" type="text" 
			description="Id of the originating rd (local information)"/>
		<column name="column_index" type="smallint"
			tablehead="Ind."
			description="1-based index of the column in database order.">
			<property name="std">1</property>
			<values nullLiteral="-1"/>
		</column>
	</table>

	<table id="keys" onDisk="True" system="True"
			primary="key_id" readProfiles="defaults,untrustedquery" adql="True">
		<meta name="description">Foreign key relationships between tables 
			available for ADQL querying.
		</meta>
		<column name="key_id" type="text"
			tablehead="Id"
			description="Unique key identifier">
			<property name="std">1</property>
		</column>
		<column name="from_table" type="text" 
			tablehead="From table..."
			description="Fully qualified table name">
			<property name="std">1</property>
		</column>
		<column name="target_table" type="text" 
			tablehead="To table..."
			description="Fully qualified table name">
			<property name="std">1</property>
		</column>
		<column name="description" type="text" 
			description="Description of this key">
			<property name="std">1</property>
		</column>
		<column name="utype" type="text" 
			description="Utype of this key">
			<property name="std">1</property>
		</column>
		<column name="sourceRD" type="text" 
			description="Id of the originating rd (local information)"/>
	</table>

	<table id="key_columns" onDisk="True" system="True"
			readProfiles="defaults,untrustedquery" adql="True">
		<meta name="description">Columns participating in foreign key 
			relationships between tables available for ADQL querying.
		</meta>
		<column name="key_id" type="text" 
			tablehead="Id"
			description="Key identifier from TAP_SCHEMA.keys">
			<property name="std">1</property>
		</column>
		<column name="from_column" type="text" 
			tablehead="Src. Column"
			description="Key column name in the from table">
			<property name="std">1</property>
		</column>
		<column name="target_column" type="text" 
			tablehead="Tgt. Column"
			description="Key column in the target table">
			<property name="std">1</property>
		</column>
		<column name="sourceRD" type="text" 
			description="Id of the originating rd (local information)"/>
	</table>

	<table id="groups" onDisk="True" system="True"
		readProfiles="defaults,untrustedquery" adql="True">
		<meta name="description">Columns that are part of groups
			within tables available for ADQL querying.
		</meta>
		<foreignKey source="table_name" inTable="tables"/>
		<!-- this is slightly denormalized, but normalizing it by introducing
		two new tables IMHO isn't worth it at all -->
		<column original="columns.table_name"/>
		<column original="columns.column_name" 
			description="Name of a column belonging to the group"/>
		<column original="columns.utype" name="column_utype"
			description="utype the column withing the group"/>
		<column name="group_name" type="text"
			description="Name of the group"/>
		<column name="group_utype" type="text"
			description="utype of the group"/>
		<column name="sourceRD" type="text" 
			description="Id of the originating rd (local information)"/>
	</table>

	<table id="supportedmodels" onDisk="True" primary="dmivorn"
			forceUnique="True" dupePolicy="overwrite" system="True">
		<meta name="description">
			Standard data models supported by this service.

			This is a non-standard tap_schema table used by DaCHS in the creation
			of registry records.  It is manipulated through gavo imp on tables
			with supportsModel and supportsModelURI properties.
		</meta>
		<column original="tables.sourceRD"/>
		<column name="dmname" type="text"
			description="Human-readable name of the data model"/>
		<column name="dmivorn" type="text"
			description="IVOID of the data model (sorry for the legacy name)."/>
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
							"table_name": table.getQName().lower(),
							"table_description": base.getMetaText(table, "description",
								propagate=True),
							"table_type": tableType,
							"table_utype": base.getMetaText(table, "utype",
								propagate=False),
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

		<rowmaker id="make_models" idmaps="*">
			<ignoreOn><keyNull key="dmivorn"/></ignoreOn>
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

	<data id="importDMsFromRD" auto="False">
		<embeddedGrammar>
			<iterator>
				<code>
					rd = self.sourceToken
					# see importTablesFromRD
					if rd.getProperty("moribund", False):
						return
					for table in rd.tables:
						if not table.adql:
							continue
						yield {
							"sourceRD": rd.sourceId,
							"table_name": table.getQName().lower(),
							"dmname": table.getProperty("supportsModel", None),
							"dmivorn": table.getProperty("supportsModelURI", None),
						}
				</code>
			</iterator>
			<rowfilter>
				<code>
				if @dmname:
					for name, uri in (
							zip(@dmname.split(","), @dmivorn.split())):
						yield {
							"sourceRD": @sourceRD, 
							"dmname": name.strip(), 
							"dmivorn": uri}
				</code>
			</rowfilter>
		</embeddedGrammar>
		<make table="supportedmodels"/>
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
						for index, col in enumerate(table):
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
								"column_index": index+1,
							}
				</code>
			</iterator>
		</embeddedGrammar>
		<make table="columns">
			<script original="removeStale"/>
		</make>
	</data>

	<data id="importGroupsFromRD" auto="False">
		<embeddedGrammar>
			<iterator>
				<code>
					rd = self.sourceToken
					if rd.getProperty("moribund", False):
						return
					for table in rd.tables:
						if not table.adql:
							continue
						for group in table.groups:
							for colRef in group.columnRefs:
								yield {
									"table_name": table.getQName().lower(),
									"column_name": colRef.resolve(table).name.lower(),
									"column_utype": colRef.utype,
									"group_name": group.name,
									"group_utype": group.utype,
									"sourceRD": rd.sourceId,
								}
				</code>
			</iterator>
		</embeddedGrammar>
		<make table="groups"/>
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
							if not fkey.isADQLKey:
								continue

							fkeyId = rd.sourceId+utils.intToFunnyWord(id(fkey))
							yield {
								"key_id": fkeyId.lower(),
								"from_table": table.getQName().lower(),
								"target_table": fkey.inTable.getQName().lower(),
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
		<make table="groups"/>
		<make table="supportedmodels"/>
		<make table="key_columns">
			<!-- this script is for bootstrapping.  Since TAP_SCHEMA isn't
			finished when the tables are created, they cannot be added
			to them.  There's special code to let tap.py ignore them
			in that situation, and this code here adds them when TAP_SCHEMA
			is done.
			-->
			<script type="postCreation" lang="python" 
					name="Add TAP_SCHEMA to TAP_SCHEMA">
				from gavo.protocols import tap
				rd = table.tableDef.rd
				for id in "schemas tables columns keys key_columns groups".split():
					rd.getById(id).adql = True
				tap.publishToTAP(rd, table.connection)
			</script>
		</make>
	</data>


<!--********************* TAP UWS job table ******************-->

<table id="tapjobs" system="True">
	<meta name="description">
		A non-standard (and not tap-accessible) table used for managing
		asynchronous TAP jobs.  It is manipulated through TAP job creation
		and destruction internally.  Under very special circumstances, operators
		can use the gavo admin cleantap command to purge jobs from this table.

		Note that such jobs have corresponding directories in $STATEDIR/uwsjobs,
		which will be orphaned if this table is manipulated through SQL.
	</meta>
	<FEED source="//uws#uwsfields"/>
	<column name="pid" type="integer" 
			description="A unix pid to kill to make the job stop">
		<values nullLiteral="-1"/>
	</column>
</table>

<data id="createJobTable">
	<make table="tapjobs"/>
</data>


<!--********************* The TAP Service *********************-->
	<service id="run" allowed="tap">
		<meta name="shortName">\metaString{authority.shortName} TAP</meta>
		<meta name="title">\getConfig{web}{sitename} TAP service</meta>


		<meta name="_longdoc" format="rst"><![CDATA[
		This service speaks TAP, a protocol designed to allow the exchange of
		queries and data between clients (that's normally something running on your
		computer) and servers (e.g., us).

		You will want to use some sort of client to query TAP services;
		examples for those include:

		* TOPCAT_ (see in the "VO" menu)
		* `TAPHandle`_ (following this link should bring you to a page 
		  that lets you query this server) works completely within your
		  browser,
		* the `TAP shell`_, giving you a command line and powerful job chaining
		  facilities,
		* the `GAVO VOTable library`_, letting you embed TAP queries in
		  python programs
		
		You can, in a pinch, use our service in an XML-enabled browser, too.
		Under `Overview <#overview>`_, look for the bullet point on tap and
		follow the link to "this service". Then, click on "New job..." 
		in the job list, enter your query, click "Set query", then 
		"Execute query".  Reload the page you are redirected to now 
		and then to see when your job is finished, then retrieve the result.

		The queries this service executes are written an a dialect of SQL called
		ADQL.  You need to learn it to use this service.  See 
		`our ADQL tutorial`_.  Also do not miss the `local examples`_.
		
		By the way, for quick ad-hoc queries from within a browser,
		our `ADQL form service`_ may be more convenient than TAP.

		Also see the `table metadata`_ of the tables exposed here.

		.. _TOPCAT: http://www.star.bris.ac.uk/~mbt/topcat/
		.. _GAVO VOTable library: http://soft.g-vo.org/subpkgs
		.. _TAP shell: http://soft.g-vo.org/tapsh
		.. _table metadata: \internallink{__system__/tap/run/tableMetadata}
		.. _ADQL form service: \internallink{__system__/adql/query/form}
		.. _service doc of our ADQL form service: \internallink{__system__/adql/query/info}
		.. _our ADQL tutorial: http://docs.g-vo.org/adql
		.. _local examples: \internallink{__system__/tap/run/tap/examples}
		.. _TAPHandle: http://saada.unistra.fr/taphandle/?url=\internallink{/tap}


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

		<meta name="identifier">ivo://\getConfig{ivoa}{authority}/tap</meta>
		<publish render="tap" sets="ivo_managed,local">
			<meta name="accessURL">\internallink{tap}</meta>
		</publish>
		<tapCore/>

		<FEED source="%#tapdescription"/>
		<FEED source="%#tapexamples"/>
	</service>

</resource>
