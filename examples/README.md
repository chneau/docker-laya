# Laya API usage examples

Start with examples **06–07** in [requests.http](requests.http) to pick a category
from a list or from a map with descriptions. The client
[classify_categories.py](classify_categories.py) uses a `dict[str, str]` that maps
each category name to its description. The examples call this project's HTTP API;
the client does not load models locally.

## Run the Python example

The example assumes Docker is already running and the API is available. The URL and
timeout are explicit in the `self._client.post` call in the Python file.
Authentication is HTTP Basic with the credentials read from `BASIC_AUTH` in the
project root `.env`. The path is resolved from the script regardless of the working
directory, so no terminal variables are needed.

1. Keep `BASIC_AUTH=user:password` in `.env` with the credentials accepted by the
   container. In `LayaCategoryClient.classify`, adjust the URL
   `http://localhost:8000/predict` if needed. The example does not use an API key.
2. Run from the repository root:

   ```bash
   uv run --script examples/classify_categories.py
   ```

   The file declares its dependencies (`httpx`, `pydantic`, `python-dotenv` and
   `pyyaml`) so `uv` prepares an isolated environment. The client requires Python
   3.14+, like the project.

3. Edit `self.categories` in `LayaCategoryClient.__init__` to use your own categories
   and [documents.yml](documents.yml) to use your own texts. The placeholders
   `{company_name}`, `{tax_id}` and `{address}` are filled with the values from
   `ClassificationExample.PLACEHOLDERS`.

If `BASIC_AUTH` contains several comma-separated pairs, the client uses the first
valid pair. Colons inside the password are preserved. Reading the file does not
expand variable references inside `.env` values. If there is no valid pair, the
script reports the problem before sending any request. Credentials are sent through
`auth=httpx.BasicAuth(...)`, without an API key and without printing them. If you
change the server credentials in `.env`, recreate the service with `make up` so the
container receives the new configuration.

The script makes one `POST /predict` call per text. The whole dictionary, including
descriptions, goes in `questions.category.criteria`; the question uses
`type: "choice"` to select a category. The result is in `answers.category.choice`.

`classifier.classify(text)` uses the client's default categories. For a specific
call, pass another dictionary as `classifier.classify(text, categories)`. An empty
dictionary also falls back to the default categories.

The output shows the chosen category, the confidence and the probabilities returned
by the API. The values depend on real inference; the script has no predefined
results. The pinned model is `english`; change it in `LayaCategoryClient._payload`
to `multilingual` if your documents are in another language. The server must be
able to load that checkpoint; the first call may take longer.

The client uses a 120-second timeout. HTTP error responses such as `401`, `422` and
`503` raise through `raise_for_status()`. The code does not turn failures into made-up
categories.

## Run the requests

Open [requests.http](requests.http) with the VS Code REST Client extension. Adjust
`baseUrl` if needed and run each block separately. Protected routes use HTTP Basic
with `BASIC_AUTH` read from the root `.env`; the password is not stored in the
requests file.

| Examples | What they demonstrate                                         |
| -------- | ------------------------------------------------------------- |
| 01–05    | Health, models, presets, language and email preparation       |
| 06–07    | A category chosen from a list or from a map with descriptions |
| 08–10    | `choice`, `score`, `noul`, conversations and JSON objects     |
| 11–13    | Presets and batches with shared or per-item settings          |
| 14       | SystemOne / TypeSafe compatibility                            |

`POST /email/state` only prepares the content. To classify it, copy the returned
object into the `state` field of a request to `/predict`.

## curl example

With Docker already running, set the URL and key directly in the command:

```bash
curl --fail-with-body --request POST 'http://localhost:8000/predict' \
  --header 'X-API-Key: replace-with-your-key' \
  --header 'Content-Type: application/json' \
  --data '{
    "state": "I need help with a duplicate charge.",
    "model": "multilingual",
    "questions": {
      "category": {
        "type": "choice",
        "instructions": "Which category best describes this message?",
        "criteria": ["billing", "technical_support", "sales", "other"]
      }
    }
  }'
```

For Bearer authentication, replace the key header with
`--header 'Authorization: Bearer replace-with-your-key'`.
For HTTP Basic, replace it with `--user 'user:password'`, using an account
configured in `BASIC_AUTH` on the server. The Python script already uses HTTP Basic
and reads that pair directly from `.env`.

## Interpret and adapt

- `choice`: selects a category; `other` can represent cases outside the specific
  options. Having that option does not guarantee the model recognizes every unknown case.
- `score`: returns an expected value on a scale starting at zero. With four levels,
  the scale runs from 0 to 3 and the result may be fractional.
- `noul`: returns a numeric value for the binary decision, not a ready-made boolean.
- In `/predict`, use `questions` **or** `preset`. In the batch, use `states` **or**
  `items`. For per-item questions, follow example 13: a shared preset takes precedence
  over item questions in the API's current behavior.
- The batch preserves the input order. Check `results[i].ok` before reading
  `results[i].result`; individual errors appear in `results[i].error`.
