<resource schema="uws">
	<meta name="description">Tables and helpers for the support of 
	an universial worker service.</meta>
	<!-- this must be kept in sync with protocols.uws -->

	<table id="jobs" onDisk="True" system="True" primary="jobid"
			forceUnique="True" dupePolicy="overwrite">
		<column name="jobid" type="text" description="Internal id of the job.  At the same time, uwsDir-relative name of the job directory."/>
		<column name="phase" type="text" description="The state of the job.">
			<values>
				<option>PENDING</option>
				<option>QUEUED</option>
				<option>EXECUTING</option>
				<option>COMPLETED</option>
				<option>ERROR</option>
				<option>ABORTED</option>
			</values>
		</column>
		<column name="executionDuration" type="integer" unit="s"
			description="Job time limit"/>
		<column name="quote" type="timestamp" 
			description="Predicted completion time for the job."/>
		<column name="destructionTime" type="timestamp"
			description="Time at which the job, including ancillary data, will be deleted"/>
		<column name="owner" type="text" 
			description="Submitter of the job, if verified"/>
		<column name="parameters" type="text" 
			description="Pickled representation of the parameters (except uploads)"/>
		<column name="runId" type="text" description="User-chosen run Id"/>
		<column name="actions" type="text" description=
			"Name of the Transitions class managing phase changes for this job"/>
	</table>

	<data id="make_jobs">
		<make table="jobs"/>
	</data>
</resource>
