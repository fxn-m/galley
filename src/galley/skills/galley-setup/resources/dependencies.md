# External dependency bootstrap

Use this contract during every setup run and whenever the main `galley` skill encounters an
unavailable external command. The outcome is four exact commands that run in the agent's own
environment; explaining how the user could install them is not setup.

## Release requirements

| Command | Required version | Read-only probe | Why Galley needs it |
|---|---:|---|---|
| `pandoc` | `3.10` | `pandoc --version` | Parse Markdown or extracted HTML and package EPUB3. |
| `defuddle` | `0.19.1` | `defuddle --version` | Retrieve and extract the primary work from an Article-Like Page. |
| `epubcheck` | `5.3.0` | `epubcheck --version` | Check the finished EPUB and emit its conformance document. |
| `resvg` | `0.48.1` | `resvg --version` | Rasterise SVG cover and inline artwork deterministically. |

Pandoc's first line must be `pandoc 3.10`; Defuddle and resvg each print the bare version;
EPUBCheck prints `EPUBCheck v5.3.0`. Capture stdout and stderr because version banners are not
consistent about which stream they use. Record the resolved executable path as well as the
observed version.

`npm` is a bootstrap prerequisite for Defuddle, not a fifth Galley runtime dependency. A Java
runtime is part of an EPUBCheck installation, but an `epubcheck` command that already answers with
the required version needs no separate Java diagnosis; a package-manager wrapper may select its
own runtime successfully even when a bare `java` command does not.

## Choosing an installation route

Inventory first, without mutation: operating system, architecture, the four probes, writable
user-level command directories already on PATH, and available package managers. Classify each
requirement as `ready`, `missing`, `unusable`, or `wrong-version`.

For each requirement that is not ready, prefer these routes in order:

1. An existing package manager whose candidate metadata states the exact required version.
2. The immutable upstream release artifact listed below, installed in a versioned user-owned
   directory with a command or shim in a user-writable bin directory.
3. A build from the exact upstream tag when no binary exists for this platform and a suitable
   toolchain is already present or is included in the approved plan.

Inspect candidate metadata before using an unversioned package-manager command. For example,
`brew install pandoc` is suitable only while Homebrew's candidate is exactly `3.10`; a later
formula would silently install a different parser. Preserve an existing wrong-version command by
installing side by side unless the proposed plan explicitly explains why that installation itself
will be replaced.

When a command needs to be exposed, prefer an existing user-writable bin directory that is already
on PATH. If none can make the pinned command win resolution, include the exact shell-profile or
PATH change in the summary and make it after approval. Verify from a fresh command environment,
not merely by invoking an absolute path that later Galley runs will not find.

## Pinned upstream artifacts

Download only from the stated HTTPS release and verify SHA-256 before extraction. Keep the whole
versioned payload together; expose the command rather than scattering its support files.

### Pandoc 3.10

Release: <https://github.com/jgm/pandoc/releases/tag/3.10>

| Platform | Asset | SHA-256 |
|---|---|---|
| macOS arm64 | `pandoc-3.10-arm64-macOS.zip` | `d9cad01d96ae774a0dc8c8c45bb1ad3e4c5ff2cc2e24f45958f5f9b7974aee34` |
| macOS x86_64 | `pandoc-3.10-x86_64-macOS.zip` | `6334f4d9af7c9e37e761dfad56fa5507685f6d29724ebf31c4be6d5c654a3161` |
| Linux arm64 | `pandoc-3.10-linux-arm64.tar.gz` | `55413dfb0c1aec861641fe858f1f73e84848f3db497b1c0c02e62887ea76f4a4` |
| Linux x86_64 | `pandoc-3.10-linux-amd64.tar.gz` | `e0f8af62d0f267d22baa5bcefe6d5dda3a097ccc60de794b759fe03159923244` |
| Windows x86_64 | `pandoc-3.10-windows-x86_64.zip` | `bb808d00fd58762299d64582a9b4c3e4b106cd929e62c5f19bcdcb496f1e54ae` |

Use the archive rather than the system installer for a user-local installation. The executable is
under the archive's `bin` directory.

### Defuddle 0.19.1

Package: <https://www.npmjs.com/package/defuddle/v/0.19.1>

With a working npm, install the exact CLI yourself:

```sh
npm install --global defuddle@0.19.1
```

If npm is absent, select a maintained Node.js distribution through an already-present platform
package manager or the official Node.js downloads, include that bootstrap in the same plan, then
run the pinned npm installation. Use a user-local npm prefix when the global prefix is not
user-writable; expose its `bin` directory as part of the approved PATH plan.

### EPUBCheck 5.3.0

Release: <https://github.com/w3c/epubcheck/releases/tag/v5.3.0>

| Platform | Asset | SHA-256 |
|---|---|---|
| all platforms | `epubcheck-5.3.0.zip` | `6c07e68584b2e2ce2f89fe06e1246dfead3eb36b46b340e7d93524f29dcff6c5` |

The archive is a Java application and carries `epubcheck.jar` plus its sibling `lib/` directory.
Keep both in place. When an exact package-manager formula is unavailable, install a maintained Java
runtime if needed and create the platform's ordinary command wrapper around:

```sh
java -jar /PATH/TO/epubcheck-5.3.0/epubcheck.jar "$@"
```

Resolve `java` to the selected runtime in that wrapper when the runtime is not itself on PATH. On
Windows, create the equivalent `.cmd` launcher. The finished `epubcheck --version` probe must load
the JVM and answer with the pinned version.

### resvg 0.48.1

Release: <https://github.com/linebender/resvg/releases/tag/v0.48.1>

| Platform | Asset | SHA-256 |
|---|---|---|
| macOS arm64 | `resvg-macos-aarch64.zip` | `06440eb5aa14a28cbfc7e40ae39e1ffa71adc051b89fbaa913b4f1d9b905d09f` |
| macOS x86_64 | `resvg-macos-x86_64.zip` | `0135923e443863db251a26bd78eabc6efb4b59d67b8cdc5469e3e1da26bc0ce2` |
| Linux x86_64 | `resvg-linux-x86_64.tar.gz` | `fa8c26495a187e592c501db15bf9e8a9fdc051d4b2b336b39703d5b59f912b9d` |

Those archives contain the standalone `resvg` executable. On another Rust-supported target, the
fallback is an exact crates.io build with an existing or approved Rust toolchain:

```sh
cargo install resvg --version 0.48.1 --locked
```

## Approval and completion

The setup summary names every download URL and digest, package-manager or build command,
installation destination, wrapper, and environment edit. One confirmation covers that finite
plan together with the Workspace proposal. Installation tools may still surface their own host
approval when they cross a protected boundary.

After executing the plan, start a fresh command environment and rerun all four probes. Setup is
complete only when every resolved command reports the required version and Workspace validation
also succeeds. On a failed download, digest, installer, build, wrapper or probe, retain the
command's diagnostic, report the precise blocker, and stop without turning the remaining commands
into instructions for the user.
