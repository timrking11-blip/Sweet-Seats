# Private Next lint glob adapter

This is an intentionally private compatibility package installed under the dependency
name `fast-glob`, not an upstream fast-glob release or a general-purpose replacement.
It supports only the call used by `@next/eslint-plugin-next@15.5.28`:
`globSync(pattern, { onlyDirectories: true })`. Unexpected calls fail explicitly.

The upstream chain contains unpatched `braces` GHSA-vfj7-8cjw-p6xm. This package removes
that chain rather than ignoring the advisory. `tinyglobby@0.2.17` supplies directory
glob matching; this adapter preserves fast-glob's absolute/relative path and trailing
separator behavior for the supported call. Tests invoke the actual pinned Next utility.
All Next recommended/core-web-vitals rules remain enabled. CommonJS require is allowed
only for the Node tooling/tests in ESLint; application lint rules are unchanged.

Remove this adapter and the scoped override when the Next lint dependency chain is
patched. Any Next plugin upgrade must recheck its glob usage and run the compatibility
tests, full lint/build and zero-finding audit. Do not publish this private package.
