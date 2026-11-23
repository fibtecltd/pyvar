# pyvar-derivatives

62 functions: BS/Heston/SABR/Dupire/LSM, exotic options, bonds, IRS/CDS, FX.

A Claude skill: it teaches Claude which of pyvar's functions fits a question, what to send, and how to read the answer. Every number comes from the live API at https://www.pyvar.com; the skill computes nothing itself.

## Install

Add the pyvar marketplace, then open the `/plugin` Discover tab and install **pyvar-derivatives**:

```
/plugin marketplace add fibtecltd/pyvar
```

## The API key

The skill needs your own pyvar API key to call the API, and never reads one from your
machine. Get a free key at https://www.pyvar.com#get-api-key (sign in with Google or an emailed
link; no password, no card). The dashboard shows the key once; it lasts a year and can be revoked
or replaced there at any time. Keep it to yourself: do not paste it into a chat.

Use it with the Python client:

```
pip install pyvar-client
```

```python
from pyvar_client import Client

client = Client(api_key="<your pyvar key>")
```

or with the REST API: `POST https://www.pyvar.com/api/v1/<domain>/<function>` with the header
`Authorization: Bearer <your pyvar key>` and the request body as JSON. Every example in the
skill is a real request body.

## Links

- Documentation: https://www.pyvar.com/plugins.html
- Source: https://github.com/fibtecltd/pyvar
- Support: https://github.com/fibtecltd/pyvar/issues
- Privacy policy: https://www.pyvar.com/privacy.html
- Terms of service: https://www.pyvar.com/terms.html

Licence: Apache-2.0. pyvar is not independently validated for regulatory use; its output is
not a substitute for your institution's own model validation.
