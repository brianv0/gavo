"""
Support code for attaching scripts to objects.

Scripts can be either in python or in SQL.  They always live on
make instances.  For details, see Scripting_ in the reference
documentation.
"""

import re
import sys
import weakref

from pyparsing import Word, OneOrMore, ZeroOrMore, QuotedString, Forward,\
	SkipTo, Optional, StringEnd, Regex, LineEnd, Suppress, ParserElement,\
	Literal, White, ParseException, dblQuotedString

from gavo import base
from gavo import utils
from gavo.base import sqlsupport
from gavo.rscdef import rmkfuncs


class Error(base.Error):
	pass


def _getSQLScriptGrammar():
	"""returns a pyparsing ParserElement that splits SQL scripts into
	individual commands.

	The rules are: Statements are separated by semicolons, empty statements
	are allowed.
	"""
	atom = Forward()
	atom.setName("Atom")

	sqlComment = Literal("--")+SkipTo("\n", include=True)
	cStyleComment = Literal("/*")+SkipTo("*/", include=True)
	comment = sqlComment | cStyleComment

	simpleStr = QuotedString(quoteChar="'", escChar="\\", unquoteResults=False)
	quotedId = QuotedString(quoteChar='"', escChar="\\", unquoteResults=False)
	dollarQuoted = Regex(r"(?s)\$(\w*)\$.*?\$\1\$")
	dollarQuoted.setName("dollarQuoted")
	# well, quotedId is not exactly a string literal.  I hate it, and so
	# it's lumped in here.
	strLiteral = simpleStr | dollarQuoted | quotedId
	strLiteral.setName("strLiteral")

	other = Regex("[^;'\"$]+")
	other.setName("other")

	literalDollar = Literal("$") + ~ Literal("$")
	statementEnd = ( Literal(';') | StringEnd())

	atom <<  ( Suppress(comment) | other | strLiteral | literalDollar )
	statement = OneOrMore(atom) + Suppress( statementEnd )
	statement.setName("statement")
	statement.setParseAction(lambda s, p, toks: " ".join(toks))

	script = OneOrMore( statement ) + StringEnd()
	script.setName("script")
	script.setParseAction(lambda s, p, toks: [t for t in toks.asList()
		if str(t).strip()])

	if False:
		atom.setDebug(True)
		other.setDebug(True)
		strLiteral.setDebug(True)
		statement.setDebug(True)
		statementEnd.setDebug(True)
		dollarQuoted.setDebug(True)
		literalDollar.setDebug(True)
	return script


getSQLScriptGrammar = utils.CachedGetter(_getSQLScriptGrammar)


class ScriptRunner(object):
	"""An object encapsulating the preparation and execution of
	scripts.

	They are constructed with instances of Script below and have
	a method run(dbTable, **kwargs).

	You probably should not override __init__ but instead override
	_prepare(script) which is called by __init__.
	"""
	def __init__(self, script):
		self.name, self.notify = script.name, script.notify
		self._prepare(script)
	
	def _prepare(self, script):
		raise ValueError("Cannot instantate plain ScriptRunners")


class SQLScriptRunner(ScriptRunner):
	"""A runner for SQL scripts.

	These will always use the table's querier to execute the statements.

	Keyword arguments to run are ignored.
	"""
	def _prepare(self, script):
		self.statements = getSQLScriptGrammar().parseString(script.getSource())
	
	def run(self, dbTable, **kwargs):
		for statement in self.statements:
			dbTable.query(statement.replace("%", "%%"))


class PythonScriptRunner(ScriptRunner):
	"""A runner for python scripts.

	The scripts can access the current table as table (and thus run
	SQL statements through table.query(query, pars)).

	Additional keyword arguments are available under their names.

	You are in the namespace of usual procApps (like procs, rowgens, and
	the like).
	"""
	def _prepare(self, script):
		code = ("def scriptFun(table, **kwargs):\n"+
			utils.fixIndentation(script.getSource(), "      ")+"\n")
		self.scriptFun = rmkfuncs.makeProc("scriptFun", code, "", self)
	
	def run(self, dbTable, **kwargs):
# XXX BAD HACK ALERT: I want the names from kwargs to be visible
# in scriptFun, and thus I abuse func_globals.  I guess even exec
# would be better...
		self.scriptFun.func_globals.update(kwargs)
		self.scriptFun(dbTable, **kwargs)


class Script(base.Structure):
	"""A script, i.e., some executable item within a resource descriptor.

	The content of scripts is given by their type -- usually, they are
	either python scripts or SQL with special rules for breaking the
	script into individual statements (which are basically like python's).

	See `Scripting`_.
	"""
	name_ = "script"
	typeDesc_ = "Embedded executable code with a type definition"

	_lang = base.EnumeratedUnicodeAttribute("lang", base.Undefined,
		description="Language of the script.", 
		validValues=["SQL", "python"], copyable=True)
	_type = base.EnumeratedUnicodeAttribute("type", base.Undefined,
		description="Point of time at which script is to run.", 
		validValues=["preImport", "newSource", "preIndex", "postCreation",
			"beforeDrop"], copyable=True)
	_name = base.UnicodeAttribute("name", default="anonymous",
		description="A human-consumable designation of the script.",
		copyable=True)
	_notify = base.BooleanAttribute("notify", default=True,
		description="Send out a notification when running this"
			" script.", copyable=True)
	_content = base.DataContent(copyable=True, description="The script body.")
	_original = base.OriginalAttribute()

	def getSource(self):
		"""returns the content with all macros expanded.
		"""
		return self.parent.getExpander().expand(self.content_)


class ScriptingMixin(object):
	"""A mixin that gives objects a getRunner method and a script attribute.

	Within the DC, this is only mixed into make.

	The getRunner() method returns a callable that takes the current table
	(we expect db tables, really), the phase and possibly further keyword
	arguments, as appropriate for the phase.

	Objects mixing this in must also support define a method
	getExpander() returning an object mixin in a MacroPackage.
	"""
	_scripts = base.StructListAttribute("scripts", childFactory=Script,
		description="Code snippets attached to this object.  See Scripting_ .",
		copyable=True)

	def getRunner(self):
		runnersByPhase = {}
		for rawScript in self.scripts:
			if rawScript.lang=="SQL":
				runner = SQLScriptRunner(rawScript)
			else:
				runner = PythonScriptRunner(rawScript)
			runnersByPhase.setdefault(rawScript.type, []).append(runner)
			
		def runScripts(table, phase, **kwargs):
			for runner in runnersByPhase.get(phase, []):
				if runner.notify:
					base.ui.notifyScriptRunning(runner)
				runner.run(table, **kwargs)
		
		return runScripts
