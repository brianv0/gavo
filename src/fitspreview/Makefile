LDFLAGS=-lcfitsio -ljpeg -lm
CFLAGS=-Wall -g

TARGET=$(shell  P=`gavo config platform`; if [ -z $$P ]; \
	then echo "fitspreview"; else echo "fitspreview-$$P"; fi)

install:

$(TARGET): fitspreview.o
	$(CC) $(CFLAGS) -o $(TARGET) $^ $(LDFLAGS)

install: $(TARGET)
	mkdir -p `gavo config inputsDir`/__system/bin
	cp $(TARGET) `gavo config inputsDir`/__system/bin

clean:
	rm -f *.o fitspreview $(TARGET)
