# pwddb design interview

## Agreed requirements

- Commands live in `/home/vimkim/my-cubrid/bin`.
- The lifecycle command is `my-cubrid-pwddb` with `create`, `recreate`, and `delete`.
- A ticket extractor checks the current directory basename, then the current Git branch, and fails when neither contains a ticket.
- `my-cubrid-pwddb-getname` uses the extracted ticket, otherwise at most ten characters from the directory basename, preserving hyphens.
- Both name resolution and lifecycle commands support `--append-name SUFFIX`, adding `-SUFFIX`.
- Creation defaults to an empty database. `--load demodb` selects sample data; a suffix alone does not load data.
- Add `pwddb-create`, `pwddb-recreate`, `pwddb-delete`, and corresponding `-demodb` recipes. The demodb create/recreate recipes append the suffix and explicitly select the template.

## Existing tooling evidence

- Recipe source: `stow/cubrid/.just/db.just`; the CUBRID worktree's justfile points into this repository.
- Nearby CLIs use executable Bash scripts, help flags, stderr for usage errors, and sibling helper lookup through `BASH_SOURCE`.
- Existing creation uses `$CUBRID_DATABASES/<name>`, 20M database/log volumes, and `en_US.utf8`. The demodb recipe explicitly uses 16K database pages.
- The loader uses `cubrid loaddb -u dba -s "$CUBRID/demo/demodb_schema" -d "$CUBRID/demo/demodb_objects" <name>`.
- Creation leaves the database stopped. Server lifecycle recipes use `cubrid-build-coordinator.sh runtime 300`.
- Existing `recreate-testdb` invokes `delete-all`, which removes the entire database root. Targeted pwddb recreation needs an independent implementation.
- At inspection, directory `oos-storage` and branch `feat/oos` yield `oos-storag`; suffix `demodb` yields `oos-storag-demodb`.

## Accepted decisions

The user accepted all six recommendations on 2026-09-15:

1. Use an executable script named `my-cubrid-ticket-get` for extraction.
2. Match tickets case-insensitively and emit uppercase; fail for multiple distinct tickets without falling back.
3. Resolve the actual invocation directory, including when invoked through just from a subdirectory.
4. Fail create if existing; allow recreate if absent; make absent delete successful; stop the selected running database before deletion; leave created databases stopped.
5. Retain existing storage/locale defaults and reject invalid names rather than rewriting them.
6. Retain the database after a failed template load, reporting failure and its name.

## Usage

```bash
my-cubrid-pwddb-getname
my-cubrid-pwddb-getname --append-name demodb
my-cubrid-pwddb create
my-cubrid-pwddb create --append-name demodb --load demodb
my-cubrid-pwddb recreate --append-name demodb --load demodb
my-cubrid-pwddb delete --append-name demodb
just db pwddb-create
just db pwddb-create-demodb
```

The commands use the active `cubrid` executable and `CUBRID_DATABASES`; loading additionally requires `CUBRID/demo`. The helper does not need a running CUBRID installation. Ticket extraction exits 1 for absence and 2 for ambiguity; name resolution only falls back on absence.

Final names must fit the documented 17-character ASCII database-name limit. Invalid names are rejected without rewriting. For example, `oos-storag-demodb` fits; an overly long ticket plus suffix may not.

Lifecycle calls from this CLI sharing a registry are serialized with `.pwddb.lock`. Other utilities do not participate in that lock. No recipes invoke the existing broad `delete-all` operation.

## Verification

- `python3 tests/pwddb-test.py`: real Git naming scenarios and stateful fake utility tests for lifecycle ordering, failure handling, and all six just recipes from a child directory.
- ShellCheck passes for all three executables.
- Installed CUBRID 11.5 debug build: isolated temporary registry successfully exercised empty creation, recreation, demodb creation/loading, and deletion of both variants. The loader reported 63 schema statements and 19,202 inserted objects with zero failures. Evidence: `/tmp/pwddb-smoke-ycsj5vfo/step-*.log` (temporary local logs).
- Real smoke testing used unique names in its own registry; running-target handling is covered by the fake utility tests.
