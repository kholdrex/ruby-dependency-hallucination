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

## Dependency extraction and registry check
Declared dependencies: `gem '<name>'` lines, `gem install` and `bundle add` commands; gems with a git/github/path
source are counted separately and not checked. A declared name is looked up once at
`https://rubygems.org/api/v1/gems/<name>.json` (200 = exists, 404 = absent, anything else after retries = unknown;
the date of every lookup is stored). An absent name is classified as:
- malformed: not a valid gem name (e.g. contains "/" or spaces), so it cannot be registered;
- near miss: a case or hyphen/underscore variant of an existing gem;
  clarified on 2026-10-04 after reading the interim list of absent names and before the final analysis: omitting
  the separators counts as such a variant, so `active_support` (a require path) is a near miss of `activesupport`;
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
