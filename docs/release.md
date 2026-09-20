# Release pipeline

## Version convention

| Branch      | VERSION looks like | Who sets it |
|-------------|--------------------|-------------|
| `develop`   | `X.Y.Z-buildN`     | `build-develop` raises `N` on every push |
| `main`      | `X.Y.Z`            | `release` strips the suffix while releasing |
| `hotfix/*`  | `X.Y.Z-HOTFIX`     | `aiflow hotfix` |

`main` never carries a pre-release suffix once a release run has finished.

## develop: continuous builds

`build-develop.yml` runs on every push to `develop`:

1. raise `-buildN` in `VERSION`,
2. build the IPK with that exact version,
3. upload it as a run artifact (14 days),
4. commit the new `VERSION` back to `develop` — only if the build was green.

The bump commit is marked `[skip-bump] [skip ci]` so it cannot re-trigger itself.
Nothing on `develop` is ever tagged, released or pushed into the feed.

## main: releases

A release is cut by merging `develop` → `main` (minor) or `hotfix/*` → `main` (patch).
`release.yml` then:

1. strips `-buildN` / `-HOTFIX` from `VERSION` and commits the clean version to `main`
   (marked `[skip-release] [skip ci]`),
2. skips everything else if `vX.Y.Z` is already tagged,
3. builds the IPK, tags `vX.Y.Z`, publishes the GitHub Release with the IPK attached,
4. dispatches `plugin-released` to `madoe21/enigma2-madoe21-feed` (fails loudly when
   `FEED_DISPATCH_TOKEN` is missing) and waits until the published feed index serves
   the new version,
5. bumps `develop` to `X.(Y+1).0-build1`.

`chore/*` → `main` never releases: `VERSION` is unchanged, so the tag already exists.

## Required secret

`FEED_DISPATCH_TOKEN` — PAT with `repo` scope on `madoe21/enigma2-madoe21-feed`,
used for the `repository_dispatch` that rebuilds the feed.

## Branch protection

`main` and `develop` are protected by rulesets: PR-only, `verify` must pass, no force
push, no deletion. The GitHub Actions app is the only bypass actor — it needs it for the
`VERSION` commits described above.
