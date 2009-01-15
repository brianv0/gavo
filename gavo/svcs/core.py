"""
Cores are the standard data structure for computing things in the DC.
"""

import sets
import weakref

from gavo import base
from gavo import rscdef
from gavo.svcs import inputdef
from gavo.svcs import outputdef


_coreRegistry = {}

def registerCore(core):
	_coreRegistry[core.name_] = core

def getCore(name):
	return _coreRegistry[name]


class Core(base.Structure):
	"""is something that does computations for a service.

	Cores have an inputDD  which defines what inputs it can possibly take (these
	must be inputdef.InputTables).  The output should be a res.Data instance
	with the necessary descriptions.

	Service currently expect cores to return a table; cores define the
	structure of their default return table in outputTable.  The table
	returned might have a different structure if the core asks the service
	what columns it should return for a concrete query.  Users of the
	tables returned should consult the table metadata, not the core metadata,
	which is there for registry-type purposes.
	"""
	name_ = "core"

	_rd = rscdef.RDAttribute()
	_inputDD = base.StructAttribute("inputDD", 
		childFactory=inputdef.InputDescriptor, description="Description of the"
			" input data")
	_outputTable = base.StructAttribute("outputTable",
		childFactory=outputdef.OutputTableDef, description="Table describing"
			" what fields are available from this core.", copyable=True)
	_original = base.OriginalAttribute()

	def __repr__(self):
		return "<%s at %s>"%(self.__class__.__name__, id(self))
	
	def __str__(self):
		return repr(self)

	def run(self, service, inputData, queryMeta):
		raise NotImplementedError("%s cores are missing the run method"%
			self.__class__.__name__)


class StaticCore(Core):
	"""is a core that always returns a static file.
	"""
	name_ = "staticCore"

	_file = rscdef.ResdirRelativeAttribute("file", default=base.Undefined,
		description="Resdir-relative path of the file to deliver")

	def completeElement(self):
		if self.outputTable is base.Undefined:
			self.outputTable = base.makeStruct(outputdef.OutputTableDef)
		if self.inputDD is base.Undefined:
			self.inputDD = base.makeStruct(inputdef.InputDescriptor)
		self._completeElementNext(StaticCore)

	def run(self, service, inputData, queryMeta):
		f = open(self.file)
		res = f.read()
		f.close()
		return res

registerCore(StaticCore)
