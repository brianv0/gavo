<?xml version="1.0" encoding="utf-8"?>
<!-- Definition of tables for the SSA interfaces. -->


<resource resdir="__system" schema="dc">
	<STREAM id="base_columns"> 
		<!-- a table containing columns required for all SSA tables.
		
		There is only minimal CoordSys metadata here; we assume 
		such information is conveyed via STC groups anyway.  If that
		should turn out to be not sufficient, we'll think again. -->

		<stc>Time TT "ssa_dateObs" Size "ssa_timeExt" 
			Position ICRS [ssa_location] Size "ssa_aperture" "ssa_aperture"
			SpectralInterval "ssa_specstart" "ssa_specend"
				Spectral "ssa_specmid" Size "ssa_specext"</stc>
		
		<FEED source="//products#tablecols">
			<EDIT ref="column[accref]" utype="ssa:Access.Reference"
				ucd="meta.ref.url;meta.dataset"/>
			<EDIT ref="column[mime]" utype="ssa:Access.Format"/>
			<EDIT ref="column[accsize]" utype="ssa:Access.Size"/>
		</FEED>
		
		<column name="ssa_dstitle" type="text" required="True"
			utype="ssa:DataID.Title" ucd="meta.title;meta.dataset"
			tablehead="Title" verbLevel="15"
			description="Title or the dataset (usually, spectrum)"/>
		<column name="ssa_creatorDID" type="text"
			utype="ssa:DataID.CreatorDID" ucd="meta.id"
			tablehead="C. DID" verbLevel="15"
			description="Dataset identifier assigned by the creator"/>
		<column name="ssa_pubDID" type="text"
			utype="ssa:Curation.PublisherDID"
			tablehead="P. DID" verbLevel="15" 
			description="Dataset identifier assigned by the publisher"/>
		<column name="ssa_cdate" type="timestamp"
			utype="ssa:DataID.Date" ucd="time;meta.dataset"
			tablehead="Proc. Date" verbLevel="15" 
			description="Processing/Creation date"
			xtype="adql:TIMESTAMP"/>
		<column name="ssa_pdate" type="timestamp"
			utype="ssa:Curation.Date"
			tablehead="Pub. Date" verbLevel="25" 
			description="Date last published."
			xtype="adql:TIMESTAMP"/>
		<column name="ssa_bandpass" type="text"
			utype="ssa:DataID.Bandpass" ucd="instr.bandpass"
			tablehead="Bandpass" verbLevel="15" 
			description="Bandpass (i.e., rough spectral location) of this dataset"/>
		<column name="ssa_cversion" type="text"
			utype="ssa:DataID.Version" ucd="meta.version;meta.dataset"
			tablehead="C. Version" verbLevel="25" 
			description="Creator assigned version for this dataset (will be 
				incremented when this particular item is changed)."/>
		<column name="ssa_targname" type="text" required="True"
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
		<column name="ssa_targetpos" type="spoint"
			utype="ssa:Target.pos" ucd="pos.eq;src"
			tablehead="Obj. pos" verbLevel="25"
			description="Equatorial (ICRS) position of the target object."/>
		<column name="ssa_snr" 
			utype="ssa:Derived.SNR" ucd="stat.snr"
			tablehead="SNR" verbLevel="25"
			description="Signal-to-noise ratio estimated for this dataset"/>
		<column name="ssa_location" type="spoint"
			utype="ssa:Char.SpatialAxis.Coverage.Location.Value"
			ucd="pos.eq"
			verbLevel="5" tablehead="Location"
			description="ICRS location of aperture center" unit="deg,deg"/>
		<column name="ssa_aperture" 
			utype="ssa:Char.SpatialAxis.Coverage.Bounds.Extent" ucd="instr.fov"
			verbLevel="15" tablehead="Aperture" unit="deg"
			description="Angular diameter of aperture"/>
		<column name="ssa_dateObs" type="timestamp"
			utype="ssa:Char.TimeAxis.Coverage.Location.Value" ucd="time.epoch"
			verbLevel="5" tablehead="Date Obs."
			description="Midpoint of exposure"
			xtype="adql:TIMESTAMP"/>
		<column name="ssa_timeExt"
			utype="ssa:Char.TimeAxis.Coverage.Bounds.Extent" ucd="time.duration"
			verbLevel="5" tablehead="Exp. Time"
			description="Exposure duration"/>
		<column name="ssa_specmid"
			utype="ssa:Char.SpectralAxis.Coverage.Location.Value"
			ucd="em.wl;instr.bandpass"
			verbLevel="15" tablehead="Mid. Band" unit="m"
			description="Midpoint of region covered in this dataset"/>
		<column name="ssa_specext"
			utype="ssa:Char.SpectralAxis.Coverage.Bounds.Extent"
			ucd="em.wl;instr.bandwidth"
			verbLevel="15" tablehead="Bandwidth" unit="m"
			description="Width of the spectrum"/>
		<column name="ssa_specstart"
			utype="ssa:Char.SpectralAxis.Coverage.Bounds.Start" ucd="em.wl;stat.min"
			verbLevel="15" tablehead="Band start" unit="m"
			description="Lower value of spectral coordinate"/>
		<column name="ssa_specend"
			utype="ssa:Char.SpectralAxis.Coverage.Bounds.Stop" ucd="em.wl;stat.max"
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
			description="Number of points in the spectrum">
			<values nullLiteral="-1"/>
		</column>
	</STREAM>

	<STREAM id="hcd_outpars">
		<doc>The parameters table for an SSA (HCD) result.  The definition
		of the homogeneous in HCD is that all these parameters are
		constant for all datasets within a table ("collection").  

		These params are supposed to be filled using mixin parameters
		(or stream parameters, but the available parameters are documented
		in the hcd mixin).  Some params are hardcoded to NULL right now;
		they can easily be added to hcd's paramters if someone needs them.

		ssa_model and ssa_dstype cannot be changed right now.  Changing
		them would probably not make much sense since they reflect
		what's in this RD.</doc>
	
		<param name="ssa_model" type="text" required="True"
			utype="ssa:Dataset.DataModel"
			description="Data model name and version">Spectrum-1.0</param>
		<param name="ssa_dstype" type="text" 
			utype="ssa:Dataset.DataModel"
			description="Type of data (spectrum, time series, etc)"
			>Spectrum</param>
		<param name="ssa_timeSI" type="text"
			utype="ssa:Dataset.TimeSI"
			description="Time unit">\timeSI</param>
		<param name="ssa_spectralSI" type="text"
			utype="ssa:Dataset.SpectralSI"
			description="Unit of frequency or wavelength"
			>\spectralSI</param>
		<param name="ssa_fluxSI" type="text"
			utype="ssa:Dataset.FluxSI"
			description="Unit of flux/magnitude">\fluxSI</param>
		<param name="ssa_csysName" type="text" required="True"
			utype="ssa:CoordSys.SpaceFrame.Name"
			tablehead="Sys" verbLevel="25"
			description="System RA and Dec are given in"
			>ICRS</param>
		<param name="ssa_publisher" type="text" required="True"
			utype="ssa:Curation.Publisher"
			tablehead="Publisher" verbLevel="25" 
			description="Publisher of the datasets included here.">\publisher</param>
		<param name="ssa_creator" type="text"
			utype="ssa:DataID.Creator"
			tablehead="Creator" verbLevel="25" 
			description="Creator of the datasets included here.">\creator</param>
		<param name="ssa_collection" type="text"
			utype="ssa:DataID.Collection"
			tablehead="Collection" verbLevel="25" 
			description="IOVA Id of the originating dataset collection"
			>\collection</param>
		<param name="ssa_instrument" type="text"
			utype="ssa:DataID.Instrument" ucd="meta.id;instr"
			tablehead="Instrument" verbLevel="25" 
			description="Instrument or code used to produce these datasets"
			>\instrument</param>
		<param name="ssa_datasource" type="text"
			utype="ssa:DataID.DataSource"
			tablehead="Src" verbLevel="25" 
			description="Method of generation for the data."
			>\dataSource</param>
		<param name="ssa_creationtype" type="text"
			utype="ssa:DataID.CreationType"
			tablehead="Using" verbLevel="25" 
			description="Process used to produce the data">\creationType</param>
		<param name="ssa_reference" type="text"
			utype="ssa:Curation.Reference"
			tablehead="Ref." verbLevel="25" 
			description="URL or bibcode of a publication describing this data."
			>\reference</param>
		<param name="ssa_fluxunit" type="text" required="True"
			utype="ssa:Char.FluxAxis.Unit"
			tablehead="unit(flux)" verbLevel="25" 
			description="UCD of the flux column">\fluxSI</param>
		<param name="ssa_fluxucd" type="text" required="True"
			utype="ssa:Char.FluxAxis.Ucd"
			tablehead="UCD(flux)" verbLevel="25" 
			description="UCD of the flux column">\fluxUCD</param>
		<param name="ssa_spectralunit" type="text" required="True"
			utype="ssa:Char.SpectralAxis.Unit"
			tablehead="unit(spectral)" verbLevel="25" 
			description="Unit of the spectral column">\spectralSI</param>
		<param name="ssa_spectralucd" type="text" required="True"
			utype="ssa:Char.SpectralAxis.Ucd"
			tablehead="UCD(spectral)" verbLevel="25" 
			description="UCD of the spectral column">\spectralUCD</param>
		<param name="ssa_statError" 
			utype="ssa:Char.FluxAxis.Accuracy.StatError"
			ucd="stat.error;phot.flux.density;em"
			verbLevel="25"
			description="Statistical error in flux">\statFluxError</param>
		<param name="ssa_sysError" 
			utype="ssa:Char.FluxAxis.Accuracy.SysError"
			ucd="stat.error.sys;phot.flux.density;em"
			verbLevel="25"
			description="Systematic error in flux">\sysFluxError</param>
		<param name="ssa_fluxcalib" type="text"
			utype="ssa:Char.FluxAxis.Calibration"
			verbLevel="25"
			description="Type of flux calibration">\fluxCalibration</param>
		<param name="ssa_binSize"
			utype="ssa:Char.SpectralAxis.Accuracy.BinSize" ucd="em.wl;spect.binSize"
			verbLevel="25" unit="m"
			description="Bin size in wavelength"/>
		<param name="ssa_statError"
			utype="ssa:Char.SpectralAxis.Accuracy.StatError" ucd="stat.error;em"
			verbLevel="25" unit="m"
			description="Statistical error in wavelength">\statSpectError</param>
		<param name="ssa_sysError"
			utype="ssa:Char.SpectralAxis.Accuracy.SysError" ucd="stat.error.sys;em"
			verbLevel="25" unit="m"
			description="Systematic error in wavelength">\sysSpectError</param>
		<param name="ssa_speccalib" type="text"
			utype="ssa:Char.SpectralAxis.Calibration" ucd="meta.code.qual"
			verbLevel="25"
			description="Type of wavelength calibration">\spectralCalibration</param>
		<param name="ssa_specres" 
			utype="ssa:Char.SpectralAxis.Resolution" ucd="spect.resolution;em.wl"
			verbLevel="25" unit="m"
			description="Resolution on the spectral axis">\spectralResolution</param>
		<param name="ssa_spaceError"
			utype="ssa:Char.SpatialAxis.Accuracy.StatError" ucd="stat.error;pos.eq"
			verbLevel="15" unit="deg"
			description="Statistical error in position">\statSpaceError</param>
		<param name="ssa_spaceCalib" type="text"
			utype="ssa:Char.SpatialAxis.Calibration" ucd="meta.code.qual"
			verbLevel="25"
			description="Type of calibration in spatial coordinates"/>
		<param name="ssa_spaceRes"
			utype="ssa:Char.SpatialAxis.Resolution" ucd="pos.angResolution"
			verbLevel="25" unit="deg"
			description="Spatial resolution of data"/>
	</STREAM>

	<STREAM id="coreOutputAdditionals">
		<!-- Fields added to the queried table def to make the core
		output table. -->
		<outputField name="ssa_score" 
				utype="ssa:Query.Score" 
				tablehead="Score" verbLevel="15"
				select="0">
			<description>A measure of how closely the record matches your
				query.  Higher numbers mean better matches.</description>
		</outputField>
	</STREAM>

	<table id="instance" onDisk="False">
		<meta name="description">A sample of SSA fields for referencing and such.
		</meta>
		<FEED source="hcd_fields"/>
		<FEED source="hcd_outpars" timeSI="junk" fluxSI="junk"
			publisher="junk" creator="junk" collection="junk"
			instrument="junk" dataSource="junk" creationType="junk"
			reference="junk" fluxUCD="junk" spectralSI="junk"
			spectralUCD="junk" statFluxError="NaN" sysFluxError="NaN"
			fluxCalibration="junk" statSpectError="NaN" sysSpectError="NaN"
			spectralCalibration="junk" statSpaceError="NaN"
			spectralResolution="NaN"/>
	</table>



	<procDef type="apply" id="setMeta">
		<doc>
			Sets metadata for an SSA data set, including its products definition.

			The values are left in vars, so you need to do manual copying,
			e.g., using idmaps="*", or, if you need to be more specific,
			idmaps="ssa_*".
		</doc>
		<setup>
			<par key="dstitle" late="True" description="a title for the data set
				(e.g., instrument, filter, target in some short form; must be filled
				in); ssa:DataID.Title"/>
			<par key="creatorDID" late="True" description="id given by the
				creator (leave out if not applicable); ssa:DataID.CreatorDID"
				>None</par>
			<par key="pubDID" late="True" description="Id provided by the
				publisher (i.e., you); this is an opaque string and must be given;
				ssa:Curation.PublisherDID"/>
			<par key="cdate" late="True" description="date the file was
				created (or processed; optional); this must be either a string
				in ISO format, or you need to parse to a timestamp yourself; 
				ssa:DataID.Date">None</par>
			<par key="pdate" late="True" description="date the file was
				last published (in general, the default is fine); ssa:Curation.Date"
				>datetime.datetime.utcnow()</par>
			<par key="bandpass" late="True" description="bandpass (i.e., rough
				spectral location) of this dataset; ssa:DataID.Bandpass"
				>None</par>
			<par key="cversion" late="True" description="creator assigned version 
				for this file (should be incremented when it is changed); 
				ssa:DataID.Version">None</par>
			<par key="targname" late="True" description="common name of 
				the object observed; ssa:Target.Name">None</par>
			<par key="targclass" late="True" description="object class (star,
				QSO,...); ssa:Target.Class">None</par>
			<par key="redshift" late="True" description="source redshift; 
				ssa:Target.Redshift">None</par>
			<par key="snr" late="True" description="signal-to-noise ratio 
				estimated for this dataset; ssa:Derived.SNR">None</par>
			<par key="alpha" late="True" description="right ascension of target
				(ICRS degrees); ssa:Char.SpatialAxis.Coverage.Location.Value.C1"
				>None</par>
			<par key="delta" late="True" description="declination of target
				(ICRS degrees); ssa:Char.SpatialAxis.Coverage.Location.Value.C2"
				>None</par>
			<par key="aperture" late="True" description="angular diameter of
				aperture (expected in degrees);
				ssa:Char.SpatialAxis.Coverage.Bounds.Extent">None</par>
			<par key="dateObs" late="True" description="observation midpoint
				(datetime or iso format)">None</par>
			<par key="timeExt" late="True" description="exposure time
				(in seconds); ssa:Char.TimeAxis.Coverage.Bounds.Extent">None</par>
			<par key="specmid" late="True" description="central wavelength
				(in meters); ssa:Char.SpectralAxis.Coverage.Location.Value">None</par>
			<par key="specext" late="True" description="width of bandpass
				(in meters of wavelength); 
				ssa:Char.SpectralAxis.Coverage.Bounds.Extent">None</par>
			<par key="specstart" late="True" description="lower bound of
				wavelength interval (in meters);
				ssa:Char.SpectralAxis.Coverage.Bounds.Start">None</par>
			<par key="specend" late="True" description="upper bound of
				wavelength interval (in meters);
				ssa:Char.SpectralAxis.Coverage.Bounds.Stop">None</par>
			<par key="length" late="True" description="Number of samples
				in the spectrum; ssa:Dataset.Length">None</par>
			<code>
				copiedKWs = ['dstitle', 'creatorDID', 'pubDID', 'cdate', 
					'pdate', 'bandpass', 'cversion', 'targname', 'targclass', 
					'redshift', 'snr', 'aperture', 'dateObs', 'timeExt', 
					'specmid', 'specext', 'specstart', 'specend', 'length']
			</code>
		</setup>
		<code>
			userPars = locals()
			for kw in copiedKWs:
				vars["ssa_"+kw] = userPars[kw]
			alpha = parseFloat(alpha)
			delta = parseFloat(delta)
			if alpha is not None and delta is not None:
				vars["ssa_location"] = pgsphere.SPoint.fromDegrees(alpha, delta)
			else:
				vars["ssa_location"] = None
		</code>
	</procDef>

	<mixinDef id="hcd">
		<doc><![CDATA[
			This mixin is for "homogeneous" data collections, where homogeneous
			means that all values in hcd_outpars are constant for all datasets
			in the collection.  This is usually the case if they all come
			from one instrument.

			Rowmakers for tables using this mixin should use the `//ssap#setMeta`_
			proc application.

			Do not forget to call the `//products#define`_ row filter in grammars
			feeding tables mixing this in.  At the very least, you need to
			say::

				<rowfilter procDef="//products#define">
					<bind name="table">"mySchema.myTableName"</bind>
				</rowfilter>
		]]></doc>
		<mixinPar key="timeSI" description="Time unit (WCS convention);
			ssa:DataSet.TimeSI">s</mixinPar>
		<mixinPar key="fluxSI" description="Flux unit in the spectrum
			instance (not the SSA metadata); use a blank (or a percent) for
			relative or uncalibrated fluxes; ssa:Dataset.FluxSI"/>
		<mixinPar key="spectralSI" description="Unit of frequency or 
			wavelength in the spectrum instance (not the SSA metadata);
			ssa:Dataset.SpectralSI"/>
		<mixinPar key="creator" description="Creator designation;
			ssa:DataID.Creator">__NULL__</mixinPar>
		<mixinPar key="publisher" description="Publisher IVO (by default
			 taken from the DC config); ssa:Curation.Publisher"
			 >\metaString{publisherID}</mixinPar>
		<mixinPar key="instrument" description="Instrument or code used to produce
			these datasets; ssa:DataID.Instrument">__NULL__</mixinPar>
		<mixinPar key="dataSource" description="Generation type (typically, one
			survey, pointed, theory, custom, artificial); ssa:DataID.DataSource"
			>__NULL__</mixinPar>
		<mixinPar key="creationType" description="Process used to
			produce the data (zero or more of archival, cutout, filtered, 
			mosaic, projection, spectralExtraction, catalogExtraction); 
			ssa:DataID.CreationType">__NULL__</mixinPar>
		<mixinPar key="reference" description="URL or bibcode of a 
			publication describing this data; ssa:Curation.Reference"
			>__NULL__</mixinPar>
		<mixinPar key="statFluxError" description="Statistical error in flux;
			ssa:Char.FluxAxis.Accuracy.StatError"
			>__NULL__</mixinPar>
		<mixinPar key="sysFluxError" description="Systematic error in flux;
			ssa:Char.FluxAxis.Accuracy.SysError"
			>__NULL__</mixinPar>
		<mixinPar key="fluxCalibration" description="Type of flux calibration
			(one of ABSOLUTE, RELATIVE, NORMALIZED, or UNCALIBRATED);
			ssa:Char.FluxAxis.Calibration"/>
		<mixinPar key="statSpectError" 
			description="Statistical error in wavelength; 
			ssa:Char.SpectralAxis.Accuracy.StatError">__NULL__</mixinPar>
		<mixinPar key="sysSpectError" description="Systematic error in wavelength;
			ssa:Char.SpectralAxis.Accuracy.SysError"
			>__NULL__</mixinPar>
		<mixinPar key="spectralCalibration" description="Type of wavelength 
			Calibration (one of ABSOLUTE, RELATIVE, NORMALIZED, or UNCALIBRATED);
			ssa:Char.SpectralAxis.Calibration">__NULL__</mixinPar>
		<mixinPar key="statSpaceError" description="Statistical error in position;
			ssa:Char.SpatialAxis.Accuracy.StatError"
			>__NULL__</mixinPar>
		<mixinPar key="collection" description="ivo id of the originating
			collection; ssa:DataID.Collection">__NULL__</mixinPar>
		<mixinPar key="spectralUCD" description="ucd of the spectral column, like
			em.freq or em.energy; default is wavelength; ssa:Char.SpectralAxis.Ucd"
			>em.wl</mixinPar>
		<mixinPar key="fluxUCD" description="ucd of the flux column, like
			phot.count, phot.flux.density, etc.  Default is for flux over
			wavelength; ssa:Char.FluxAxis.Ucd">phot.flux.density;em.wl</mixinPar>
		<mixinPar key="spectralResolution" 
			description="Resolution on the spectral axis; you must give this here
			as wavelength in meters; approximate as necessary; 
			ssa:Char.SpectralAxis.Resolution">NaN</mixinPar>

		<FEED source="//products#hackProductsData"/>
		<events>
			<LFEED source="//ssap#hcd_fields"/>
			<LFEED source="//ssap#hcd_outpars"/>
		</events>
	</mixinDef>


	<STREAM id="hcd_condDescs">
		<condDesc id="coneCond" combining="True">
			<!-- condCond is combining to let the client specify SIZE but
			not POS (as splat does); pql#coneParameter can handle that. -->
			<inputKey name="POS" type="text" description="ICRS position of target
				object" unit="deg,deg" std="True"
				utype="ssa:Char.SpatialAxis.Coverage.Location.Value"/>
			<inputKey name="SIZE" description="Size of the region of
				interest around POS" std="True" 
				unit="deg"
				utype="ssa:Char.SpatialAxis.Coverage.Bounds.Extent"/>
			<phraseMaker procDef="//pql#coneParameter">
				<bind name="posCol">"ssa_location"</bind>
			</phraseMaker>
		</condDesc>

		<condDesc id="bandCond">
			<inputKey name="BAND" type="text" description="Wavelength (range)
				of interest (or symbolic bandpass names)" unit="m"
				std="True" utype="ssa:DataId.Bandpass"/>
			<phraseMaker>
				<code>
					key = inputKeys[0].name
					lit = inPars.get(key, None)
					if lit is None:
						return
					try:
						ranges = pql.PQLFloatPar.fromLiteral(lit, key)
						if ranges is None: # null string
							return
						yield ranges.getSQLForInterval(
							"ssa_specstart", "ssa_specend", outPars)
					except base.LiteralParseError: 
						# As float ranges, things didn't work out.  Try band names ("V")
						# and bail out if unsuccessful.
						yield pql.PQLPar.fromLiteral(lit, key).getSQL(
							"ssa_bandpass", outPars)
				</code>
			</phraseMaker>
		</condDesc>

		<condDesc id="timeCond">
			<inputKey original="//ssap#instance.ssa_dateObs" name="TIME" unit="Y-M-D"
				type="text" std="True"/>
			<phraseMaker procDef="//pql#dateParameter">
				<bind name="consCol">"ssa_dateObs"</bind>
			</phraseMaker>
		</condDesc>

		<condDesc id="formatCond">
			<inputKey original="//ssap#instance.mime" name="FORMAT" type="text"
				std="True"/>
			<phraseMaker>
				<setup>
					<par name="compliantFormats">frozenset([
						"application/x-votable+xml"])</par>
					<par name="nativeFormats">frozenset([
						"application/fits", "text/csv", "text/plain"])</par>
					<par name="consCol">"mime"</par>
				</setup>
				<code>
					val = inPars.get("FORMAT", None)
					if val is None:
						return
					if val=="" or val=="ALL":  # no constraint
						return

					if "/" in val:
						raise base.ValidationError("No ranges allowed here",
							colName="FORMAT")
					sel = pql.PQLPar.fromLiteral(val.lower(), "FORMAT").getValuesAsSet()

					if "all" in sel:
						return  # No constraints

					if "compliant" in sel:
						yield "%s IN %%(%s)s"%(consCol, base.getSQLKey(consCol,
							compliantFormats, outPars))
						sel.remove("compliant")

					if "native" in sel:
						yield "%s IN %%(%s)s"%(consCol, base.getSQLKey(consCol,
							nativeFormats, outPars))
						sel.remove("native")

					if "graphic" in sel:
						yield "%s LIKE 'image/%%'"%(consCol)
						sel.remove("graphic")

					if "votable" in sel:
						yield "%s = 'application/x-votable+xml'"%consCol
						sel.remove("votable")

					if "fits" in sel:
						yield "%s = 'application/fits'"%consCol
						sel.remove("fits")

					if "xml" in sel:
						yield "1=0"  # whatever would *that* be?
						sel.remove("xml")
					
					if sel:
						yield "%s IN %%(%s)s"%(consCol, base.getSQLKey(consCol,
							sel, outPars))
				</code>
			</phraseMaker>
		</condDesc>

		<!-- 
			The following ssa keys make no sense for hcd tables since they
		  are constant by definition:
			SPECRP, SPATRES, TIMERES, FLUXCALIB, WAVECALIB, COLLECTION

			The following ssa keys cannot be generically supported since 
			no SSA model column corresponds to them:
			VARAMPL -->
		<LOOP>
			<csvItems>
				keyName,      matchCol,      procDef
				APERTURE,     ssa_aperture,  //pql#floatParameter
				SNR,          ssa_snr,       //pql#floatParameter
				REDSHIFT,     ssa_redshift,  //pql#floatParameter
				TARGETNAME,   ssa_targname,  //pql#irStringParameter
				TARGETCLASS,  ssa_targclass, //pql#stringParameter
				PUBDID,       ssa_pubDID,    //pql#stringParameter
				CREATORDID,   ssa_creatorDID,//pql#stringParameter
				MTIME,        ssa_pdate,     //pql#dateParameter
			</csvItems>
			<events>
				<condDesc id="\keyName\+_cond">
					<inputKey original="//ssap#instance.\matchCol" name="\keyName"
						type="text" std="True"/>
					<phraseMaker procDef="\procDef">
						<bind name="consCol">"\matchCol"</bind>
					</phraseMaker>
				</condDesc>
			</events>
		</LOOP>

		<condDesc combining="True">
			<!-- meta keys not (directly) entering the query -->
			<inputKey name="REQUEST" type="text" tablehead="Request type"
				description='This currently has to be queryData' std="True">
				<values default="queryData"/>
			</inputKey>
			<inputKey name="TOP" type="integer" tablehead="#Best"
				description='Only return the TOP "best" records' std="True"/>
			<inputKey name="MAXREC" type="integer" tablehead="Limit"
				description="Do not return more than MAXREC records"
				std="True">5000</inputKey>
			<inputKey name="COMPRESS" type="boolean" tablehead="Compress?"
				description="Return compressed results?"
				std="True">True</inputKey>
			<inputKey name="RUNID" type="text" tablehead="Run id"
				description="An identifier for a certain run.  Opaque to the service"
				std="True"/>
			<phraseMaker> <!-- done by the core code for these -->
				<code>
					if False:
						yield
				</code>
			</phraseMaker>
		</condDesc>
	</STREAM>

	<NXSTREAM id="makeSpecGroup" doc="copies over SSA fields into groups
		required by the spectral DM; enter the names of the fields,
		whitespace-separated, in the fieldnames parameter">
		<group utype="\groupUtype">
			<LOOP>
				<codeItems>
					from gavo.protocols import ssap
					srcTable = context.getById("instance")
					for name in "\fieldnames".split():
						utype = ssap.getSpecForSSA(srcTable.getElementForName(name).utype)
						yield {"dest": name, "utype": utype}
				</codeItems>
				<events>
					<paramRef dest="\\dest" utype="\\utype"/>
				</events>
			</LOOP>
		</group>
	</NXSTREAM>

	<mixinDef id="sdm-instance">
		<doc><![CDATA[
			This mixin is intended for tables that get serialized into documents
			conforming to the Spectral Data Model, specifically to VOTables
			(serialization to FITS would take a couple of additional hacks).

			The input to such tables comes from ssa tables (hcd, in this case).
			Their columns (and params) are transformed into params here.

			The mixin adds two columns (you could add more if, e.g., you had
			errors depending on the spectral or flux value), spectral (wavelength
			or the like) and flux.  Their metadata is taken from the ssa fields
			(fluxSI -> unit of flux, fluxUCD as its UCD, etc).

			This mixin in action could look like this::

				<table id="instance" onDisk="False">
					<mixin ssaTable="spectra">//ssap#sdm-instance</mixin>
				</table>

			]]></doc>
		
		<!-- technically the sdm-instance defines the (silly) SDM-groups
		using the translation of names to utypes as given by the
		ssa instance above, whereas the actual params and columns are
		taken from the ssaTable.  This works if the ssa table actually
		mixes in ssap#hcd; otherwise, you're on your own. -->

		<mixinPar key="ssaTable" description="The SSAP (HCD) instance table
			 to take the params from"/>
		<mixinPar key="spectralDescription" description="Description
			for the spectral column">The independent variable of this spectrum 
			(see its ucd to figure out whether it's a wavelength, frequency, or
			energy)</mixinPar>
		<mixinPar key="fluxDescription" description="Description
			for the flux column">The dependent variable of this spectrum (see the
			ucd for its physical meaning</mixinPar>

		<events>
			<FEED source="makeSpecGroup" 
				groupUtype="spec:Target"
				fieldnames="ssa_targname ssa_redshift ssa_targetpos"/>
			<FEED source="makeSpecGroup" 
				groupUtype="spec:Char"
				fieldnames="ssa_location ssa_aperture ssa_dateObs ssa_timeExt
					ssa_specmid ssa_specext ssa_specstart ssa_specend ssa_spectralucd
					ssa_binSize ssa_statError ssa_sysError ssa_speccalib
					ssa_specres"/>
			<FEED source="makeSpecGroup" 
				groupUtype="spec:Curation" 
				fieldnames="ssa_reference ssa_pubDID ssa_pdate"/>
			<FEED source="makeSpecGroup" 
				groupUtype="spec:DataID" 
				fieldnames="ssa_dstitle ssa_creatorDID ssa_cdate ssa_bandpass 
					ssa_cversion ssa_creator ssa_collection ssa_instrument 
					ssa_datasource ssa_creationtype"/>

			<!-- units and UCDs are being filled in by processEarly -->
			<column name="spectral" type="double precision"
				utype="spec:Data.SpectralAxis.Value"
				description="\spectralDescription"/>
			<column name="flux" type="double precision"
				utype="spec:Data.FluxAxis.Value"
				description="\fluxDescription"/>
		</events>

		<processEarly>
			<setup>
				<code>
					from gavo import base
					from gavo import rscdef
					from gavo.protocols import ssap
				</code>
			</setup>
			<code>
				# copy over columns and params from the instance table as
				# params for us.
				ssapInstance = context.resolveId(mixinPars["ssaTable"])
				for col in ssapInstance.columns:
					atts = col.getAttributes()
					atts["utype"] = ssap.getSpecForSSA(atts["utype"])
					atts["required"] = False
					substrate.feedObject("param", 
						base.makeStruct(rscdef.Param, parent_=substrate, **atts))
				for param in ssapInstance.params:
					newUtype = ssap.getSpecForSSA(param.utype)
					substrate.feedObject("param", 
						param.change(utype=newUtype))

				specCol = substrate.getColumnByName("spectral")
				specCol.ucd = substrate.getParamByName("ssa_spectralucd").value
				specCol.unit = substrate.getParamByName("ssa_spectralunit").value
				fluxCol = substrate.getColumnByName("flux")
				fluxCol.ucd = substrate.getParamByName("ssa_fluxucd").value
				fluxCol.unit = substrate.getParamByName("ssa_fluxunit").value

				# set the SDM container meta if not already present
				if substrate.getMeta("utype", default=None) is None:
					substrate.setMeta("utype", "spec:Spectrum")
			</code>
		</processEarly>
	</mixinDef>

	<procDef type="apply" id="feedSSAToSDM">
		<doc>
			feedSSAToSDM takes the current rowIterator's sourceToken and
			feeds it to the params of the current target.  sourceTokens must
			be an SSA rowdict (as provided by the sdmCore).  Futher, it takes
			the params from the sourceTable argument and feeds them to the
			params, too.

			All this probably only makes sense in parmakers when making tables 
			mixing in //ssap#sdm-instance in data children of sdmCores.
		</doc>
		<code>
			for key, value in vars["parser_"].sourceToken.iteritems():
				targetTable.setParam(key, value)
		</code>
	</procDef>
</resource>
