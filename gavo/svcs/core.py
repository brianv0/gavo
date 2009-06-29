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
	"""A definition of the "active" part of a service.

	Cores have inputs defined via inputDD, a data descriptor containing
	InputTables.  The output is normally defined as an OutputTable, though
	Cores may return other data structures if appropriate.  They cannot
	be used in services using the standard form renderer then, though.

	Note that the table returned by a core must not necessarily match
	the output format requested by a service exactly.  Services can build
	restrictions of the core's output.

	Users of the tables returned should consult the table metadata, not the 
	core metadata, which is there for registry-type purposes.

	The abstract core element will never occur in resource descriptors.  See 
	`Cores Available`_ for concrete cores.  Use the names of the concrete
	cores in RDs.

	You can specify a contextGrammar in a grammarXML and an outputTable
	in outputTableXML.  These contain fragments of RDs.  They can be
	overridden in the RD XML.
	"""
	name_ = "core"

	grammarXML = None
	outputTableXML = None

	_rd = rscdef.RDAttribute()
	_inputDD = base.StructAttribute("inputDD", 
		childFactory=inputdef.InputDescriptor, description="Description of the"
			" input data.") # must not be copyable, else autogeneration of
	                    # inputDDs for DbCores fails for copied cores.
	_outputTable = base.StructAttribute("outputTable",
		childFactory=outputdef.OutputTableDef, description="Table describing"
			" what fields are available from this core.", copyable=True)
	_original = base.OriginalAttribute()
	_properties = base.PropertyAttribute()

	def __init__(self, parent, **kwargs):
		if self.grammarXML is not None:
			g = base.parseFromString(inputdef.ContextGrammar, self.grammarXML)
			if "inputDD" in kwargs:
				raise base.StructureError("Cannot give an inputDD for custom cores"
					" defining one.")
			kwargs["inputDD"] = base.makeStruct(inputdef.InputDescriptor,
				grammar=g)
		if self.outputTableXML is not None:
			o = base.parseFromString(outputdef.OutputTableDef, self.outputTableXML)
			if "outputTable" in kwargs:
				raise base.StructureError("Cannot give an outputTable for custom cores"
					" defining one.")
			kwargs["outputTable"] = o
		base.Structure.__init__(self, parent, **kwargs)

	def __repr__(self):
		return "<%s at %s>"%(self.__class__.__name__, id(self))
	
	def __str__(self):
		return repr(self)

	def run(self, service, inputData, queryMeta):
		raise NotImplementedError("%s cores are missing the run method"%
			self.__class__.__name__)

	def makeUserDoc(self):
		return ("Polymorphous core element.  May contain any of the cores"
			" mentioned in `Cores Available`_ .")


class StaticCore(Core):
	"""A core that always returns a static file.

	This core clearly will not run with most renderers.  It's also
	not usually necessary since you can allow a static renderer on
	services that does the same thing (and better).

	So, this is for really weird situations.
	"""
	name_ = "staticCore"

	_file = rscdef.ResdirRelativeAttribute("file", default=base.Undefined,
		description="Resdir-relative path of the file to deliver.")

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
