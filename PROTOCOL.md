# Analysis plan

Fixed on 2026-10-04 after a pilot of 20 tasks (the first task of every category × context cell, both languages) with
the eight models, used only to check providers, output form and dependency extraction; the pilot replies are not part
of the results.

## Question
When a language model writes Ruby code, how often does it declare a dependency that does not exist on rubygems.org,
and does this change when the same request is written in Ukrainian instead of English, or when the task concerns
Ukrainian services rather than global ones?

## Tasks
200 original coding tasks written for this study: five categories (payments, commerce and delivery, government and
identity, messaging, language processing) × two contexts (global services; Ukrainian services, standards and
language) × 20 tasks. Each task has an English and a Ukrainian wording with the same content. The request asks for a
Gemfile with every needed gem followed by the implementation.

## Models
Eight models through OpenRouter with one pinned provider each, temperature 0.7, at most 1200 completion tokens,
seed = sample number: GPT-4o mini, Gemini 2.5 Flash-Lite, DeepSeek V3.1, Llama 3.3 70B, Qwen3 Coder 30B-A3B,
Mistral Small 3.2 24B, Gemma 3 12B, Llama 3.1 8B. Main run: one sample (0) for all tasks and both languages.
Repeats: samples 1 and 2 for 60 tasks (6 per category × context cell, seed 2026), both languages.

Change on 2026-10-04, before any analysis of Qwen3 Coder: its pinned provider (Novita) returned empty message
content for 194 of the 400 main-run replies while billing the generated tokens; all Qwen3 Coder replies were
discarded and the model was run again through SiliconFlow (FP8).

## Dependency extraction and registry check
Declared dependencies: `gem '<name>'` lines, `gem install` and `bundle add` commands; gems with a git/github/path
source are counted separately and not checked. A declared name is looked up once at
`https://rubygems.org/api/v1/gems/<name>.json` (200 = exists, 404 = absent, anything else after retries = unknown;
the date of every lookup is stored). An absent name is classified as:
- malformed: not a valid gem name (e.g. contains "/" or spaces), so it cannot be registered;
- near miss: a case or hyphen/underscore variant of an existing gem;
  clarified on 2026-10-04 after reading the interim list of absent names and before the final analysis: a name is
  a near miss when some published gem has the same name up to letter case, hyphens and underscores (including their
  omission or a mixture), so `active_support` (a require path) is a near miss of `activesupport`; the full list of
  published names (rubygems.org/names) is used for this test. The first definition (case or a swap of all hyphens
  for underscores) is kept as a sensitivity analysis;
- invented: any other absent name; these are the names an attacker could register.
`require` calls are recorded and reported descriptively only.

## Outcomes and analyses
Primary outcome: a reply declares at least one invented gem.
1. Rate of the primary outcome per model × language × context, with 95% intervals from a bootstrap over tasks
   (10000 resamples).
2. Primary contrast: Ukrainian minus English wording, per model and averaged over models, paired by task (sample 0),
   task-level bootstrap interval and exact McNemar test per model, Holm correction over the eight models.
3. Context contrast: Ukrainian-service minus global tasks, per model and averaged, bootstrap over tasks.
4. Name-level: share of declared names that are invented, near misses or malformed; replies with no declared gem;
   truncated replies.
5. Recurrence: for invented names in the repeat subset, the share that appears again in another sample of the same
   model, task and language; names proposed by two or more models.

## Additions after the main analysis (2026-10-12)

- Exploratory secondary outcome: a reply declares any absent name (invented, near miss or malformed), with the same
  contrasts as the primary outcome (`secondary_any_absent` in `results/summary.json`).
- Descriptive counts quoted in the paper (`descriptive`): tasks set in a Rails application, invented-gem rates by finish
  status, truncated replies by model and language, Rails component paths among near misses, and dependencies declared
  for Ukrainian payment and delivery tasks.
- Clarification of the first paragraph: the "pilot of 20 tasks" was 10 distinct tasks (the first task of every
  category × context cell), each in both languages, that is 20 requests per model.

## Run B: revised protocol, fixed on 2026-10-13 before generation

The experiment above (run A, git tag `run-a`, data in `archive/run-a/`) was run and analysed. 1672 of its 3200 main-run
replies (52%) stopped at the 1200-token cap: from 1.5% to 100% per model and language, over 90% for three models in
both languages, so for those models it measured the start of a reply rather than a complete answer. The whole
experiment is run again as run B, and run B supplies the reported results whatever they show. Run A informed this
revision and is kept unchanged for reference; it is not pooled with run B.

Changes:
- At most 8192 completion tokens (every pinned endpoint allows at least 11059). Before the main run, the pilot (the same
  10 tasks in both languages, 160 requests) is repeated and only finish reasons are inspected; if any pilot reply stops
  at the cap, the cap becomes 16384, or the endpoint maximum where that is lower. Replies still stopped at the cap are
  kept and reported; no request is repeated to obtain a complete reply.
- Every reply also records the requested cap, the response id, the model name returned by OpenRouter and the creation
  time.
- Registry lookups and the list of published names are made afresh after generation (`results/registry.json`,
  `results/rubygems_names.txt.gz`), so all labels refer to one snapshot.

Unchanged: tasks and wordings, prompt, models and pinned providers with their quantisation, temperature 0.7, seed =
sample number, the main run and the repeat subset, the extraction rules, the final near-miss rule (the first rule
kept as a sensitivity analysis), outcomes and the analyses 1–5 above, and the secondary outcome and descriptive counts
added on 2026-10-12.

Extraction rules made explicit (the same code as run A): a name counts as declared when it appears in a `gem` line, a
`gem install` or a `bundle add` command anywhere in the reply, including a declaration the reply later replaces or
calls unavailable; `gem` lines inside Ruby comments are not counted; a line whose quotes do not match is not counted.

Added analyses (sensitivity, reported with the main results):
- declared names per reply by model and language, and the paired Ukrainian minus English contrast at the name level
  (invented names among declared names, bootstrap over tasks);
- the primary contrast restricted to task × model pairs that declare the same number of names in both languages;
- the primary contrast using all three samples of the repeat subset, averaged within task, model and language;
- the primary contrast per model and pooled with the first near-miss rule;
- the share of replies stopped at the cap by model and language.

Changes after the run B pilot (2026-10-13, before the main run; only finish reasons and output form were inspected,
`results/pilot.jsonl`):
- One pilot reply (Gemini 2.5 Flash-Lite, Ukrainian) stopped at 8192 tokens, so by the rule above the cap is 16384 for
  every model.
- Llama 3.3 70B on its pinned provider (Novita, bf16) broke off 9 of its 20 pilot replies into an endless run of "!"
  until the cap; the same fault is present in 21 of its run A replies. As with Qwen3 Coder in run A, the model is moved
  to another provider, CoreWeave (fp16), where 20 trial requests (the pilot tasks, not stored) showed no such output.
