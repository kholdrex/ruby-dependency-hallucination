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


def test_variants_cover_case_and_separator():
    assert set(extract.variants("Nova-Poshta")) >= {"nova-poshta", "Nova_Poshta", "nova_poshta", "novaposhta"}
    assert "activesupport" in extract.variants("active_support")


def test_classification():
    cache = {
        "rails": {"status": "exists"},
        "nova_poshta_api": {"status": "absent"},
        "Nokogiri": {"status": "absent"},
        "nokogiri": {"status": "exists"},
    }
    assert analysis.classify("rails", cache) == "exists"
    assert analysis.classify("nova_poshta_api", cache) == "invented"
    assert analysis.classify("Nokogiri", cache) == "near_miss"
    assert analysis.classify("net/http", cache) == "malformed"


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
