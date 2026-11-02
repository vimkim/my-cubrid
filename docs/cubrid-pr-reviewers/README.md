# Recommend CUBRID pull request reviewers

Run `cubrid-pr-reviewers https://github.com/CUBRID/cubrid/pull/8348` with an authenticated GitHub CLI. Use `--json` for a structured report. The command reads GitHub and never requests reviews.

The report considers changes under `src/`. It excludes the author and counts existing individual requests whose logins appear in `cubrid-review-owners.toml`. Both primary and secondary owners cover a module. The command finds minimum-size sets of additional reviewers, then ranks sets by the number of modules covered by primary owners. Individual ranks count covered modules, then primary roles. These scores are not probabilities. Use `--alternatives N` to change how many equally small sets appear. The search considers every configured person before applying that display limit.

The ownership file records people, primary and secondary pairs, and source rules. The SM and DM rosters describe membership only. Dedicated paths map directly to modules. Shared C files require a changed line inside a recognized function definition from source at the pull request head or merge base. Symbol rules apply in file order, with specific rules before general ones. Shared headers and edits outside recognized functions remain unresolved. Rename analysis considers both paths. Missing or incomplete patches, unknown paths, missing source, and pull request changes during retrieval also appear as unresolved. A provisional recommendation covers known modules only and does not establish complete coverage.

The command exits with status 0 for a complete report, including no source changes. It exits with status 2 for a provisional report or uncoverable modules, and status 1 for operational or configuration errors. JSON errors contain `verdict` and `error` fields. Requested teams and unknown individual requests are listed but do not establish module coverage.

`cubrid-dev2-add-reviewers.py` is deprecated. It requests the entire configured team and still changes GitHub unless `--dry-run` is supplied.
