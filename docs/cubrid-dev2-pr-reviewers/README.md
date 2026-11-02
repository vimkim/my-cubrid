# Recommend dev2 pull request reviewers

Run `cubrid-dev2-pr-reviewers https://github.com/CUBRID/cubrid/pull/8348` with an authenticated GitHub CLI. The command reads GitHub and never requests reviews. In a terminal, the command opens an interactive view. Use the arrow keys or `j` and `k` to select a person, Page Up and Page Down to scroll details, and `q` or Escape to exit. Add `--plain` for text output or `--json` for structured output. Piped output defaults to text.

The ranking shows all six dev2 candidates other than 김대현 (`vimkim`) and 민준 (`hornetmj`), including people with no matching modules and people already requested. It sorts by the number of known modules covered, then by the number of primary roles. Equal counts share a rank. The author remains visible without a rank and cannot be requested. Counts describe module ownership, not probabilities. Each row shows the modules and roles behind its position.

The command considers changes under `src/`. The ownership file records people, recommendation exclusions, primary and secondary pairs, and source rules. Exclusions must reference configured people. Existing individual requests still cover their known modules, even when those people are excluded from new recommendations. Requested teams and unknown individual requests are listed but do not establish module coverage. The minimum-size additional sets use only eligible candidates, then prefer sets covering more modules through primary owners. Use `--alternatives N` to change how many equally small sets appear.

Dedicated paths map directly to modules. Shared C files require a changed line inside a recognized function definition from source at the pull request head or merge base. Symbol rules apply in file order, with specific rules before general ones. Shared headers and edits outside recognized functions remain unresolved. Rename analysis considers both paths. Missing or incomplete patches, unknown paths, missing source, and pull request changes during retrieval also appear as unresolved. A provisional report covers known modules only and does not establish complete coverage.

The command exits with status 0 for a complete report, including no source changes. It exits with status 2 for a provisional report or uncoverable modules, and status 1 for operational or configuration errors. JSON errors contain `verdict` and `error` fields.

`cubrid-dev2-add-reviewers.py` is deprecated. It requests the entire configured team and still changes GitHub unless `--dry-run` is supplied.
