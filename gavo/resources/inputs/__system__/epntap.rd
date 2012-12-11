<?xml version="1.0" encoding="iso-8859-1"?>

<resource schema="__system">
	<STREAM id="_minmax">
		<doc>
			Generates a pair of minimum/maximum column pairs.  You must
			fill out basename, baseucd, basedescr, unit,
		</doc>
		<column name="\basename\+_min"
			ucd="\baseucd;stat.min" unit="\unit"
			utype="XXX FIXME"
			description="Minimum \basedescr">
			<property key="std">1</property>
		</column>
		<column name="\basename\+_max"
			ucd="\baseucd;stat.max" unit="\unit"
			utype="XXX FIXME"
			description="Maximum \basedescr">
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
			axis; this must be one of em.freq or phys.energy;phys.part"
			>em.freq</mixinPar>
		<mixinPar key="spectralStepUCD" description="UCD of the spectral
			axis; this must be one of em.freq or phys.energy;phys.part"
			>em.freq.step</mixinPar>
		<events>
			<meta name="info" infoName="SERVICE_PROTOCOL" 
				infoValue="0.3">EPN-TAP</meta>

			<column name="resource_type" type="text" 
				utype="Epn.ResourceType" ucd="meta.id;class" 
				description="ressource type can be dataset or granule">
				<property key="std">1</property>
				<values>
					<option>dataset</option>
					<option>granule</option>
				</values>
			</column>
			<column name="dataproduct_type"	type="text" 
				ucd="meta.id;class" utype="Epn.dataProductType"
				description="Organization of the data product, from enumerated list">
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
				description="name of target (from a list depending on target type)">
				<property key="std">1</property>
			</column>
			<column name="target_class"	type="text" 
				ucd="src.class"  utype="Epn.TargetClass"
				description="type of target">
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
			<column name="time_min" 
				ucd="time.start;obs.exposure" unit="d"
				utype=" Char.TimeAxis.Coverage.Bounds.Limits.Interval.StartTime"
				description="Acquisition start time (in JD)"/>
			<column name="time_max" 
				ucd="time.stop;obs.exposure" unit="d"
				utype="Char.TimeAxis.Coverage.Bounds.Limits.Interval.StopTime"
				description="Acquisition stop time (in JD)"/>
			<FEED source="_minmax"
				basename="time_sampling_step"
				baseucd="time.interval" unit="s"
				basedescr="time sampling step"/>
			<FEED source="_minmax"
				basename="time_exp"
				baseucd="time.duration;obs.exposure" unit="s"
				basedescr="integration time"/>
			<FEED source="_minmax"
				basename="spectral_range"
				baseucd="\spectralUCD" unit="Hz"
				basedescr="of spectral range"/>
			<FEED source="_minmax"
				basename="spectral_sampling_step"
				baseucd="\spectralStepUCD" unit="Hz"
				basedescr="spectral sampling step"/>
			<FEED source="_minmax"
				basename="spectral_resolution"
				baseucd="spec.resolution" unit="Hz"
				basedescr="spectral sampling step"/>
			<FEED source="_minmax"
				basename="c1"
				baseucd="obs.field" unit="\c1unit"
				basedescr="of first coordinate (e.g., longitude, 'x')"/>
			<FEED source="_minmax"
				basename="c2"
				baseucd="obs.field" unit="\c2unit"
				basedescr="of second coordinate (e.g., latitude, 'y')"/>
			<FEED source="_minmax"
				basename="c3"
				baseucd="obs.field" unit="\c3unit"
				basedescr="of third coordinate (e.g., height, 'z')"/>
			<FEED source="_minmax"
				basename="c1_resol"
				baseucd="pos.resolution" unit="\c1unit"
				basedescr="resolution in the first coordinate"/>
			<FEED source="_minmax"
				basename="c2_resol"
				baseucd="pos.resolution" unit="\c2unit"
				basedescr="resolution in the second coordinate"/>
			<FEED source="_minmax"
				basename="c3_resol"
				baseucd="pos.resolution" unit="\c3unit"
				basedescr="resolution in the third coordinate"/>

			<column name="spatial_frame_type"	type="text" 
				ucd="pos.frame"
				description="Flavor of coordinate system, also defining the nature of coordinates"/>


			<FEED source="_minmax"
				basename="incidence"
				baseucd="pos.posIncidenceAng" unit="deg"
				basedescr="incidence angle (solar zenithal angle)"/>
			<FEED source="_minmax"
				basename="emergence"
				baseucd="pos.posEmergenceAng" unit="deg"
				basedescr="emergence angle"/>
			<FEED source="_minmax"
				basename="phase"
				baseucd="pos.posang" unit="deg"
				basedescr="phase angle"/>

			<column name="instrument_host_name"	type="text" 
				ucd="meta.code" 
				description="Standard name of the observatory or spacecraft"/>
			<column name="instrument_name"	type="text" 
				ucd="meta.id;instr" 
				description="Standard name of instrument"/>
			<column name="measurement_type"	type="text" 
				ucd="meta.ucd" 
				description="UCD(s) defining the data"/>
			<column name="access_url"	type="text" 
				ucd="meta.ref.url" 
				description="URL of the data files."/>
			<column name="access_format"	type="text"
				ucd="meta.id;class" 
				description="file format type."/>
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
			<column name="time_scale"	type="text" 
				ucd="time.scale" 
				description="time scale taken from STC"/>
			<column name="element_name" type="text" 
				ucd="meta.id"
				description="Supplementary name to designate a specific target 
					within target_name"/>
		</events>
	</mixinDef>

	<procDef type="apply" id="populate">
		<doc>
			Sets metadata for an epntap data set, including its products definition.

			The values are left in vars, so you need to do manual copying,
			e.g., using idmaps="*".
		</doc>
	</procDef>

</resource>

<!--

To resolve:

Slip in cX units and spectral range utypes via mixin parameters?
-->
