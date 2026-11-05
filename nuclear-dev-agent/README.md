# nuclear-dev-agent

> **Research prototype for reference only, not an official DeepSeek product.** This code grew out of our team's day-to-day development work, with much of the engineering done by coding agents. Treat it as research code, not production-ready software. It may still contain bugs, and its coding style and engineering practices may be inconsistent. Review and adapt it before using it in your own environment.
>
> We have adapted it for publication, so it is not identical to our internal version or the implementation described in *Exploring Super-agent Design: Towards a More Autonomous Agent System*. Some designs discussed in the article are directions for future development and are not implemented in this prototype.

nuclear-dev-agent is a proactive coding agent for one GitHub repository, packaged as a bundle for [DeepSeek Harness](https://www.deepseek.com/en/harness/). It listens to GitHub and, optionally, Feishu. When someone allowed asks the agent for work, it opens a work item, works on it in its own agent session and directory, and answers in the original conversation, for example with a pull request. A web panel shows what needs a person.

## The nuclear development flow

In this repository the agent is the main body of `nuclear-dev-kit`: a proactive coding agent for nuclear software
development, not a general one. Each Ticket is a unit of work on one of the kit's seven stages — plan, requirements,
design, implementation, test, verification & validation, release — and the agent reads the stage state of the Ticket's
directory by running the kit's own command line, never by re-implementing it:

- `src/nuclear/` holds the stage table and the bridge to `nuclearctl.py`; the kit's `nuclearlib.py` remains the only
  judge of a stage, and its messages reach the panel verbatim;
- `prompts/nuclear.md` is the built-in `runtime/nuclear` section every Session reads: the stages, the gate command line
  through `$DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL`, and the rule that a person signs approvals outside this agent;
- the **Nuclear** panel tab shows one board per Ticket directory, and every Ticket page shows its seven stages;
- the deployment names the kit and the interpreter (`nuclear.kitPath`, `nuclear.python`), so one profile can point at one
  kit checkout.

Nothing here generates an approval, weakens a gate or replaces a signature: a stage the kit does not accept is reported
as it is, and work stops there.

It is also a way of working with an agent: **take as little human attention as possible, and give as much value as possible.** An agent that can act for a whole team can also waste a whole team's attention, so it acts only when asked or when a rule the team wrote allows it, and speaks only when someone must act or can use a result. [docs/000-philosophy.md](docs/000-philosophy.md) explains the principle and what it asks of the operator.

## Setup

Setup has many steps, so an agent does it with you. Ask your coding agent:

> Read SETUP.md in this repository and set up nuclear-dev-agent with me.

It asks one short question at a time, shows the full plan once, and then installs and configures everything. [SETUP.md](SETUP.md) is what it follows.

## Documentation

Read the numbered documents in order; each builds only on the ones before it.

- [000 Philosophy](docs/000-philosophy.md)
- [001 Domain model](docs/001-domain.md)
- [002 Authorization](docs/002-authorization.md)
- [003 Execution](docs/003-execution.md)
- [004 Prompts](docs/004-prompts.md)
- [005 Panel](docs/005-panel.md)
- [006 Deployment](docs/006-deployment.md): manual setup, configuration, upgrades and troubleshooting
- [007 Architecture](docs/007-architecture.md)
- [008 Cookbook](docs/008-cookbook.md): adding a Source

## Development

`pnpm check` runs the typecheck, the tests and the build.

## License

[MIT](LICENSE)
