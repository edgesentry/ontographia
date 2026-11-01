# Homebrew

The CLI formula is maintained in the tap:

[`edgesentry/homebrew-tap` `Formula/ontographia.rb`](https://github.com/edgesentry/homebrew-tap/blob/main/Formula/ontographia.rb)

`brew install ontographia` installs the Rust binary. The command that formula installs is `otg`.

Policy, what the published tap installs today, and the Python entry point: [docs/otg.md](../../docs/otg.md). Release archive layout and the tap update that follows a release: [docs/release.md](../../docs/release.md). Decision: [issue #121](https://github.com/edgesentry/ontographia/issues/121).

This directory previously held a formula that created a virtualenv and installed the PyPI wheel. That formula is gone. The wheel stays on pip and uvx. The tap pull request that points `Formula/ontographia.rb` at the `otg` binary waits until that binary is in a GitHub Release.
