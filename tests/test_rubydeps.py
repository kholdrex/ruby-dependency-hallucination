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
