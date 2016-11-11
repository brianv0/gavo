<resource resdir="." schema="test" readProfiles="trustedquery,untrustedquery">
	<meta name="description">Helpers for tests for cores.</meta>
	<table id="abcd">
		<column name="a" type="text" verbLevel="1"/>
		<column name="b" type="integer" verbLevel="5">
			<values nullLiteral="-1"/>
		</column>
		<column name="c" type="integer" verbLevel="15">
			<values nullLiteral="-1"/>
		</column>
		<column name="d" type="integer" verbLevel="20" unit="km">
			<values nullLiteral="-1"/>
		</column>
		<column name="e" type="timestamp" verbLevel="25"/>
	</table>

	<computedCore id="abccatcore" computer="/bin/cat">
		<inputTable original="abcd"/>
		<data>
			<reGrammar recordSep="&#10;" fieldSep="\s+">
				<names>a,b,c,d,e</names>
			</reGrammar>
			<make table="abcd">
				<rowmaker idmaps="a,b,c,d,e" id="parseProcessedRows"/>
			</make>
		</data>
	</computedCore>

	<service id="basiccat" core="abccatcore">
		<inputDD id="forceQuo">
			<contextGrammar inputTable="abcd" rowKey="a"/>
		</inputDD>
		<outputTable namePath="abcd">
			<outputField original="a"/>
		</outputTable>
	</service>

	<service id="convcat" core="abccatcore" allowed="form, static">
		<inputDD original="forceQuo"/>
		<outputTable namePath="abcd">
			<column original="a" verbLevel="15"/>
			<column original="b" displayHint="sf=2"/>
			<column original="d" unit="m"/>
		</outputTable>
	</service>

	<service id="enums">
		<dbCore queriedTable="abcd">
			<condDesc>
				<inputKey original="a" required="False">
					<values fromdb="tableName from dc.tablemeta" multiOk="True"/>
				</inputKey>
			</condDesc>
			<condDesc>
				<inputKey original="b">
					<values><option>1</option><option>2</option></values>
				</inputKey>
			</condDesc>
			<condDesc required="True">
				<inputKey original="c">
					<values default="1"><option>1</option><option>2</option></values>
				</inputKey>
			</condDesc>
		</dbCore>
	</service>

	<service id="cstest" allowed="form, scs.xml">
		<dbCore id="cscore" queriedTable="data/test#csdata">
			<FEED source="//scs#coreDescs"/>
			<condDesc buildFrom="mag"/>
			<condDesc>
				<inputKey original="rV" type="vexpr-float"
					>-100 .. 100<property name="cssClass">rvkey</property>
				</inputKey>
			</condDesc>
		</dbCore>
		<property name="customCSS">
			.rvkey { background:red; }
		</property>
	</service>

	<service id="grouptest" allowed="form,static">
		<dbCore queriedTable="data/test#adql">
			<condDesc>
				<inputKey original="rV"/>
			</condDesc>
			<inputTable>
				<group name="magic"
					description="Some magic parameters we took out of thin air.">
					<property name="cssClass">localstuff</property>
					<paramRef dest="mag"/>
					<paramRef dest="rV"/>
				</group>
				<inputKey original="rV">
					<values default="-4"/>
				</inputKey>
				<inputKey original="mag"/>
				<inputKey original="alpha"/>
				<inputKey original="delta"/>
			</inputTable>
		</dbCore>
	</service>

	<service id="impgrouptest" defaultRenderer="form">
		<dbCore queriedTable="data/test#adql">
			<condDesc>
				<inputKey original="rV"/>
				<inputKey original="mag"/>
				<group name="phys" description="Ah, you know.  The group with
					 the magic and the thin air">
					 <property name="label">Wonz</property>
					 <property name="style">compact</property>
				</group>
			</condDesc>
		</dbCore>
	</service>

	<service id="dl" allowed="dlget,dlmeta,dlasync">
		<meta name="title">Hollow Datalink</meta>
		<datalinkCore>
			<descriptorGenerator procDef="//soda#fits_genDesc">
				<setup>
					<code>
						from gavo import svcs
						from gavo.protocols import soda
					</code>
				</setup>
				<code>
					if pubDID=="broken":
						ddt
					elif pubDID=="somewhereelse":
						raise svcs.WebRedirect("http://some.whereel.se/there")
					return soda.getFITSDescriptor(pubDID)
				</code>
			</descriptorGenerator>
			<metaMaker procDef="//soda#fits_makeWCSParams" name="getWCSParams"/>
			<dataFunction procDef="//soda#fits_makeHDUList" name="makeHDUList"/>
			<dataFunction procDef="//soda#fits_doWCSCutout" name="doWCSCutout"/>
			<FEED source="//soda#fits_genPixelPar"/>
			<FEED source="//soda#fits_genKindPar"/>
			<dataFormatter procDef="//soda#fits_formatHDUs" name="formatHDUs"/>
		</datalinkCore>
		
		<meta name="_example" title="Example 1">
			This is an example for examples, describing
			:dl-id:`ivo://org.gavo.dc/~?bla/foo/qua` (which, incidentally,
			does not exist).
		</meta>

		<meta name="_example" title="Example 2">
			This is another example for examples.
		</meta>
	</service>

	<dbCore id="typescore" queriedTable="data/test#typesTable"/>

	<table id="conecat" onDisk="True">
		<column name="id" type="integer" ucd="meta.id;meta.main" required="True"/>
		<column name="ra" type="real" ucd="pos.eq.ra;meta.main"/>
		<column name="dec" type="double precision" ucd="pos.eq.dec;meta.main"/>
	</table>

	<data id="import_conecat">
		<sources item="nix"/>
		<embeddedGrammar>
			<iterator>
				<code>
					for id, (ra, dec) in enumerate([(1.25, 2.5), (23, -92.5)]):
						yield locals()
				</code>
			</iterator>
		</embeddedGrammar>
		<make table="conecat"/>
	</data>

	<service id="scs" allowed="scs.xml, api, form" defaultRenderer="scs.xml">
		<meta name="testQuery">
			<meta name="ra">10</meta>
			<meta name="dec">20</meta>
			<meta name="sr">1</meta>
		</meta>
		<scsCore queriedTable="conecat">
    	<FEED source="//scs#coreDescs"/>
    	<condDesc buildFrom="id"/>
		</scsCore>

		<FEED source="//pql#DALIPars"/>

	</service>

	<service id="uploadtest" allowed="api,form">
		<debugCore>
			<inputTable>
				<inputKey name="notarbitrary" type="file" 
					description="An example upload containing nothing in particular" 
					ucd="par.upload">
					<property name="adaptToRenderer">True</property>
				</inputKey>
			</inputTable>
		</debugCore>
		<inputKey name="frobnicate" type="boolean"
			description="A service key"/>
		<FEED source="//pql#DALIPars"/>
	</service>

	<service id="rds" allowed="static">
		<nullCore/>
		<property name="staticData">data</property>
	</service>

	<service id="pc" allowed="api,form,uws.xml">
		<publish sets="ivo_managed" render="api"/>
		<pythonCore>
			<inputTable>
				<inputKey name="opre" description="Operand, real part"
					required="True"/>
				<inputKey name="opim" description="Operand, imaginary part">
					<values default="1.0"/>
				</inputKey>
				<inputKey name="powers" description="Powers to compute"
					type="integer[]" multiplicity="multiple">
					<values default="1 2 3"/>
				</inputKey>
				<inputKey name="responseformat" description="Preferred
						output format" type="text">
							<values default="application/x-votable+xml"/>
				</inputKey>
				<inputKey name="stuff" type="file" description="Stuff to upload"/>
			</inputTable>
			<outputTable>
				<outputField name="re" description="Result, real part"/>
				<outputField name="im" description="Result, imaginary part"/>
				<outputField name="log"
					description="real part of logarithm of result"/>
			</outputTable>

			<coreProc>
				<setup>
					<code>
						import cmath
					</code>
				</setup>
				<code>
					powers = inputTable.getParam("powers")
					op = complex(inputTable.getParam("opre"),
						inputTable.getParam("opim"))
					rows = []
					for p in powers:
						val = op**p
						rows.append({
							"re": val.real,
							"im": val.imag,
							"log": cmath.log(val).real})
				
					if hasattr(inputTable, "job"):
						with inputTable.job.getWritable() as wjob:
							wjob.addResult("Hello World.\\n", "text/plain", "aux.txt")

					return rsc.TableForDef(self.outputTable, rows=rows)
				</code>
			</coreProc>
		</pythonCore>
	</service>

	<service id="uc" allowed="uws.xml">
		<pythonCore>
			<inputTable>
				<inputKey name="stuff" type="file" description="Stuff to upload"/>
				<inputKey name="other" type="file" 
					description="More stuff to upload"/>
			</inputTable>
			<outputTable/>

			<coreProc>
				<code>
					return None
				</code>
			</coreProc>
		</pythonCore>
	</service>

</resource>
