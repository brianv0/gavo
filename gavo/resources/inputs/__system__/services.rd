<?xml version="1.0" encoding="utf-8"?>

<resource resdir="__system">
	<schema>public</schema>
	<meta name="_related" title="Validate registry">http://rofr.ivoa.net/regvalidate/HarvestValidater?endpoint=http%3A//dc.zah.uni-heidelberg.de/oai.xml</meta>
	<meta name="creationDate">2007-11-22T13:02:00Z</meta>

	<!-- Tables related to services. 
	These have to match whatever is done in gavo.web.servicelist -->

	<table system="True" id="services" forceUnique="True" onDisk="True"
			dupePolicy="overwrite">
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
		<column name="recTimestamp" type="timestamp"
			description="UTC of gavopublish run on the source RD"/>
		<column name="deleted" type="boolean"/>
		<primary>internalId,sourceRd</primary>
	</table>

	<table system="True" id="srv_interfaces" forceUnique="True" onDisk="True">
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="shortName" type="text"/>
		<column name="accessURL" type="text"/>
		<column name="renderer" type="text"/>
		<primary>accessURL</primary>
		<ignoreOn>
			<keyIs key="accessURL" value="__NULL__"/>
		</ignoreOn>
	</table>

	<table system="True" id="srv_sets" forceUnique="True" onDisk="True"
			dupePolicy="overwrite">
		<column name="shortName" type="text"/>
		<column name="setName" type="text"/>
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="renderer" type="text"/>
		<column name="deleted" type="boolean"/>
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
		<script type="newSource">
			# mark services from rd imported as deleted (or remove them if
			# we don't need to keep a record)
			for id in ["srv_interfaces", "srv_subjs"]:
				data.tables[id].deleteMatching(
					"sourceRd=%(sourceRD)s", {"sourceRD": sourceToken.sourceId})
			# sets and services are queried by oai, so I can't delete them
			for id in ["srv_sets", "services"]:
				data.tables[id].query("UPDATE %s SET deleted=True"
					" WHERE sourceRD=%%(sourceRD)s"%id, 
					{"sourceRD": sourceToken.sourceId})
		</script>
		<nullGrammar/>
		<make table="services"/>
		<make table="srv_interfaces"/>
		<make table="srv_sets"/>
		<make table="srv_subjs"/>
	</data>

	<table id="srv_join" namePath="services" onDisk="true">
		<column original="shortName"/>
		<column original="internalId"/>
		<column original="sourceRd"/>
		<column original="title"/>
		<column original="description"/>
		<column original="owner"/>
		<column original="dateUpdated"/>
		<column original="recTimestamp"/>
		<column original="deleted"/>
		<column original="srv_interfaces.accessURL"/>
		<column original="srv_interfaces.renderer"/>
		<column original="srv_sets.setName"/>

		<script type="viewCreation" name="create services join">
			CREATE OR REPLACE VIEW srv_join AS (
				SELECT shortName, internalId, sourceRd, title, description,
					owner, dateUpdated, recTimestamp, deleted, accessURL, renderer, 
					setName 
				FROM 
					services 
					NATURAL JOIN srv_sets
					NATURAL LEFT OUTER JOIN srv_interfaces)
			</script> <!-- The left outer join is crucial for resource records
			  without interfaces -->
	</table>

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
						WHERE setName='local'
					) AS q 
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

	<service id="overview" core="overviewcore" allowed="form,external">
		<meta name="shortName">_cs_srv</meta>
		<meta name="title">Published Services</meta>
		<meta name="description">A list of all services published on the
			GAVO Data Center, with links to information pages about them</meta>
		<meta name="subject">Virtual Observatory</meta>

		<!-- we abuse the service for an easy redirect to the central operator's
			help site -->
		<publish render="external" sets="ignore">
			<meta name="accessURL">http://vo.ari.uni-heidelberg.de/docs/DaCHS</meta>
		</publish>

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

	<service id="registry" core="registrycore" allowed="pubreg.xml">
		<publish render="pubreg.xml" sets="ivo_managed"/>
		<meta name="resType">registry</meta>
		<meta name="title">GAVO Data Center Registry</meta>
		<meta name="creationDate">2008-05-07T11:33:00</meta>
		<meta name="description">The GAVO data center registry provides 
			records for resources in GAVO's data center</meta>
		<meta name="subject">Registry</meta>
		<meta name="shortName">GAVO DC registry</meta>
		<meta name="content.type">Archive</meta>
		<meta name="rights">public</meta>
		<meta name="harvest.description">The harvesting interface for GAVO's data
			center registry</meta>
		<meta name="full">false</meta>
		<meta name="maxRecords">10000</meta>
		<meta name="managedAuthority">org.gavo.dc</meta>
		<meta name="referenceURL">http://vo.uni-hd.de/builtin/help.shtml</meta>
		<meta name="publisher">GAVO Data Center Team</meta>
		<meta name="contact.name">GAVO Data Center Team</meta>
		<meta name="contact.email">gavo@ari.uni-heidelberg.de</meta>

	</service>
</resource>
