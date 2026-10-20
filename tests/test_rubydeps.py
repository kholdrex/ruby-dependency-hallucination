import pytest

from rubydeps import analysis, extract, tasks
from rubydeps.cli import DATA

REPLY = """### Gemfile

```ruby
source 'https://rubygems.org'

gem 'rails', '~> 7.1'
gem "nova_poshta_api"
gem 'liqpay', require: 'liqpay'
gem 'diia-sharing', github: 'example/diia-sharing'
gem 'net/http'
```

Install with `gem install httparty --no-document`.

```ruby
require 'net/http'
require "liqpay"
require_relative 'lib/client'
```
"""


def test_parse_separates_registry_and_external_sources():
    deps = extract.parse(REPLY)
    assert deps.declared == ("rails", "nova_poshta_api", "liqpay", "net/http", "httparty")
    assert deps.external == ("diia-sharing",)
    assert deps.required == ("net/http", "liqpay")


def test_names_with_slashes_are_not_valid_gem_names():
    assert extract.valid("nova_poshta_api")
    assert not extract.valid("net/http")


def test_key_ignores_case_and_separators():
    assert extract.key("Google-Cloud-Text-To_Speech") == extract.key("google-cloud-text_to_speech")
    assert extract.key("active_support") == "activesupport"
    assert set(extract.original_variants("Nova-Poshta")) >= {"nova-poshta", "Nova_Poshta", "nova_poshta"}


def test_parse_handles_shell_commands_blocks_and_comments():
    text = """echo "gem 'whatsapp-business-api'" >> Gemfile
gem install --no-document example_gem
gem install rails && bundle exec ruby app.rb
gem 'local_gem' # path: ../local is only a comment
git 'https://github.com/example/tools.git' do
  gem 'tool_a'
end
gem 'after_block'
gem 'multi_line',
    git: 'https://example.org/repo.git'
git 'https://example.org/other.git' do
  group :test do
    gem 'inner_a'
  end
  gem 'inner_b'
end
"""
    deps = extract.parse(text)
    assert deps.declared == ("whatsapp-business-api", "local_gem", "after_block", "example_gem", "rails")
    assert deps.external == ("tool_a", "multi_line", "inner_a", "inner_b")


def test_classification():
    cache = {
        "rails": {"status": "exists"},
        "nova_poshta_api": {"status": "absent"},
        "Nokogiri": {"status": "absent"},
        "nokogiri": {"status": "exists"},
        "google-cloud-text-to-speech": {"status": "absent"},
        "pending_name": {"status": "unknown"},
    }
    keys = {extract.key(n) for n in ("rails", "nokogiri", "google-cloud-text_to_speech")}
    assert analysis.classify("rails", cache, keys) == "exists"
    assert analysis.classify("nova_poshta_api", cache, keys) == "invented"
    assert analysis.classify("Nokogiri", cache, keys) == "near_miss"
    assert analysis.classify("google-cloud-text-to-speech", cache, keys) == "near_miss"
    assert analysis.classify("google-cloud-text-to-speech", cache, keys, rule="original") == "unknown"
    for v in extract.original_variants("google-cloud-text-to-speech"):
        cache[v] = {"status": "absent"}
    assert analysis.classify("google-cloud-text-to-speech", cache, keys, rule="original") == "invented"
    assert analysis.classify("net/http", cache, keys) == "malformed"
    assert analysis.classify("pending_name", cache, keys) == "unknown"
    assert analysis.classify("never_checked", cache, keys) == "unknown"


def test_mcnemar_is_symmetric_and_bounded():
    assert analysis.mcnemar(0, 0) == 1.0
    assert analysis.mcnemar(3, 9) == analysis.mcnemar(9, 3)
    assert 0 < analysis.mcnemar(0, 8) < 0.01


def test_task_set_is_balanced_and_bilingual():
    all_tasks = tasks.load(DATA / "tasks.jsonl")
    assert len(all_tasks) == 200
    cells = {(t.category, t.context) for t in all_tasks}
    assert len(cells) == 10
    assert all(t.text["en"] and t.text["uk"] for t in all_tasks)
    subset = tasks.repeat_subset(all_tasks, 6, 2026)
    assert len(subset) == 60
    assert subset == tasks.repeat_subset(all_tasks, 6, 2026)


def test_outcome_matrix_rejects_missing_and_duplicate_records():
    task = tasks.Task("t1", "web", "global", {"en": "", "uk": ""})
    rows = [{"model": m, "lang": lang, "task": "t1", "sample": 0, "classes": {}} for m in analysis.MODELS
            for lang in tasks.LANGS]
    assert analysis.outcome_matrix(rows, [task])
    with pytest.raises(ValueError, match="missing"):
        analysis.outcome_matrix(rows[1:], [task])
    with pytest.raises(ValueError, match="duplicate"):
        analysis.outcome_matrix(rows + rows[:1], [task])


def test_spaces_inside_quotes_make_a_name_malformed():
    deps = extract.parse("gem ' Chronic '\nrequire ' json '")
    assert deps.declared == (" Chronic ",)
    assert not extract.valid(deps.declared[0])
    assert deps.required == (" json ",)


