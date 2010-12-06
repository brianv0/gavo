"""
Cores are the standard object for computing things in the DC.

This module also contains the registry for cores.  If you want to
be able to refer to cores from within an RD, you need to enter your
core here.

Cores return pairs of a type and a payload.  Renderers should normally
be prepared to receive (None, OutputTable) and (mime/str, data/str),
though individual cores might return other stuff (and then only
work with select renderers).

In general, the input table definition is mandatory, i.e., you have
to come up with it.  Services do this either ad-hoc from input from
the web or using an inputDD.

The output table, on the other hand, is "advisory", mainly for registry
and documentation purposes ("I *could* return this").  In particular
DBBasedCores will usually adapt to the service's wishes when it comes
to the output table structure, not to mention the ADQL core.  This doesn't
hurt since whatever is returned comes with structure documentation of
its own.

Cores may also want to adapt to renderers.  This is a bit of a hack to
support, e.g., form and scs within a single service, which avoids
two different VOResource records just because of slightly differning
input definitions.

The interface here is the adaptForRenderer method.  It takes a single
argument, the renderer, either as a simple name resolvable in the renderer
registry, or as a renderer instance or class.  It must return a new
core instance.

Currently, two mechanisms for core adaptation are in place:

(1) generically, inputKeys can have properties onlyForRenderer and 
notForRenderer with the obvious semantics.

(2) cores that have condDescs may adapt by virtue of condDesc's 
adaptForRenderer method.
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

	def adaptForRenderer(self, renderer):
		"""returns a core object tailored for renderer.
		"""
		newIT = self.inputTable.adaptForRenderer(renderer)
		if newIT is self.inputTable:
			return self
		else:
			return self.change(inputTable=newIT)

	def run(self, service, inputData, queryMeta):
		raise NotImplementedError("%s cores are missing the run method"%
			self.__class__.__name__)

	def makeUserDoc(self):
		return ("Polymorphous core element.  May contain any of the cores"
			" mentioned in `Cores Available`_ .")
