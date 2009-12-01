"""
The rscdef subpackage, concerned with defining resources and their structures,
plus quite a bit of source parsing.
"""

from gavo.rscdef.column import Column, Option, Values, makeOptions

from gavo.rscdef.common import (RDAttribute, ResdirRelativeAttribute,
	ColumnListAttribute, NamePathAttribute, ColumnList)

from gavo.rscdef.coosys import CooSys

from gavo.rscdef.dddef import (DataDescriptor, registerGrammar, Make,
	SourceSpec)

from gavo.rscdef.macros import (StandardMacroMixin, MacroPackage,
	MacDefAttribute)

from gavo.rscdef.mixins import RMixinBase, registerRMixin, getMixin

from gavo.rscdef.procdef import ProcDef, ProcApp

from gavo.rscdef.rmkdef import RowmakerDef, MapRule

from gavo.rscdef.rmkfuncs import addRmkFunc, IgnoreThisRow

from gavo.rscdef.rowtriggers import IgnoreOn, TriggerPulled

from gavo.rscdef.tabledef import (TableDef, SimpleView, makeTDForColumns)
