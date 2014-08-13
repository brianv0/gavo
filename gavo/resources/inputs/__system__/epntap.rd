<?xml version="1.0" encoding="iso-8859-1"?>

<resource schema="__system">
	<STREAM id="_minmax">
		<doc>
			Generates a pair of minimum/maximum column pairs.  You must
			fill out basename, baseucd, basedescr, unit.
		</doc>
		<column name="\basename\+_min"
			ucd="\baseucd;stat.min" unit="\unit"
			description="\basedescr, lower limit.">
			<property key="std">1</property>
		</column>
		<column name="\basename\+_max"
			ucd="\baseucd;stat.max" unit="\unit"
			description="\basedescr, upper limit">
			<property key="std">1</property>
		</column>
	</STREAM>

	<mixinDef id="table">
		<doc>
			This mixin defines a table suitable for publication via the
			EPN-TAP protocol.
		</doc>
		<mixinPar key="c1unit" description="Unit of the first spatial
			coordinate">deg</mixinPar>
		<mixinPar key="c2unit" description="Unit of the second spatial
			coordinate">deg</mixinPar>
		<mixinPar key="c3unit" description="Unit of the third spatial
			coordinate">__EMPTY__</mixinPar>
		<mixinPar key="spectralUCD" description="UCD of the spectral
			axis; this must be one of em.freq (for electromagnetic
			radiation) or phys.energy;phys.part (for particles)"
			>em.freq</mixinPar>
		<events>
			<meta name="info" infoName="SERVICE_PROTOCOL" 
				infoValue="0.26">EPN-TAP</meta>

			<column name="resource_type" type="text" 
				utype="Epn.ResourceType" ucd="meta.id;class" 
				description="This can be 'granule' the smallest element reachable
					in a service (e.g., a file), or 'dataset', which is an aggregate
					of granules.">
				<property key="std">1</property>
				<values>
					<option>dataset</option>
					<option>granule</option>
				</values>
			</column>

			<column name="dataproduct_type"	type="text" 
				ucd="meta.id;class" utype="Epn.dataProductType"
				description="The high-level organization of the data product
					described (image, spectrum, etc)"
				note="et_prod">
				<property key="std">1</property>
				<values>
					<option>image</option>
					<option>spectrum</option>
					<option>dynamic_spectrum</option>
					<option>spectral_cube</option>
					<option>profile</option>
					<option>volume</option>
					<option>movie</option>
					<option>cube</option>
					<option>time_series</option>
					<option>catalog</option>
					<option>spatial_vector</option>
				</values>
			</column>

			<column name="target_name"	type="text" 
				ucd="meta.id;src" utype="Epn.TargetName"
				description="The name of the target of the observation, or a
					suitable id.">
				<property key="std">1</property>
			</column>
			
			<column name="target_class"	type="text" 
				ucd="src.class"  utype="Epn.TargetClass"
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

			<!-- time doesn't use not _minmax because ucds and utypes
			are irregular -->
			<column name="time_min" 
				ucd="time.start;obs.exposure" unit="d"
				utype=" Char.TimeAxis.Coverage.Bounds.Limits.Interval.StartTime"
				description="Acquisition start time (as JD)"/>
			<column name="time_max" 
				ucd="time.stop;obs.exposure" unit="d"
				utype="Char.TimeAxis.Coverage.Bounds.Limits.Interval.StopTime"
				description="Acquisition stop time (as JD)"/>
			<column name="time_scale"	type="text" 
				ucd="time.scale" 
				description="Time scale as defined by the IVOA STC Data model."/>

			<FEED source="_minmax"
				basename="t_sampling_step"
				baseucd="time.interval" unit="s"
				basedescr="Sampling time for measurements of dynamical
					phenomena"/>
			<FEED source="_minmax"
				basename="t_exp"
				baseucd="time.duration;obs.exposure" unit="s"
				basedescr="Integration time of the measurement"/>
			<FEED source="_minmax"
				basename="spectral_range"
				baseucd="\spectralUCD" unit="Hz"
				basedescr="Spectral domain of the data"/>
			<FEED source="_minmax"
				basename="sampling_step"
				baseucd="spect" unit="Hz"
				basedescr="Separation between the centers of two adjacent
					filters or channels."/>
			<FEED source="_minmax"
				basename="spectral_resolution"
				baseucd="spec.resolution" unit="Hz"
				basedescr="FWHM of the instrument profile."/>
			<FEED source="_minmax"
				basename="c1"
				baseucd="obs.field" unit="\c1unit"
				basedescr="First coordinate (e.g., longitude, 'x')"/>
			<FEED source="_minmax"
				basename="c2"
				baseucd="obs.field" unit="\c2unit"
				basedescr="Second coordinate (e.g., latitude, 'y')"/>
			<FEED source="_minmax"
				basename="c3"
				baseucd="obs.field" unit="\c3unit"
				basedescr="Third coordinate (e.g., height, 'z')"/>
			<FEED source="_minmax"
				basename="c1_resol"
				baseucd="pos.resolution" unit="\c1unit"
				basedescr="Resolution in the first coordinate"/>
			<FEED source="_minmax"
				basename="c2_resol"
				baseucd="pos.resolution" unit="\c2unit"
				basedescr="Resolution in the second coordinate"/>
			<FEED source="_minmax"
				basename="c3_resol"
				baseucd="pos.resolution" unit="\c3unit"
				basedescr="Resolution in the third coordinate"/>

			<column name="spatial_frame_type"	type="text" 
				ucd="pos.frame"
				description="Flavor of coordinate system, also defining the 
					nature of coordinates"/>

			<FEED source="_minmax"
				basename="incidence"
				baseucd="pos.incidenceAng" unit="deg"
				basedescr="Incidence angle (solar zenithal angle) during
					data acquisition"/>
			<FEED source="_minmax"
				basename="emergence"
				baseucd="pos.emergenceAng" unit="deg"
				basedescr="Emergence angle during data acquisition"/>
			<FEED source="_minmax"
				basename="phase"
				baseucd="pos.posang" unit="deg"
				basedescr="Phase angle during data acquisition"/>

			<column name="instrument_host_name"	type="text" 
				ucd="meta.class"
				utype="Provenance.ObsConfig.Facility.name"
				description="Name of the observatory or spacecraft that
					performed the measurements.">
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
				description="UCD(s) defining the data">
				<property key="std">1</property>
			</column>

			<column name="access_url"	type="text" 
				ucd="meta.ref.url" 
				description="URL to retrieve the data described."/>
			<column name="access_format"	type="text"
				ucd="meta.id;class" 
				description="Format of the file containing the data."/>
			<column name="access_estsize"	type="integer" required="True"
				ucd="phys.size;meta.file"
				description="estimate file size in kB."/>
			<column name="processing_level"	type="integer" required="True"
				ucd="meta.class.qual" 
				description="type of calibration from CODMAC."/>
			<column name="publisher"	type="text" 
				ucd="meta.name" 
				description="publiher of the ressource"/>
			<column name="reference"	type="text" 
				ucd="meta.ref" 
				description="publication of reference"/>
			<column name="service_title"	type="text" 
				ucd="meta.note" 
				description="Title of the ressourcee"/>
			<column name="target_region"	type="text" 
				ucd="meta.id;class" 
				description="region of interest from a predifine list"/>
			<column name="element_name" type="text" 
				ucd="meta.id"
				description="Supplementary name to designate a specific target 
					within target_name"/>
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
		</events>

	</mixinDef>

	<procDef type="apply" id="populate">
		<doc>
			Sets metadata for an epntap data set, including its products definition.

			The values are left in vars, so you need to do manual copying,
			e.g., using idmaps="*".
		</doc>

		<setup>
			<par key="target_name" description="Name of the target object,
				preferably according to the official IAU nomenclature.
				As appropriate, take these from the exoplanet encyclopedia
				http://exoplanet.eu, the meteor catalog at 
				http://www.lpi.usra.edu/meteor/, the catalog of stardust
				samples at http://curator.jsc.nasa.gov/stardust/catalog/"/>
			<par key="time_scale" description="Time scale used for the
				various times, as given by IVOA's STC data model.  Choose
				from TT, TDB, TOG, TOB, TAI, UTC, GPS, UNKNOWN"/>
			<par key="spatial_frame_type" description="Flavor of the
				coordinate system (this also fixes the meanings of c1, c2, and
				c3).  Values defined by EPN-TAP include celestial, body,
				cartesian, cylindrical, and spherical."/>
			<par key="instrument_host" description="Name of the observatory
				or spacecraft that the observation originated from; for
				ground-based data, use IAU observatory codes, 
				http://www.minorplanetcenter.net/iau/lists/ObsCodesF.html,
				for space-borne instruments use
				http://nssdc.gsfc.nasa.gov/nmc/"/>
			<par key="instrument_name" description="Service providers are
				invited to include multiple values for instrumentname, e.g.,
				complete name + usual acronym. This will allow queries on either
				'VISIBLE AND INFRARED THERMAL IMAGING SPECTROMETER' or VIRTIS to
				produce the same reply."/>
		</setup>
	</procDef>

</resource>

<!--

To resolve:

Slip in cX units and spectral range utypes via mixin parameters?
-->
