.PHONY: srpm
srpm:
	dnf -y install python3 git rpm-build
	python3 packaging/check_release.py --require-license
	python3 packaging/make_source.py --output packaging/fedora --no-aur
	mkdir -p "$(outdir)"
	rpmbuild -bs --define "_sourcedir $(CURDIR)/packaging/fedora" --define "_srcrpmdir $(outdir)" packaging/fedora/mirivue-gnome.spec
