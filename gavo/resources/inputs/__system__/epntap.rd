<?xml version="1.0" encoding="iso-8859-1"?>

<resource schema="__system">
	<STREAM id="_minmax">
		<doc>
			Generates a pair of minimum/maximum column pairs.  You must
			fill out basename, baseucd, basedescr, unit, and possibly type.
		</doc>
		<DEFAULTS type="real"/>
		<column name="\basename\+min" type="\type"
			ucd="\baseucd;stat.min" unit="\unit"
			description="\basedescr, lower limit."
			utype="\baseutype\+min">
			<property key="std">1</property>
		</column>
		<column name="\basename\+max" type="\type"
			ucd="\baseucd;stat.max" unit="\unit"
			description="\basedescr, upper limit"
			utype="\baseutype\+max">
			<property key="std">1</property>
		</column>
	</STREAM>

 	<STREAM id="v037columns">
		<doc>
			Colums that are deprecated in the version 2.0 of EPN-TAP parameters 	
		</doc>

		<!-- for cn, the naming scheme is different from v2 -->
		<FEED source="_minmax"
			basename="c1_"
			baseucd="pos.stat" unit="\c1unit"
			baseutype="Epn.Spatial.Spatial_range.c1_"
			basedescr="First coordinate (e.g., longitude, 'x', or right ascension)"/>
		<FEED source="_minmax"
			basename="c2_"
			baseucd="pos.stat" unit="\c2unit"
			baseutype="Epn.Spatial.Spatial_range.c2_"
			basedescr="Second coordinate (e.g., latitude, 'y', or declination)"/>
		<FEED source="_minmax"
			basename="c3_"
			baseucd="pos.stat" unit="\c3unit"
			baseutype="Epn.Spatial.Spatial_range.c3_"
			basedescr="Third coordinate (e.g., height, 'z', or distance)"/>

		<column name="index_" type="bigint" required="True"
			ucd="meta.id" description="Numeric identifier (like a record number) 
				of this row.">
			<property key="std">1</property>
		</column>

		<column name="resource_type" type="text" 
			utype="Epn.ResourceType" ucd="meta.id;class" 
			description="'granule' if the row describes a smallest 
				element reachable
				in a service (e.g., a file), or 'dataset' for an aggregate
				of granules.">
			<property key="std">1</property>
			<values>
				<option>dataset</option>
				<option>granule</option>
			</values>
		</column>

		<column name="dataset_id" type="text"
			ucd="meta.id;meta.dataset"
			description="An identifier for the dataset this granule belongs to.">
			<property key="std">1</property>
		</column>

		<FEED source="_minmax"
			basename="sampling_step_" type="double precision"
			baseucd="em.freq.step" unit="Hz"
			baseutype="Epn.Spectral.Spectral_sampling_step_"
			basedescr="Separation between the centers of two adjacent filters or channels"/>

		<column name="reference"	type="text" 
			ucd="meta.bib" 
			description="A bibcode or URL of a publication about the data.">
			<property key="std">1</property>
		</column>

		<column name="collection_id" type="text"
			ucd="meta.id"
			description="Identifier of the collection this piece of data belongs to">
			<property key="std">1</property>
		</column>

		<column name="preview_url" type="text" 
			ucd="meta.ref.url"
			description="URL to retrieve a preview of the data"
			displayHint="type=url">
			<property key="std">1</property>
		</column>

		<param name="processing_level" type="integer"
			utype="PSR:processingLevel"
			ucd="meta.code;obs.calib"
			description="Calibration level with coded according to CODMAC."
			note="et_cal">
			<property key="std">1</property>\\processing_level</param>
	</STREAM>
	
	<STREAM id="v20columns">
		<doc>
			New columns introduced by the version 2.0 of EPN-TAP parameters
		</doc>

		<!-- for cn, the naming scheme is different from v0.37 -->
		<FEED source="_minmax"
			basename="c1"
			baseucd="obs.field" unit="\c1unit"
			baseutype="Epn.Spatial.Spatial_range.c1."
			basedescr="First coordinate (e.g., longitude, 'x', or right ascension)"/>
		<FEED source="_minmax"
			basename="c2"
			baseucd="obs.field" unit="\c2unit"
			baseutype="Epn.Spatial.Spatial_range.c2."
			basedescr="Second coordinate (e.g., latitude, 'y', or declination)"/>
		<FEED source="_minmax"
			basename="c3"
			baseucd="obs.field" unit="\c3unit"
			baseutype="Epn.Spatial.Spatial_range.c3."
			basedescr="Third coordinate (e.g., height, 'z', or distance)"/>

		<column name="granule_uid" type="text" 
			ucd="meta.id" description="Unique ID in data service, aplphanumeric identifier 
				(like a record number) of this row.">
			<property key="std">1</property>
		</column>

		<column name="granule_gid" type="text"
			ucd="meta.id"
			description="Common to granules of the same type, in order to distinguish different files relative to the same data.">
			<property key="std">1</property>
		</column>	 

		<column name="obs_id" type="text"
			ucd="meta.id"
			description="Common to granules derived from the same data, may be the ID of original observation">
			<property key="std">1</property>
		</column>	 

		<FEED source="_minmax"
			basename="spectral_sampling_step_" type="double precision"
			baseucd="em.freq.step" unit="Hz"
			baseutype="Epn.Spectral.Spectral_sampling_step_"
			basedescr="Separation between the centers of two adjacent filters or channels"/>

		<column name="creation_date" type="date"
			ucd="time.creation"
			description="Date of first entry of the granule">
			<property key="std">1</property>
		</column>	 
		
		<column name="modification_date" type="date"
			ucd="time.update"
			description="Date of the last modification">
			<property key="std">1</property>
		</column>	 

		<column name="release_date" type="date"
			ucd="time.release"
			description="Start of public access period (set to creation_date if no
				proprietary period)">
			<property key="std">1</property>
		</column>	 

		<column name="s_region" type="\\regiontype"
			ucd="phys.outline;obs.field"
			description="ObssCore-like footprint, valid for celestial or body-fixed frames">
			<property key="std">1</property>
		</column>	 

		<column name="thumbnail_url"	type="text" 
			ucd="meta.ref.url;meta.file" 
			description="URL of a thumbnail image with predefined size (png ~200pix)">
			<property key="std">1</property>
		</column>

		<column name="species"	type="text" 
			ucd="meta.id;phys.atmol" 
			description="Identify a chemical species">
			<property key="std">1</property>
		</column>

		<column name="alt_target_name"	type="text" 
			ucd="meta.id;src" 
			description="Alternative name for the target">
			<property key="std">1</property>
		</column>

		<column name="feature_name"	type="text" 
			ucd="meta.id;pos" 
			description="Secondary name">
			<property key="std">1</property>
		</column>

		<column name="bib_reference"	type="text" 
			ucd="meta.bib" 
			description="A bibcode or URL of a publication about the data.">
			<property key="std">1</property>
		</column>

		<column name="spatial_coordinate_description"	type="text" 
			ucd="meta.code.class;pos.frame" 
			description="ID or specific coordinate system and version">
			<property key="std">1</property>
		</column>

		<column name="spatial_origin"	type="text" 
			ucd="meta.ref;pos.frame" 
			description="Defines the frame origin">
			<property key="std">1</property>
		</column>

		<column name="time_origin"	type="text" 
			ucd="meta.ref;time.scale" 
			description="Defines where the time is measured">
			<property key="std">1</property>
		</column>

		<column name="file_name"	type="text" 
			ucd="meta.id;meta.file" 
			description="Name of the file only">
			<property key="std">1</property>
		</column>

		<FEED source="_minmax"
			basename="time_exp_" type="double precision"
			baseucd="time.duration;obs.exposure" unit="s"
			baseutype="Epn.Time.Time_exp_"
			basedescr="Integration time of the measurement"/>
	</STREAM>

	<STREAM id="commoncolumns">
		<doc>Columns common to versions 0.37 and 2.0</doc>

		<!-- this is for DaCHS-internal bookkeeping; this means we
		have two links to the data, but for now that's a small price to 
		pay -->
		<column name="accref" original="//products#products.accref"/>

		<column name="dataproduct_type"	type="text" 
			ucd="meta.code.class" utype="Epn.dataProductType"
			description="The high-level organization of the data product
				described (image, spectrum, etc)"
			note="et_prod">
			<property key="std">1</property>
			<values>
				<option>im</option>
				<option>sp</option>
				<option>ds</option>
				<option>sc</option>
				<option>pr</option>
				<option>vo</option>
				<option>mo</option>
				<option>cu</option>
				<option>ts</option>
				<option>ca</option>
				<option>sv</option>
			</values>
		</column>

		<column name="target_name"	type="text" 
			ucd="meta.id;src" utype="Epn.TargetName"
			description="The name of the target of the observation, or a
				suitable id.">
			<property key="std">1</property>
		</column>
		
		<column name="target_class"	type="text" 
			ucd="meta.code.class;src"  utype="Epn.TargetClass"
			description="Type of target (from a controlled vocabulary)">
			<property key="std">1</property>
			<values>
				<option>asteroid</option>
				<option>dwarf_planet</option>
				<option>planet</option>
				<option>satellite</option>
				<option>comet</option>
				<option>exoplanet</option>
				<option>interplanetary_medium</option>
				<option>ring</option>
				<option>sample</option>
				<option>sky</option>
				<option>spacecraft</option>
				<option>spacejunk</option>
				<option>star</option>
			</values>
		</column>

		<column name="processing_level" type="integer"
			utype="PSR:processingLevel"
			ucd="meta.code;obs.calib"
			description="Calibration level with coded according to CODMAC."
			note="et_cal">
			<values nullLiteral="-1"/>
			<property key="std">1</property>
		</column>  

		<!-- time doesn't use not _minmax because ucds and utypes
		are irregular -->

		<column name="time_min"  type="double precision"
			ucd="time.start" unit="d"
			utype=" Char.TimeAxis.Coverage.Bounds.Limits.Interval.StartTime"
			description="Acquisition start time (as JD)"/>
		<column name="time_max"  type="double precision"
			ucd="time.end" unit="d"
			utype="Char.TimeAxis.Coverage.Bounds.Limits.Interval.StopTime"
			description="Acquisition stop time (as JD)"/>

		<FEED source="_minmax" 
			basename="time_sampling_step_"
			baseucd="time.interval" unit="s" type="double precision"
			baseutype="Epn.Time.Time_sampling_step_"
			basedescr="Sampling time for measurements of dynamical
				phenomena"/>
		<FEED source="_minmax"
			basename="time_exp_" type="double precision"
			baseucd="time.duration;obs.exposure_" unit="s"
			baseutype="Epn.Time.Time_exp"
			basedescr="Integration time of the measurement"/>
		<FEED source="_minmax"
			basename="spectral_range_" type="double precision"
			baseucd="em.freq" unit="Hz"
			baseutype="Epn.Spectral.Spectral_range_"
			basedescr="Spectral domain of the data"/>
		<FEED source="_minmax"
			basename="spectral_resolution_" type="double precision"
			baseucd="spect.resolution" unit="Hz"
			baseutype="Epn.Spectral.Spectral_resolution_"
			basedescr="FWHM of the instrument profile"/>
		<FEED source="_minmax"
			basename="c1_resol_" type="double precision"
			baseucd="pos.resolution" unit="\c1unit"
			baseutype="Epn.Spatial.Spatial_resolution.c1_resol_"
			basedescr="Resolution in the first coordinate"/>
		<FEED source="_minmax"
			basename="c2_resol_" type="double precision"
			baseucd="pos.resolution" unit="\c2unit"
			baseutype="Epn.Spatial.Spatial_resolution.c2_resol_"
			basedescr="Resolution in the second coordinate"/>
		<FEED source="_minmax"
			basename="c3_resol_" type="double precision"
			baseucd="pos.resolution" unit="\c3unit"
			baseutype="Epn.Spatial.Spatial_resolution.c3_resol_"
			basedescr="Resolution in the third coordinate"/>

		<column name="spatial_frame_type"	type="text" 
			ucd="meta.code.class;pos.frame"
			description="Flavor of coordinate system, also defining 
				the nature of coordinates"/>

		<FEED source="_minmax"
			basename="incidence_" type="double precision"
			baseucd="pos.posAng" unit="deg"
			baseutype="Epn.View_angle.Incidence_angle_"
			basedescr="Incidence angle (solar zenithal angle) during 
				data acquisition"/>
		<FEED source="_minmax"
			basename="emergence_" type="double precision"
			baseucd="pos.posAng" unit="deg"
			baseutype="Epn.View_angle.Emergence_angle_"
			basedescr="Emergence angle during data acquisition"/>
		<FEED source="_minmax"
			basename="phase_" type="double precision"
			baseucd="pos.phaseAng" unit="deg"
			baseutype="Epn.View_angle.Phase_angle_"
			basedescr="Phase angle during data acquisition"/>

		<column name="instrument_host_name"	type="text" 
			ucd="meta.id;instr.obsty"
			utype="Provenance.ObsConfig.Facility.name"
			description="Name of the observatory or spacecraft that performed the measurements.">
			<property key="std">1</property>
		</column>

		<column name="instrument_name"	type="text" 
			ucd="meta.id;instr" 
			utype="Provenance.ObsConfig.Instrument.name"
			description="Instrument used to acquire the data.">
			<property key="std">1</property>
		</column>

		<column name="measurement_type"	type="text" 
			ucd="meta.ucd" 
			utype="Epn.Measurement_type"
			description="UCD(s) defining the data, with multiple entries separated by space characters.">
			<property key="std">1</property>
		</column>

		<column name="publisher"	type="text" 
			ucd="meta.name" 
			description="A short string identifying the entity running the data service used.">
			<property key="std">1</property>
		</column>

		<column name="service_title"	type="text" 
			ucd="meta.title" 
			description="The title of the data service producing this row.(an acronym really, will 
				be used to handle multiservice results)">
			<property key="std">1</property>
		</column>

		<column name="access_url"	type="text" 
			ucd="meta.ref.url;meta.file" utype="Obs.Access.Reference"
			description="URL to retrieve the data product described."
			displayHint="type=url">
			<property key="std">1</property>
		</column>

		<column name="access_format"	type="text"
			ucd="meta.code.mime" utype="Obs.Access.Format"
			description="Format of the file containing the data.">
			<property key="std">1</property>
		</column>

		<column name="access_estsize"	type="integer"
			ucd="phys.size;meta.file" unit="kbyte"
			utype="Obs.Access.Size"
			description="Estimated size of the data product.">
			<property key="std">1</property>
			<values nullLiteral="-1"/>
		</column>

		<column name="access_md5" type="text"
			ucd="meta.checsum;meta.file"
			description="MD5 hash of the file content.">
			<property key="std">1</property>
		</column>

		<column name="target_region"	type="text" 
			ucd="obs.field" 
			description="The part of the target object that was being observed, 
				type of region of interest">
			<property key="std">1</property>
		</column>

		<column name="time_scale"	type="text" 
			ucd="time.scale" 
			description="Time scale as defined by the IVOA STC Data model."/>

		<meta name="note" tag="et_prod">
			The following values are defined for this field:

			image
				associated scalar fields with two spatial axes, e.g., images with
				multiple color planes like from multichannel cameras for example.
				Maps of planetary surfaces are considered as images.
			spectrum
				data product which spectral coverage is the primary attribute, e.g.,
				a set of spectra.
			dynamic_spectrum
				consecutive spectral measurements through time, organized as a time
				series.
			spectral_cube
				sets of spectral measurements with 1 or 2 D spatial coverage, e.g.,
				imaging spectroscopy. The choice between Image and spectral_cube is
				related to the characteristics of the instrument .
			profile
				scalar or vectorial measurements along 1 spatial dimension, e.g.,
				atmospheric profiles, atmospheric paths, sub-surface profiles…
			volume
				other measurements with 3 spatial dimensions, e.g., internal or
				atmospheric structures.
			movie
				sets of chronological 2 D spatial measurements
			cube
				multidimensional data with 3 or more axes, e.g., all that is not
				described by other 3 D data types such as spectral cubes or volume.
			time_series
				measurements organized primarily as a function of time (with
				exception of dynamical spectra) . A Spacecraft dust detect or
				measurement is a typical example of a time series.
			catalog 
				can be a list of events, a catalog of object parameters, a list of f
				eatures... It can be limited to scalar quantities, and possibly
				limited to a single element. E.g., a list of asteroid properties.
				Time_series, Profile, and Catalog are essentially tables of scalar
				values. In Time_series the primary key is time; in Profile it is
				altitude or distance; in Catalog, it may be a qualitative parameter
				(name, ID...) .
			spatial_vector
				list of summit coordinates defining a vector, e.g., vector
				information from a GIS, spatial footprints...
		</meta>

		<meta name="note" tag="et_cal">
			CODMAC levels are:

			1 -- Raw (UDR in PDS)

			2 -- Edited (EDR in PDS, NASA level 0)

			3 -- Calibrated (RDR in PDS, NASA Level 1A)

			4 -- Resampled (REFDR in PDS, NASA Level 1B)

			5 -- Derived (DDR in PDS, NASA Level 3)

			6 -- Ancillary (ANCDR in PDS)
		</meta>
	</STREAM>

	<mixinDef id="table">
		<doc><![CDATA[
			This mixin defines a table suitable for publication via the
			EPN-TAP protocol, version 0.37.  For new services, use something
			newer (as of this writing, //epntap#table-2_0).

			According to the standard definition, tables mixing this in
			should be called ``epn_core``.  The mixin already arranges
			for the table to be accessible by ADQL and be on disk.

			This also causes the product table to be populated.
			This means that grammars feeding such tables need a 
			`//products#define`_ row filter.  At the very least, you need to say::

				<rowfilter procDef="//products#define">
					<bind name="table">"\schema.epn_core"</bind>
				</rowfilter>

			Use the `//epntap#populate`_ apply in rowmakers
			feeding tables mixing this in.
		]]></doc>

		<mixinPar key="c1unit" description="Unit of the first spatial
			coordinate">deg</mixinPar>
		<mixinPar key="c2unit" description="Unit of the second spatial
			coordinate">deg</mixinPar>
		<mixinPar key="c3unit" description="Unit of the third spatial
			coordinate">__EMPTY__</mixinPar>
		<mixinPar key="spectralUCD" description="UCD of the spectral
			axis (ignored for version 2.0">
			>em.freq</mixinPar>
		<mixinPar key="processing_level" description="How processed is the
			data?  This is a numerical code explained in the corresponding
			table footnote.  In short: 1 -- Raw; 2 -- Edited; 3 -- Calibrated;
			4 -- Resampled; 5 -- Derived; 6 -- Ancillary"/>

		<events>
			<adql>True</adql>
			<onDisk>True</onDisk>
			<meta name="utype">ivo://ivoa.net/std/epntap#table-1.0</meta>

			<meta name="info" infoName="SERVICE_PROTOCOL" 
				infoValue="0.37">EPN-TAP</meta>

			<FEED source="commoncolumns"/>
			<FEED source="v037columns"/>
		</events>

		<FEED source="//products#hackProductsData"/>
	</mixinDef>

	<mixinDef id="table-2_0">
		<doc><![CDATA[
			This mixin defines a table suitable for publication via the
			EPN-TAP protocol, version 2.0.

			According to the standard definition, tables mixing this in
			should be called ``epn_core``.  The mixin already arranges
			for the table to be accessible by ADQL and be on disk.

			This also causes the product table to be populated.
			This means that grammars feeding such tables need a 
			`//products#define`_ row filter.  At the very least, you need to say::

				<rowfilter procDef="//products#define">
					<bind name="table">"\schema.epn_core"</bind>
				</rowfilter>

			Use the `//epntap#populate`_ apply in rowmakers
			feeding tables mixing this in.

			See https://voparis-confluence.obspm.fr/display/VES/EPN-TAP+V2.0+parameters
			for more information on EPN-TAP.
		]]></doc>

		<mixinPar key="c1unit" description="Unit of the first spatial
			coordinate">deg</mixinPar>
		<mixinPar key="c2unit" description="Unit of the second spatial
			coordinate">deg</mixinPar>
		<mixinPar key="c3unit" description="Unit of the third spatial
			coordinate">__EMPTY__</mixinPar>
		<mixinPar key="regiontype" description="Type of the
			s_region column.  This can be spoly (the default), scircle,
			sbox (a coordinate range) or possibly spoint (avoid that, though)."
			>spoly</mixinPar>

		<events>
			<adql>True</adql>
			<onDisk>True</onDisk>
			<meta name="utype">ivo://ivoa.net/std/epntap#table-1.0</meta>

			<meta name="info" infoName="SERVICE_PROTOCOL" 
				infoValue="2.0">EPN-TAP</meta>

			<FEED source="commoncolumns"/>
			<FEED source="v20columns"/>
		</events>

		<FEED source="//products#hackProductsData"/>
	</mixinDef>

	<NXSTREAM id="procDefTemplate">	
		<doc>A stream to define the populate-type applys.  This needs
		procname (of the apply being made), mixinid, and version (of
		the EPN-TAP table built) FEED arguments.
		</doc>

		<procDef type="apply" id="\procname">
			<doc>
				Sets metadata for an epntap version \version data set, including 
				its products definition.

				The values are left in vars, so you need to do manual copying,
				e.g., using idmaps="*".
			</doc>

			<setup>
				<par key="index_" description="A numeric reference for the
					item.  By default, this is just the row number.  As this will
					(usually) change when new data is added, you should override it
					with some unique integer number specific to the data product 
					when there is such a thing." late="True">\\rowsMade</par>
				<par key="dataset_id" description="Unless you understand the
					implications, leave this at the default.  In particular, note
					that this is *not* a dataset id in the VO sense, so this should
					normally not be whatever standardPubDID generates."
					late="True">"1"</par>
				<par key="target_name" description="Name of the target object,
					preferably according to the official IAU nomenclature.
					As appropriate, take these from the exoplanet encyclopedia
					http://exoplanet.eu, the meteor catalog at 
					http://www.lpi.usra.edu/meteor/, the catalog of stardust
					samples at http://curator.jsc.nasa.gov/stardust/catalog/" 
					late="True"/>
				<par key="time_scale" description="Time scale used for the
					various times, as given by IVOA's STC data model.  Choose
					from TT, TDB, TOG, TOB, TAI, UTC, GPS, UNKNOWN" 
					late="True">"UNKNOWN"</par>
				<par key="spatial_frame_type" description="Flavor of the
					coordinate system (this also fixes the meanings of c1, c2, and
					c3).  Values defined by EPN-TAP include celestial, body,
					cartesian, cylindrical, spherical, healpix." late="True"/>
				<par key="instrument_host_name" description="Name of the observatory
					or spacecraft that the observation originated from; for
					ground-based data, use IAU observatory codes, 
					http://www.minorplanetcenter.net/iau/lists/ObsCodesF.html,
					for space-borne instruments use
					http://nssdc.gsfc.nasa.gov/nmc/" late="True"/>
				<par key="instrument_name" description="Service providers are
					invited to include multiple values for instrumentname, e.g.,
					complete name + usual acronym. This will allow queries on either
					'VISIBLE AND INFRARED THERMAL IMAGING SPECTROMETER' or VIRTIS to
					produce the same reply." late="True">None</par>
				<par key="access_format" description="The standard text proposes
					the standard names VOTable, Fits, CSV, ASCII, PDS, as well as
					image formats." late="True"/>
				<par key="target_region" description="This is a complement to the
					target name to identify a substructure of the target that was
					being observed (e.g., Atmosphere, Surface).  Take terms from
					them Spase dictionary at http://www.spase-group.org or the
					IVOA thesaurus." late="True">None</par>
				<par key="target_class" description="The type of the target;
					choose from asteroid, dwarf_planet, planet, satellite, comet, 
					exoplanet, interplanetary_medium, ring, sample, sky, spacecraft, 
					spacejunk, star" late="True">"UNKNOWN"</par>
				<par key="processing_level" description=" CODMAC calibration level
					(ignored for version 0.37)" late="True">0</par>

				<!-- Note: only late parameters allowed in here.  Also, don't
				define anything here unless you have to; we pick up the
				columns from the mixin's stream automatically. -->

				<!-- if you add more manual parameters, make sure you list them
				in overridden below -->

				<LOOP>
					<codeItems>
						# overridden is a set of column names for which the parameters
						# are manually defined above
						overridden = set(["target_name", "time_scale",
							"spatial_frame_type", "instrument_host_name", "instrument_name",
							"access_format", "target_region", "processing_level",
							"target_class", "index_", "dataset_id", 
							# the following are set via products#define
							"access_estsize", "access_url", "accref",
							"preview_url",])

						mixin = context.getById("\mixinid")
						colDict = {}
						for type, name, content, pos in mixin.events.events_:
							if type=="value":
								colDict[name] = content
							elif type=="end":
								if name=="column":
									if colDict.get("name") not in overridden:
										yield colDict
									colDict = {}
					</codeItems>
					<events>
						<par key="\\name" description="\\description"
							late="True">None</par>
					</events>
				</LOOP>
				<code>
					# find myself to get the list of my parameters
					for app in parent.apps:
						if app.procDef and app.procDef.id=='\procname':
							break
					else:
						raise base.Error("Internal: epntap#\procname cannot find itself")

					EPNTAP_KEYS = [p.key for p in app.procDef.setups[0].pars]
					del app
					del p
				</code>
			</setup>
			<code>
				l = locals()
				for key in EPNTAP_KEYS:
					vars[key] = l[key]
				
				# map things from products#define
				vars["access_estsize"] = vars["prodtblFsize"]/1024
				vars["access_url"] = makeProductLink(vars["prodtblAccref"])
				if @prodtblPreview:
					vars["preview_url"] = @prodtblPreview
				vars["accref"] = vars["prodtblAccref"]
			</code>
		</procDef>
	</NXSTREAM>

	<FEED source="procDefTemplate" procname="populate" version="0.37"
		mixinid="table"/>
	<FEED source="procDefTemplate" procname="populate-2_0" version="2.0"
		mixinid="table-2_0"/>
</resource>
