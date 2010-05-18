<?xml version="1.0" encoding="utf-8"?>

<resource resdir="__system">
	<schema>public</schema>
	<meta name="creationDate">2007-11-22T13:02:00Z</meta>

	<!-- Tables related to services. 
	These have to match whatever is done in gavo.web.servicelist -->

	<table system="True" id="services" forceUnique="True" onDisk="True"
			dupePolicy="overwrite" primary="internalId,sourceRd">
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
	</table>

	<table system="True" id="srv_interfaces" forceUnique="True" onDisk="True"
			primary="accessURL">
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="shortName" type="text"/>
		<column name="accessURL" type="text"/>
		<column name="referenceURL" type="text"/>
		<column name="browseable" type="boolean"/>
		<column name="renderer" type="text"/>
	</table>

	<table system="True" id="srv_sets" forceUnique="True" onDisk="True"
			dupePolicy="overwrite" primary="shortName, setName, renderer">
		<column name="shortName" type="text"/>
		<column name="setName" type="text" tablehead="Set name"
			description="Name of an OAI set.  Here, probably only 'local' and 'ivo_managed' will output anything sensible"/>
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="renderer" type="text"/>
		<column name="deleted" type="boolean"/>
	</table>
			
	<table system="True" id="srv_subjs" forceUnique="True" onDisk="True"
			primary="shortName, subject">
		<column name="shortName" type="text"/>
		<column name="sourceRd" type="text" tablehead="Source RD"/>
		<column name="subject" type="text"/>
	</table>

	<data id="tables">
		<meta name="description">gavo imp --system this to create the service 
		tables.  servicelist has special grammars to feed these.</meta>
		<nullGrammar/>

		<rowmaker id="make_interfaces" idmaps="*">
			<ignoreOn>
				<keyIs key="accessURL" value="__NULL__"/>
			</ignoreOn>
		</rowmaker>

		<!-- the scripts in the makes mark services from the rd as deleted
		  in sets and services since oai may query those.  In interfaces
			and subjects we can safely delete them.  All that will be overwritten
			by new entries if they come. -->
		<make table="services">
			<script type="newSource" lang="python" id="markDeleted">
				table.query("UPDATE \curtable SET deleted=True"
					" WHERE sourceRD=%(sourceRD)s",
					{"sourceRD": sourceToken.sourceId})
			</script>
		</make>

		<make table="srv_interfaces" rowmaker="make_interfaces">
			<script type="newSource" lang="python" id="deleteByRDId">
				table.deleteMatching(
					"sourceRd=%(sourceRD)s", {"sourceRD": sourceToken.sourceId})
			</script>
		</make>

		<make table="srv_sets">
			<script original="markDeleted"/>
		</make>

		<make table="srv_subjs">
			<script original="deleteByRDId"/>
		</make>
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
		<column original="srv_interfaces.referenceURL"/>
		<column original="srv_interfaces.browseable"/>
		<column original="srv_interfaces.renderer"/>
		<column original="srv_sets.setName"/>

		<viewStatement>
			CREATE OR REPLACE VIEW srv_join AS (
				SELECT \colNames
				FROM 
					services 
					NATURAL JOIN srv_sets
					NATURAL LEFT OUTER JOIN srv_interfaces)
		</viewStatement> <!-- The left outer join is crucial for resource records
			  without interfaces -->
	</table>

	<table id="srv_subjs_join" namePath="services" onDisk="true">
		<column original="srv_subjs.subject"/>
		<column original="shortName"/>
		<column original="title"/>
		<column original="owner"/>
		<column original="srv_interfaces.accessURL"/>
		<column original="srv_interfaces.referenceURL"/>
		<column original="srv_interfaces.browseable"/>
		<column original="srv_sets.setName"/>

		<viewStatement>
			CREATE OR REPLACE VIEW srv_subjs_join AS (
				SELECT \colNames
				FROM 
					srv_interfaces 
					NATURAL JOIN services 
					NATURAL JOIN srv_subjs 
					NATURAL JOIN srv_sets
				ORDER BY subject)
		</viewStatement>
	</table>

	<data id="views">
		<make table="srv_join"/>
		<make table="srv_subjs_join"/>
	</data>

	<dbCore queriedTable="srv_join" id="overviewcore">
		<condDesc buildFrom="setName"/>
	</dbCore>

	<service id="overview" core="overviewcore" 
			allowed="form,external,admin">
		<meta name="shortName">_cs_srv</meta>
		<meta name="title">Published Services</meta>
		<meta name="description">A list of all services published on the
			GAVO Data Center, with links to information pages about them</meta>
		<meta name="subject">Virtual Observatory</meta>
		<meta name="_related" title="Validate registry">http://rofr.ivoa.net/regvalidate/HarvestValidater?endpoint=http%3A//dc.zah.uni-heidelberg.de/oai.xml</meta>
		<meta name="_related" title="Stats">/logs/logs/stats/form</meta>

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

	<nullCore id="null"/>

	<service id="root" core="null" allowed="fixed">
		<meta name="description">The root page, vanity-named to /</meta>
		<template key="fixed">//root.html</template>
		<customDF name="chunkedServiceList">
			return base.caches.getChunkedServiceList("\RDid")
		</customDF>
		<customDF name="subjectServiceList">
			return base.caches.getSubjectsList("\RDid")
		</customDF>
		<customRF name="ifprotected">
			if data["owner"]:
				return ctx.tag
			else:
				return ""
		</customRF>
	</service>
</resource>
