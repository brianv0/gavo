<?xml version="1.0" encoding="utf-8"?>

<resource resdir="__system" schema="dc">
	<meta name="creationDate">2007-11-22T13:02:00Z</meta>
	<meta name="description">\metaString{site.description}</meta>

	<!-- Tables related to resources (this used to be for services exclusively,
	hence the names.) 

	These have to match whatever is done in gavo.registry; most explanations
	are around there, but quickly: RD+id identify a resource uniquely.
	Publication takes into account the renderer for services; renderer
	is rcdisplay for non-rendered services. 
	
	The main reason we're not using foreign keys here is that we need
	to handle deleted records and much of the automatic management
	afforded by foreign keys would work against us here.
	-->

	<table system="True" id="resources" forceUnique="True" onDisk="True"
			dupePolicy="overwrite" primary="sourceRD,resId">
		<column name="sourceRD" type="text"
			tablehead="Source RD" required="True"/>
		<column name="resId" type="text"
			tablehead="RD-relative id" displayHint="type=hidden"/>
		<column name="shortName" type="text"
			tablehead="Short"/>
		<column name="title" type="text" required="True"/>
		<column name="description" type="text"/>
		<column name="owner" type="text"/>
		<column name="dateUpdated" type="timestamp" unit="a"/>
		<column name="recTimestamp" type="timestamp"
			description="UTC of gavo publish run on the source RD"/>
		<column name="deleted" type="boolean" required="True"/>
		<column name="ivoid" type="text" description="The full ivo-id of
			the resource.  This is usually ivo://auth/rdid/frag but may
			be overridden (you should probably not create records for
			which you are not authority, but we do not enforce that any more)."/>
	</table>

	<table system="True" id="interfaces" forceUnique="True" onDisk="True"
			primary="accessURL" namePath="resources">
		<column original="sourceRD"/>
		<column original="resId"/>
		<column name="accessURL" type="text"/>
		<column name="referenceURL" type="text"/>
		<column name="browseable" type="boolean" required="True"/>
		<column name="renderer" type="text"/>
	</table>

	<table system="True" id="sets" forceUnique="True" onDisk="True"
			dupePolicy="overwrite" 
			primary="sourceRD, resId, renderer, setName"
			namePath="resources">
		<column original="sourceRD"/>
		<column original="resId"/>
		<column name="setName" type="text" tablehead="Set name"
			description="Name of an OAI set.  Here, probably only 'local' 
				and 'ivo_managed' will yield anything."/>
		<column name="renderer" type="text"/>
		<column name="deleted" type="boolean" required="True"/>
	</table>
			
	<table system="True" id="subjects" forceUnique="True" onDisk="True"
			primary="sourceRD, resId, subject" namePath="resources">
		<column original="sourceRD"/>
		<column original="resId"/>
		<column name="subject" type="text"/>
	</table>

	<table system="True" id="res_dependencies" forceUnique="True"
			onDisk="True" primary="rd, prereq" dupePolicy="overwrite">
		<meta name="description">An RD-level map of dependencies, meaning
		that before generating resource records from rd, requisite should
		be imported.</meta>
		<column name="rd" type="text" description="id of an RD"/>
		<column name="prereq" type="text" description="id of an RD that
			should be imported before records from rd are generated."/>
		<column name="sourceRD" type="text" description="id of the RD
			that introduced this dependency"/>
	</table>

	<data id="tables">
		<meta name="description">gavo imp --system this to create the service 
		tables.  servicelist has special grammars to feed these.</meta>
		<nullGrammar/>

		<!-- the scripts in the makes mark services from the rd as deleted
		  in sets and services since oai may query those.  In interfaces
			and subjects we can safely delete them.  All that will be overwritten
			by new entries if they come. -->
		<make table="resources">
			<script type="newSource" lang="python" id="markDeleted">
				table.query("UPDATE \curtable SET deleted=True"
					" WHERE sourceRD=%(sourceRD)s",
					{"sourceRD": sourceToken.sourceId})
			</script>
		</make>

		<make table="interfaces">
			<rowmaker idmaps="*">
				<ignoreOn>
					<keyIs key="accessURL" value="__NULL__"/>
				</ignoreOn>
			</rowmaker>

			<script type="newSource" lang="python" id="deleteByRDId">
				table.deleteMatching(
					"sourceRD=%(sourceRD)s", {"sourceRD": sourceToken.sourceId})
			</script>
		</make>

		<make table="sets">
			<script original="markDeleted"/>
		</make>

		<make table="subjects">
			<script original="deleteByRDId"/>
		</make>
	</data>

	<data id="deptable" updating="True">
		<meta name="description">import the RD-dependencies from an RD.</meta>

		<embeddedGrammar>
			<iterator>
				<code>
					rd = self.sourceToken
					for rdId, reqId in rd.rdDependencies:
						yield {
							'rd': rdId,
							'prereq': reqId,
							'sourceRD': rd.sourceId,
						}
				</code>
			</iterator>
		</embeddedGrammar>

		<make table="res_dependencies">
			<script original="deleteByRDId"/>
		</make>
	</data>

	<data id="upgrade_0.6.3_0.7" auto="False">
		<make table="res_dependencies">
			<script original="deleteByRDId"/>
		</make>
	</data>

	<table id="resources_join" namePath="resources" onDisk="true">
		<column original="sourceRD"/>
		<column original="resId"/>
		<column original="title"/>
		<column original="description"/>
		<column original="owner"/>
		<column original="dateUpdated"/>
		<column original="recTimestamp"/>
		<column original="deleted"/>
		<column original="interfaces.accessURL"/>
		<column original="interfaces.referenceURL"/>
		<column original="interfaces.browseable"/>
		<column original="interfaces.renderer"/>
		<column original="sets.setName"/>
		<column original="ivoid"/>

		<viewStatement>
			CREATE OR REPLACE VIEW dc.resources_join AS (
				SELECT \colNames
				FROM 
					dc.resources 
					NATURAL JOIN dc.sets
					NATURAL LEFT OUTER JOIN dc.interfaces)
		</viewStatement> <!-- The left outer join is crucial for resource records
			  without interfaces -->
	</table>

	<table id="subjects_join" namePath="resources" onDisk="true">
		<column original="subjects.subject"/>
		<column original="sourceRD"/>
		<column original="resId"/>
		<column original="title"/>
		<column original="owner"/>
		<column original="interfaces.accessURL"/>
		<column original="interfaces.referenceURL"/>
		<column original="interfaces.browseable"/>
		<column original="sets.setName"/>
		<column original="ivoid"/>

		<viewStatement>
			CREATE OR REPLACE VIEW dc.subjects_join AS (
				SELECT \colNames
				FROM 
					dc.interfaces 
					NATURAL JOIN dc.resources 
					NATURAL JOIN dc.subjects 
					NATURAL JOIN dc.sets
				ORDER BY subject)
		</viewStatement>
	</table>

	<data id="views">
		<make table="resources_join"/>
		<make table="subjects_join"/>
	</data>

	<dbCore queriedTable="resources_join" id="overviewcore">
		<condDesc buildFrom="setName"/>
	</dbCore>

	<service id="overview" core="overviewcore" 
			allowed="form,external,admin,rdinfo">
		<meta name="shortName">_cs_srv</meta>
		<meta name="title">Published Services</meta>
		<meta name="description">A list of all services published on the
			\getConfig{web}{sitename}, with links to information pages 
			about them</meta>
		<meta name="subject">Virtual Observatory</meta>
		<meta name="_related" title="Validate registry">http://rofr.ivoa.net/regvalidate/HarvestValidater?endpoint=http%3A//dc.zah.uni-heidelberg.de/oai.xml</meta>
		<meta name="_related" title="Stats">/logs/logs/stats/form</meta>

		<!-- we abuse the service for an easy redirect to the central operator's
			help site -->
		<publish render="external" sets="ignore">
			<meta name="accessURL">http://vo.ari.uni-heidelberg.de/docs/DaCHS</meta>
		</publish>

		<outputTable namePath="resources_join">
			<outputField original="sourceRD"/>
			<outputField original="resId"/>
			<outputField original="title"/>
			<outputField original="owner"/>
			<outputField original="dateUpdated" displayHint="type=humanDatetime"/>
			<outputField original="renderer"/>
			<outputField original="setName"/>
			<outputField original="deleted"/>
		</outputTable>
	</service>

	<resRec id="authority"> <!-- ivo id of the authority is overridden in
			nonservice.NonServiceResource -->
		<meta>
			resType: authority
			creationDate: \metaString{authority.creationDate}{UNCONFIGURED}
			title: \metaString{authority.title}{UNCONFIGURED}
			shortName: \metaString{authority.shortName}{UNCONFIGURED}
			subject: Authority
			managingOrg: \metaString{authority.managingOrg}{UNCONFIGURED}
			description: \metaString{authority.description}{UNCONFIGURED}
			referenceURL: \metaString{authority.referenceURL}{UNCONFIGURED}
			identifier: ivo://\getConfig{ivoa}{authority}
			sets: ivo_managed
		</meta>
	</resRec>

	<resRec id="manager"> <!-- the organisation running this registry -->
		<meta>
			resType: organization
			creationDate: \metaString{authority.creationDate}{UNCONFIGURED}
			title: \metaString{organization.title}{UNCONFIGURED}
			subject: Organization
			description: \metaString{organization.description}{UNCONFIGURED}
			referenceURL: \metaString{organization.referenceURL}{UNCONFIGURED}
			identifier: ivo://\getConfig{ivoa}{authority}/org
			sets: ivo_managed
		</meta>
	</resRec>

	<registryCore id="registrycore"/>

	<service id="registry" core="registrycore" allowed="pubreg.xml">
		<publish render="pubreg.xml" sets="ivo_managed">
			<meta name="accessURL"
				>\getConfig{web}{serverURL}\getConfig{web}{nevowRoot}oai.xml</meta>
		</publish>
		<meta name="resType">registry</meta>
		<meta name="title">\getConfig{web}{sitename} Registry</meta>
		<meta name="creationDate">2008-05-07T11:33:00</meta>
		<meta name="description">
			The publishing registry for the \getConfig{web}{sitename}.
		</meta>
		<meta name="subject">Registry</meta>
		<meta name="shortName">\metaString{authority.shortName} Reg</meta>
		<meta name="content.type">Archive</meta>
		<meta name="rights">public</meta>
		<meta name="harvest.description">The harvesting interface for 
			the publishing registry of the \getConfig{web}{sitename}</meta>
		<meta name="maxRecords">10000</meta>
		<meta name="managedAuthority">\getConfig{ivoa}{authority}</meta>
		<meta name="referenceURL">http://vo.uni-hd.de/static/help.shtml</meta>
		<meta name="publisher">The staff at the \getConfig{web}{sitename}</meta>
	</service>

	<nullCore id="null"/>

	<service id="root" core="null" allowed="fixed">
		<template key="fixed">//root.html</template>
		<meta name="title">\getConfig{web}{sitename}</meta>
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
