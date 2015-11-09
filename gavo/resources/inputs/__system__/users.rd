<?xml version="1.0" encoding="utf-8"?>

<resource resdir="__system" schema="dc">

<!-- This has to match whatever is done in gavo.web.creds.
-->
	<table id="users" primary="username" onDisk="True" system="True">
		<meta name="description">
			Users known to the data center, together with their credentials.

			Right now, DaCHS only supports user/password.  Note that passwords
			are currently stored in cleartext, so do discourage your users
			from using valuable passwords here (whether you explain to them
			that DaCHS so far only provides "mild security" is up to you).

			Manipulate this table through gavo admin adduser, gavo admin
			deluser, and gavo admin listusers.
		</meta>
<!-- prevent "normal" (e.g., ADQL) users from accessing this table -->
		<readProfiles/>
		<column name="username" type="text" tablehead="Username"
			description="Name of the user."/>
		<column name="password" type="text" displayHint="type=suppress"
			description="Password in clear text."/>
		<!-- This is a plain text password.  We could store md5s, but
			then I guess it's more likely that people will ask for pws
			than that any unauthorized entity will be interested in them.
			If that assessment changes, by all means store md5s, since
			this table is largely unprotected -->
		<column name="remarks" type="text" description="Free text
			mainly intended to explain what the user is supposed to
			be/do"/>
	</table>

	<table id="groups" onDisk="True" system="True" namePath="users">
		<meta name="description">
			Assignment of users to groups.

			Conceptually, each user has an associated group of the same name.
			A user always is a member of her group.  Other users can be added
			to that group, essentially as in the classic Unix model.

			Manipulate this table through gavo admin addtogroup and gavo admin
			delfromgroup.
		</meta>
		<readProfiles/>
		<foreignKey inTable="users" source="username"/>
		<column original="username" description="Name of the user belonging
			to the group"/>
		<column name="groupname" type="text" description="Name of the group"/>
	</table>

	<data id="maketables">
		<nullGrammar/>
		<make table="users"/>
		<make table="groups"/>
		
	</data>
</resource>
