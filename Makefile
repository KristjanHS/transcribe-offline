# Maintainer helper; not part of the release zip.
BUMP ?= patch

# make release [BUMP=patch|minor|major]: tag the current version if it is untagged,
# otherwise bump, commit and tag the next one; the pushed tag triggers release.yml.
.PHONY: release
release:
	@test -z "$$(git status --porcelain)" || { echo "Working tree not clean."; exit 1; }
	@test "$$(git branch --show-current)" = main || { echo "Not on main."; exit 1; }
	@git fetch -q --tags origin
	@v=$$(uv --directory app version --short); \
	if git rev-parse -q --verify "refs/tags/v$$v" >/dev/null; then \
		v=$$(uv --directory app version --bump $(BUMP) --no-sync --short) && \
		git commit -q -m "chore(release): v$$v" -- app/pyproject.toml app/uv.lock || exit 1; \
	fi; \
	git tag "v$$v" && git push -q --atomic origin main "v$$v" && \
	echo "Pushed v$$v; release.yml is running (gh run watch)."
