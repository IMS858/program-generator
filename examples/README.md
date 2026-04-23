# Examples

## `example_sarah.py`

Reference client file showing how to build a program from code. Demonstrates ·
- A 2x/week runner profile
- No spine constraints (axial loading allowed)
- Endurance-forward nutrition strategy
- Different FRA priorities and strength markers than Matt

Run ·
```bash
python examples/example_sarah.py
```

Produces `sarah_program.json` + `sarah_plan.pdf` (14 pages).

## Your own clients

After filling in `web/index.html`, use the "Download .py" button to save a client file here. The filename will be `client_YOUR_CLIENT_NAME.py`. Then ·

```bash
python examples/client_your_client_name.py
```

Each run produces a `_program.json` (raw data) and `_plan.pdf` (the 15-page client deliverable).

**Note:** `.gitignore` excludes `*_program.json` and `*_plan.pdf` by default to keep the repo small and protect client privacy. Only commit example/test data that's okay to be public.
