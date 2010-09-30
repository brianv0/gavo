from gavo.web import adminrender    # for registration
from gavo.web import jpegrenderer   # for registration
from gavo.web import formrender     # for registration
from gavo.web import metarender     # for registration
from gavo.web import productrender  # for registration
from gavo.web import qprenderer     # for registration
from gavo.web import soaprender     # for registration
from gavo.web import taprender      # for registration
from gavo.web import vodal          # for registration
from gavo.web import vosi           # for registration
from gavo.web import uploadservice  # for registration

from gavo.web.grend import GavoRenderMixin, ServiceBasedPage

# XXX DEPRECATED, fix custom renderers and delete the following line
from gavo.web.grend import ServiceBasedPage as ServiceBasedRenderer
