<resource schema="tap_schema">
	<meta name="description">Support tables (views) for TAP</meta>
	<property name="TAP_VERSION">1.0</property>

	<table id="schemas" onDisk="True" system="True"
			forceUnique="True" dupePolicy="drop" primary="schema_name"
			readRoles="defaults,untrusted">
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
		<column name="key_id" type="text" 
			description="Key identifier from TAP_SCHEMA.keys"/>
		<column name="from_column" type="text" 
			description="Key column name in the from table"/>
		<column name="target_column" type="text" 
			description="Key column in the target table"/>
		<column name="sourceRD" type="text" description="Id of the originating rd"/>
	</table>

	<data id="importTablesFromRD">
		<embeddedGrammar>
			<iterator>
				<code>
					rd = self.sourceToken
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
								propagate=False),
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
					name="delete stale TAP_SCHEMA entries">
				table.deleteMatching("sourceRD=%(sourceRD)s",
					{"sourceRD": sourceToken.sourceId})
			</script>
		</make>
	</data>

	<data id="importColumnsFromRD">
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
								"table_name": table.getQName(),
								"column_name": col.name,
								"description": col.description,
								"unit": col.unit,
								"ucd": col.ucd,
								"utype": col.utype,
								"datatype": type,
								"size": size,
								"principal": col.verbLevel&lt;=10,
								"indexed": indexed,
								"std": 0,
								"sourceRD": rd.sourceId,
							}
				</code>
			</iterator>
		</embeddedGrammar>
		<make table="columns">
			<script original="removeStale"/>
		</make>
	</data>

	<data id="importFkeysFromRD">
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
								"key_id": fkeyId,
								"from_table": table.getQName(),
								"target_table": fkey.table,
								"description": None,
								"utype": None,
								"sourceRD": rd.sourceId,
								"dest": "keys",
							}
							for src, dst in zip(fkey.source, fkey.dest):
								yield {
									"key_id": fkeyId,
									"from_column": src,
									"target_column": dst,
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

	<staticCore id="nullcore" file="no/file"/>

	<service id="run" core="nullcore" allowed="tap"/>
</resource>
