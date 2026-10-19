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

Corrections after the run B analysis (2026-10-13):
- `gem install` arguments: a closing parenthesis or quote of a surrounding call (`system('gem install pcsc smartcard')`)
  was kept in the name, and placeholders (`gem install ...`) and paths (`gem install -r ./`) were counted as malformed
  names. They are now stripped or skipped. All removed entries were malformed (17 to 11 in the main run); the name
  counts, the exposure analyses and the secondary outcome were recomputed, and the primary outcome is unchanged.
- The extraction rules above overstate the implementation in two respects: a `gem` line with mismatched quotes is
  counted, and `=begin`/`=end` block comments are not recognised. No run B declaration is affected by either.

## Revision after the review (2026-10-19): post hoc analyses

These analyses were specified after reviewers pointed out wording asymmetries and other issues; they are post hoc and
exploratory, assess sensitivity to how the tasks were worded and to analysis choices, and do not replace the results
above (`rubydeps revision` → `results/revision.json`).

Task coding (`data/task_coding.csv`; both annotations in `data/task_coding_annotations.csv`). Two LLM annotators
(A: Claude, B: GPT via Codex) coded the 200 pairs from the task texts only, without replies or results, by three rules:
- name_script_switch: the English wording contains, in Latin script, the proper name of a specific service, company,
  product, app, platform, standard, algorithm, register, organisation or institution (including its acronym), and the
  Ukrainian wording does not contain that name in Latin script (it gives it in Cyrillic or not at all); not counted:
  countries, languages, cities, nationalities, generic terms, formats and identifier types, and names the Ukrainian
  wording keeps in Latin script;
- en_has_cyrillic: the English wording contains Cyrillic;
- content_differs: the wordings ask for something materially different beyond language and script.
Disagreements on name_script_switch (2 of 200) were resolved by the rule text; content_differs is the union of the two
annotations. Agreement and kappa per flag are reported.

Analyses:
- UK − EN by context × name_script_switch, with a bootstrap over the tasks of each stratum; the language contrast,
  context gap and interaction without the name-switch tasks and without any flagged task, for run B, run A and the
  any-absent outcome, with a bootstrap over tasks within category × context;
- invented names in replies to name-switch tasks by language, coded by one LLM annotator (Claude) as derived from the
  switched name (any spelling, transliteration or translation), other or ambiguous
  (`data/switch_task_invented_names.csv`);
- the share of main-run replies that declare a general HTTP client (httparty, faraday, rest-client, http, excon,
  typhoeus, httpclient, net-http-persistent) by category and context;
- the recurrence share of invented names from the first reply with an interval from resampling whole repeated tasks;
- RubyGems typo protection (`app/models/gem_typo.rb`, commit fc87b0c) applied to near misses: a name with a published
  case-insensitive exact match is refused by name uniqueness; otherwise it is blocked when a published gem with the
  same name after upper-casing and removing `_` and `-` has at least 10000 downloads or a most recent version created
  within five years; the exception list is unknown and a pusher owning none of the colliding gems is assumed;
  downloads and release dates were looked up on 2026-10-19 (`results/gem_details.json`);
- invented-gem rate per category × context and the context difference per category with pointwise intervals;
- run A and run B under the final and the original near-miss rule and the any-absent outcome, with the same
  bootstrap; names reclassified between the rules; the name-level share without `bundler`;
- agreement between runs: run B replies identical to or extending the run A reply for the same task, language and seed;
- existing declared names flagged for inspection (first release on or after 2025-01-01 with fewer than 1000 downloads,
  or a placeholder word in the description).

## Run C: script experiment and two current models, fixed on 2026-10-19 before generation

Run C was planned after the review and the post hoc analyses above; it is a new, separately reported experiment and
does not change run B or its analyses. Code: `src/rubydeps/runc.py`; replies: `results/run-c/replies.jsonl`.

### Part 1: script experiment (confirmatory)
Question: for the same Ukrainian request, does writing the name of the service, standard or algorithm in Cyrillic
instead of Latin script change how often a model declares an invented gem?

- Tasks: the 36 name-switch tasks of `data/task_coding.csv` (32 Ukrainian-service, 4 global).
- Arms: *cyrillic* = the Ukrainian wording of the task set; *latin* = the same wording with each switched name replaced
  by its Latin form from the English wording, with only the grammatical changes this requires
  (`data/script_tasks.jsonl`; in gov-u02 the instrumental case is rephrased as "за допомогою Diia.Signature"; in lng-u01
  the institution is written "Cabinet of Ministers", the English wording has "Cabinet"; in msg-u14 the omitted name
  Unisender is added, so this task tests the presence of a name rather than its script and is excluded from the primary
  analysis). The prompt template is the Ukrainian one of run B.
- Models: the eight models of run B with the same pinned providers and settings (temperature 0.7, at most 16384
  completion tokens, seed = sample number), samples 10 and 11 in both arms (1152 requests); and the two models of part
  2 with sample 10 in both arms (144 requests).
