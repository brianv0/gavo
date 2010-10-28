"""
Import this to load some standard protocols that may be needed by RDs.

Parsing RDs using, e.g., the SCS mixin will fail unless the protocols.scs
module has not been imported.
"""

from gavo.protocols import adqlglue
from gavo.protocols import products
from gavo.protocols import scs
from gavo.protocols import siap
from gavo.protocols import simbadinterface
