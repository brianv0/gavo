"""
Support code for attaching scripts to objects.
"""

import re
import sys
import weakref

from pyparsing import Word, OneOrMore, ZeroOrMore, QuotedString, Forward,\
	SkipTo, Optional, StringEnd, Regex, LineEnd, Suppress, ParserElement,\
	Literal, White, ParseException

import gavo
from gavo import config
from gavo import sqlsupport
from gavo import utils


class SqlMacroExpander(object):
	"""is a collection of "Macros" that can be used in SQL scripts.

	This whole thing needs to be redone into a general mechanism of
	placing values from the resource descriptor and/or the parent
	into scripts.
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

	def SCHEMA(self):
		return self.rd.get_schema()


def _getSQLScriptGrammar():
	"""returns a pyparsing ParserElement that splits SQL scripts into
	individual commands.

	The rules are: One statement per line, but linebreaks are ignored
	withing strings and inside of open parens.
	"""
	ParserElement.setDefaultWhitespaceChars(" \t")
#	ParserElement.enablePackrat()
	atom = Forward()
	atom.setName("Atom")

	sqlComment = Literal("--")+SkipTo("\n", include=True)
	cStyleComment = Literal("/*")+SkipTo("*/", include=True)
	comment = sqlComment | cStyleComment

	simpleStr = QuotedString(quoteChar="'", escChar="\\", unquoteResults=False)
	dollarQuoted = Regex(r"(?s)\$(\w*)\$.*?\$\1\$")
	dollarQuoted.setName("dollarQuoted")
	strLiteral = simpleStr | dollarQuoted
	strLiteral.setName("strLiteral")

	parenExpr = "(" + ZeroOrMore( atom | "\n" ) + ")"
	parenExpr.setName("parenExpr")

	other = Regex("[^(')$\n\\\\]+")
	other.setName("other")

	ignoredLinebreak = Suppress(Literal("\\\n"))
	ignoredLinebreak.setName("ignored linebreak")
	literalBackslash = Literal("\\")
	literalDollar = Literal("$") + ~ Literal("$")
	statementEnd = ( Literal('\n') | StringEnd())
	statementEnd.setName("end of line")
	emptyLine = Regex("\\s*\n")
	emptyLine.setName("empty line")

	atom <<  ( ignoredLinebreak | Suppress(comment) | other | strLiteral | 
		parenExpr | literalDollar | literalBackslash )
	statement = OneOrMore(atom) + statementEnd
	statement.setName("statement")
	statement.setParseAction(lambda s, p, toks: " ".join(toks))

	script = OneOrMore( statement | emptyLine ) + StringEnd()
	script.setName("script")
	script.setParseAction(lambda s, p, toks: [t for t in toks.asList()
		if t.strip()])

	if False:
		atom.setDebug(True)
		other.setDebug(True)
		parenExpr.setDebug(True)
		strLiteral.setDebug(True)
		statement.setDebug(True)
		statementEnd.setDebug(True)
		dollarQuoted.setDebug(True)
		literalDollar.setDebug(True)
		literalBackslash.setDebug(True)
		ignoredLinebreak.setDebug(True)
		emptyLine.setDebug(True)
	return script


def getSQLScriptGrammar(memo=[]):
	if not memo:
		memo.append(_getSQLScriptGrammar())
	return memo[0]


class SQLScriptRunner:
	"""is an interface to run simple static scripts on the SQL data base.

	The script should be a string containing one command per line.  You
	can use the backslash as a continuation character.  Leading whitespace
	on a continued line is ignored, the linefeed becomes a single blank.

	Also, we abort and raise an exception on any error in the script unless
	the first character of the command is a "-" (which is ignored otherwise).
	"""
	def _parseScript(self, script):
		queries = []
		for query in getSQLScriptGrammar().parseString(script):
			failOk = False
			if query.startswith("-"):
				failOk = True
				query = query[1:]
			queries.append((failOk, query))
		return queries

	def run(self, script, verbose=False, connection=None):
		"""runs script in a transaction of its own.

		The function will retry a script that fails if the failing command
		was marked with a - as first char.  This means it may rollback
		an active connection, so don't pass in a connection object
		unless you're sure what you're doing.
		"""
		borrowedConnection = connection!=None
		if not borrowedConnection:
			connection = sqlsupport.getDbConnection(config.getDbProfile())
		queries = self._parseScript(script)
		while 1:
			cursor = connection.cursor()
			for ct, (failOk, query) in enumerate(queries):
				query = query.strip()
				if not query:
					continue
				try:
					if sqlsupport.debug:
						print query
					cursor.execute(query)
				except sqlsupport.DbError, msg:
					if failOk:
						gavo.logger.debug("SQL script operation %s failed (%s) -- removing"
							" instruction and trying again."%(query, 
								sqlsupport.encodeDbMsg(msg)))
						queries = queries[:ct]+queries[ct+1:]
						connection.rollback()
						break
					else:
						gavo.logger.error("SQL script operation %s failed (%s) --"
							" aborting script."%(query, sqlsupport.encodeDbMsg(msg)))
						raise
			else:
				break
		cursor.close()
		if not borrowedConnection:
			connection.commit()
			connection.close()

	def runBlindly(self, script, querier):
		"""executes all commands of script in sequence without worrying
		about the consequences.

		No rollbacks will be tried, so these scripts should only contain
		commands guaranteed to work (or whose failure indicates the whole
		operation is pointless).  Thus, failOk is ignored.
		"""
		queries = self._parseScript(script)
		for _, query in queries:
			querier.query(query)


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
		runner = SQLScriptRunner()
		runner.run(self.expander.expand(script))

	def _runSqlScriptInConnection(self, script, connection):
		"""runs a script in connection.

		Since a SQLScriptRunner may rollback, we commit and being a new transaction.
		I can't see a way around this until postgres has nested transactions
		(savepoints don't seem to cut it here).

		For this to work, the caller has to pass in a connection keyword argument
		to runScripts.
		"""
		connection.cursor().execute("COMMIT")
		runner = SQLScriptRunner()
		runner.run(self.expander.expand(script), connection=connection)

	def _runSqlScriptWithQuerier(self, script, querier):
		"""runs a script blindly using querier.

		Any error conditions will abort the script and leave querier's
		connection invalid until a rollback.
		"""
		SQLScriptRunner().runBlindly(self.expander.expand(script), 
			querier=querier)

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

		The function receives the TableDef and the TableWriter as recDef and
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
		"viewCreation": _runSqlScriptWithQuerier,
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
	ListField "scripts", and must have their resource descriptor in the
	rd attribute.
	"""
	def __getScriptHandler(self):
		try:
			return self.__scriptHandler
		except AttributeError:
			self.__scriptHandler = ScriptHandler(self, self.rd)
			return self.__getScriptHandler()
	
	def runScripts(self, waypoint, **kwargs):
		self.__getScriptHandler().runScripts(waypoint, **kwargs)

	def hasScript(self, waypoint):
		"""returns True if there is at least one script for waypoint
		on this object.
		"""
		for scriptType, _, _ in self.get_scripts():
			if scriptType==waypoint:
				return True
		return False

	def addto_scripts(self, item):
		type, name, content = item
		if not type in self.validWaypoints:
			raise gavo.Error("%s objects do not support %s waypoints"%(
				self.__class__.__name__, type))
		self.dataStore["scripts"].append(item)


if __name__=="__main__":
	g = getSQLScriptGrammar()
	print g.parseString("""(foo""")
