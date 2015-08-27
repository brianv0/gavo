<resource schema="test" resdir="" readProfiles="trustedquery,untrustedquery">
	<table id="slaptest" onDisk="True" mixin="//slap#basic">
		<column original="wavelength" displayHint="displayUnit=Angstrom"/>
	</table>

	<data id="import">
		<sources item="test"/>
		<embeddedGrammar>
			<iterator>
				<code>
					yield {"wavelength": 400, "chemical_element": "Mo", "base": 1.2e6, 
						"takenfrom": "2003junk.yard.0123X"}
					yield {"wavelength": 300, "chemical_element": "Bi", "base": 1.8e6, 
						"takenfrom": "2003junk.yard.3210Y"}
					yield {"wavelength": 1200, "chemical_element": "H", "base": 3e7, 
						"takenfrom": "2003junk.yard.0001B"}

				</code>
			</iterator>
		</embeddedGrammar>
		<make table="slaptest">
			<rowmaker idmaps="*">
				<var key="linename">"%s %s A"%(@chemical_element, @wavelength)</var>
				<var key="wavelength">float(@wavelength)*1e-10</var>
				<var key="initial_level_energy"
					>1/float(@base)*100*PLANCK_H*LIGHT_C</var>
				<var key="final_level_energy"
					>@initial_level_energy+PLANCK_H*LIGHT_C/@wavelength</var>
				<apply procDef="//slap#fillBasic">
					<bind key="pub">@takenfrom</bind>
					<bind key="initial_name">"Upper Level"</bind>
					<bind key="final_name">"Lower Level"</bind>
				</apply>
			</rowmaker>
		</make>
	</data>

	<service id="s" allowed="slap.xml">
		<meta name="shortName">slap test</meta>
		<meta name="slap.dataSource">theoretical</meta>
		<meta name="slap.testQuery">MAXREC=1</meta>
		<publish render="slap.xml" sets="ivo_managed"/>
		<FEED source="//slap#servicePars"/>
		<dbCore queriedTable="slaptest">
			<FEED source="//slap#corePars"/>
		</dbCore>
	</service>
			

</resource>
