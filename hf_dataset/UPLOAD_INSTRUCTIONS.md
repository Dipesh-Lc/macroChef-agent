# Publishing this dataset to the Hugging Face Hub

**Publication is a human gate.** This directory (`hf_dataset/`) is fully
prepared and ready to upload, but no agent has published it and none should
— per `CLAUDE.md`'s "Public actions" human gate, the human pulls the
trigger on publishing. These are the exact steps to do that.

## 1. Create the dataset repo on the Hub

Suggested repo name (under your own namespace):

```
<your-hf-username>/macrochef-adversarial-safety-benchmark
```

You can create it either via the web UI
(https://huggingface.co/new-dataset) or via the CLI in step 3 below
(`huggingface-cli upload` will create the repo automatically with
`--repo-type dataset` if it doesn't exist yet, but creating it explicitly
first lets you set it private/public and review settings before anything is
pushed).

## 2. Authenticate

```bash
pip install -U huggingface_hub
huggingface-cli login
```

This will prompt for a User Access Token. Use the token you already have as
`HUGGING_FACE_TOKEN` (see `.env.example`'s `Hugging_Face_Token` placeholder
— fill in the real value only in your own `.env`, never commit it). Create
one at https://huggingface.co/settings/tokens if you don't have one yet —
it needs **write** scope to push a dataset.

Non-interactive alternative (e.g. in a script or CI), using the same token
value:

```bash
huggingface-cli login --token $HUGGING_FACE_TOKEN
```

## 3. Upload

From the repository root (`D:\Desktop\Projects\macrochef-agent`):

```bash
huggingface-cli upload <your-hf-username>/macrochef-adversarial-safety-benchmark \
  hf_dataset/ . \
  --repo-type dataset \
  --commit-message "Publish MacroChef adversarial allergy/diet safety benchmark v1"
```

This uploads the entire `hf_dataset/` directory (README.md dataset card,
LICENSE, UPLOAD_INSTRUCTIONS.md, and `data/*.jsonl`) to the root of the
dataset repo. If you'd rather upload file-by-file for more control:

```bash
huggingface-cli upload <your-hf-username>/macrochef-adversarial-safety-benchmark \
  hf_dataset/README.md README.md --repo-type dataset

huggingface-cli upload <your-hf-username>/macrochef-adversarial-safety-benchmark \
  hf_dataset/LICENSE LICENSE --repo-type dataset

huggingface-cli upload <your-hf-username>/macrochef-adversarial-safety-benchmark \
  hf_dataset/data data --repo-type dataset
```

## 4. Verify

After upload, check:
- The dataset card renders correctly on the repo page (YAML front-matter
  parses, tags/license show up in the sidebar).
- The Hub's dataset viewer loads `data/benchmark_cases.jsonl` (and the
  per-category configs) without errors — this confirms the no-script JSONL
  auto-loading actually works, not just that the card claims it does.
- `datasets.load_dataset("<your-hf-username>/macrochef-adversarial-safety-benchmark")`
  works from a clean Python environment.

## 5. Reminder

Do not publish any "0 violations" claim about MacroChef anywhere alongside
this dataset (README, model card, social posts) without stating both
numbers together, per `CLAUDE.md`'s "Honest scope" rule: **"judge-flagged
17/259 inherent; adjudicated true 0/259"** (plus the non-blocking
precautionary and safe-control numbers). This dataset's own card already
follows that rule — keep any future announcement consistent with it.
