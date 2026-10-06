# Build the CoreSpace C scanner. Run inside Ubuntu (WSL):  make
CC      ?= cc
CFLAGS  ?= -std=c11 -O2 -Wall -Wextra -Wpedantic
TARGET  ?= diskviz-scan
PREFIX  ?= $(HOME)/.local

.PHONY: all clean install check

all: $(TARGET)

$(TARGET): diskviz-scan.c
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ $< $(LDFLAGS)

install: $(TARGET)
	install -D -m 755 $(TARGET) $(DESTDIR)$(PREFIX)/bin/diskviz-scan

check:
	cd .. && python3 -m unittest tests.test_c_scanner -v

clean:
	rm -f diskviz-scan
