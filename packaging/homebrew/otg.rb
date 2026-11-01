# Homebrew formula for the `otg` CLI.
#
# Copy this file to https://github.com/edgesentry/homebrew-tap Formula/otg.rb
# when the release that contains `otg` is on PyPI. Do not bottle it and do not
# add a formula for `ontographia-mcp` (MCP stays on `uvx` / pip).
#
# Native code ships as the maturin wheels from the existing release workflow.
# This formula only creates a virtualenv and installs `ontographia[cli]` from
# PyPI, then symlinks the `otg` console script. Users do not compile Rust
# when a wheel exists (macOS Apple Silicon, Linux x86_64/arm64, Windows is
# not a Homebrew target).
#
# The `url` / `sha256` pair is a Homebrew source anchor so the formula has a
# version. Install does not build that tarball. When cutting the release that
# adds `otg`, point `url` and `sha256` at that tag and pin `PYPI_SPEC` to the
# same version (see docs/otg.md). Until that publish, `brew install` fails
# closed: PyPI 0.1.6 has no `otg` script and no `cli` extra.

class Otg < Formula
  desc "Intent JSON to deterministic Cypher 25, with read-only Neo4j execute"
  homepage "https://github.com/edgesentry/ontographia"
  url "https://github.com/edgesentry/ontographia/archive/refs/tags/v0.1.6.tar.gz"
  sha256 "f34308f63f15fea28419dba7e8eeb62de8684b8ec73e75281f779c4b76d4929c"
  license "Apache-2.0"

  # Pin this to the PyPI release that contains the `otg` script, for example
  # "ontographia[cli]==0.1.7", before copying the formula into the tap.
  # Unpinned, `uv` resolves the newest `ontographia[cli]` (fails until that
  # extra exists).
  PYPI_SPEC = "ontographia[cli]"

  depends_on "python@3.13"
  depends_on "uv" => :build

  def install
    python = Formula["python@3.13"].opt_bin/"python3.13"
    system "uv", "venv", libexec, "--python", python
    system "uv", "pip", "install", "--python", libexec/"bin/python", PYPI_SPEC
    otg = libexec/"bin/otg"
    unless otg.exist?
      odie "#{PYPI_SPEC} did not install bin/otg. Publish the release that adds the otg script."
    end

    bin.install_symlink otg
  end

  def caveats
    <<~EOS
      `otg` compiles Intent JSON to Cypher and can execute only read-only queries.
      Neo4j credentials come from flags or NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD.
      The MCP server is not part of this formula; use `uvx` or pip for `ontographia-mcp`.
    EOS
  end

  test do
    assert_match "read-only", shell_output("#{bin}/otg --help")
    assert_match "execute", shell_output("#{bin}/otg --help")
  end
end
