<?xml version="1.0" encoding="utf-8"?>
<!-- meta tables containing field descriptions of all fields of data center
tables and the RDs the tables come from. -->

<!-- note that much of the stuff in here is reflected in code in
* rsc.dbtable
* rsc.metatable
* rscdef.column
-->

<resource resdir="__system" schema="dc">
	<meta name="description">Column description and related metadata for
		the tables within the data holdings.
		This is primarily for use with ADQL queries.</meta>

	<table id="columnmeta" onDisk="True" system="True">
		<meta name="description">A table mapping field names and their
			principal properties (types, ucds, descriptions...).</meta>
		<column name="tableName" type="text"
			description="Fully qualified name of the table the column is in"/>
		<column name="fieldName" type="text"
			description="SQL identifier for the column"/>
		<column name="unit" type="text" description="Unit for the value"/>
		<column name="ucd" type="text" description="UCD for the column"/>
		<column name="description" type="text" 
			description="A one-line characterization of the value"/>
		<column name="tablehead" type="text" 
			description="A string suitable as a table heading for the values"/>
		<column name="longdescr" type="text" 
			description="A possibly long information on the values"/>
		<column name="longmime" type="text" description="Mime type of longdescr"/>
		<column name="utype" type="text" description="The utype for the column"/>
		<column name="colInd" type="integer" 
			description="Index of the column within the table"/>
		<column name="type" type="text" 
			description="SQL type of this column"/>
		<column name="verbLevel" type="integer" 
			description="Level of verbosity at which to include this column"/>
		<column name="displayHint" type="text"
			description="Hints how to display that item for human consumption"/>
		<primary>tableName,fieldName</primary>
	</table>

	<rowmaker id="fromColumnList">
		<!-- turns a rawrec with column, colInd, tableName keys into a
		columnmeta row -->
		<apply name="makerow">
			<code>
				column = vars["column"]
				for key in ["description", "unit", "ucd", "tablehead",
						"longmime", "utype", "verbLevel", "type", "longdescr"]:
					result[key] = getattr(column, key)
				result["displayHint"] = column.getDisplayHintAsString()
				result["fieldName"] = column.name
			</code>
		</apply>
		<map dest="colInd"/>
		<map dest="tableName"/>
	</rowmaker>

	<table id="tablemeta" onDisk="True" system="True" forceUnique="True"
			dupePolicy="overwrite">
		<meta name="description">A table mapping table names and schemas to
			the resource descriptors they come from and whether they are open
			to ADQL queries.  This table is primarily used for the table info
			services defined below.</meta>

		<column name="tableName" description="Fully qualified table name"
			type="text" verbLevel="1"/>
		<column name="sourceRd" type="text"
			description="Id of the resource descriptor containing the table's definition"
			tablehead="RD" verbLevel="15"/>
		<column name="tableDesc" type="text"
			description="Description of the table content" 
			tablehead="Table desc." verbLevel="1"/>
		<column name="resDesc" type="text"
			description="Description of the resource this table is part of"
			tablehead="Res desc." verbLevel="15"/>
		<column name="adql" type="boolean"
			description="True if this table may be accessed using ADQL"
			verbLevel="30"/>
		<primary>tableName, sourceRd</primary>
	</table>

	<data id="import">
		<make table="columnmeta"/>
		<make table="tablemeta"/>
	</data>

	<outputTable id="metaRowdef" namePath="columnmeta">
		<meta name="description">The definition of the input to
		column.fromMetaTableRow</meta>
		<outputField original="description"/>
		<outputField original="fieldName"/>
		<outputField original="unit"/>
		<outputField original="ucd"/>
		<outputField original="tablehead"/>
		<outputField original="longdescr"/>
		<outputField original="longmime"/>
		<outputField original="utype"/>
		<outputField original="type"/>
		<outputField original="verbLevel"/>
		<outputField original="displayHint"/>
	</outputTable>

	<fixedQueryCore id="queryList"
		query="SELECT tableName, tableName, tableDesc, resDesc FROM dc.tablemeta WHERE adql ORDER BY tableName">
		<outputTable namePath="tablemeta">
			<outputField original="tableName"/>
			<outputField name="tableinfo" original="tableName"/>
			<outputField original="tableDesc"/>
			<outputField original="resDesc"/>
		</outputTable>
	</fixedQueryCore>

	<service id="show" allowed="tableinfo" core="queryList">
			<!-- actually, we have a null core here since tableinfo doesn't call
			     a core -->
		<meta name="shortName">GAVO tab infos</meta>
		<meta name="description">Information on tables within the GAVO data
			center</meta>
		<meta name="title">Table Infos</meta>
	</service>

	<service id="list" core="queryList">
		<meta name="shortName">gavo ADQL tabs</meta>
		<meta name="description">An overview over the tables available for ADQL 
			querying in the GAVO data center.</meta>
		<meta name="title">GAVO ADQL tables</meta>
		<outputTable namePath="tablemeta">
			<outputField original="tableName"/>
			<outputField name="tableinfo" type="text" tablehead="Info">
				<formatter>
					return T.a(href=base.makeSitePath("/__system__/dc_tables/"
						"show/tableinfo?tableName="+urllib.quote(data)))["Table Info"]
				</formatter>
			</outputField>
			<outputField original="tableDesc"/>
			<outputField original="resDesc"/>
		</outputTable>
	</service>
</resource>

