<!-- Definitions of SLAP (simple line access) columns and parameters -->

<!--  Ausgabe braucht noch 

xmlns:ssldm="http://www.ivoa.net/xml/SimpleSpectrumLineDM/SimpleSpectrumLineDM-v1.0.xsd"

-->

<resource resdir="__system" schema="dc">

	<mixinDef id="basic">
		<doc>
			This mixin is for tables serving SLAP services, i.e., tables
			with spectral lines.  It does not contain all "optional" columns,
			hence the name basic.  We'd do "advanced", too, if there's demand.

			Use the `//slap#fillBasic`_ procDef to populate such tables.
		</doc>
		<events>
			<column name="wavelength" type="double precision" required="True"
				utype="ssldm:Line.wavelength.value"
				unit="m" ucd="em.wl;phys.atmol.transition"
				tablehead="Lambda"
				description="Wavelength of the transition."
				verbLevel="1"/>
			<column name="linename" type="text" required="True"
				utype="ssldm:Line.title"
				ucd="meta.id;spect.line"
				tablehead="Line"
				description="Terse descriptor of the line"
				verbLevel="1"/>
			<column name="chemical_element" type="text"
				utype="ssldm:Line.species.name"
				ucd="phys.atmol.element"
				tablehead="Element"
				description="Element transitioning"
				verbLevel="1"/>
			<column name="initial_name" type="text"
				utype="ssldm:Line.initialLevel.name"
				ucd="phys.atmol.initial;phys.atmol.level"
				tablehead="Initial"
				description="Name of the level the atom or molecule starts in."
				verbLevel="15"/>
			<column name="final_name" type="text"
				utype="ssldm:Line.finalLevel.name"
				ucd="phys.atmol.final;phys.atmol.level"
				tablehead="Final"
				description="Name of the level the atom or molecule ends up in."
				verbLevel="15"/>
			<column name="initial_level_energy" type="double precision"
				unit="J" ucd="phys.energy;phys.atmol.initial;phys.atmol.level"
				tablehead="E_init"
				description="Energy of the level the atom or molecule starts in."
				verbLevel="15"/>
			<column name="final_level_energy" type="double precision"
				unit="J" ucd="phys.energy;phys.atmol.final;phys.atmol.level"
				tablehead="E_final"
				description="Energy of the level the atom or molecule ends up in."
				verbLevel="15"/>
			<column name="pub" type="text"
				ucd="meta.bib"
				tablehead="Pub"
				description="The publication this value orginated from."
				verbLevel="15"
				displayHint="type=bibcode"/>
			<column name="id_status" type="text"
				ucd="meta.code"
				tablehead="Id?"
				description="Identification status of the line"
				verbLevel="15"/>
			</events>
	</mixinDef>

	<procDef type="apply" id="fillBasic">
		<doc>
			This apply is intended for rowmakers filling tables mixing in
			//slap#basic.  It populates vars for all the columns in there;
			you'll normally want idmaps="*" with this apply.

			For most of its parameters, it will take them for same-named vars,
			so you can slowly build up its arguments through var elements.
		</doc>
		<setup>
			<par late="true" key="wavelength" description="Wavelength of
				the transition in meters; this will typically be an
				expression like int(@wavelength)*1e-10">@wavelength</par>
			<par late="true" key="linename" description="A brief designation
				for the line, like 'H alpha' or 'N III 992.973 A'.">@linename</par>
			<par late="true" key="id_status" description="Identification
				status; this would be identified or unidentified plus
				possibly uncorrected (but read the SLAP spec for that)."
				>"identified"</par>
			<par late="true" key="chemical_element" description="Element that makes
				the transition.  It's probably ok to dump molecule names
				in here, too.">@chemical_element</par>
			<par late="true" key="initial_name" description="Designation
				of the initial state">@initial_name</par>
			<par late="true" key="final_name" description="Designation
				of the final state">@final_name</par>
			<par late="true" key="initial_level_energy" description="Energy
				of the initial state">@initial_level_energy</par>
			<par late="true" key="final_level_energy" description="Energy
				of the final state">@final_level_energy</par>
			<par late="true" key="pub" description="Publication
				this came from (use a bibcode).">@pub</par>
		</setup>
		<code>
			vars.update(locals())
		</code>
	</procDef>

	<STREAM id="servicePars">
		<doc>
			The service parameters of SLAP services.  Replay this in
			all your SLAP services (not in the core)
		</doc>

		<inputKey name="REQUEST" type="text" tablehead="Request type"
			description="If you give this parameter, in must be queryData.
				Hence, better don't pass it in." std="True"
			multiplicity="forced-single"/>
		<inputKey name="VERSION" type="text"
			tablehead="Service Version" std="True"
			description="If you pass this, it must be 1.0."/>
		<FEED source="//pql#DALIPars"/>
	</STREAM>

	<STREAM id="corePars">
		<doc>
			The mandatory core parameters of SLAP services.  This is currently
			just WAVELENGTH.
		</doc>
		<condDesc buildFrom="wavelength"/>
		<condDesc buildFrom="chemical_element"/>
		<condDesc buildFrom="final_level_energy"/>
		<condDesc buildFrom="initial_level_energy"/>
	</STREAM>

</resource>
