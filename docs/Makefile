# VPATH must include the directory the RST files are in in a checkout of 
# https://github.com/chbrandt/dachs-doc.git
RST_DIR=../../dachs-doc/docs/source
VPATH=$(RST_DIR):.

HTMLTARGET=vo.ari.uni-heidelberg.de:/var/www/docs/DaCHS
RST_SOURCES=data_checklist.rstx howDoI.rstx ref.rstx tutorial.rstx\
	booster.rstx install.rstx stc.rstx processors.rstx adql.rstx\
	votable.rstx commonproblems.rstx tapquery.rstx develNotes.rstx\
	opguide.rstx elemref.rstx templating.rstx deploy_docker.rstx
ALL_HTML=index.html $(subst .rstx,.html,$(RST_SOURCES))
HTML_FILES=$(ALL_HTML)
ALL_PDF=$(subst .rstx,.pdf,$(RST_SOURCES))


%.html: %.rstx
	gavo gendoc html $<  >$@

%.dvi: %.tex
	latex $<
	latex $<
	rm $*.log

%.ps: %.dvi
	dvips $<

%.pdf: %.tex
	pdflatex $<
	pdflatex $<

%.tex: %.rstx
	gavo gendoc latex $< > $@

booster.html: booster.rstx

.PHONY: ref.rstx elemref.rstx apidoc-stamp
ref.rstx:
	gavo --debug --traceback gendoc refdoc > ref.rstx

elemref.rstx:
	python makeElementIndex.py > $@
	
# Since building apidoc takes forever, you need to manually trigger it
# using make apidoc-stamp
apidoc-stamp:
	touch apidoc-stamp

apidoc: gavo-epydoc.conf apidoc-stamp
	rm -rf apidoc
	epydoc -v --config gavo-epydoc.conf

install: all
	rsync -av *.css gavodoc.js $(HTML_FILES) $(ALL_PDF) index.rstx apidoc $(HTMLTARGET) 
	rsync -av $(RST_DIR)/*.rstx $(HTMLTARGET)

all: $(HTML_FILES) $(ALL_PDF)

clean:
	rm -f $(ALL_HTML)
	rm -f *.log *.aux *.out *.pdf *.toc
	rm -f apidoc-stamp
