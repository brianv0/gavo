"""
Support code for attaching scripts to objects.
"""

import re
import sys
import weakref

import gavo
from gavo import sqlsupport
from gavo import utils


class SqlMacroExpander(object):
	"""is a collection of "Macros" that can be used in SQL scripts.

	This is a terrible hack, but there's little in the way of alternatives
	as far as I can see.
	"""
	def __init__(self, rd):
		self.rd = rd
		self.macrodict = {}
		for name in dir(self):
			if name.isupper():
				self.macrodict[name] = getattr(self, name)
	
	def _expandScriptMacro(self, matob):
		return eval(matob.group(1), self.macrodict)

	def expand(self, script):
		"""expands @@@...@@@ macro calls in SQL scripts
		"""
		return re.sub("@@@(.*?)@@@", self._expandScriptMacro, script)

	def TABLERIGHTS(self, tableName):
		return "\n".join(sqlsupport.getTablePrivSQL(tableName))
	
	def SCHEMARIGHTS(self, schema):
		return "\n".join(sqlsupport.getSchemaPrivSQL(schema))
	
	def SCHEMA(self):
		return self.rd.get_schema()


class ScriptHandler(object):
	"""is a container for the logic of running scripts.

	Objects like ResourceDescriptors and DataDescriptors can have
	scripts attached that may run at certain points in their lifetime.

	This class provides a uniform interface to them.  Right now,
	the have to be constructed just with a resource descriptor and
	a parent.  I do hope that's enough.
	"""
	def __init__(self, parent, rd):
		self.rd, self.parent = rd, weakref.proxy(parent)
		self.expander = SqlMacroExpander(self.rd)

	def _runSqlScript(self, script):
		runner = sqlsupport.ScriptRunner()
		runner.run(self.expander.expand(script))

	def _runSqlScriptInConnection(self, script, connection):
		"""runs a script in connection.

		Since a ScriptRunner may rollback, we commit and being a new transaction.
		I can't see a way around this until postgres has nested transactions
		(savepoints don't seem to cut it here).

		For this to work, the caller has to pass in a connection keyword argument
		to runScripts.
		"""
		connection.cursor().execute("COMMIT")
		runner = sqlsupport.ScriptRunner()
		runner.run(self.expander.expand(script), connection=connection)

	def _runPythonDDProc(self, script):
		"""compiles and run script to a python function working on a
		data descriptor's table(s).

		The function receives the data descriptor (as dataDesc) and a 
		database connection (as connection) as arguments.  The script only
		contains the body of the function, never the header.
		"""
		def makeFun(script):
			ns = dict(globals())
			code = ("def someFun(dataDesc, connection):\n"+
				utils.fixIndentation(script, "      ")+"\n")
			exec code in ns
			return ns["someFun"]
		makeFun(script)(self.parent, sqlsupport.getDefaultDbConnection())

	def _runPythonTableProc(self, script, **kwargs):
		"""compiles and run script to a python function working on a
		with a tableWriter.

		The function receives the RecordDef and the TableWriter as recDef and
		tw arguments.  The script only contains the body of the function, never 
		the header.
		"""
		def makeFun(script):
			ns = dict(globals())
			code = ("def someFun(recDef, tw):\n"+
				utils.fixIndentation(script, "      ")+"\n")
			exec code in ns
			return ns["someFun"]
		makeFun(script)(self.parent, **kwargs)

	handlers = {
		"preCreation": _runSqlScript,
		"postCreation": _runSqlScript,
		"processTable": _runPythonDDProc,
		"preIndex": _runPythonTableProc,
		"preIndexSQL": _runSqlScriptInConnection,
	}
	
	def _runScript(self, scriptType, scriptName, script, **kwargs):
		gavo.ui.displayMessage("Running %s script %s"%(scriptType, scriptName))
		self.handlers[scriptType](self, script, **kwargs)

	def runScripts(self, waypoint, **kwargs):
		for scriptType, scriptName, script in self.parent.get_scripts():
			if scriptType==waypoint:
				self._runScript(scriptType, scriptName, script, **kwargs)


class ScriptingMixin(object):
	"""can be mixed into objects wanting to support scripting.

	The objects have to define a set (or similar) validWaypoints defining
	what waypoints they'll call, must behave like they are Records sporting a 
	ListField "scripts", and must return their resource descriptor through
	a getRd method.
	"""
	def __getScriptHandler(self):
		try:
			return self.__scriptHandler
		except AttributeError:
			self.__scriptHandler = ScriptHandler(self, self.getRd())
			return self.__getScriptHandler()
	
	def runScripts(self, waypoint, **kwargs):
		self.__getScriptHandler().runScripts(waypoint, **kwargs)
	
	def addto_scripts(self, item):
		type, name, content = item
		if not type in self.validWaypoints:
			raise gavo.Error("%s objects to not support %s waypoints"%(
				self.__class__.__name__, type))
		self.dataStore["scripts"].append(item)
