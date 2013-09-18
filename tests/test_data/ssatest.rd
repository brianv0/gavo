<resource schema="test" resdir=".">
	<meta name="creationDate">1973-02-03T12:22:01Z</meta>
	<meta name="title">DaCHS SSA unittest resource</meta>
	<meta name="description">You should not see this.</meta>
	<meta name="subject">Testing</meta>
	<meta name="creator.name">Hendrix, J.; Page, J; et al.</meta>
	<meta name="creator.name">The Master Tester</meta>

	<table id="hcdtest" onDisk="True" primary="accref">
		<meta name="description">A boring and pointless test table</meta>
		<mixin 
			instrument="DaCHS test suite" 
			fluxCalibration="UNCALIBRATED"
			spectralCalibration="CALIBRATED"
			fluxSI=" "
			spectralSI="1 10-10 m"
			spectralResolution="1e-10"
			collection="test set"
			>//ssap#hcd</mixin>
		<column name="excellence" type="integer" description="random number">
			<values nullLiteral="-1"/>
		</column>
	</table>

	<table id="mixctest" onDisk="True" primary="accref">
		<mixin
			fluxSI="Jy"
			spectralSI="Hz"
			fluxUCD="whatever.junk"
			spectralUCD="frequency">//ssap#mixc</mixin>
	</table>

	<data id="test_import">
		<sources pattern="data/*.ssatest"/>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
				<bind name="table">"\schema.hcdtest"</bind>
				<bind name="mime">@mime</bind>
			</rowfilter>
			<rowfilter>
				<code>
					yield row
					baseAccref = row["prodtblPath"]
					row["prodtblAccref"] = baseAccref+".vot"
					row["prodtblPath"] = "dcc://data.ssatest/mksdm?"+baseAccref
					row["prodtblMime"] = "application/x-votable+xml"
					yield row
				</code>
			</rowfilter>
		</keyValueGrammar>
		<make table="hcdtest" role="primary">
			<rowmaker idmaps="*" id="makeRow">
				<apply procDef="//ssap#setMeta">
					<bind name="pubDID">"ivo://test.inv/"+@id</bind>
					<LOOP listItems="dstitle specstart specend bandpass alpha delta
							dateObs">
						<events>
							<bind name="\item">@\item</bind>
						</events>
					</LOOP>
					<bind name="targname">@targetName</bind>
				</apply>
			</rowmaker>
		</make>
	</data>

	<data id="test_mixc">
		<sources pattern="data/*.ssatest"/>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
				<bind name="table">"\schema.hcdtest"</bind>
			</rowfilter>
		</keyValueGrammar>
		<make table="mixctest" role="primary">
			<rowmaker idmaps="*">
				<apply procDef="//ssap#setMeta">
					<bind name="pubDID">"ivo://test.inv/"+@id</bind>
					<bind name="dstitle">"junk from "+@id</bind>
					<bind name="targname">@targetName</bind>
				</apply>
				<apply procDef="//ssap#setMixcMeta">
					<bind name="reference">"Paper on "+@id</bind>
					<bind name="instrument">"Bruce Astrograph"</bind>
				</apply>
			</rowmaker>
		</make>
	</data>

	<data id="test_macros">
		<!-- some scaffolding to test SSA-related macros; expand as required;
		no disk table is created here. -->
		<sources pattern="data/*.ssatest"/>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
				<bind name="table">"test.junk"</bind>
			</rowfilter>
		</keyValueGrammar>
		<make>
			<table id="junk">
				<column name="pubDID" type="text"/>
			</table>
			<rowmaker idmaps="*">
				<map key="pubDID">\standardPubDID</map>
			</rowmaker>
		</make>
	</data>

	<table id="spectrum">
		<mixin ssaTable="hcdtest">//ssap#sdm-instance</mixin>
	</table>

	<sdmCore id="mksdm" queriedTable="hcdtest">
		<data>
			<embeddedGrammar>
				<iterator>
					<code>
						for i in range(20):
							yield {"spectral": 3000+i, "flux": 30-i}
					</code>
				</iterator>
			</embeddedGrammar>
			<make table="spectrum">
				<parmaker>
					<apply procDef="//ssap#feedSSAToSDM"/>
				</parmaker>
			</make>
		</data>
	</sdmCore>

	<service id="s">
		<ssapCore queriedTable="hcdtest" id="foocore">
			<FEED source="//ssap#hcd_condDescs"/>
			<condDesc buildFrom="excellence"/>
		</ssapCore>
		<publish render="ssap.xml" sets="local"/>
		<meta name="shortName">ssatest test ssa</meta>
		<meta name="ssap.dataSource">artificial</meta>
		<meta name="ssap.creationType">archival</meta>
		<meta name="ssap.testQuery">TARGETNAME=alpha%20Boo</meta>

		<property name="returnData">True</property>
	</service>

	<table id="instance">
		<mixin ssaTable="hcdtest"
			spectralDescription="Wavelength"
			fluxDescription="Stellar surface flux density"
		>//ssap#sdm-instance</mixin>
	</table>

	<data id="datamaker">
		<!-- a hacked data maker that uses the source token passed in
		to come up with essentially random data. -->
		<embeddedGrammar>
			<iterator>
				<code>
					seed = sum(ord(c) for c in self.sourceToken["accref"])
					for count in range(seed/10):
						yield {"spectral": seed+count, "flux": seed-count}
				</code>
			</iterator>
 		</embeddedGrammar>
  	<make table="instance">
   		<parmaker>
     		<apply procDef="//ssap#feedSSAToSDM"/>
   		</parmaker>
  	</make>
	</data>

	<service id="dl" allowed="datalink">
		<datalinkCore>
			<descriptorGenerator procDef="//datalink#sdm_genDesc">
				<bind name="ssaTD">"\rdId#hcdtest"</bind>
			</descriptorGenerator>
			<dataFunction procDef="//datalink#sdm_genData">
				<bind name="builder">"\rdId#datamaker"</bind>
			</dataFunction>
			<FEED source="//datalink#sdm_plainfluxcalib"/>
			<FEED source="//datalink#sdm_cutout"/>
			<FEED source="//datalink#sdm_format"/>
		</datalinkCore>
	</service>

	<service id="c" original="s">
		<meta name="description">An SSAP service supporting getData 
			and datalink.</meta>
		<property name="tablesource">datamaker</property>
		<property name="datalink">dl</property>
		<property name="returnData"/>
	</service>
</resource>
