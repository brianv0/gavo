"""
This module allows embedding voplot.

To use this, you need to download the VOPlot jar from 
http://vo.iucaa.ernet.in/~voi/voplot.htm
and set the variables below accordingly.
"""

_htmlTemplate = """
<html>
<head>
<title>VOTable Plot</title>
</head>
<body>
<center>
            <EMBED 
                  type = "application/x-java-applet"
                  code = "com.jvt.applets.PlotVOApplet"
                  codebase = "%(codebase)s"
                  votablepath = "%(votablepath)s"
                  userguideURL = "%(userguide_url)s"
                  archive = "%(archive)s"
                  width = "850"
                  height = "650"
                  parameters = "%(parameters)s"
                  MAYSCRIPT = true
                  background = "#faf0e6"
                  scriptable = "true"
                  pluginspage = "http://java.sun.com/products/plugin/1.3.1/plugin-install.html"
            <NOEMBED> 
                    No Java Plug-in support for applet, see, e.g., <a href="http://java.sun.com/products/plugin/">http://java.sun.com/products/plugin/</a>
            </NOEMBED>
            </EMBED>
</center>
</body>
</html>
"""

def getVOPlotPage(template, context):
	return _htmlTemplate%{
		"codebase": "/soft/VOPlot",
		"votablepath": "%s/%s/run/%s?"%(context.getServerURL(),
			context.getEnv("ROOT_URL"), 
			template.getPath()),
		"userguide_url": "/docs/JVTUserGuide.html",
		"archive": ("voplot.jar,voplot_3rdParty/Aladin.jar,voplot_3rdParty/"
			"cern.jar,voplot_3rdParty/fits-0.99.1-1.4-compiled.jar,"
			"voplot_3rdParty/commons-discovery-0.2.jar,"
			"voplot_3rdParty/commons-logging-1.0.4.jar,"
			"voplot_3rdParty/axis.jar,voplot_3rdParty/jaxrpc.jar,"
			"voplot_3rdParty/log4j-1.2.8.jar,voplot_3rdParty/saaj.jar,"
			"voplot_3rdParty/wsdl4j-1.5.1.jar"),
		"parameters": "outputFormat=VOTable%2030&"+context.getQueryArgs(
			suppress=["outputFormat"]),
	}