- Outcome: a reply declares at least one invented gem (final near-miss rule; extraction rules of run B). Registry
  lookups and the list of published names are made afresh after generation.
- Primary analysis: for each of the 35 tasks (all name-switch tasks except msg-u14), d = the difference cyrillic − latin
  averaged over the two samples of each of the eight run-B models and then over the models (equal weights); the
  estimate is the mean of d over tasks, with a 95% percentile interval from 10000 bootstrap resamples of tasks (seed
  2026), and the test is a two-sided sign-flip permutation test with statistic |mean(d)| and Monte Carlo p-value
  (1 + number of permutations with |mean| ≥ observed) / 10001 (10000 random sign vectors, seed 2026), α = 0.05; the
  test assumes that under the null the per-task differences are symmetric about zero. Inference concerns these tasks
  and these eight models. With 35 task clusters the power is adequate for a difference near the 8 pp seen post hoc in
  run B (a UK − EN contrast, not cyrillic − latin) but a smaller script effect may be missed.
- Replies: an empty reply counts as declaring no invented gem; replies stopped at the cap are kept; a request that fails
  after the client's retries is sent again until a reply is stored, and the number of such failures is reported.
- Schedule: all requests of a part are sent in one reproducible random order (seed 2026), so arms and models are
  interleaved in time.
- Secondary (descriptive): the same contrast over all 36 tasks, per model, for the Ukrainian-service tasks only, for
  the two added models, and for the any-absent outcome; identical replies between arms or samples; the number of invented names derived from the switched name (any spelling,
  transliteration or translation) by arm, coded from the list of names without the arm labels; the latin arm compared
  with the English replies of run B (different runs, descriptive only).

### Part 2: two current models
- Claude Sonnet 5.5 (anthropic/claude-sonnet-5.5, provider Anthropic; the endpoint accepts neither temperature nor
  seed, so the provider defaults are used and no seed is sent) and DeepSeek V4 Pro (deepseek/deepseek-v4-pro, provider
  GMICloud, fp8; temperature 0.7, seed = sample number). Reasoning settings are the provider defaults; reasoning tokens
  are recorded.
- Main run: all 200 tasks in both languages, sample 0 (800 requests); no repeat subset.
- Analyses: the run B analyses 1 and 2 (rates by language and context, Ukrainian − English per model with the exact
  McNemar test, Holm correction over the two models) and the name classes, for each added model; reported separately
  from run B and not pooled with it. Analysis code: `src/rubydeps/runc_analysis.py` (`rubydeps runc-check`,
  `rubydeps runc-analyze`), written before generation.

### Pilot and budget
Before the main requests, a pilot of the first 3 script tasks in both arms for all ten models and 2 main-run tasks in
both languages for the two added models, all with seed 99 (`results/run-c/pilot.jsonl`, not analysed), checks the
endpoints and the cost per reply. The projection is the mean recorded cost per pilot reply of each model times its
planned requests, plus the pilot cost. The total budget is 20 USD: if the projection exceeds 17 USD, part 2 is reduced
to the 100 Ukrainian-service tasks before any part 2 main request is sent; if it still exceeds 17 USD, part 2 is limited
to DeepSeek V4 Pro. Nothing else is changed after the pilot. The runner stops sending requests when the recorded cost
of all run C files reaches 17 USD; the replies stored by then are analysed and the stop is reported.

Pilot outcome (2026-10-19, before any main request): 68 pilot replies cost 0.71 USD, none empty or stopped at the cap.
Mean cost per reply was 0.0586 USD for Claude Sonnet 5.5 (about 5800 completion tokens, of them about 1800 reasoning
tokens at the provider default) and 0.0096 USD for DeepSeek V4 Pro. The projection was 33.61 USD for the full design and
19.97 USD with part 2 reduced to the Ukrainian-service tasks, so by the rule above part 2 is limited to DeepSeek V4 Pro
on the 100 Ukrainian-service tasks (projection 4.04 USD), and Claude Sonnet 5.5 is dropped from run C, including its
script requests in part 1.

Run C notes (after generation, 2026-10-19): all planned requests returned a reply; 9 replies ended with a broken
stream (finish reason "error": 8 DeepSeek V4 Pro, 1 Gemini 2.5 Flash-Lite) and 5 DeepSeek V4 Pro main-run replies were
empty because reasoning used the whole token limit; as prescribed they are kept. The invented names of the script
replies were classified without arm labels by an LLM annotator (GPT via Codex), `data/script_run_c_invented_names.csv`.
The cost recorded for run C, pilot included, was 3.53 USD.

Correction (2026-10-19, after the analysis): the pilot had 68 replies, not 76 as first written above. The budget rule
reduced part 2 only; dropping Claude Sonnet 5.5 also from the script requests of part 1 was the authors' reading of
"the two models of part 2" and was stricter than the rule required: keeping its 72 script requests was projected at
8.26 USD in total. This reading was recorded in commit 39c1cd7 before any main request was sent.
