from scraper.robots import RobotsRules

UA = "my-bot/1.0 (+https://example.test/contact)"
BASE = "https://example.test"


def test_longest_match_wins_and_allow_wins_ties():
    rules = RobotsRules.parse("User-agent: *\nDisallow: /shop/\nAllow: /shop/public/\nDisallow: /a\nAllow: /a\n")
    assert rules.can_fetch(UA, BASE + "/shop/item") is False
    assert rules.can_fetch(UA, BASE + "/shop/public/item") is True
    assert rules.can_fetch(UA, BASE + "/a") is True  # 同じ長さなら Allow


def test_specific_agent_group_overrides_star():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: My-Bot\nDisallow: /private\n"
    rules = RobotsRules.parse(text)
    assert rules.can_fetch(UA, BASE + "/page") is True
    assert rules.can_fetch(UA, BASE + "/private/x") is False
    assert rules.can_fetch("other-bot/2.0", BASE + "/page") is False


def test_grouped_user_agents_and_comments():
    text = "# comment\nUser-agent: a-bot\nUser-agent: my-bot  # same group\nDisallow: /x\nCrawl-delay: 3\n"
    rules = RobotsRules.parse(text)
    assert rules.can_fetch(UA, BASE + "/x/1") is False
    assert rules.crawl_delay(UA) == 3.0


def test_wildcards_and_end_anchor():
    rules = RobotsRules.parse("User-agent: *\nDisallow: /*.php$\nDisallow: /search*q=\n")
    assert rules.can_fetch(UA, BASE + "/index.php") is False
    assert rules.can_fetch(UA, BASE + "/index.php5") is True
    assert rules.can_fetch(UA, BASE + "/search?page=2&q=book") is False


def test_empty_disallow_and_robots_txt_itself():
    rules = RobotsRules.parse("User-agent: *\nDisallow:\n")
    assert rules.can_fetch(UA, BASE + "/anything") is True
    assert RobotsRules.disallow_all().can_fetch(UA, BASE + "/robots.txt") is True
    assert RobotsRules.disallow_all().can_fetch(UA, BASE + "/") is False


def test_bom_at_start_is_ignored():
    rules = RobotsRules.parse("\ufeffUser-agent: *\nDisallow: /p\n")
    assert rules.can_fetch(UA, BASE + "/p/q") is False
