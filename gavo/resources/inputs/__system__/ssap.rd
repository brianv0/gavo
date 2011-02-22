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
				ucd="meta.ref.url;meta.dataset"/>
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
			description="ICRS location of target object" unit="deg,deg"/>
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


	<table id="instance">
		<meta name="description">A sample of SSA fields for referencing and such.
		</meta>
		<FEED source="base_columns"/>
	</table>


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
	
		<param name="ssa_model" type="text" 
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
		<param name="ssa_fluxSI" type="text" utype="ssa:Dataset.FluxSI"
			description="Unit of flux/magnitude">\fluxSI</param>
		<param name="ssa_creator" type="text"
			utype="ssa:DataID.Creator"
			tablehead="Creator" verbLevel="25" 
			description="Creator of the datasets included here.">\creator</param>
		<param name="ssa_collection" type="text"
			utype="ssa:DataID.Collection"
			tablehead="Collection" verbLevel="25" 
			description="IOVA Id of the originating dataset collection"/>
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
		<param name="ssa_fluxucd" type="text"
			utype="ssa:Char.FluxAxis.Ucd"
			tablehead="UCD(flux)" verbLevel="25" 
			description="UCD of the flux column (only necessary when result does
				not come as VOTable)"/>
		<param name="ssa_spectralucd" type="text"
			utype="ssa:Char.SpectralAxis.Ucd"
			tablehead="UCD(spectral)" verbLevel="25" 
			description="UCD of the spectral column (only necessary when result does
				not come as VOTable)"/>
		<param name="ssa_statError" 
			utype="ssa:Char.FluxAxis.Accuracy.StatError"
			ucd="stat.error;phot.flux.density;em"
			verbLevel="25"
			description="Statistical error in flux">\statFluxError</param>
		<param name="ssa_sysError" 
			utype="ssa:Char.FluxAxis.Accuracy.SysError"
			ucd="stat.error.sys;phot.flux.density;em"
			verbLevel="25"
			description="Systematic error in flux">\statFluxError</param>
		<param name="ssa_fluxcalib" type="text"
			utype="ssa:Char.FluxAxis.Calibration"
			verbLevel="25"
			description="Type of flux calibration">\fluxCalibration</param>
		<param name="ssa_binSize"
			utype="Char.SpectralAxis.Accuracy.BinSize" ucd="em.wl;spect.binSize"
			verbLevel="25" unit="m"
			description="Bin size in wavelength"/>
		<param name="ssa_statError"
			utype="Char.SpectralAxis.Accuracy.StatError" ucd="stat.error;em"
			verbLevel="25" unit="m"
			description="Statistical error in wavelength">\statSpectError</param>
		<param name="ssa_sysError"
			utype="Char.SpectralAxis.Accuracy.StatError" ucd="stat.error.sys;em"
			verbLevel="25" unit="m"
			description="Systematic error in wavelength">\sysSpectError</param>
		<param name="ssa_speccalib" type="text"
			utype="ssa:Char.SpectralAxis.Calibration" ucd="meta.code.qual"
			verbLevel="25"
			description="Type of wavelength calibration">\spectCalibration</param>
		<param name="ssa_specres" 
			utype="ssa:Char.SpectralAxis.Resolution" ucd="spect.resolution;em"
			verbLevel="25" unit="m"
			description="Resolution on the spectral axis"/>
		<param name="ssa_spaceError"
			utype="ssa:Char.SpatialAxis.Accuracy.StatError" ucd="stat.error;pos.eq"
			verbLevel="15" unit="deg"
			description="Statistical error in position">\statSpaceError</param>
		<param name="ssa_spaceCalib" type="text"
			utype="Char.SpatialAxis.Calibration" ucd="meta.code.qual"
			verbLevel="25"
			description="Type of calibration in spatial coordinates"/>
		<param name="ssa_spaceRes"
			utype="Char.SpatialAxis.Resolution" ucd="pos.angResolution"
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
				in)"/>
			<par key="creatorDID" late="True" description="id given by the
				creator (leave out if not applicable)">None</par>
			<par key="pubDID" late="True" description="Id provided by the
				publisher (i.e., you); this is an opaque string and must be given"/>
			<par key="cdate" late="True" description="date the file was
				created (or processed; optional)">None</par>
			<par key="pdate" late="True" description="date the file was
				last published (in general, the default is fine)"
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
			<par key="length" late="True" description="Number of sample
				in the spectrum">None</par>
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
			in the collection.  This is usually the case if they call come
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
		<mixinPar key="timeSI" description="Time unit (WCS convention)"
			>s</mixinPar>
		<mixinPar key="fluxSI" description="Flux unit (WCS convention)"
			>s</mixinPar>
		<mixinPar key="spectralSI" description="Unit of frequency or 
			wavelength (WCS convention)">m</mixinPar>
		<mixinPar key="creator" description="Creator designation"
			>__NULL__</mixinPar>
		<mixinPar key="instrument" description="Instrument or code used to produce
			these datasets">__NULL__</mixinPar>
		<mixinPar key="dataSource" description="Generation type (typically, one
			survey, pointed, theory, custom, artificial)">__NULL__</mixinPar>
		<mixinPar key="creationType" description="Process used to
			produce the data (zero or more of archival, cutout, filtered, 
			mosaic, projection, spectralExtraction, catalogExtraction)"
			>__NULL__</mixinPar>
		<mixinPar key="reference" description="URL or bibcode of a 
			publication describing this data.">__NULL__</mixinPar>
		<mixinPar key="statFluxError" description="Statistical error in flux"
			>__NULL__</mixinPar>
		<mixinPar key="sysFluxError" description="Systematic error in flux"
			>__NULL__</mixinPar>
		<mixinPar key="fluxCalibration" description="Type of flux calibration
			(one of ABSOLUTE, RELATIVE, NORMALIZED, or UNCALIBRATED)"/>
		<mixinPar key="statSpectError" 
			description="Statistical error in wavelength">__NULL__</mixinPar>
		<mixinPar key="sysSpectError" description="Systematic error in wavelength"
			>__NULL__</mixinPar>
		<mixinPar key="spectCalibration" description="Type of wavelength 
			Calibration (one of ABSOLUTE, RELATIVE, NORMALIZED, or UNCALIBRATED)"
			>__NULL__</mixinPar>
		<mixinPar key="statSpaceError" description="Statistical error in position"
			>__NULL__</mixinPar>

		<FEED source="//products#hackProductsData"/>
		<events>
			<LFEED source="//ssap#hcd_fields"/>
			<LFEED source="//ssap#hcd_outpars"/>
		</events>
	</mixinDef>


	<STREAM id="hcd_condDescs">
		<condDesc id="coneCond">
			<inputKey name="POS" type="text" description="ICRS position of target
				object" unit="deg,deg" std="True"
				utype="ssa:Char.SpatialAxis.Coverage.Location.Value"/>
			<inputKey name="SIZE" description="Size of the region of
				interest around POS" std="True" 
				utype="ssa:Char.SpatialAxis.Coverage.Bounds.Extent"/>
			<phraseMaker procDef="//pql#coneParameter">
				<bind name="posCol">"ssa_location"</bind>
			</phraseMaker>
		</condDesc>

		<condDesc id="bandCond">
			<inputKey name="BAND" type="text" description="Wavelength (range)
				of interest (or symbolic bandpass names)" unit="m"
				std="True"/>
			<phraseMaker>
				<code>
					key = inputKeys[0].name
					lit = inPars.get(key, None)
					if lit is None:
						return
					try:
						ranges = pql.PQLFloatPar.fromLiteral(lit, key)
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
					if "/" in val:
						raise base.ValidationError("No ranges allowed here",
							colName="FORMAT")
					sel = pql.PQLPar.fromLiteral(val, "FORMAT").getValuesAsSet()

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
				TARGETNAME,   ssa_targname,  //pql#stringParameter
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

</resource>
