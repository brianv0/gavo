<resource schema="__system">
	<STREAM id="obscore-extraevents">
		<doc><![CDATA[
			Write extra events to mix into obscore-published tables.  This
			will almost always be just additions to the obscore clause of
			looking roughly like::
				
				<property name="obscoreClause" cumulate="True">
					,
					CAST(\\\\plutoLong AS real) AS pluto_long,
					CAST(\\\\plutoLat AS real) AS pluto_lat
				</property>

			See also `Extending Obscore`_ in the reference manual.
		]]></doc>
	</STREAM>

	<STREAM id="obscore-extrapars">
		<doc><![CDATA[
			For each macro you reference in obscore-extraevents, add a
			mixinPar here, like:

				<mixinPar key="plutoLong">NULL</mixinPar>
			
			Note that all mixinPars here must have default (i.e., there must
			be some content in the element suitable as an SQL expression
			of the appropriate type).  If you fail to give one, the creation
			of the empty prototype obscore table will fail with fairly obscure
			error messages.
		]]></doc>
	</STREAM>

	<STREAM id="obscore-extracolumns">
		<doc>
			Add column definitions for obscore here.  See `Extending Obscore`_ for
			details.
		</doc>
	</STREAM>

	<script id="_test-script" lang="python" name="test instrumentation"
		type="preIndex">
		# (this space left blank intentionally)
	</script>
</resource>
