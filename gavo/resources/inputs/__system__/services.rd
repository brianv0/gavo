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
		<meta name="description">
			The table of published "resources" (i.e., services, tables,
			data collections) within this data center.  There are separate
			tables of the interfaces these resources have, their authors,
			subjects, and the sets they belong to.
			
			Manipulate through gavo pub; to remove entries from this table, remove
			the publication element of the service or table in question
			and re-run gavo pub on the resource descriptor.
		</meta>

		<column name="sourceRD" type="text"
			tablehead="Source RD" required="True"
			description="Id of the RD (essentially, the inputsDir-relative
			path, with the .rd cut off)."/>
		<column name="resId" type="text"
			tablehead="RD-relative id" displayHint="type=hidden"
			description="Id of the service, data or table within the RD.
			Together with the RD id, this uniquely identifies the resource
			to DaCHS."/>
		<column name="shortName" type="text"
			description="The content of the service's shortName metadata.
				This is not currently used by the root pages delivered with
				DaCHS, so this column essentially is ignored."
			tablehead="Short"/>
		<column name="title" type="text" required="True"
				description="The content of the service's title metadata
				(gavo pub will fall back to the resource's title if
				the service doesn't have a description of its own)."/>
		<column name="description" type="text"
			description="The content of the service's description metadata
				(gavo pub will fall back to the resource's description if
				the service doesn't have a description of its own)."/>
		<column name="owner" type="text" description="NULL for public
			services, otherwise whatever is in limitTo.  The root pages delivered
			with DaCHS put a [P] in front of services with a non-NULL owner."/>
		<column name="dateUpdated" type="timestamp" unit="a"
			description="Date of last update on the resource itself (i.e.,
				run of gavo imp)."/>
		<column name="recTimestamp" type="timestamp"
			description="UTC of gavo publish run on the source RD"/>
		<column name="deleted" type="boolean" required="True"
			description="True if the service is deleted.  On deletion,
				services are not removed from the resources and sets tables
				so the OAI-PMH service can notify incremental harvesters that
				a resource is gone."/>
		<column name="ivoid" type="text" description="The full ivo-id of
			the resource.  This is usually ivo://auth/rdid/frag but may
			be overridden (you should probably not create records for
			which you are not authority, but we do not enforce that any more)."/>
		<column name="authors" type="text" description="Resource authors
			in source sequence"/>
	</table>

	<table system="True" id="interfaces" forceUnique="True" onDisk="True"
			primary="accessURL" namePath="resources">
		<meta name="description">
			A table that has "interfaces", i.e., actual URLs under which
			services are accessible.  This is in a separate table, as services
			can have multiple interfaces (e.g., SCS and form).
			
			Manipulate through gavo pub; to remove entries from this table, remove
			the publication element of the service or table in question
			and re-run gavo pub on the resource descriptor.
		</meta>

		<column original="sourceRD"/>
		<column original="resId"/>
		<column name="accessURL" type="text" description="The URL
			this service with the given renderer can be accessed under."/>
		<column name="referenceURL" type="text" description="The URL
				this interface is explained at.  In DaCHS, as in VOResource,
				this column should actually be in dc.resources, but we don't consider
				that wart bad enough to risk any breakage."/>
		<column name="browseable" type="boolean" required="True"
			description="True if this interface can sensibly be operated
				with a web browser (e.g., form, but not scs.xml; browseable
				service interfaces are eligible for being put below the
				'Use this service with your browser' button on the service
				info page."/>
		<column name="renderer" type="text" description="The renderer
			used for this interface."/>
	</table>

	<table system="True" id="sets" forceUnique="True" onDisk="True"
			dupePolicy="overwrite" 
			primary="sourceRD, resId, renderer, setName"
			namePath="resources">
		<meta name="description">
			A table that contains set membership of published resources.
			For DaCHS, the sets ivo_managed ("publish to the VO") and local
			("show on a generated root page" if using one of the shipped
			root pages) have a special role.
			
			Manipulate through gavo pub; to remove entries from this table, remove
			the publication element of the service or table in question
			and re-run gavo pub on the resource descriptor.
		</meta>

		<column original="sourceRD"/>
		<column original="resId"/>
		<column name="setName" type="text" tablehead="Set name"
			description="Name of an OAI set."/>
		<column name="renderer" type="text" description="The renderer
			used for the publication belonging to this set.  Typically,
			protocol renderers (e.g., scs.xml) will be used in VO publications,
			whereas form and friends might be both in local and ivo_managed"/>
		<column original="deleted"/>
	</table>
			
	<table system="True" id="subjects" forceUnique="True" onDisk="True"
			primary="sourceRD, resId, subject" namePath="resources">
		<meta name="description">
			A table that contains the subject metadata for published services.  It is
			used by the shipped templates of the root pages ("...by subject").
			
			Manipulate through gavo pub; to remove entries from this table, remove
			the publication element of the service or table in question
			and re-run gavo pub on the resource descriptor.
		</meta>

		<column original="sourceRD"/>
		<column original="resId"/>
		<column name="subject" type="text" description="A subject heading.
			Terms should ideally come from the IVOA thesaurus."/>
	</table>

	<table system="True" id="authors" forceUnique="True"
			onDisk="True" primary="sourceRD, resId, author">
		<meta name="description">
			A table that contains the (slightly processed) creator.name
			metadata from published services.  It is used by the shipped
			templates of the root pages.
			
			Manipulate through gavo pub; to remove entries from this table, remove
			the publication element of the service or table in question
			and re-run gavo pub on the resource descriptor.
		</meta>
		<foreignKey inTable="resources" source="sourceRD,resId"/>
		<column original="resources.sourceRD"/>
		<column original="resources.resId"/>
		<column name="author" type="unicode"
			description="An author name taken from creator.name; DaCHS assumes
				this to be in the form Last, I."/>
	</table>

	<table system="True" id="res_dependencies" forceUnique="True"
			onDisk="True" primary="rd, prereq" dupePolicy="overwrite">
		<meta name="description">An RD-level map of dependencies, meaning
		that before generating resource records from rd, prereq should
		be imported (think: TAP needs the metadata of all dependent tables).
		
		This is managed by gavo pub and used in the OAI-PMH interface.
		</meta>
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
		<make table="resources" role="resources">
			<script type="newSource" lang="python" id="markDeleted">
				table.query("UPDATE \curtable SET deleted=True"
					" WHERE sourceRD=%(sourceRD)s",
					{"sourceRD": sourceToken.sourceId})
			</script>
		</make>

		<make table="interfaces" role="interfaces">
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

		<make table="sets" role="sets">
			<script original="markDeleted"/>
		</make>

		<make table="subjects" role="subjects">
			<script original="deleteByRDId"/>
		</make>

		<make table="authors" role="authors">
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

	<table id="resources_join" namePath="resources" onDisk="true">
		<meta name="description">
			A join of resources, interfaces, and sets used internally.
		</meta>

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
		<meta name="description">
			A join of resources, subjects, and sets used internally.
		</meta>

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

	<FEED source="%#registry-interfacerecords"/>

	<service id="root" allowed="fixed">
		<!-- this is just a placeholder for render functions the root
		page may need.  There are basically two rather different of
		those; the old, more static one, uses the chunkedServiceList
		and subjectServiceList DFs; the other the titleList (and lots
		of javascript and stuff in web/jsonquery.py -->

		<template key="fixed">//root.html</template>
		<meta name="title">\getConfig{web}{sitename}</meta>

		<nullCore/>

		<customDF name="chunkedServiceList">
			rd = base.caches.getRD("__system__/services")
			if not hasattr(rd, "chunkedServiceList"):
				from gavo.registry import servicelist
				rd.chunkedServiceList = servicelist.getChunkedServiceList()
			return rd.chunkedServiceList
		</customDF>

		<customDF name="titleList">
			rd = base.caches.getRD("__system__/services")
			if True:  # not hasattr(rd, "portal__titleList"):
				with base.getTableConn() as conn:
					rd.portal__titleList = list(conn.queryToDicts("SELECT"
						" title, dateUpdated, accessURL, referenceURL, browseable, owner,"
						" sourceRD, resId"
						" FROM dc.resources_join"
						" WHERE setName='local' AND NOT deleted"
						" ORDER BY title"))
			return rd.portal__titleList
		</customDF>

		<customDF name="subjectServiceList">
			rd = base.caches.getRD("__system__/services")
			if not hasattr(rd, "subjectServiceList"):
				from gavo.registry import servicelist
				rd.subjectServiceList = servicelist.querySubjectsList()
			return rd.subjectServiceList
		</customDF>

		<customRF name="ifprotected">
			if data["owner"]:
				return ctx.tag
			else:
				return ""
		</customRF>
	</service>

</resource>
