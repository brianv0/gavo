"""
Services, cores, and support.

A Service is something that receives some sort of structured data (typically,
a nevow context), processes it into input data using a grammar (default is
the ContextGrammar), pipes it through a core to receive a data set and
optionally tinkers with that data set.

A core receives a data set, processes it, and returns another data set.

Support code is in common.  Most importantly, this is QueryMeta, a data
structure carrying lots of information on the query being processed.
"""

from gavo.svcs.common import (Error, UnknownURI, ForbiddenURI, WebRedirect,
	Authenticate, QueryMeta, emptyQueryMeta)

from gavo.svcs.core import registerCore, getCore, Core

from gavo.svcs.customcore import CustomCore

from gavo.svcs.customwidgets import (OutputFormat, DBOptions, FormalDict, 
	SimpleSelectChoice, 
	NumericExpressionField, DateExpressionField, StringExpressionField, 
	ScalingTextArea)

from gavo.svcs.feedback import FeedbackService

from gavo.svcs.inputdef import InputKey, ContextGrammar, InputDescriptor

from gavo.svcs.outputdef import OutputField, OutputTableDef

from gavo.svcs.runner import runWithData

from gavo.svcs.service import (Service, SvcResult, Publication,
	registerRenderer, getRenderer, RegistryMetaMixin)

from gavo.svcs.standardcores import (DBCore, CondDesc, registerCondDesc,
	mapDBErrors)

from gavo.svcs.computedcore import ComputedCore

from gavo.svcs.uploadcores import UploadCore
