<resource schema="ivoa" resdir="__system">
	<meta name="creationDate">2011-03-25T10:23:00</meta>
	<meta name="description">Definition and support code for the ObsCore
		data model and table.</meta>
	
	<table id="ObsCore" onDisk="True" adql="True">
		<!-- the view creation statement is bogus; in reality, we create
		the view creation statement from the _obscoresources table in the
		data create -->
		<viewStatement>
			create view \qName (\colNames) as (select * from (VALUES(
				NULL, NULL, NULL, NULL, NULL,
				NULL, NULL, NULL, NULL, NULL,
				NULL, NULL, NULL, NULL, NULL,
				NULL, NULL, NULL, NULL, NULL,
				NULL, NULL, NULL, NULL, NULL,
				NULL)) as q WHERE 0=1);
		</viewStatement>
		<column name="dataproduct_type" type="text"
			utype="obscore:obs.dataproducttype" ucd="meta.id;class"
			description="High level scientific classification of the data product,
				taken from an enumeration"
			verbLevel="5">
			<values>
				<option>image</option>
				<option>cube</option>
				<option>spectrum</option>
				<option>sed</option>
				<option>timeseries</option>
				<option>visibility</option>
				<option>event</option>
			</values>
			<property name="std">1</property>
		</column>

		<column name="dataproduct_subtype" type="text"
			utype="obscore:obs.dataproductsubtype" ucd="meta.id;class"
			description="Data product specific type"
			verbLevel="15"/>
	
		<column name="calib_level" type="smallint" 
			utype="obscore:obs.caliblevel" ucd="meta.id;class"
			description="Amount of data processing that has been
				applied to the data"
			verbLevel="10" note="calib">
			<values>
				<option>0</option>
				<option>1</option>
				<option>2</option>
				<option>3</option>
			</values>
			<property name="std">1</property>
		</column>

		<meta name="note" tag="calib">
			The calib_level flag takes the following values:

			=== ===========================================================
			 0  Raw Instrumental data requiring instrument-specific tools
			 1  Instrumental data processable with standard tolls
			 2  Calibrated, science-ready data without instrument signature
			 3  Enhanced data products (e.g., mosaics)
			=== ===========================================================
		</meta>

		<column name="obs_collection" type="text"
				utype="obscore:dataid.collection" ucd="meta.id"
				description="Name of a data collection (e.g., project name) this
					data belongs to"
				verbLevel="15">
			<property name="std">1</property>
		</column>

		<column name="obs_id" type="text" 
			utype="obscore:dataid.creatordid" ucd="meta.id"
			description="Unique identifier for an observation"
			verbLevel="5">
			<property name="std">1</property>
		</column>

		<column name="obs_title" type="text"
			utype="obscore:dataid.title" ucd="meta.title;meta.dataset"
			description="Free-from title of the data set"
			verbLevel="5"/>

		<column name="obs_publisher_did" type="text"
			utype="obscore:curation.publisherdid" ucd="meta.ref.url;meta.curation"
			description="Dataset identifier assigned by the publisher."
			verbLevel="5">
			<property name="std">1</property>
		</column>

		<column name="obs_creator_did" type="text"
			utype="obscore:curation.creatordid" ucd="meta.id"
			description="Dataset identifier assigned by the creator."
			verbLevel="15"/>

		<column name="access_url" type="text"
			utype="obscore:access.reference" ucd="meta.ref.url"
			description="The URL at which to obtain the data set."
			verbLevel="1">
			<property name="std">1</property>
		</column>

		<column name="access_format" type="text"
			description="MIME type of the resource at access_url"
			utype="obscore:access.format" ucd="meta.id;class"
			verbLevel="5">
			<property name="std">1</property>
		</column>

		<column name="access_estsize" type="bigint"
			description="Estimated size of data product"
			unit="kB" utype="obscore:access.size" ucd="phys.size;meta.file"
			verbLevel="5">
			<property name="std">1</property>
		</column>

		<column name="target_name" type="text" 
			description="Object a targeted observation targeted"
			utype="obscore:target.name" ucd="meta.id;src"
			verbLevel="15">
			<property name="std">1</property>
		</column>

		<column name="target_class" type="text" 
			description="Class of the target object (star, QSO, ...)"
			utype="obscore:target.name" ucd="src.class"
			verbLevel="20">
			<property name="std">1</property>
		</column>

		<column name="s_ra" type="double precision"
			description="RA of (center of) observation, ICRS"
			unit="deg"  ucd="pos.eq.ra"
			utype="obscore:char.spatialaxis.coverage.location.coord.position2d.value2.c1"
			verbLevel="1">
			<property name="std">1</property>
		</column>
																					 
		<column name="s_dec" type="double precision"
			description="Dec of (center of) observation, ICRS"
			unit="deg" ucd="pos.eq.dec"
			utype="obscore:char.spatialaxis.coverage.location.coord.position2d.value2.c2"
			verbLevel="1">
			<property name="std">1</property>
		</column>

		<column name="s_fov" type="double precision"
			description="Approximate spatial extent for the region covered by the
				observation"
			unit="deg" ucd="phys.angSize;instr.fov"
			utype="obscore:char.spatialaxis.coverage.bounds.extent.diameter"
			verbLevel="5">
			<property name="std">1</property>
		</column>
			
		<column name="s_region" type="spoly"
			description="Region covered by the observation, as a polygon"
			utype="obscore:char.spatialaxis.coverage.support.area" ucd="phys.area;obs"
			verbLevel="15">
			<property name="std">1</property>
		</column>

		<column name="s_resolution" type="double precision"
			description="Best spatial resolution within the data set"
			unit="arcsec"  
			utype="obscore:char.spatialaxis.resolution.refval.cresolution"
			ucd="pos.angResolution"
			verbLevel="15">
			<property name="std">1</property>
		</column>
		
		<column name="t_min" type="double precision"
			description="Lower bound of times represented in the data set, as MJD"
			unit="d" 
			utype="obscore:char.timeaxis.coverage.bounds.limits.interval.starttime"
			ucd="time.start;obs.exposure"
			verbLevel="10">
			<property name="std">1</property>
		</column>
																					 
		<column name="t_max" type="double precision"
			description="Upper bound of times represented in the data set, as MJD"
			unit="d" 
			utype="obscore:char.timeaxis.coverage.bounds.limits.interval.stoptime"
			ucd="time.stop;obs.exposure"
			verbLevel="10">
			<property name="std">1</property>
		</column>

		<column name="t_exptime" type="real"
			description="Total exporure time"
			unit="s" utype="obscore:char.timeaxis.coverage.support.extent"
			ucd="time.duration;obs.exposure"
			verbLevel="10">
			<property name="std">1</property>
		</column>
	 
		<column name="t_resolution" type="real" 
			description="Minimal significant time interval along the time axis"
			unit="s" utype="obscore:char.timeaxis.resolution.refval" ucd="time.resolution"
			verbLevel="15">
			<property name="std">1</property>
		</column>

		<column name="em_min" type="double precision"
			description="Minimal wavelength represented within the data set"
			unit="m" utype="obscore:char.spectralaxis.coverage.bounds.limits.interval.lolimit"
			ucd="em.wl;stat.min"
			verbLevel="10">
			<property name="std">1</property>
		</column>
																			
		<column name="em_max" type="double precision"
			description="Maximal wavelength represented within the data set"
			unit="m" utype="obscore:char.spectralaxis.coverage.bounds.limits.interval.hilimit"
			ucd="em.wl;stat.max"
			verbLevel="10">
			<property name="std">1</property>
		</column>

		<column name="em_res_power" type="double precision"
			description="Spectral resolving power delta lambda/lamda"
			utype="obscore:char.spectralaxis.resolution.resolpower.refval"
			ucd="spec.resolution"
			verbLevel="15">
			<property name="std">1</property>
		</column>

		<column name="o_ucd" type="text"
			description="UCD for the product's observable"
			utype="obscore:char.observableaxis.ucd" ucd="meta.codeucd"
			verbLevel="15">
			<property name="std">1</property>
		</column>
	</table>

	<table id="_obscoresources" onDisk="True" forceUnique="True"
			dupePolicy="overwrite" primary="tableName" system="True">
		<!-- internal table giving strings to be combined into a view creation
		statement.  Those are, in turn, generated by the publish macro.
		-->
		<column name="tableName" type="text"/>
		<column name="sqlFragment" type="text"/>
	</table>

	<data id="makeSources">
		<make table="_obscoresources"/>
	</data>

	<data id="create" auto="False">
		<!-- the view is created from prescriptions in _obscoresources -->
		<make table="ObsCore">
			<script name="create obscore view" type="postCreation" lang="python">
				from gavo import rsc
				ocTable = rsc.TableForDef(table.tableDef.rd.getById("_obscoresources"),
					connection=table.connection)
				parts = ["(%s)"%row["sqlFragment"]
					for row in ocTable.iterQuery(ocTable.tableDef, "")]
				if parts:
					table.query("drop view ivoa.ObsCore")
					table.query("create view ivoa.ObsCore as (%s)"%(
						" UNION ".join(parts)))
					table.updateMeta()
			</script>
		</make>
	</data>

	<!-- a helper script for the publish mixin.  It is added as a postCreation
	script to all makes running on obscore#published tables. -->
	<script id="addTableToObscoreSources" name="addTableToObscore"
			lang="python" type="postCreation">
		obscoreClause = table.tableDef.getProperty("obscoreClause")

		# fix a couple of fields as needed
		for srcRE, replacement in [
			(r"\$COMPUTE AS obs_publisher_did",
				"'ivo://%s/getproduct#' || accref"%base.getConfig('ivoa', 'authority')+
					" AS obs_publisher_did"),
			(r"\$COMPUTE AS access_url",
				"'%s?key=' || accref AS access_url"%
					base.makeAbsoluteURL("/getproduct")),]:
			obscoreClause = re.sub(srcRE, replacement, obscoreClause)

		from gavo import rsc
		ots = rsc.TableForDef(
			base.caches.getRD("//obscore").getById("_obscoresources"),
			connection=table.connection)
		ots.addRow({"tableName": table.tableDef.getQName(),
			"sqlFragment": "SELECT %s FROM %s"%(
				obscoreClause, table.tableDef.getQName())})
	</script>

	<!-- another helper script for the publish mixin that gets added to
	obscore#published tables.  -->
	<script id="removeTableFromObscoreSources" lang="SQL" type="beforeDrop">
		DELETE FROM ivoa._obscoresources WHERE tableName='\qName'
	</script>

	<STREAM id="_publishCommon">
		<doc>
			Common elements for ObsTAP publication mixins.
		</doc>
		<mixinPar name="productSubtype" description="File subtype.  Details
			pending">NULL</mixinPar>
		<mixinPar name="calibLevel" description="Calibration level of data,
			a number between 0 and 3; for details, see obsCore's calib_level
			column.">NULL</mixinPar>
		<mixinPar name="collectionName" description="A human-readable name
			for this collection.  This should be short, so don't just use the
			resource title">NULL</mixinPar>
		<mixinPar name="targetName" description="Name of the target object."
			>NULL</mixinPar>
		<mixinPar name="targetClass" description="Class of target object(s).
			You should take whatever you put here from 
			http://simbad.u-strasbg.fr/guide/chF.htx">NULL</mixinPar>
		<mixinPar name="sResolution" description="The (best) angular
			resolution within the data set, in arcsecs">NULL</mixinPar>
		<mixinPar name="tResolution" description="Temporal resolution"
			>NULL</mixinPar>
		<mixinPar name="emResPower" description="Spectral resolution as
			delta lambda/lambda">NULL</mixinPar>
		<mixinPar name="expTime" description="Total time of event counting.
			This simply is tMax-tMin for simple exposures.">NULL</mixinPar>

		<events>
			<adql>True</adql>
			<property name="obscoreClause">
						\productType AS dataproduct_type,
						\productSubtype AS dataproduct_subtype,
						\calibLevel AS calib_level,
						\collectionName AS obs_collection,
						\obsId AS obs_id,
						\title AS obs_title,
						\did AS obs_publisher_did,
						\creatorDID AS obs_creator_did,
						\accessURL AS access_url,
						\mime AS access_format,
						\size AS access_estsize,
						\targetName AS target_name,
						\targetClass AS target_class,
						\ra AS s_ra,
						\dec AS s_dec,
						\fov AS s_fov,
						\coverage AS s_region,
						\sResolution AS s_resolution,
						\tMin AS t_min,
						\tMax AS t_max,
						\expTime AS t_exptime,
						\tResolution AS t_resolution,
						\emMin AS em_min,
						\emMax AS em_max,
						\emResPower AS em_res_power,
						\oUCD AS o_ucd
			</property>
		</events>

		<processLate>
			<doc>
				Find all data items importing the table and furnish them
				with the scripts necessary to update the obscore view.
			</doc>
			<!-- see //products#hackProductsData for why this is a huge pain in
			the neck and how to get out of this. -->
			<code><![CDATA[
				if not substrate.onDisk:
					raise base.StructureError("Only onDisk tables can be obscore"
						" published, but %s is not."%substrate.id)

				rd = base.caches.getRD("//obscore")
				insertScript = rd.getById("addTableToObscoreSources")
				removeScript = rd.getById("removeTableFromObscoreSources")

				for dd in substrate.rd.iterDDs():
					addDependent = False
					for make in dd.makes:
						if make.table is substrate:
							make.scripts.append(insertScript)
							# the remove script needs to have the right parent
							make.feedObject("script", removeScript.copy(make))
							addDependent = True
					if addDependent:
						dd.dependents.append("//obscore#create")
			]]></code>
		</processLate>
	</STREAM>

	<STREAM id="_publishProduct">
		<doc>
			publish mixin parameters deriving from products#table interface
			fields.
		</doc>
		<mixinPar name="obsId" description="Identifier of the data set.  
			Only change this when you do not mix in products."
			>accref</mixinPar>
		<mixinPar name="did" description="Global identifier of the data set.  
			Leave $COMPUTE for tables mixing in products.">$COMPUTE</mixinPar>
		<mixinPar name="creatorDID" description="Global identifier of the
			data set assigned by the creator.  Leave NULL unless the creator
			actually assigned an IVO id himself.">NULL</mixinPar>
		<mixinPar name="accessURL" description="URL at which the product
			can be obtained.  Leave at $COMPUTE for tables mixing in products."
			>$COMPUTE</mixinPar>
		<mixinPar name="mime" description="The MIME type of
			the product file.  Only touch if you do not mix in products."
			>mime</mixinPar>
		<mixinPar name="size" description="The estimated size of the product
			 in kilobytes.  Only touch when you do not mix in products#table."
			>accsize/1024</mixinPar>
	</STREAM>

	<mixinDef id="publish">
		<doc>
			Publish this table to ObsTAP.

			This means mapping or giving quite a bit of data from the present
			table to ObsCore rows.  Internally, this information is converted
			to an SQL select statement used within a create view statement.
			In consequence, you must give *SQL* expression in the parameter 
			values; or just naked column names from your input table are ok,
			of course.  Most parameters are set to NULL or appropriate
			defaults for tables mixing in //products#table.

			Since the mixin generates script elements, it cannot be used
			in untrusted RDs.  The fact that you can enter raw SQL also
			means you will get ugly error messages if you give invalid
			parameters.

			Some items are filled from product interface fields automatically.
			You must change these if you obscore-publish tables noch mixin
			in products.
		</doc>
		<mixinPar name="productType" description="Data product type; one
			of image, cube, spectrum, sed, timeseries, visibility, event, or
			NULL if None of the above"/>
		<mixinPar name="title" description="A human-readable title
			of the data set.">NULL</mixinPar>
		<mixinPar name="ra" description="Center RA">NULL</mixinPar>
		<mixinPar name="dec" description="Center Dec">NULL</mixinPar>
		<mixinPar name="fov" 
			description="Approximate diameter of region covered">NULL</mixinPar>
		<mixinPar name="coverage" description="A polygon giving the
			spatial coverage of the data set; this must always be in
			ICRS.  Instead of an SPOLY other pgsphere areas might work, too."
			>NULL</mixinPar>
		<mixinPar name="tMin" description="MJD for the lower bound of
			times covered in the data set (e.g. start of exposure).  Use
			to_char(COLUMN, 'J')::double precision-2400000.5 to get this
			from a postgres timestamp.">NULL</mixinPar>
		<mixinPar name="tMax" description="MJD for the upper bound of
			times covered in the data set.  See tMin">NULL</mixinPar>
		<mixinPar name="emMin" description="Lower bound of wavelengths
			represented in the data set, in meters.">NULL</mixinPar>
		<mixinPar name="emMax" description="Upper bound of wavelengths
			represented in the data set, in meters.">NULL</mixinPar>
		<mixinPar name="oUCD" description="UCD of the observable quantity, 
			e.g., em.opt for wide-band optical frames.">NULL</mixinPar>

		<LFEED source="_publishProduct"/>
		<LFEED source="_publishCommon"/>
	</mixinDef>

	<mixinDef id="publishSIAP">
		<doc>
			Publish a PGS SIAP table to ObsTAP.

			This works like //obscore#publish except some defaults apply
			that copy fields that work analoguously in SIAP and in ObsTAP.

			For special situations, you can, of course, override any
			of the parameters, but most of them should already be all right.
			To find out what the parameters described as "preset for SIAP"
			mean, refer to //obscore#publish.
		</doc>
		
		<mixinPar name="productType" description="preset for SIAP"
			>'image'</mixinPar>
		<mixinPar name="title" description="preset for SIAP"
			>imageTitle</mixinPar>
		<mixinPar name="ra" description="preset for SIAP">centerAlpha</mixinPar>
		<mixinPar name="dec" description="preset for SIAP">centerDelta</mixinPar>
		<mixinPar name="fov" description="preset for SIAP; we use the
			extent along the X axis as a very rough estimate for the size.
			If you can do better, by all means do."
			>pixelScale[1]*pixelSize[1]</mixinPar>
		<mixinPar name="coverage" description="preset for SIAP; TODO: use coverage
		here (this does not work right now since postgres can 'not identify an ordering
		operator for type spoly'; figure out what's wrong)"
			>NULL</mixinPar>
		<mixinPar name="tMin" description="preset for SIAP; if you want,
			change this to start of observation as available."
			>(to_char(dateObs, 'J')::double precision-2400000.5)</mixinPar>
		<mixinPar name="tMax" description="preset for SIAP; if you want,
			change this to end of observation as available."
			>(to_char(dateObs, 'J')::double precision-2400000.5)</mixinPar>
		<mixinPar name="emMin" description="preset for SIAP"
			>bandpassLo</mixinPar>
		<mixinPar name="emMax" description="preset for SIAP"
			>bandpassHi</mixinPar>
		<mixinPar name="oUCD" description="preset for SIAP; fix if you either
			know more about the band of if your images are not in the optical."
			>'em.opt'</mixinPar>

		<LFEED source="_publishProduct"/>
		<LFEED source="_publishCommon"/>

	</mixinDef>
</resource>
