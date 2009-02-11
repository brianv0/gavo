"""
Cores wrapping some external program.
"""

import os
import subprocess
import threading
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.svcs import core
from gavo.svcs import outputdef
from gavo.svcs import service


argMFRegistry = base.ValueMapperFactoryRegistry()
_registerArgMF = argMFRegistry.registerFactory

def _defaultMapperFactory(colProps):
	def coder(val):
		return str(val)
	return coder
_registerArgMF(_defaultMapperFactory)

datetimeDbTypes = set(["timestamp", "date", "time"])
def _datetimeMapperFactory(colProps):
	if colProps["dbtype"] not in datetimeDbTypes:
		return
	def coder(val):
		if val:
			return val.strftime("%Y-%m-%dT%H:%M:%S")
		return "None"
	return coder
_registerArgMF(_datetimeMapperFactory)


class ComputedCore(core.Core):
	"""A core wrapping external applications.
	
	ComputedCores wrap command line tools taking command line arguments,
	reading from stdin, and outputting to stdout.

	The command line arguments are described a table with role "parameters"
	in the inputDD.  Only the first row of that table is used.

	The input to the program are described in a table with role "inputLine"
	in the inputDD.  All rows are serialized quite like they are with the
	TSV output, except only whitespace is entered between the values.
	
	The output is the primary table of parsing the program's output with
	the data child.
	"""
	name_ = "computedCore"

	_computer = rscdef.ResdirRelativeAttribute("computer",
		default=base.Undefined, description="Resdir-relative basename of"
			" the binary doing the computation.  The standard rules for"
			" cross-platform binary name determination apply.")
	_resultParse = base.StructAttribute("resultParse",
		description="Data descriptor to parse the computer's output.",
		childFactory=rscdef.DataDescriptor)

	def completeElement(self):
		if self.resultParse:
			self.outputTable = outputdef.OutputTableDef.fromTableDef(
				self.resultParse.getPrimary())
		self._completeElementNext(ComputedCore)

	def _feedInto(self, data, destFile):
		"""writes data into destFile from a thread.

		This is done to cheaply avoid deadlocks.  Ok, I'll to a select loop
		piping directly into the grammar one of these days.
		"""
		def writeFile():
			destFile.write(data)
			destFile.close()
		writeThread = threading.Thread(target=writeFile)
		writeThread.setDaemon(True)
		writeThread.start()
		return writeThread

	def _getArgs(self, inputData):
		t = inputData.getTableWithRole("parameters")
		argRow = t.rows[0]
		args = [base.getBinaryName(self.computer)]
		for c in t.tableDef:
			val = argRow.get(c.name, base.Undefined)
			if val is base.Undefined:
				raise base.ValidationError("Command line argument %s must not"
					" be undefined"%c.name, c.name, base.Undefined)
# XXX TODO: use valuemappers here
			args.append(str(val))
		return args

	def _getInput(self, inputData):
		t = inputData.getTableWithRole("inputLine")
		names = [c.name for c in t.tableDef]
		res = []
		for row in base.getMappedValues(t, argMFRegistry):
			res.append(" ".join([row[name] for name in names]))
		return str("\n".join(res))

	def _runAndCapture(self, inputData):
# if we wanted to get really fancy, it shouldn't be hard to pipe that stuff
# directly into the grammar.
		pipe = subprocess.Popen(self._getArgs(inputData), 2**16, 
			stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True,
			cwd=os.path.dirname(self.computer))
		writeThread = self._feedInto(self._getInput(inputData), pipe.stdin)
# XXX TODO: detect and handle errors in some sensible way.
		data = pipe.stdout.read()
		writeThread.join(0.1)
		return data

	def run(self, service, inputData, queryMeta):
		"""starts the computing process if this is a computed data set.
		"""
		res = rsc.makeData(self.resultParse,
			forceSource=StringIO(self._runAndCapture(inputData)))
		return res.getPrimaryTable()


core.registerCore(ComputedCore)

