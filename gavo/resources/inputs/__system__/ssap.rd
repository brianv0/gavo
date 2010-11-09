<?xml version="1.0" encoding="utf-8"?>
<!-- Definition of tables for the SSA interfaces. -->


<resource resdir="__system" schema="dc">
	<STREAM id="base_columns"> 
		<!-- a table containing columns required for all SSA tables.
		
		There is no CoordSys metadata here; it is assumed that all our
		Tables are ICRS/TT to the required accuracy.  And you should
		convey such information via STC anyway...
		-->
		<stc>Time TT "ssa_dateObs" Size "ssa_timeExt" 
			Position ICRS [ssa_location] Size "ssa_aperture" "ssa_aperture"
			SpectralInterval "ssa_specstart" "ssa_specend"
				Spectral "ssa_specmid" Size "ssa_specext"</stc>

		<FEED source="//products#tablecols">
			<EDIT ref="column[accref]" utype="ssa:Access.Reference"
				ucd="meta.number"/>
			<EDIT ref="column[mime]" utype="ssa:Access.Format"/>
			<EDIT ref="column[accsize]" utype="ssa:Access.Size"/>
		</FEED>

		<column name="ssa_dstitle" type="text"
			utype="ssa:DataID.title" ucd="meta.title;meta.dataset"
			tablehead="Title" verbLevel="15"
			description="Title or the dataset (usually, spectrum)"/>
		<column name="ssa_creatorDID" type="text"
			utype="ssa:DataID.CreatorDID" ucd="meta.id"
			tablehead="C. DID" verbLevel="29"
			description="Dataset identifier assigned by the creator"/>
		<column name="ssa_pubDID" type="text"
			utype="ssa:Curation.PublisherDID"
			tablehead="P. DID" verbLevel="25" 
			description="Dataset identifier assigned by the publisher"/>
		<column name="ssa_cdate" type="timestamp"
			utype="ssa:DataID.Date" ucd="time;meta.dataset"
			tablehead="Proc. Date" verbLevel="25" 
			description="Processing/Creation date"/>
		<column name="ssa_pdate" type="timestamp"
			utype="ssa:Curation.Date"
			tablehead="Pub. Date" verbLevel="25" 
			description="Date last published."/>
		<column name="ssa_bandpass" type="text"
			utype="ssa:DataID.Bandpass" ucd="instr.bandpass"
			tablehead="Bandpass" verbLevel="15" 
			description="Bandpass (i.e., rough spectral location) of this dataset"/>
		<column name="ssa_cversion" type="text"
			utype="ssa:DataID.Version" ucd="meta.version;meta.dataset"
			tablehead="C. Version" verbLevel="25" 
			description="Creator assigned version for this dataset (will be 
				incremented when this particular item is changed)."/>
		<column name="ssa_targname" type="text"
			utype="ssa:Target.Name" ucd="meta.id;src"
			tablehead="Object" verbLevel="15" 
			description="Common name of object observed."/>
		<column name="ssa_targclass" type="text"
			utype="ssa:Target.Class" ucd="src.class"
			tablehead="Ob. cls" verbLevel="25"
			description="Object class (star, QSO,...)"/>
		<column name="ssa_redshift" 
			utype="ssa:Target.Redshift" ucd="src.redshift"
			tablehead="z" verbLevel="25"
			description="Redshift of target object"/>
		<column name="ssa_snr" 
			utype="ssa:Derived.SNR" ucd="stat.snr"
			tablehead="SNR" verbLevel="25"
			description="Signal-to-noise ratio estimated for this dataset"/>
		<column name="ssa_location" type="spoint"
			utype="ssa:Char.SpatialAxis.Coverage.Location.Value"
			ucd="pos.eq"
			verbLevel="5" tablehead="Location"
			description="ICRS location of target object" unit="deg,deg"/>
		<column name="ssa_aperture" 
			utype="ssa:Char.SpatialAxis.Coverage.Bounds.Extent" ucd="instr.fov"
			verbLevel="15" tablehead="Aperture" unit="deg"
			description="Angular diameter of aperture"/>
		<column name="ssa_dateObs" type="timestamp"
			utype="ssa:Char.TimeAxis.Coverage.Location.Value" ucd="time.epoch"
			verbLevel="5" tablehead="Date Obs."
			description="Midpoint of exposure"/>
		<column name="ssa_timeExt"
			utype="Char.TimeAxis.Coverage.Bounds.Extent" ucd="time.duration"
			verbLevel="5" tablehead="Exp. Time"
			description="Exposure duration"/>
		<column name="ssa_specmid"
			utype="Char.SpectralAxis.Coverage.Location.Value"
			ucd="em.wl;instr.bandpass"
			verbLevel="15" tablehead="Mid. Band" unit="m"
			description="Midpoint of region covered in this dataset"/>
		<column name="ssa_specext"
			utype="Char.SpectralAxis.Coverage.Bounds.Extent"
			ucd="em.wl;instr.bandwidth"
			verbLevel="15" tablehead="Band width" unit="m"
			description="Width of the spectrum"/>
		<column name="ssa_specstart"
			utype="Char.SpectralAxis.Coverage.Location.Start" ucd="em.wl;stat.min"
			verbLevel="15" tablehead="Band start" unit="m"
			description="Lower value of spectral coordinate"/>
		<column name="ssa_specend"
			utype="Char.SpectralAxis.Coverage.Location.Stop" ucd="em.wl;stat.max"
			verbLevel="15" tablehead="Band end" unit="m"
			description="Upper value of spectral coordinate"/>
	</STREAM>

	<!-- The SSA metadata is huge, and many arrangements are conceivable.  
	To come up with some generally useful interface definitions, I'll
	first define a table for a "homogeneous" data collection, the ssahcd
	case.  There's also a core for this. -->
	
	<STREAM id="hcd_fields"> 
		<!-- the SSA (HCD) fields for an instance table -->
		<FEED source="//ssap#base_columns"/>
		<column name="ssa_length" type="integer"
			utype="ssa:Dataset.Length" tablehead="Length"
			verbLevel="5" 
			description="Number of points in the spectrum"/>
	</STREAM>

	<STREAM id="hcd_outtable">
		<!-- the output table definition for a homogeneous data collection.
		Everything not in here is handled via params. -->
		<FEED source="//ssap#hcd_fields"/>
		<column original="//products#instance.accref"/>
		<column name="ssa_score" 
				utype="ssa:Query.Score" 
				tablehead="Score" verbLevel="15">
			<description>A measure of how closely the record matches your
				query.  Higher numbers mean better matches.</description>
		</column>
	</STREAM>

	<STREAM id="hcd_outpars">
		<!-- the parameters table for an SSA (HCD) result.  The definition
		of the homogeneous in HCD is that all these parameters are
		constant for all datasets within a table ("collection").  -->
		<column name="ssa_model" type="text" 
				utype="ssa:Dataset.DataModel"
				description="Data model name and version">
			<values default="Spectrum-1.0"/>
		</column>
		<column name="ssa_dstype" type="text" 
				utype="ssa:Dataset.DataModel"
				description="Type of data (spectrum, time series, etc)">
			<values default="Spectrum"/>
		</column>
		<column name="ssa_timeSI" type="text" 
			utype="ssa:Dataset.TimeSI"
			description="Time unit (WCS/OGIP convention)"/>
		<column name="ssa_spectralSI" type="text" 
			utype="ssa:Dataset.SpectralSI"
			description="Unit of frequency or wavelength (WCS/OGIP convention)"/>
		<column name="ssa_fluxSI" type="text" utype="ssa:Dataset.FluxSI"
			description="Unit of flux/magnitude (WCS/OGIP convention)"/>
		<column name="ssa_creator" type="text"
			utype="ssa:DataID.Creator"
			tablehead="Creator" verbLevel="25" 
			description="Creator of the datasets included here."/>
		<column name="ssa_collection" type="text"
			utype="ssa:DataID.Collection"
			tablehead="Collection" verbLevel="25" 
			description="IOVA Id of the originating dataset collection"/>
		<column name="ssa_instrument" type="text"
			utype="ssa:DataID.Instrument" ucd="meta.id;instr"
			tablehead="Instrument" verbLevel="25" 
			description="Instrument or code used to produce these datasets"/>
		<column name="ssa_datasource" type="text"
			utype="ssa:DataID.DataSource"
			tablehead="Src" verbLevel="25" 
			description="Original source of the data (survey, pointed, theory...)."/>
		<column name="ssa_creationtype" type="text"
			utype="ssa:DataID.CreationType"
			tablehead="Using" verbLevel="25" 
			description="Process used to produce the data (cutout, filtered,
				spectralExtraction...)"/>
		<column name="ssa_reference" type="text"
			utype="ssa:Curation.Reference"
			tablehead="Ref." verbLevel="25" 
			description="URL or bibcode of a publication describing this data."/>
		<column name="ssa_fluxucd" type="text"
			utype="ssa:Char.FluxAxis.Ucd"
			tablehead="UCD(flux)" verbLevel="25" 
			description="UCD of the flux column (only necessary when result does
				not come as VOTable)"/>
		<column name="ssa_spectralucd" type="text"
			utype="ssa:Char.SpectralAxis.Ucd"
			tablehead="UCD(spectral)" verbLevel="25" 
			description="UCD of the spectral column (only necessary when result does
				not come as VOTable)"/>
		<column name="ssa_statError" 
			utype="ssa:Char.FluxAxis.Accuracy.StatError"
			ucd="stat.error;phot.flux.density;em"
			verbLevel="25"
			description="Statistical error in flux"/>
		<column name="ssa_sysError" 
			utype="ssa:Char.FluxAxis.Accuracy.SysError"
			ucd="stat.error.sys;phot.flux.density;em"
			verbLevel="25"
			description="Systematic error in flux"/>
		<column name="ssa_fluxcalib" type="text"
			utype="ssa:Char.FluxAxis.Calibration"
			verbLevel="25"
			description="Type of flux calibration"/>
		<column name="ssa_binSize"
			utype="Char.SpectralAxis.Accuracy.BinSize" ucd="em.wl;spect.binSize"
			verbLevel="25" unit="m"
			description="Bin size in wavelength"/>
		<column name="ssa_statError"
			utype="Char.SpectralAxis.Accuracy.StatError" ucd="stat.error;em"
			verbLevel="25" unit="m"
			description="Statistical error in wavelength"/>
		<column name="ssa_sysError"
			utype="Char.SpectralAxis.Accuracy.StatError" ucd="stat.error.sys;em"
			verbLevel="25" unit="m"
			description="Systematic error in wavelength"/>
		<column name="ssa_speccalib" type="text"
			utype="ssa:Char.SpectralAxis.Calibration" ucd="meta.code.qual"
			verbLevel="25"
			description="Type of wavelength calibration"/>
		<column name="ssa_specres" 
			utype="ssa:Char.SpectralAxis.Resolution" ucd="spect.resolution;em"
			verbLevel="25" unit="m"
			description="Resolution on the spectral axis"/>
		<column name="ssa_spaceError"
			utype="ssa:Char.SpatialAxis.Accuracy.StatError" ucd="stat.error;pos.eq"
			verbLevel="15" unit="deg"
			description="Statistical error in position"/>
		<column name="ssa_spaceCalib" type="text"
			utype="Char.SpatialAxis.Calibration" ucd="meta.code.qual"
			verbLevel="25"
			description="Type of calibration in spatial coordinates"/>
		<column name="ssa_spaceRes"
			utype="Char.SpatialAxis.Resolution" ucd="pos.angResolution"
			verbLevel="25" unit="deg"
			description="Spatial resolution of data"/>
	</STREAM>

	<procDef type="apply" id="setMeta">
		<doc>
			Sets metadata for SSAP.
		</doc>
		<setup>
			<par key="dstitle" late="True" description="a title for the data set
				(e.g., instrument, filter, target in some short form; must be filled
				in)"/>
			<par key="creatorDID" late="True" description="id given by the
				creator (leave out if not applicable)">None</par>
			<par key="pubDID" late="True" description="Id provided by the
				publisher (i.e., you); this is an opaque string and must be given"/>
			<par key="cdate" late="True" description="date the file was
				created (or processed; optional)">None</par>
			<par key="pdate" late="True" description="date the file was
				last published (in gerneral, the default is fine)"
				>datetime.datetime.utcnow()</par>
			<par key="bandpass" late="True" description="bandpass (i.e., rough
				spectral location) of this dataset">None</par>
			<par key="cversion" late="True" description="creator assigned version 
				for this file (should be incremented when it is changed)."
				>None</par>
			<par key="targname" late="True" description="common name of 
				the object observed.">None</par>
			<par key="targclass" late="True" description="object class (star,
				QSO,...)">None</par>
			<par key="redshift" late="True" description="source redshift">
				None</par>
			<par key="snr" late="True" description="signal-to-noise ratio 
				estimated for this dataset">None</par>
			<par key="alpha" late="True" description="right ascension of target
				(ICRS degrees)" >None</par>
			<par key="delta" late="True" description="declination of target
				(ICRS degrees)">None</par>
			<par key="aperture" late="True" description="angular diameter of
				aperture (expected in degrees)">None</par>
			<par key="dateObs" late="True" description="observation midpoint
				(datetime or iso format)">None</par>
			<par key="timeExt" late="True" description="exposure time
				(in seconds)">None</par>
			<par key="specmid" late="True" description="central wavelength
				(in meters)">None</par>
			<par key="specext" late="True" description="width of bandpass
				(in meters of wavelength)">None</par>
			<par key="specstart" late="True" description="lower bound of
				wavelength interval (in meters)">None</par>
			<par key="specend" late="True" description="upper bound of
				wavelength interval (in meters)">None</par>
			<code>
				copiedKWs = ['dstitle', 'creatorDID', 'pubDID', 'cdate', 
					'pdate', 'bandpass', 'cversiontargname', 'targclass', 
					'redshift', 'snr', 'aperture', 'dateObs', 'timeExt', 
					'specmid', 'specext', 'specstart', 'specend']
			</code>
		</setup>
		<code>
			# write to vars to give mappers a chance to convert
			for kw in copiedKWs:
				vars["ssa_"+kw] = vars[copiedKWs]
			alpha = parseFloat(alpha)
			delta = parseFloat(alpha)
			if alpha is not None and delta is not None:
				result["ssa_location"] = pgsphere.SPoint(alpha, delta)
		</code>
	</procDef>

	<mixinDef id="hcd">
		<doc>
			This mixin is for "homogeneous" data collections, where homogeneous
			means that all values in hcd_outpars are constant for all datasets
			in the collection.  This is usually the case if they call come
			from one instrument.

			Rowmakers for tables using this mixin should use the //ssap#setMeta
			proc application.
		</doc>
		<FEED source="//products#hackProductsData"/>
		<events>
			<FEED source="//ssap#hcd_fields"/>
		</events>
	</mixinDef>
</resource>
