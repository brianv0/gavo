<?xml version="1.0" encoding="utf-8"?>

<!-- A resource descriptor for testing privileges.  This spits out
warnings when created, so we don't want it in the main test.rd -->

<resource resdir=".">

	<schema>test</schema>

	<table id="privtable" onDisk="True">
		<readProfiles>defaults,privtest</readProfiles>
		<allProfiles>testadmin</allProfiles>
		<column name="foo"/>
	</table>
</resource>
