"""
A manual registry of renderers.

Renderers are the glue between a core and some output.  A service is the
combination of a subset of renderers and a core.

Renderers are actually defined in web.grend, but we need some way to
get at them from svcs and above, so the registry is kept here.
"""


from gavo import base
from gavo import utils


RENDERER_REGISTRY = {
	'admin': ("web.adminrender", "AdminRenderer"),
	'static': ("web.constantrender", "StaticRenderer"),
	'fixed': ("web.constantrender", "FixedPageRenderer"),
	'form': ("web.formrender", "FeedbackForm"),
	'custom': ("web.customrender", "CustomRenderer"),
	'external': ("web.metarender", "ExternalRenderer"),
	'tablenote': ("web.metarender", "TableNoteRenderer"),
	'tableinfo': ("web.metarender", "TableInfoRenderer"),
	'info': ("web.metarender", "ServiceInfoRenderer"),
	'img.jpeg': ("web.oddrender", "JpegRenderer"),
	'mimg.jpeg': ("web.oddrender", "MachineJpegRenderer"),
	'get': ("web.productrender", "ProductRenderer"),
	'qp': ("web.qprenderer", "QPRenderer"),
	'soap': ("web.soaprender", "SOAPRenderer"),
	'tap': ("web.taprender", "TAPRenderer"),
	'upload': ("web.uploadservice", "Uploader"),
	'mupload': ("web.uploadservice", "MachineUploader"),
	'scs.xml': ("web.vodal", "SCSRenderer"),
	'siap.xml': ("web.vodal", "SIAPRenderer"),
	'siap.xml': ("web.vodal", "SIAPRenderer"),
	'pubreg.xml': ("web.vodal", "RegistryRenderer"),
	'availability': ("web.vosi", "VOSIAvailabilityRenderer"),
	'capabilities': ("web.vosi", "VOSICapabilityRenderer"),
	'tableMetadata': ("web.vosi", "VOSITablesetRenderer"),
}


@utils.memoized
def getRenderer(name):
	if name not in RENDERER_REGISTRY:
		raise base.NotFoundError(name, "renderer", "registred renderers")
	cls = utils.loadInternalObject(*RENDERER_REGISTRY[name])
	if cls.name!=name:
		raise base.ReportableError("Internal Error: Renderer %s is registred"
			" under the wrong name."%name,
			hint="This is probably a typo in svcs.renderers; it needs"
			" to be fixed there")
	return cls

