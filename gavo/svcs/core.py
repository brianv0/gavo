"""
Cores are the standard data structure for computing things in the DC.

This module also contains the registry for cores.  If you want to
be able to refer to cores from within an RD, you need to enter your
core here.

Cores return pairs of a type and a payload.  Renderers should normally
be prepared to receive (None, OutputTable) and (mime/str, data/str),
though individual cores might return other stuff (and then only
work with select renderers).
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
	"fancyQueryCore": ("svcs.standardcores", "FancyQueryCore"),
	"dbCore": ("svcs.standardcores", "DBCore"),
	"fixedQueryCore": ("svcs.standardcores", "FixedQueryCore"),
	"nullCore": ("svcs.standardcores", "NullCore"),
	"uploadCore": ("svcs.uploadcores", "UploadCore"),
	"editCore": ("svcs.uploadcores", "EditCore"),
	"ssapCore": ("protocols.ssap", "SSAPCore"),
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

	Cores receive their input in tables the structure of which is
	defined by their inputTable attribute.

	The abstract core element will never occur in resource descriptors.  See 
	`Cores Available`_ for concrete cores.  Use the names of the concrete
	cores in RDs.

	You can specify a contextGrammar in a grammarXML and an outputTable
	in outputTableXML.  These contain fragments of RDs.  They can be
	overridden in the RD XML.
	"""
	name_ = "core"

	inputTableXML = None
	outputTableXML = None

	_rd = rscdef.RDAttribute()
	_inputTable = base.StructAttribute("inputTable", 
		default=base.NotGiven,
		childFactory=inputdef.InputTable, 
		description="Description of the input data.", 
		copyable=True)
	_outputTable = base.StructAttribute("outputTable", 
		default=base.NotGiven,
		childFactory=outputdef.OutputTableDef, 
		description="Table describing what fields are available from this core.", 
		copyable=True)
	_original = base.OriginalAttribute()
	_properties = base.PropertyAttribute()

	def __init__(self, parent, **kwargs):
		if self.inputTableXML is not None:
			g = base.parseFromString(inputdef.InputTable, self.inputTableXML)
			if "inputTable" in kwargs:
				raise base.StructureError(
					"Cannot give an inputTable for cores embedding one.")
			kwargs["inputTable"] = g
		if self.outputTableXML is not None:
			o = base.parseFromString(outputdef.OutputTableDef, self.outputTableXML)
			if "outputTable" in kwargs:
				raise base.StructureError(
					"Cannot give an outputTable for cores embedding one.")
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
