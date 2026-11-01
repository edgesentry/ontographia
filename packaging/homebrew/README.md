# Homebrew

The CLI formula is maintained in the tap:

[`edgesentry/homebrew-tap` `Formula/ontographia.rb`](https://github.com/edgesentry/homebrew-tap/blob/main/Formula/ontographia.rb)

`brew install ontographia` installs the Rust binary. The command that formula installs is `otg` (published formula: v0.1.8 archives).

Policy and the Python entry point: [docs/otg.md](../../docs/otg.md). Release archive layout, and the Actions vs Mac checks before the next Release: [docs/release.md](../../docs/release.md#pre-release-checks). Decision: [issue #121](https://github.com/edgesentry/ontographia/issues/121).

This directory previously held a formula that created a virtualenv and installed the PyPI wheel. That formula is gone. The wheel stays on pip and uvx. The release workflow does not edit the tap. After a GitHub Release, a follow-up pull request points `Formula/ontographia.rb` at the new archive.
