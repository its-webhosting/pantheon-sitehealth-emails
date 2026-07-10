/ultraplan using the prompt template in `prompts/new-feature-design.prompt-template.md`, plan/design a new
  command line option `--resume-from <SITE_NAME>` that can only be used together with `--all` and will start the
  site loop from the point in the site list where `<SITE_NAME>` is; this allows us to resume `--all` runs that die
  due to a fatal error or that the user interrupts

