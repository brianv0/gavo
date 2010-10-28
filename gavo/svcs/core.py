"""
Cores are the standard data structure for computing things in the DC.

This module also contains the registry for cores.  If you want to
be able to refer to cores from within an RD, you need to enter your
core here.
"""

import sets
import weakref

from gavo import base
from gavo import rscdef
from gavo import utils
from gavo.svcs import inputdef
from gavo.svcs import outputdef


CORE_REGISTRY = {
#	elementName -> module (without gavo.), class name
	"adqlCore": ("protocols.adqlglue", "ADQLCore"),
	"productCore": ("protocols.products", "ProductCore"),
	"siapCore": ("protocols.siap", "SIAPCore"),
	"siapCutoutCore": ("protocols.siap", "SIAPCutoutCore"),
	"registryCore": ("registry.oaiinter", "RegistryCore"),
	"computedCore": ("svcs.computedcore", "ComputedCore"),
	"customCore": ("svcs.customcore", "CustomCore"),
	"feedback": ('svcs.feedback', "FeedbackCore"),
	"fancyQueryCore": ("svcs.standardcores", "FancyQueryCore"),
	"dbCore": ("svcs.standardcores", "DBCore"),
	"fixedQueryCore": ("svcs.standardcores", "FixedQueryCore"),
	"nullCore": ("svcs.standardcores", "NullCore"),
	"uploadCore": ("svcs.uploadcores", "UploadCore"),
	"editCore": ("svcs.uploadcores", "EditCore"),
}


def getCore(name):
	if name not in CORE_REGISTRY:
		raise base.NotFoundError(name, "core", "registred cores")
	cls = utils.loadInternalObject(*CORE_REGISTRY[name])
	if cls.name_!=name:
		raise base.ReportableError("Internal Error: Core %s is registred"
			" under the wrong name."%name,
			hint="This is probably a typo in svcs.core; it needs"
			" to be fixed there")
	return cls


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
