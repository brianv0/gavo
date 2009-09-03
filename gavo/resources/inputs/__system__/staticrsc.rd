<?xml version="1.0" encoding="utf-8"?>

<resource resdir="__system">
	<schema>public</schema>
	<meta name="description">Static resources, imported to services.
		This exists mainly for easy identification of static resources.</meta>
	
	<data id="tables" original="__system__/services#tables"/>

	<data id="fixedrecords" auto="False">
		<meta name="description">Descriptor for importing static resources.
			There's a special handling for this in staticresource, don't run
			gavoimp on this.</meta>
		<sources pattern="*.rr" recurse="True"/>
		<keyValueGrammar enc="utf-8" yieldPairs="True"/>
	</data>

</resource>
