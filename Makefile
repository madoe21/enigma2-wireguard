ifneq (,$(wildcard .env))
include .env
endif

PLUGIN_NAME  = WireGuard
PACKAGE_NAME = enigma2-plugin-extensions-wireguard
VERSION := $(shell cat VERSION 2>/dev/null | tr -d '[:space:]')

BUILD_DIR       = build
IPK_WORK_DIR    = $(BUILD_DIR)/ipk
DATA_STAGING    = $(IPK_WORK_DIR)/data
CONTROL_STAGING = $(IPK_WORK_DIR)/control

PLUGIN_PATH = usr/lib/enigma2/python/Plugins/Extensions/$(PLUGIN_NAME)
INITD_PATH  = etc/init.d

OUTPUT_IPK = $(BUILD_DIR)/$(PACKAGE_NAME)_$(VERSION)_all.ipk

DOS2UNIX_BIN := $(shell command -v dos2unix 2>/dev/null)

BOX_HOST ?=
BOX_USER ?= root
BOX_PORT ?= 22

.PHONY: all build clean normalize prepare ipk install check-wg restart deploy test

all: ipk

test:
	sh tests/test-resolvconf-shim.sh

clean:
	rm -rf $(BUILD_DIR)

normalize:
ifneq ($(DOS2UNIX_BIN),)
	find src control -type f -exec dos2unix {} \;
endif

prepare: normalize
	mkdir -p $(DATA_STAGING)/$(PLUGIN_PATH)
	mkdir -p $(DATA_STAGING)/$(INITD_PATH)
	mkdir -p $(CONTROL_STAGING)
	cp -r src/$(PLUGIN_NAME)/* $(DATA_STAGING)/$(PLUGIN_PATH)/
	cp src/init.d/wireguard-simple $(DATA_STAGING)/$(INITD_PATH)/wireguard-simple
	chmod 755 $(DATA_STAGING)/$(INITD_PATH)/wireguard-simple
	cp control/control   $(CONTROL_STAGING)/
	sed -i 's/^Version:.*/Version: $(VERSION)/' $(CONTROL_STAGING)/control
	cp control/postinst  $(CONTROL_STAGING)/
	cp control/prerm     $(CONTROL_STAGING)/
	chmod 755 $(CONTROL_STAGING)/postinst $(CONTROL_STAGING)/prerm

ipk: clean prepare
	cd $(IPK_WORK_DIR) && \
	tar -czf data.tar.gz    -C data    . && \
	tar -czf control.tar.gz -C control . && \
	echo "2.0" > debian-binary && \
	ar r $(PACKAGE_NAME)_$(VERSION)_all.ipk debian-binary control.tar.gz data.tar.gz
	mv $(IPK_WORK_DIR)/$(PACKAGE_NAME)_$(VERSION)_all.ipk $(OUTPUT_IPK)

install: ipk
	@test -n "$(BOX_HOST)" || (echo "ERROR: BOX_HOST not set – create a .env file (see .env.example)"; exit 1)
	scp -P $(BOX_PORT) $(OUTPUT_IPK) $(BOX_USER)@$(BOX_HOST):/tmp/
	ssh -p $(BOX_PORT) $(BOX_USER)@$(BOX_HOST) "opkg install --force-reinstall /tmp/$(PACKAGE_NAME)_$(VERSION)_all.ipk"

build: ipk

deploy: install apply

check-wg:
	@test -n "$(BOX_HOST)" || (echo "ERROR: BOX_HOST not set – create a .env file (see .env.example)"; exit 1)
	ssh -p $(BOX_PORT) $(BOX_USER)@$(BOX_HOST) "wg show"

apply:
	@test -n "$(BOX_HOST)" || (echo "ERROR: BOX_HOST not set – create a .env file (see .env.example)"; exit 1)
	ssh -p $(BOX_PORT) $(BOX_USER)@$(BOX_HOST) \
	    "init 4 >/dev/null 2>&1 || killall -9 enigma2 >/dev/null 2>&1 || true; sleep 2; init 3 >/dev/null 2>&1 || true"

restart: apply
