"""
The rscdef subpackage, concerned with defining resources and their structures,
plus quite a bit of source parsing.
"""

from gavo.rscdef.callablebase import FuncArg

from gavo.rscdef.column import Column, Option, Values, makeOptions

from gavo.rscdef.common import (RDAttribute, ResdirRelativeAttribute,
	ColumnListAttribute, NamePathAttribute, ColumnList)

from gavo.rscdef.coosys import CooSys

from gavo.rscdef.dddef import DataDescriptor, registerGrammar, Make

from gavo.rscdef.macros import (StandardMacroMixin, MacroPackage,
	MacDefAttribute)

from gavo.rscdef.mixins import RMixinBase, registerRMixin, getMixin

from gavo.rscdef.rmkdef import RowmakerDef, MapRule, ProcDef, RDFunction

from gavo.rscdef.rmkprocs import registerProcedure

from gavo.rscdef.rowgens import RowGenDef

from gavo.rscdef.rowtriggers import IgnoreOn, TriggerPulled

from gavo.rscdef.tabledef import TableDef, IgnoreThisRow
