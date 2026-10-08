# Current-branch PR context

Install the generic `my-git-utils` PR commands before using implicit PR lookup
in `cubrid-pr-status`, `cubrid-pr-tc-info`, `cubrid-pr-tc-base-check`, or
`cubrid-format-pr-diff.sh`.
After the reviewed generic changes are merged, run `just sync` from the
`my-git-utils` main checkout. Personal URL wrappers are managed separately by
chezmoi and need their own targeted deployment.

`cubrid-pr-review-worktree` records the canonical PR URL under the created
branch's repository-local `pr-url` configuration. This does not change the
behavior of bare `gh pr view`. For an existing review branch:

```sh
gh-pr-associate https://github.com/CUBRID/cubrid/pull/8095
gh-pr-info --repo CUBRID/cubrid --json url --jq .url
gh-pr-associate --clear
```

URL-only lookup of a recorded association is offline. Live status/base/head
metadata still comes from GitHub. Branch renaming preserves the association;
switching branches selects the new branch's context. Unassociated branches
use read-only discovery from tracking/publishing identities. Ambiguous matches
require an explicit selector. Detached HEAD also requires an explicit selector.

The CUBRID consumers constrain discovery to `CUBRID/cubrid`, even when the
PR head belongs to a fork. The rebase helper's existing local-branch checks
remain independent of metadata lookup.