def test_exposure_contrasts():
    task_list = [tasks.Task(f"t{k}", "web", "global", {"en": "", "uk": ""}) for k in range(2)]
    en = {"t0": {"a": "exists", "b": "invented"}, "t1": {"a": "exists"}}
    uk = {"t0": {"a": "exists", "x": "invented", "y": "exists", "z": "exists"}, "t1": {"a": "exists"}}
    rows = [{"model": m, "lang": lang, "task": t, "sample": 0, "classes": classes[t]}
            for m in analysis.MODELS for lang, classes in (("en", en), ("uk", uk)) for t in ("t0", "t1")]
    rows += [dict(r, sample=1, classes={}) for r in rows if r["task"] == "t0" and r["lang"] == "uk"]
    rows += [dict(r, sample=1) for r in rows if r["task"] == "t0" and r["lang"] == "en" and r["sample"] == 0]
    res = analysis.exposure(rows, task_list)
    assert res["declared_per_reply_pooled"] == {"en": 1.5, "uk": 2.5}
    assert res["name_level_uk_minus_en"]["pooled"]["value"] == pytest.approx(1 / 5 - 1 / 3)
    assert res["equal_count_pairs_uk_minus_en"]["pairs"] == len(analysis.MODELS)
    assert res["equal_count_pairs_uk_minus_en"]["value"] == 0
    assert res["repeat_subset_all_samples_uk_minus_en"]["tasks"] == 1
    assert res["repeat_subset_all_samples_uk_minus_en"]["value"] == -0.5


def test_install_commands_skip_placeholders_paths_and_call_syntax():
    text = "system('gem install pcsc smartcard')\nRun `gem install ...` and `gem install -r ./`."
    assert extract.parse(text).declared == ("pcsc", "smartcard")


def _near(name):
    return {"model": "m", "task": "t", "lang": "en", "sample": 0, "classes": {name: "near_miss"}}


def test_typo_protection_follows_gem_typo_predicate():
    from datetime import datetime, timezone

    from rubydeps import revision

    assessed = datetime(2026, 10, 19, tzinfo=timezone.utc)
    index = {"activesupport", "rare_old", "rare-new", "Capybara".lower(), "edge"}
    details = {
        "activesupport": {"downloads": 10_000, "latest_release": "2001-01-01T00:00:00Z"},
        "rare_old": {"downloads": 9_999, "latest_release": "2021-10-18T23:59:59Z"},
        "edge": {"downloads": 0, "latest_release": "2021-10-19T00:00:00Z"},
        "rare-new": {"downloads": 5, "latest_release": "2021-10-20T00:00:00Z"},
    }
    labelled = [_near(n) for n in ("active_support", "rareold", "rare_new", "Capybara", "e-dge")]
    names = revision.typo_protection(labelled, index, details, assessed)["names"]
    assert names["active_support"]["status"] == "blocked"
    assert names["rareold"]["status"] == "not_blocked"
    assert names["rare_new"]["status"] == "blocked"
    assert names["Capybara"]["status"] == "case_only_exists"
    assert names["e-dge"]["status"] == "blocked"


def test_agreement_kappa(tmp_path):
    from rubydeps import revision

    path = tmp_path / "a.csv"
    rows = ["id,coder,name_script_switch,en_has_cyrillic,content_differs,note"]
    for i, (a, b) in enumerate([(1, 1), (0, 0), (1, 0), (0, 0)]):
        rows += [f"t{i},A,{a},0,0,", f"t{i},B,{b},0,0,"]
    path.write_text("\n".join(rows) + "\n")
    res = revision.agreement(path)["name_script_switch"]
    assert res["agreement"] == 0.75
    assert res["kappa"] == pytest.approx(0.5)


def test_task_coding_covers_every_task():
    from rubydeps import revision

    coding = revision.load_coding(DATA / "task_coding.csv")
    assert set(coding) == {t.id for t in tasks.load(DATA / "tasks.jsonl")}


def test_script_estimate_and_sign_flip():
    import numpy as np

    from rubydeps import runc_analysis

    res = runc_analysis.estimate(np.array([0.5] * 20), test=True)
    assert res["value"] == 0.5
    assert res["p_sign_flip"] < 0.001
    null = runc_analysis.estimate(np.array([0.5, -0.5] * 10), test=True)
    assert null["p_sign_flip"] > 0.5


def test_script_variants_change_only_the_named_tasks():
    from rubydeps import runc

    variants = runc.script_tasks(tasks.load(DATA / "tasks.jsonl"), DATA / "script_tasks.jsonl")
    coding = __import__("rubydeps.revision", fromlist=["load_coding"]).load_coding(DATA / "task_coding.csv")
    assert set(variants) == {i for i, c in coding.items() if c["name_script_switch"]}
    for arms in variants.values():
        assert arms["latin"].text["uk"] != arms["cyrillic"].text["uk"]
        assert arms["latin"].text["en"] == arms["cyrillic"].text["en"]


def test_run_d_jobs():
    from rubydeps import runc, rund

    all_tasks = tasks.load(DATA / "tasks.jsonl")
    jobs = rund.jobs(all_tasks, runc.script_tasks(all_tasks, DATA / "script_tasks.jsonl"))
    from collections import Counter

    count = Counter((j[0], j[1]) for j in jobs)
    assert count == {("script", rund.SONNET): 72, ("main", rund.SONNET): 400, ("main", rund.DEEPSEEK): 200}
    assert all(j[2].context == "global" for j in jobs if j[1] == rund.DEEPSEEK)
    assert len({(j[0], j[1], j[2].id, j[3], j[4], j[5]) for j in jobs}) == len(jobs)
