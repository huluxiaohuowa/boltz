# Boltz Agent Instructions

These instructions apply to work inside the `apps/boltz` submodule.

## Repository Role

This repository is the ictrek fork used to build a VOS WebApp around the
upstream Boltz project.

- `origin` is the ictrek working fork: `git@github.com:huluxiaohuowa/boltz.git`.
- `upstream` is the original Boltz source: `git@github.com:jwohlwend/boltz.git`.
- Treat `upstream` as read-only reference material. Do not push to it.

## Upstream Merge Standard

When bringing code from `upstream`:

1. Fetch explicitly with `git fetch upstream --no-tags` unless tags are needed
   for a specific release task.
2. Review upstream changes before merging. Do not blindly overwrite ictrek
   WebApp files or VOS packaging files.
3. Prefer merging from `upstream/main` unless the user names another upstream
   branch or commit.
4. Keep upstream Boltz library, docs, examples, and tests as close to upstream
   as practical.
5. Preserve ictrek-specific WebApp and VOS files:
   - `README.md`
   - `AGENTS.md`
   - `ictrek.app/`
6. The upstream README content must live in `README.origin.md`, not
   `README.md`. If upstream changes `README.md`, merge those updates into
   `README.origin.md`.
7. The top-level `README.md` is reserved for ictrek WebApp development notes,
   local workflow, remotes, and VOS packaging entry points.
8. If a conflict mixes upstream model code with ictrek WebApp behavior, keep the
   upstream model behavior intact and isolate ictrek integration in separate
   app-specific files where possible.
9. After a merge, check that:
   - `git remote -v` still shows `upstream` push disabled or otherwise not
     usable for accidental pushes;
   - `README.md` remains the ictrek WebApp README;
   - `README.origin.md` contains the latest upstream README content;
   - `ictrek.app/` still has the VOS package scaffold.

## Packaging Scope

Do not run VOS packaging, Docker builds, or test suites unless the user
explicitly specifies the target environment. Static inspection and shell syntax
checks are acceptable.

