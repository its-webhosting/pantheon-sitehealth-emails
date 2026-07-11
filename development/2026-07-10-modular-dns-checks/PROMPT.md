Move all site-level DNS related tests and checks out of the main script and make them modular under the `./check`
directory, as plugins (only where it makes sense,) and in other internal-to-the-project python
files/modules/packages. A single check can be used for multiple tests wherever they fit naturally together (this
may mean adding only a single check for all site-level DNS related tests, or adding multiple).  Generally clean
up / improve the site-level DNS tests at the same time. Update the site-level DNS related test and checks to take
full advantage of the program's check framework, plugin framework, configuration framework.  I do not think any
of the site-level DNS checks should be disable-able in the config file, but challenge me on this if appropriate.
Cloudflare-specific DNS checks should obey the Cloudflare.enabled config setting and can live in either the DNS
check(s) or in the Cloudflare check (whatever is most logical). Adhere to everything in
`prompts/new-feature-standards.md`.  Let's brainstorm it.

