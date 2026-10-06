<!--
SPDX-FileCopyrightText: 'Copyright Contributors to the 'IEC 61850 WebSocket Proof-of-Concept' project' 

SPDX-License-Identifier: Apache-2.0
-->

# How to contribute

We'd love to accept your patches and contributions to this project. There are just a few guidelines you need to follow.

## Ways of contributing

Contribution does not necessarily mean committing code to the repository.
We recognize different levels of contributions as shown below in increasing order of dedication.

1. Use and test the project. Give feedback on the user experience or suggest new features.
2. Report bugs or security vulnerabilities.
3. Fix bugs.
4. Improve the project by developing new features.

## Filing bugs, security vulnerabilities, or feature requests

You can file bugs against and feature requests for the project via GitHub Issues.
Read [GitHub Help](https://docs.github.com/en/free-pro-team@latest/github/managing-your-work-on-github/creating-an-issue)
for more information on using GitHub Issues.

If you think you've found a potential vulnerability in this project, please
email <rti@netbeheernederland.nl> to responsibly disclose it.

## Community guidelines

This project follows the following [Code of Conduct](CODE_OF_CONDUCT.md).

## REUSE compliance and source code headers

All the files in the repository need to be [REUSE compliant](https://reuse.software/).
CI does not check this yet, and the repository is not fully compliant today (`reuse lint` reports files without a
header). Add the header to every file you create or change, and check with:

```bash
uvx reuse lint
```

This means that every file containing source code must include copyright and license information. This includes any
JS/CSS files that you might be serving out to browsers. (This is to help well-intentioned people avoid accidental
copying that doesn't comply with the license.)

Apache 2.0 header, as used in the source files (in the comment syntax of the file):

```text
SPDX-FileCopyrightText: 2025 Netbeheer Nederland
SPDX-License-Identifier: Apache-2.0
```

For files that can't carry a comment (images, JSON), add a `<file>.license` next to it with the same two lines, as
`.github/pull_request_template.md.license` does.

## Git branching

`main` is the default branch and holds the latest reviewed state. Work happens on topic branches with a short,
descriptive name (for example `code-clean-up` or `rti-demo-docker-optimization`) and reaches `main` through a pull
request. A larger effort can use a longer-lived integration branch (such as `initial-refactor`): topic branches merge
into it, and it merges into `main` by pull request when the effort is done.

## Signing the Developer Certificate of Origin (DCO)

This project uses a Developer Certificate of Origin (DCO) to ensure that each commit was written by the author or that
the author has the appropriate rights necessary to contribute the change.
Specifically, we use [Developer Certificate of Origin, Version 1.1](http://developercertificate.org/), which is the same
mechanism that the Linux® Kernel and many other communities use to manage code contributions.
The DCO is considered one of the simplest tools for sign-offs from contributors as the representations are meant to be
straightforward to read and indicating signoff is done as a part of the commit message.

This means that each commit must include a DCO which looks like this:

`Signed-off-by: Joe Smith <joe.smith@email.com>`

The project requires that the name used is your real name and the e-mail used is your real e-mail.
Neither anonymous contributors nor those utilizing pseudonyms will be accepted.

There are other great tools out there to manage DCO signoffs for developers to make it much easier to do signoffs:

* Git makes it easy to add this line to your commit messages. Make sure the `user.name` and `user.email` are set in your
  git configs. Use `-s` or `--signoff` to add the Signed-off-by line to the end of the commit message.
* [GitHub UI automatic signoff capabilities](https://github.blog/changelog/2022-06-08-admins-can-require-sign-off-on-web-based-commits/)
  for adding the signoff automatically to commits made with the GitHub browser UI. This one can only be activated by the
  GitHub org or repo admin.
* [GitHub UI automatic signoff capabilities via custom plugin]( https://github.com/scottrigby/dco-gh-ui ) for adding the
  signoff automatically to commits made with the GitHub browser UI.
* Additionally, it is possible to use shell scripting to automatically apply the sign-off. For an example for bash to be
  put into a .bashrc file,
  see [here](https://wiki.lfenergy.org/display/HOME/Contribution+and+Compliance+Guidelines+for+LF+Energy+Foundation+hosted+projects).
* Alternatively, you can add `prepare-commit-msg hook` in .git/hooks
  directory. [See an example](https://github.com/Samsung/ONE-vscode/wiki/ONE-vscode-Developer's-Certificate-of-Origin).

## Code reviews

All patches and contributions, including patches and contributions by project members, require review by one of the
maintainers of the project.
We use GitHub pull requests for this purpose.
See [GitHub Help](https://help.github.com/articles/about-pull-requests/) for more information on using pull requests.

## Pull request process

Contributions should be submitted as GitHub pull requests.
See [Creating a pull request](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request)
if you're unfamiliar with this concept.

Follow this process for a code change and pull request:

1. Create a topic branch in your local repository with a short, descriptive name (see [Git branching](#git-branching)).
1. Make changes, compile, and test thoroughly. Ensure any install or build dependencies are removed before the end of
   the layer when doing a build. Code style should match existing style and conventions, and changes should be focused
   on the topic the pull request will be addressed. Python style is enforced by `ruff` (configured in
   `pyproject.toml`); the HMI follows [docs/rti-demo/design/style-guide.md](docs/rti-demo/design/style-guide.md).
1. Run the checks CI runs (see [Before you push](#before-you-push)), and update the documentation your change affects:
   the module's README, and anything under `docs/` that describes it.
1. Push commits to your branch.
1. Create a GitHub pull request from your topic branch.
1. Pull requests will be reviewed by one of the maintainers who may discuss, offer constructive feedback, request
   changes, or approve the work. See [Code reviews](#code-reviews).
1. Upon receiving the sign-off from one of the maintainers you may merge your changes. If you do not have permission to
   do that, you may request a maintainer to merge it for you.

## Before you push

CI (`.github/workflows/ci.yml`) runs these on every pull request; run them locally first, from the repository root:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .      # `uv run ruff format .` fixes the formatting
uv run pytest tests/unit -q
```

If you changed an rti-demo module, also run its tests, for example
`uv run --package bff pytest examples/rti-demo/modules/bff/tests -q`, and for the HMI `npm test` in
`examples/rti-demo/modules/hmi` (see `examples/rti-demo/TESTING.md`).

## Attribution

This CONTRIBUTING.md is adapted from Google, available
at https://github.com/google/new-project/blob/master/docs/contributing.md.
