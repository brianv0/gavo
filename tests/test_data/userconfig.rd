<resource schema="__system">
				<STREAM id="obscore-extraevents">
					<property name="obscoreClause" cumulate="True">
						,
						CAST(\\plutoLong AS real) AS pluto_long,
						CAST(\\plutoLat AS real) AS pluto_lat
					</property>
				</STREAM>
				<STREAM id="obscore-extrapars">
					<mixinPar name="plutoLong">NULL</mixinPar>
					<mixinPar name="plutoLat">22</mixinPar>
				</STREAM>
				<STREAM id="obscore-extracolumns">
					<column name="pluto_long" tablehead="lambda_Pluto"/>
					<column name="pluto_lat"/>
				</STREAM>
			</resource>