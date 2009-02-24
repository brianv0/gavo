<?xml version="1.0" encoding="utf-8"?>

<resource resdir="__system">
	<schema>public</schema>
	<meta name="_related" title="Validate registry">http://rofr.ivoa.net/regvalidate/HarvestValidater?endpoint=http%3A//vo.uni-hd.de/oai.xml</meta>

	<!-- this is for static resources imported via the fixedrecords data below.

	It *must* match the id of this resource descriptor (properties can't do
	field computing, so you need to maintain it by hand).
	-->
	<property name="srcRdId">__system__/services</property>

	<!-- Tables related to services. 
	These have to match whatever is done in gavo.web.servicelist -->

	<table system="True" id="services" forceUnique="True" onDisk="True">
		<column name="shortName" type="text"
			tablehead="Service ID"/>
		<column name="internalId" type="text"
			tablehead="Internal relative id" displayHint="type=hidden"/>
		<column name="sourceRd" type="text"
			tablehead="Source RD" required="True"/>
		<column name="title" type="text" required="True"/>
		<column name="description" type="text"/>
		<column name="owner" type="text"/>
		<column name="dateUpdated" type="timestamp"/>
		<primary>internalId,sourceRd</primary>
	</table>

	<table system="True" id="srv_interfaces" forceUnique="True" onDisk="True">
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="shortName" type="text"/>
		<column name="accessURL" type="text"/>
		<column name="renderer" type="text"/>
<!-- scrap that field. It used be used to assign default sets, but
that was folly -->
		<column name="type" type="text">
			<values>
				<option>web</option>
				<option>vo</option>
			</values>
		</column>
		<primary>accessURL</primary>
		<ignoreOn>
			<keyIs key="accessURL" value="__NULL__"/>
		</ignoreOn>
	</table>

	<table system="True" id="srv_sets" forceUnique="True" onDisk="True">
		<column name="shortName" type="text"/>
		<column name="setName" type="text"/>
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="renderer" type="text"/>
		<primary>shortName, setName, renderer</primary>
	</table>
			
	<table system="True" id="srv_subjs" forceUnique="True" onDisk="True">
		<column name="shortName" type="text"/>
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="subject" type="text"/>
		<primary>shortName, subject</primary>
	</table>

	<data id="tables">
		<meta name="description">gavoimp system this to create the service tables.
		servicelist has special grammars to feed these.</meta>
		<nullGrammar/>
		<make table="services"/>
		<make table="srv_interfaces"/>
		<make table="srv_sets"/>
		<make table="srv_subjs"/>
	</data>

	<data id="fixedrecords" auto="False">
		<meta name="description">Descriptor for importing static resources.
			There's a special handling for this in staticresource, don't run
			gavoimp on this.</meta>
		<sources pattern="*.rr" recurse="True"/>
		<keyValueGrammar enc="utf-8" yieldPairs="True"/>
	</data>

	<!-- a join of services, interfaces, and sets tables - REPLACE WITH ADQL -->
	<table id="srv_join" namePath="services" onDisk="true">
		<column original="shortName"/>
		<column original="internalId"/>
		<column original="sourceRd"/>
		<column original="title"/>
		<column original="description"/>
		<column original="owner"/>
		<column original="dateUpdated"/>
		<column original="srv_interfaces.accessURL"/>
		<column original="srv_interfaces.renderer"/>
		<column original="srv_sets.setName"/>

		<script type="viewCreation" name="create services join">
			CREATE OR REPLACE VIEW srv_join AS (
				SELECT shortName, internalId, sourceRd, title, description,
					owner, dateUpdated, accessURL, renderer, setName 
				FROM 
					services 
					NATURAL JOIN srv_sets
					NATURAL LEFT OUTER JOIN srv_interfaces)
			</script> <!-- The left outer join is crucial for resource records
			  without interfaces -->
	</table>

	<!-- a join of locally defined services, by subject - REPLACE WITH ADQL -->
	<table id="srv_subjs_join" namePath="services" onDisk="true">
		<column original="srv_subjs.subject"/>
		<column original="shortName"/>
		<column original="title"/>
		<column original="owner"/>
		<column original="srv_interfaces.accessURL"/>

		<script type="viewCreation" name="create subjects view">
			CREATE OR REPLACE VIEW srv_subjs_join AS (
				SELECT subject, shortName, title, owner, accessurl
				FROM 
					(
						SELECT accessurl, sourceRd, shortName, renderer 
						FROM srv_interfaces 
							JOIN srv_sets USING (shortName, renderer, sourcerd) 
						WHERE setName='local') AS q 
					NATURAL JOIN services 
					NATURAL JOIN srv_subjs 
				ORDER BY subject);
		</script>
	</table>

	<data id="views">
		<make table="srv_join"/>
		<make table="srv_subjs_join"/>
	</data>

	<registryCore id="registrycore"/>

	<service id="registry" core="registrycore" allowed="pubreg.xml"/>

	<dbCore queriedTable="srv_join" id="overviewcore">
		<condDesc buildFrom="setName"/>
	</dbCore>

	<service id="overview" core="overviewcore">
		<meta name="shortName">_cs_srv</meta>
		<meta name="title">Published Services</meta>
		<outputTable namePath="srv_join">
			<outputField original="shortName"/>
			<outputField original="sourceRd"/>
			<outputField original="title"/>
			<outputField original="owner"/>
			<outputField original="dateUpdated" unit="Y-M-D"/>
			<outputField original="renderer"/>
			<outputField original="setName"/>
		</outputTable>
	</service>

	<registryCore id="registrycore"/>

	<service id="registry" core="registrycore" allowed="pubreg.xml"/>
</resource>
