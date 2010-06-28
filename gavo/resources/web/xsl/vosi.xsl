<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet
    xmlns:avl="http://www.ivoa.net/xml/Availability/v0.4"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:ri="http://www.ivoa.net/xml/RegistryInterface/v1.0"
    xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
   
    <!-- ################################################# Configuration

    The idea is to define named templates that are inserted at certain
    places in all top-level templates.  This is mainly to allow custom
    head elements (stylesheet...) or foot lines. -->

    <xsl:template name="localCompleteHead">
        <link rel="stylesheet" href="/static/css/gavo_dc.css"
            type="text/css"/>
        <!-- in GAVO DC, don't index this, there are better meta pages -->
        <meta name="robots" content="noindex,nofollow"/>
    </xsl:template>

    <xsl:template name="localMakeFoot">
        <hr/>
        <a href="/">The GAVO Data Center</a>
    </xsl:template>


    <!-- ############################################## Global behaviour -->

    <xsl:output method="xml" 
      doctype-public="-//W3C//DTD XHTML 1.0 Strict//EN"
      doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"/>

    <!-- Don't spill the content of unknown elements. -->
    <xsl:template match="text()"/>


    <!-- ################################### VOSI availability templates -->
    
    <xsl:template match="avl:available">
        <p>This service is <strong>
            <xsl:choose>
                <xsl:when test=".='true'">up</xsl:when>
                <xsl:when test=".='false'">down</xsl:when>
                <xsl:otherwise>broken</xsl:otherwise>
            </xsl:choose></strong></p>
    </xsl:template>

    <xsl:template match="avl:upSince">
        <p>It has been up since <xsl:value-of select="."/>.</p>
    </xsl:template>

    <xsl:template match="avl:downAt">
        <p>It will go offline approximately at <xsl:value-of select="."/>.</p>
    </xsl:template>

    <xsl:template match="avl:backAt">
        <p>The operators predict it will be back at
            <xsl:value-of select="."/>.</p>
    </xsl:template>

    <xsl:template match="avl:note">
        <p><xsl:value-of select="."/></p>
    </xsl:template>

    <xsl:template match="avl:availability">
        <html>
            <head>
              <title>Service availability</title>
              <xsl:call-template name="localCompleteHead"/>
            </head>
            <body>
                <h1>Availability information for this service</h1>
    				    <xsl:apply-templates/>
                <p><em>All times in UTC</em></p>
                <xsl:call-template name="localFoot"/>
            </body>
        </html>
    </xsl:template>


    <!-- ################################### VOSI capabilities templates -->

    <xsl:template match="identifier"/>

    <xsl:template match="curation">
        <dl class="curation">
            <xsl:apply-templates/>
        </dl>
    </xsl:template>

    <xsl:template match="content">
        <div class="content">
            <p>Further information may be found at the
                <a>
                    <xsl:attribute name="href">
                        <xsl:value-of select="referenceURL"/>
                    </xsl:attribute>
                    reference URL</a>.
            </p>
            <xsl:apply-templates/>
        </div>
    </xsl:template>

    <xsl:template match="title">
        <p class="vosititle"><xsl:value-of select="."/></p>
    </xsl:template>

    <xsl:template match="publisher">
        <dt>Publisher</dt><dd><xsl:value-of select="."/></dd>
    </xsl:template>

    <xsl:template match="creator/name">
        <xsl:value-of select="."/>
    </xsl:template>

    <xsl:template match="creator/logo">
        <xsl:text> </xsl:text>
        <img alt="[Creator logo]">
            <xsl:attribute 
                name="src"><xsl:value-of select="."/></xsl:attribute>
        </img>
    </xsl:template>

    <xsl:template match="creator">
        <dt>Created by</dt><dd><xsl:apply-templates/></dd>
    </xsl:template>

    <xsl:template match="contact">
        <dt>Contact</dt>
        <dd>
            <xsl:value-of select="name"/><br/>
            <xsl:value-of select="address"/><br/>
            <xsl:value-of select="email"/><br/>
            <xsl:value-of select="telephone"/><br/>
        </dd>
    </xsl:template>

    <xsl:template match="content/description">
        <p><strong>Description: </strong><xsl:value-of select="."/></p>
    </xsl:template>

    <xsl:template match="content/referenceURL"/>


    <xsl:template match="ri:Resource">
        <html>
            <head>
              <title>Service Capabilities</title>
              <xsl:call-template name="localCompleteHead"/>
            </head>
            <body>
                <h1>Capabilities of VO service 
                    <xsl:value-of select="identifier"/></h1>
                <p class="capmeta"><em><xsl:value-of select="@status"/></em>,
                    updated <xsl:value-of select="@updated"/></p>
                <xsl:apply-templates/>
                <p><em>All times in UTC</em></p>
                <xsl:call-template name="localMakeFoot"/>
            </body>
        </html>
    </xsl:template>


    <!-- #################################################### Table Sets -->

    <xsl:template match="dataType">
        <xsl:value-of select="text()"/>
        <xsl:if test="@arraysize and @arraysize!='1'"
            >[<xsl:value-of select="@arraysize"/>]
        </xsl:if>
    </xsl:template>

    <xsl:template match="column">
        <tr>
            <td><xsl:value-of select="name"/></td>
            <td><xsl:value-of select="unit"/></td>
            <td><xsl:value-of select="ucd"/></td>
            <td><xsl:apply-templates select="dataType"/></td>
            <td><xsl:value-of select="description"/></td>
        </tr>
    </xsl:template>

    <xsl:template match="table">
        <h2>Table <xsl:value-of select="name"/></h2>
        <p><xsl:value-of select="description"/></p>
        <table class="shorttable">
            <tr>
                <th>Name</th>
                <th>Unit</th>
                <th>UCD</th>
                <th>VOTable type</th>
                <th>Description</th>
            </tr>
            <xsl:apply-templates select="column"/>
        </table>
    </xsl:template>

    <xsl:template match="tableset">
        <html>
            <head>
              <title>VOSI Table Set</title>
              <xsl:call-template name="localCompleteHead"/>
            </head>
            <body>
                <h1>VOSI Table Set</h1>
                <xsl:apply-templates select="*/table"/>
                <xsl:call-template name="localMakeFoot"/>
            </body>
        </html>
    </xsl:template>

</xsl:stylesheet>


<!-- vim:et:sw=4:sta
-->
