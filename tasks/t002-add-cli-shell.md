# T002 - Add CLI shell

ID: T002
Title: Add CLI shell
Status: done
Depends on: T001
Requirement coverage: FR-100 through FR-107, NFR-001
Milestone: M0 - Project skeleton and baseline
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Implement `codectx.cli:main`.
- Add subcommands: `index`, `health`, `search`, `symbols`, `context`, `neighborhood`, `inspect-node`, `inspect-edge`.
- Each command should parse arguments and print a clear placeholder or dispatch to stub service functions.

Deliverable:

- Working CLI entry point.

Acceptance:

- `codectx --help` lists commands.
- `codectx index --help` shows repo argument.
- Stub commands return successful exit code or explicit not-yet-implemented message.
