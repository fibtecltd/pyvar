# pyvar-alm

33 functions: Duration gap, NII/EVE, IRRBB 6 shocks, repricing, NMD, FTP.

A Claude skill: it teaches Claude which of pyvar's functions fits a question, what to send, and how to read the answer. Every number comes from the live API at https://www.pyvar.com; the skill computes nothing itself.

## Install

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-alm@pyvar-marketplace
```

## The API key

The skill needs your own pyvar API key to call the API, and never reads one from your
machine. Get a free key at https://www.pyvar.com#get-api-key (sign in with Google or an emailed
link; no password, no card), then install the `pyvar-mcp` plugin: Claude Code asks for the key
when it is enabled and keeps it in the system's secure credential store.

```
/plugin install pyvar-mcp@pyvar-marketplace
```

## Links

- Documentation: https://www.pyvar.com/plugins.html
- Source: https://github.com/fibtecltd/pyvar
- Support: https://github.com/fibtecltd/pyvar/issues
- Privacy policy: https://www.pyvar.com/privacy.html
- Terms of service: https://www.pyvar.com/terms.html

Licence: Apache-2.0. pyvar is not independently validated for regulatory use; its output is
not a substitute for your institution's own model validation.
