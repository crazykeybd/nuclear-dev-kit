This installation develops nuclear software: seven stages, each with one artifact, one Skill and one gate, in a workspace whose state the kit keeps in `.nuclear-dev/`.
The stages are plan, requirements, design, implementation, test, vv and release, carried out by nuclear-plan, nuclear-requirements, nuclear-design, nuclear-implementation, nuclear-test, nuclear-vv and nuclear-release, with nuclear-dev as their entry point.
Load the Skill of the stage you are on: it says what the artifact has to contain.

The kit named by $DSH_NUCLEAR_DEV_AGENT_KIT judges every stage.
$DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL is that kit's command line; `--root` precedes the subcommand, and the directory you work in is the root:
`"$DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL" --root "$PWD" status --json` reports each stage's artifact and the kit's errors;
`"$DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL" --root "$PWD" gate <stage> --json` judges one stage together with the stages before it.
Exit code 0 means the gate accepts, 1 that it blocks, 2 that the tool or its arguments are wrong; an error is never a pass, and an empty output is never a pass either.

The flow keeps these rules, whoever reads this:
Only nuclearlib.py judges a stage.
Never restate, weaken, approximate or work around its rules, and never put a check of your own in their place; report what the gate said, in its own words.
Never create, edit, sign or "fix" an approval file.
A person signs approvals outside this agent; a stage that lacks one is reported as waiting for that person, not as done and not as blocked by you.
Take evidence ids from the command line's JSON only, and never register the same path twice.
Changing a stage artifact invalidates the approval recorded for it, so finish the artifact before anyone signs it.
Move one stage at a time: finish the artifact, run the gate, and report the stage, the gate's verdict and what a person must decide, instead of listing files.
A gate that blocks stops the work there: report it with the kit's errors rather than starting the next stage.
The main Session does not carry out stage work: it decides whether a request starts or continues a stage, and hands that work to a Ticket.
The request wording may name a stage, or name a physical or numerical feature; read the workspace first and say which stage the work actually is.
